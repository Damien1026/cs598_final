from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from observe.events import EventType, ObsEvent


@dataclass
class LineageGraph:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, str]] = field(default_factory=list)

    def to_snapshot(self) -> dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges}


class LineageBuilder:
    """Build a source → tool → sink provenance graph.

    Artifacts are NOT visible nodes; they are tracked internally to draw
    direct tool-to-tool (and source-to-tool) edges so the graph reads
    left-to-right as data flows through the pipeline.
    """

    def __init__(self) -> None:
        self.graph = LineageGraph()
        # artifact_id → node_id of the current "owner" (source or tool that produced it)
        self._artifact_owner: dict[str, str] = {}
        # tool_name → most recent tool node_id (for policy_violation lookup)
        self._last_tool_node: dict[str, str] = {}

    def ingest(self, event: ObsEvent) -> None:
        pl = event.payload
        et = event.event_type

        if et == EventType.source_fetch:
            origin = pl.get("origin", "unknown")
            nid = f"source:{event.step_id}:{origin}"
            self.graph.nodes[nid] = {
                "id": nid,
                "kind": "source",
                "origin": origin,
                "labels": event.labels.get("labels", []),
            }
            artifact_id = pl.get("artifact_id")
            if artifact_id:
                self._artifact_owner[artifact_id] = nid

        elif et == EventType.tool_call:
            tool_name = pl.get("name", "unknown")
            phase = pl.get("phase", "")

            if not phase:
                # Before-dispatch: create tool node and wire up input artifact owners
                tid = f"tool:{event.step_id}:{tool_name}"
                self.graph.nodes[tid] = {
                    "id": tid,
                    "kind": "tool",
                    "name": tool_name,
                }
                self._last_tool_node[tool_name] = tid
                for aid in pl.get("input_artifact_ids", []) or []:
                    owner = self._artifact_owner.get(aid)
                    if owner:
                        self.graph.edges.append({"from": owner, "to": tid, "rel": "input"})
            else:
                # After-dispatch (result): transfer ownership of output artifacts
                tid = self._last_tool_node.get(tool_name)
                if tid:
                    for aid in pl.get("output_artifact_ids", []) or []:
                        prev_owner = self._artifact_owner.get(aid)
                        if prev_owner:
                            # Source/prev-tool produced this artifact; this tool fetched/processed it
                            self.graph.edges.append({"from": prev_owner, "to": tid, "rel": "reads"})
                        # Transfer ownership so downstream tools connect to this tool
                        self._artifact_owner[aid] = tid

        elif et == EventType.sink_write:
            sid = f"sink:{event.step_id}:{pl.get('sink', '')}"
            self.graph.nodes[sid] = {
                "id": sid,
                "kind": "sink",
                "sink": pl.get("sink", ""),
            }
            for aid in pl.get("artifact_ids", []) or []:
                owner = self._artifact_owner.get(aid)
                if owner:
                    self.graph.edges.append({"from": owner, "to": sid, "rel": "flows_to"})

        elif et == EventType.policy_violation:
            sid = f"sink_blocked:{event.step_id}:{pl.get('sink', '')}"
            self.graph.nodes[sid] = {
                "id": sid,
                "kind": "sink_blocked",
                "sink": pl.get("sink", ""),
                "rule": pl.get("rule", ""),
                "labels": event.labels.get("labels", []),
            }
            # Connect from the tool that triggered the violation
            tool_name = pl.get("tool", "")
            parent = self._last_tool_node.get(tool_name)
            if parent and parent in self.graph.nodes:
                self.graph.edges.append({"from": parent, "to": sid, "rel": "blocked"})
            else:
                for aid in pl.get("artifact_ids", []) or []:
                    owner = self._artifact_owner.get(aid)
                    if owner:
                        self.graph.edges.append({"from": owner, "to": sid, "rel": "blocked"})

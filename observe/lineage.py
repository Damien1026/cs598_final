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
    def __init__(self) -> None:
        self.graph = LineageGraph()

    def ingest(self, event: ObsEvent) -> None:
        pl = event.payload
        et = event.event_type

        if et == EventType.source_fetch:
            nid = pl.get("artifact_id", event.id)
            self.graph.nodes[nid] = {
                "id": nid,
                "kind": "source",
                "origin": pl.get("origin", ""),
                "labels": pl.get("labels", []),
            }
        elif et == EventType.tool_call:
            tid = f"tool:{event.step_id}:{pl.get('name', 'unknown')}"
            self.graph.nodes[tid] = {
                "id": tid,
                "kind": "tool",
                "name": pl.get("name", ""),
            }
            for aid in pl.get("input_artifact_ids", []) or []:
                if aid:
                    self.graph.edges.append({"from": aid, "to": tid, "rel": "input"})
            for aid in pl.get("output_artifact_ids", []) or []:
                if aid:
                    self.graph.edges.append({"from": tid, "to": aid, "rel": "output"})
        elif et == EventType.sink_write:
            sid = f"sink:{event.step_id}:{pl.get('sink', '')}"
            self.graph.nodes[sid] = {
                "id": sid,
                "kind": "sink",
                "sink": pl.get("sink", ""),
            }
            for aid in pl.get("artifact_ids", []) or []:
                if aid:
                    self.graph.edges.append({"from": aid, "to": sid, "rel": "flows_to"})

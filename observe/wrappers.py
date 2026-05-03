from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from observe.events import EventType, ObsEvent
from observe.hub import ObsHub
from observe.policy import PolicyOutcome, PolicyResult, action_fingerprint, evaluate_sink
from observe.risk import compute_risk
from observe.taint import Sensitivity, infer_labels_from_text

if TYPE_CHECKING:
    from agent.sources.email import EmailSource
    from agent.sources.rag import RAGSource


class MonitoredIO:
    """All source/sink I/O goes through here for taint + policy + events."""

    def __init__(
        self,
        hub: ObsHub,
        workspace_root: Path,
        *,
        agent_id: str = "",
        email_source: "EmailSource | None" = None,
        rag_source: "RAGSource | None" = None,
    ) -> None:
        self.hub = hub
        self.workspace_root = workspace_root.resolve()
        self.agent_id = agent_id
        self._email_source = email_source
        self._rag_source = rag_source

    def _p(self, **kwargs: Any) -> dict[str, Any]:
        """Inject agent_id into every event payload."""
        if self.agent_id:
            kwargs["agent_id"] = self.agent_id
        return kwargs

    def _abs_path(self, rel: str) -> Path:
        p = (self.workspace_root / rel).resolve()
        if not str(p).startswith(str(self.workspace_root)):
            raise ValueError("path escapes workspace")
        return p

    async def source_gmail_mock(self) -> tuple[str, str]:
        step = self.hub.next_step()
        text = (
            "Inbox: (1) From: alice@example.com Subject: Your order #9922\n"
            "Body: Hi, your shipment arrives Tuesday. SSN last four: 1234\n"
        )
        art = self.hub.taint.new_artifact("gmail_mock", ["pii"], preview=text)
        await self.hub.emit(
            ObsEvent(
                step_id=step,
                event_type=EventType.source_fetch,
                payload=self._p(origin="gmail_mock", artifact_id=art.id, byte_len=len(text)),
                labels={"labels": sorted(art.labels)},
            )
        )
        return text, art.id

    async def source_email(self) -> tuple[str, str]:
        """Fetch real email via IMAP. Falls back to mock if source not configured."""
        step = self.hub.next_step()
        if self._email_source is not None:
            import asyncio
            text = await asyncio.get_running_loop().run_in_executor(None, self._email_source.fetch)
        else:
            text = (
                "Inbox: (1) From: alice@example.com Subject: Your order #9922\n"
                "Body: Hi, your shipment arrives Tuesday. SSN last four: 1234\n"
            )
        labels = infer_labels_from_text(text) or {"public"}
        art = self.hub.taint.new_artifact("email", labels, preview=text)
        await self.hub.emit(
            ObsEvent(
                step_id=step,
                event_type=EventType.source_fetch,
                payload=self._p(origin="email", artifact_id=art.id, byte_len=len(text)),
                labels={"labels": sorted(art.labels)},
            )
        )
        return text, art.id

    async def source_rag_search(self, query: str) -> tuple[str, str]:
        step = self.hub.next_step()
        if self._rag_source is not None:
            import asyncio
            text = await asyncio.get_running_loop().run_in_executor(
                None, self._rag_source.search, query
            )
        else:
            text = (
                f"[RAG chunk for '{query}'] Internal roadmap Q3: deprecate legacy API; "
                "API_KEY_ROTATION=sk-internal-demo-not-real"
            )
        labels = infer_labels_from_text(text) or {"public"}
        art = self.hub.taint.new_artifact("rag_search", labels, preview=text)
        await self.hub.emit(
            ObsEvent(
                step_id=step,
                event_type=EventType.source_fetch,
                payload=self._p(origin="rag_search", query=query, artifact_id=art.id),
                labels={"labels": sorted(art.labels)},
            )
        )
        return text, art.id

    async def source_file_read(self, rel_path: str) -> tuple[str, str]:
        step = self.hub.next_step()
        path = self._abs_path(rel_path)
        if not path.is_file():
            text = f"(missing file {rel_path})"
            art = self.hub.taint.new_artifact("file_read", ["public"], preview=text)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            art = self.hub.taint.new_artifact("file_read", ["public"], preview=text)
        await self.hub.emit(
            ObsEvent(
                step_id=step,
                event_type=EventType.source_fetch,
                payload=self._p(origin="file_read", path=rel_path, artifact_id=art.id),
                labels={"labels": sorted(art.labels)},
            )
        )
        return text, art.id

    async def source_http_get(self, url: str, artifact_ids: list[str] | None = None) -> tuple[str, str]:
        step = self.hub.next_step()
        is_external = not (url.startswith("http://127.0.0.1") or url.startswith("mock://"))

        # Pre-flight policy: if tainted artifacts flow into an external GET, apply R2
        if artifact_ids and is_external:
            labels_in = self.hub.taint.labels_for_tool_args(url, artifact_ids)
            ok = await self._apply_policy_hitl(
                sink="http_get_external",
                labels=labels_in,
                sink_meta={"url": url},
                tool="http_get",
                args={"url": url},
                artifact_ids=artifact_ids,
            )
            if not ok:
                blocked_art = self.hub.taint.new_artifact("http_get", set(), preview="blocked")
                return "blocked by policy", blocked_art.id

        if not is_external:
            text = '{"status":"ok","msg":"mock response"}'
            labels: list[str] = ["public"]
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                text = r.text[:8000]
            labels = list(infer_labels_from_text(text) or {"public"})
        art = self.hub.taint.new_artifact("http_get", labels, preview=text)
        await self.hub.emit(
            ObsEvent(
                step_id=step,
                event_type=EventType.source_fetch,
                payload=self._p(origin="http_get", url=url, artifact_id=art.id),
                labels={"labels": sorted(art.labels)},
            )
        )
        return text, art.id

    async def _apply_policy_hitl(
        self,
        *,
        sink: str,
        labels: set[str],
        sink_meta: dict[str, Any],
        tool: str,
        args: dict[str, Any],
        artifact_ids: list[str],
    ) -> bool:
        pr = evaluate_sink(sink, labels, sink_meta=sink_meta)
        fp = action_fingerprint(tool, args, sink)
        trust = self.hub.trust.trust_for(fp)
        max_s = Sensitivity.public
        for lab in labels:
            if lab in Sensitivity.__members__:
                max_s = max(max_s, Sensitivity[lab])
        risk = compute_risk(max_s, sink, self.hub.step_id, trust)
        await self.hub.emit(
            ObsEvent(
                step_id=self.hub.step_id,
                event_type=EventType.risk_update,
                payload={"risk": risk, "sink": sink, "fingerprint": fp},
                labels={"labels": sorted(labels)},
            )
        )
        self.hub.risk_history.append({"risk": risk, "sink": sink, "fp": fp})

        threshold = self.hub.trust.hitl_threshold(fp)
        if risk >= threshold and pr.outcome == PolicyOutcome.allow:
            pr = PolicyResult(PolicyOutcome.hitl, "RISK", f"risk {risk:.2f} >= {threshold:.2f}")

        if pr.outcome == PolicyOutcome.deny:
            await self.hub.emit(
                ObsEvent(
                    step_id=self.hub.step_id,
                    event_type=EventType.policy_violation,
                    payload=self._p(rule=pr.rule_id, reason=pr.reason, sink=sink, tool=tool),
                    labels={"labels": sorted(labels)},
                )
            )
            return False

        if pr.outcome == PolicyOutcome.hitl:
            import uuid as _uuid

            hid = str(_uuid.uuid4())
            await self.hub.emit(
                ObsEvent(
                    step_id=self.hub.step_id,
                    event_type=EventType.hitl_request,
                    payload=self._p(
                        id=hid,
                        rule=pr.rule_id,
                        reason=pr.reason,
                        sink=sink,
                        tool=tool,
                        args=args,
                        labels=sorted(labels),
                        fingerprint=fp,
                    ),
                    labels={},
                )
            )
            fut = await self.hub.register_hitl(hid)
            decision = await fut
            await self.hub.emit(
                ObsEvent(
                    step_id=self.hub.step_id,
                    event_type=EventType.hitl_resolved,
                    payload={"id": hid, "decision": decision},
                    labels={},
                )
            )
            adj = {"allow": "allow", "deny": "deny", "allow_once": "allow_once"}.get(decision, "deny")
            self.hub.trust.adjust(fp, adj)
            self.hub.trust.save()
            if decision == "deny":
                return False
        return True

    async def sink_file_write(self, rel_path: str, content: str, artifact_ids: list[str], tool: str) -> bool:
        step = self.hub.next_step()
        labels = self.hub.taint.labels_for_tool_args(content, artifact_ids)
        args = {"path": rel_path, "content_len": len(content)}
        ok = await self._apply_policy_hitl(
            sink="file_write",
            labels=labels,
            sink_meta={"path": rel_path},
            tool=tool,
            args=args,
            artifact_ids=artifact_ids,
        )
        if not ok:
            return False
        path = self._abs_path(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        out_art = self.hub.taint.new_artifact("file_write", set(labels), preview=content)
        await self.hub.emit(
            ObsEvent(
                step_id=step,
                event_type=EventType.sink_write,
                payload=self._p(
                    sink="file_write",
                    path=rel_path,
                    artifact_ids=artifact_ids + [out_art.id],
                ),
                labels={"labels": sorted(labels)},
            )
        )
        return True

    async def sink_http_post(self, url: str, body: str, artifact_ids: list[str], tool: str) -> bool:
        step = self.hub.next_step()
        labels = self.hub.taint.labels_for_tool_args(body, artifact_ids)
        external = not (url.startswith("http://127.0.0.1") or url.startswith("mock://"))
        sink = "http_post_external" if external else "http_post_internal"
        args = {"url": url, "body_len": len(body)}
        ok = await self._apply_policy_hitl(
            sink=sink,
            labels=labels,
            sink_meta={"url": url},
            tool=tool,
            args=args,
            artifact_ids=artifact_ids,
        )
        if not ok:
            return False
        if external:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(url, content=body)
        await self.hub.emit(
            ObsEvent(
                step_id=step,
                event_type=EventType.sink_write,
                payload=self._p(sink=sink, url=url, artifact_ids=artifact_ids),
                labels={"labels": sorted(labels)},
            )
        )
        return True


def tools_schema(*, use_real_email: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file under the workspace",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write text to a path under the workspace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "artifact_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Artifact IDs flowing into content",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_email" if use_real_email else "fetch_gmail_mock",
                "description": "Fetch inbox emails" if use_real_email else "Fetch mock private inbox contents",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rag_search",
                "description": "Search internal mock knowledge base",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "http_get",
                "description": "HTTP GET URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "artifact_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Artifact IDs flowing into the request (e.g. as URL params)",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "http_post",
                "description": "HTTP POST body to URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "body": {"type": "string"},
                        "artifact_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["url", "body"],
                },
            },
        },
    ]

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from observe.events import EventType, ObsEvent
from observe.hub import ObsHub
from observe.wrappers import MonitoredIO, tools_schema


class LLMClient(Protocol):
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> dict[str, Any]: ...


class MonitoredAgent:
    def __init__(self, hub: ObsHub, io: MonitoredIO, llm: LLMClient) -> None:
        self.hub = hub
        self.io = io
        self.llm = llm

    async def run(self, task: str, *, max_turns: int = 12) -> str:
        await self.hub.emit(
            ObsEvent(
                step_id=0,
                event_type=EventType.session_start,
                payload={"task": task},
                labels={},
            )
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        tools = tools_schema()
        final = ""

        for _ in range(max_turns):
            step = self.hub.next_step()
            await self.hub.emit(
                ObsEvent(
                    step_id=step,
                    event_type=EventType.llm_call,
                    payload={"message_count": len(messages)},
                    labels={},
                )
            )
            resp = await self.llm.chat(messages, tools)
            final = resp.get("content") or final
            tcalls = resp.get("tool_calls") or []
            if not tcalls:
                break

            assistant_msg = {
                "role": "assistant",
                "content": resp.get("content") or "",
                "tool_calls": [
                    {
                        "id": tc.get("id") or f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("arguments") or {}),
                        },
                    }
                    for i, tc in enumerate(tcalls)
                ],
            }
            messages.append(assistant_msg)

            for tc in tcalls:
                name = tc["name"]
                args = tc.get("arguments") or {}
                in_ids = list(args.get("artifact_ids") or [])
                await self.hub.emit(
                    ObsEvent(
                        step_id=step,
                        event_type=EventType.tool_call,
                        payload={
                            "name": name,
                            "args": {k: v for k, v in args.items() if k != "artifact_ids"},
                            "input_artifact_ids": in_ids,
                        },
                        labels={},
                    )
                )
                text, out_ids = await self._dispatch_tool(name, args)
                tool_content = text
                if out_ids:
                    tool_content = f"{text}\n[[artifacts:{','.join(out_ids)}]]"
                await self.hub.emit(
                    ObsEvent(
                        step_id=step,
                        event_type=EventType.tool_call,
                        payload={
                            "name": name,
                            "phase": "result",
                            "output_preview": text[:200],
                            "output_artifact_ids": out_ids,
                        },
                        labels={},
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "content": tool_content,
                        "tool_call_id": tc.get("id") or "call",
                    }
                )

        await self.hub.emit(
            ObsEvent(
                step_id=self.hub.step_id,
                event_type=EventType.session_end,
                payload={"summary": final[:500]},
                labels={},
            )
        )
        return final

    async def _dispatch_tool(self, name: str, args: dict[str, Any]) -> tuple[str, list[str]]:
        out_ids: list[str] = []
        if name == "read_file":
            text, aid = await self.io.source_file_read(str(args.get("path", "")))
            out_ids = [aid]
            return text, out_ids
        if name == "write_file":
            path = str(args.get("path", ""))
            content = str(args.get("content", ""))
            aids = list(args.get("artifact_ids") or [])
            ok = await self.io.sink_file_write(path, content, aids, "write_file")
            return ("ok" if ok else "blocked by policy"), out_ids
        if name == "fetch_gmail_mock":
            text, aid = await self.io.source_gmail_mock()
            return text, [aid]
        if name == "rag_search":
            text, aid = await self.io.source_rag_search(str(args.get("query", "")))
            return text, [aid]
        if name == "http_get":
            aids = list(args.get("artifact_ids") or [])
            text, aid = await self.io.source_http_get(str(args.get("url", "")), artifact_ids=aids or None)
            return text, [aid]
        if name == "http_post":
            url = str(args.get("url", ""))
            body = str(args.get("body", ""))
            aids = list(args.get("artifact_ids") or [])
            ok = await self.io.sink_http_post(url, body, aids, "http_post")
            return ("ok" if ok else "blocked by policy"), out_ids
        return f"unknown tool {name}", out_ids


def build_agent(workspace: Path, hub: ObsHub, mock_llm: bool) -> MonitoredAgent:
    from agent.llm import MockLLM, OllamaLLM

    io = MonitoredIO(hub, workspace)
    llm: LLMClient = MockLLM() if mock_llm else OllamaLLM()
    return MonitoredAgent(hub, io, llm)

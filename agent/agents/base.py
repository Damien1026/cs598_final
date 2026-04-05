from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable

from observe.events import EventType, ObsEvent
from observe.hub import ObsHub
from observe.wrappers import MonitoredIO


class BaseAgent:
    """Single-turn tool-calling agent using Gemini native message format.

    Subclasses define:
      - SYSTEM_PROMPT  — injected as Gemini system_instruction
      - tools_schema() — list of OpenAI-style tool dicts
      - _dispatch(name, args) → str — execute a single tool call
    """

    SYSTEM_PROMPT: str = "You are a helpful assistant."
    MAX_TURNS: int = 8

    def __init__(self, name: str, llm: Any, io: MonitoredIO, hub: ObsHub) -> None:
        self.name = name
        self.llm = llm
        self.io = io
        self.hub = hub

    def tools_schema(self) -> list[dict[str, Any]]:
        return []

    async def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        return f"(unknown tool: {name})"

    # ------------------------------------------------------------------ helpers

    async def _emit_context(self, tokens: int) -> None:
        pct = round(tokens / self.llm.context_window * 100, 1) if self.llm.context_window else 0
        etype = EventType.context_warning if pct >= 80 else EventType.context_usage
        await self.hub.emit(
            ObsEvent(
                step_id=self.hub.step_id,
                event_type=etype,
                payload={
                    "agent_id": self.name,
                    "tokens": tokens,
                    "context_window": self.llm.context_window,
                    "window_pct": pct,
                },
                labels={},
            )
        )

    # ------------------------------------------------------------------ main loop

    async def run(self, task: str) -> str:
        """Run the agent on a task and return the final text response."""
        await self.hub.emit(
            ObsEvent(
                step_id=self.hub.next_step(),
                event_type=EventType.session_start,
                payload={"agent_id": self.name, "task": task},
                labels={},
            )
        )

        messages: list[dict[str, Any]] = [{"role": "user", "parts": [task]}]
        tools = self.tools_schema()
        final = ""

        for _ in range(self.MAX_TURNS):
            self.hub.next_step()
            resp = await self.llm.chat(messages, tools, system_prompt=self.SYSTEM_PROMPT)
            content: str = resp.get("content") or ""
            tool_calls: list[dict[str, Any]] = resp.get("tool_calls") or []
            tokens: int = resp.get("tokens") or 0

            await self._emit_context(tokens)

            if not tool_calls:
                final = content
                break

            # Build model turn (function calls)
            model_parts: list[Any] = []
            if content:
                model_parts.append(content)
            for tc in tool_calls:
                model_parts.append(
                    {"function_call": {"name": tc["name"], "args": tc["arguments"]}}
                )
            messages.append({"role": "model", "parts": model_parts})

            # Execute tools and collect responses
            response_parts: list[Any] = []
            for tc in tool_calls:
                result = await self._dispatch(tc["name"], tc.get("arguments") or {})
                response_parts.append(
                    {"function_response": {"name": tc["name"], "response": {"result": result}}}
                )
            messages.append({"role": "user", "parts": response_parts})

        await self.hub.emit(
            ObsEvent(
                step_id=self.hub.step_id,
                event_type=EventType.session_end,
                payload={"agent_id": self.name, "summary": final[:300]},
                labels={},
            )
        )
        return final

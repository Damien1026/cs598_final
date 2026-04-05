from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, AsyncIterator

from observe.events import EventType, ObsEvent
from observe.hub import ObsHub
from observe.wrappers import MonitoredIO

from agent.agents.researcher import ResearchAgent
from agent.agents.analyst import AnalystAgent
from agent.agents.output import OutputAgent


_META_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "delegate_to_researcher",
            "description": (
                "Ask the Research Agent to gather information. "
                "Use this when you need to fetch emails, search the knowledge base, or retrieve web content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subtask": {
                        "type": "string",
                        "description": "Clear instruction for what information to retrieve",
                    }
                },
                "required": ["subtask"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_analyst",
            "description": (
                "Ask the Analyst Agent to process and structure information. "
                "Pass the raw data as context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subtask": {"type": "string", "description": "What analysis to perform"},
                    "context": {"type": "string", "description": "Raw data or notes to analyse"},
                },
                "required": ["subtask", "context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_output",
            "description": (
                "Ask the Output Agent to write a final report or send a result externally."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subtask": {"type": "string", "description": "What to produce"},
                    "content": {"type": "string", "description": "Analysed content to include"},
                },
                "required": ["subtask", "content"],
            },
        },
    },
]

_SYSTEM_PROMPT = """\
You are an orchestrator managing a team of three specialist agents:
- Research Agent: fetches emails, searches the internal knowledge base, retrieves web pages
- Analyst Agent: reads and writes notes, structures raw data into summaries
- Output Agent: writes polished reports and optionally posts content externally

For each user request, decide which agents to call and in what order. You can call multiple
agents sequentially. Once you have all results, compose a clear final answer for the user.
If a task does not require any tool calls, answer directly."""


class Orchestrator:
    """Multi-turn streaming orchestrator backed by Gemini.

    Maintains the full conversation history across REPL turns.
    Streams the final text response token-by-token.
    """

    MAX_TOOL_TURNS = 6

    def __init__(
        self,
        llm: Any,
        workspace: Path,
        hub: ObsHub,
        *,
        email_source: Any = None,
        rag_source: Any = None,
    ) -> None:
        self.llm = llm
        self.hub = hub
        self._history: list[dict[str, Any]] = []

        def _make_io(agent_id: str) -> MonitoredIO:
            return MonitoredIO(
                hub,
                workspace,
                agent_id=agent_id,
                email_source=email_source,
                rag_source=rag_source,
            )

        self._researcher = ResearchAgent(llm, _make_io("researcher"), hub)
        self._analyst = AnalystAgent(llm, _make_io("analyst"), hub)
        self._output = OutputAgent(llm, _make_io("output"), hub)

    # ------------------------------------------------------------------ REPL

    async def stream_turn(self, user_message: str) -> AsyncIterator[str]:
        """Process one user turn; stream the final text response."""
        self._history.append({"role": "user", "parts": [user_message]})

        await self.hub.emit(
            ObsEvent(
                step_id=self.hub.next_step(),
                event_type=EventType.llm_call,
                payload={"agent_id": "orchestrator", "message_count": len(self._history)},
                labels={},
            )
        )

        # Tool-call loop (non-streaming while delegating)
        for _ in range(self.MAX_TOOL_TURNS):
            resp = await self.llm.chat(self._history, _META_TOOLS, system_prompt=_SYSTEM_PROMPT)
            tool_calls: list[dict[str, Any]] = resp.get("tool_calls") or []

            if not tool_calls:
                break

            # Record model turn
            model_parts: list[Any] = []
            if resp.get("content"):
                model_parts.append(resp["content"])
            for tc in tool_calls:
                model_parts.append(
                    {"function_call": {"name": tc["name"], "args": tc["arguments"]}}
                )
            self._history.append({"role": "model", "parts": model_parts})

            # Execute delegations
            response_parts: list[Any] = []
            for tc in tool_calls:
                name = tc["name"]
                args = tc.get("arguments") or {}
                print(f"\n  [{name}] ...", end="", flush=True)
                result = await self._execute_delegation(name, args)
                print(" done", flush=True)
                response_parts.append(
                    {"function_response": {"name": name, "response": {"result": result}}}
                )
            self._history.append({"role": "user", "parts": response_parts})

        # Stream the final answer
        full_response = ""
        async for chunk in self.llm.stream_chat(self._history, None, system_prompt=_SYSTEM_PROMPT):
            full_response += chunk
            yield chunk

        if full_response:
            self._history.append({"role": "model", "parts": [full_response]})

        # Emit context usage for orchestrator
        tokens = self.llm.last_token_count
        pct = round(tokens / self.llm.context_window * 100, 1) if self.llm.context_window else 0
        etype = EventType.context_warning if pct >= 80 else EventType.context_usage
        await self.hub.emit(
            ObsEvent(
                step_id=self.hub.step_id,
                event_type=etype,
                payload={
                    "agent_id": "orchestrator",
                    "tokens": tokens,
                    "context_window": self.llm.context_window,
                    "window_pct": pct,
                    "history_turns": len(self._history),
                },
                labels={},
            )
        )

    async def _execute_delegation(self, name: str, args: dict[str, Any]) -> str:
        subtask = str(args.get("subtask", ""))
        if name == "delegate_to_researcher":
            return await self._researcher.run(subtask)
        if name == "delegate_to_analyst":
            context = str(args.get("context", ""))
            return await self._analyst.run(f"{subtask}\n\nContext:\n{context}")
        if name == "delegate_to_output":
            content = str(args.get("content", ""))
            return await self._output.run(f"{subtask}\n\nContent:\n{content}")
        return f"(unknown delegation: {name})"

    def reset(self) -> None:
        """Clear conversation history (start fresh session)."""
        self._history.clear()

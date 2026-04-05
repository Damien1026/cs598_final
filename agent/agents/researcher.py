from __future__ import annotations

from typing import Any

from agent.agents.base import BaseAgent
from observe.hub import ObsHub
from observe.wrappers import MonitoredIO, tools_schema as _base_tools


class ResearchAgent(BaseAgent):
    """Fetches data from email, RAG, and web. Never writes files."""

    SYSTEM_PROMPT = (
        "You are a research assistant. Use the available tools to gather information "
        "requested by the orchestrator. Return a concise, structured summary of what "
        "you found. Do not make up information — only report what the tools return."
    )

    def __init__(self, llm: Any, io: MonitoredIO, hub: ObsHub) -> None:
        super().__init__("researcher", llm, io, hub)
        self._artifact_ids: list[str] = []

    def tools_schema(self) -> list[dict[str, Any]]:
        base = _base_tools(use_real_email=self.io._email_source is not None)
        # Only expose source tools
        allowed = {"fetch_email", "fetch_gmail_mock", "rag_search", "http_get"}
        return [t for t in base if t["function"]["name"] in allowed]

    async def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        if name in ("fetch_email", "fetch_gmail_mock"):
            text, aid = await self.io.source_email()
            self._artifact_ids.append(aid)
            return text
        if name == "rag_search":
            text, aid = await self.io.source_rag_search(str(args.get("query", "")))
            self._artifact_ids.append(aid)
            return text
        if name == "http_get":
            text, aid = await self.io.source_http_get(str(args.get("url", "")))
            self._artifact_ids.append(aid)
            return text
        return f"(unknown tool: {name})"

from __future__ import annotations

from typing import Any

from agent.agents.base import BaseAgent
from observe.hub import ObsHub
from observe.wrappers import MonitoredIO


class OutputAgent(BaseAgent):
    """Generates final reports and optionally posts them externally."""

    SYSTEM_PROMPT = (
        "You are a report writer. You receive analysed information and produce "
        "a polished, well-structured report in Markdown. Save the report to "
        "workspace/reports/ using the write_report tool. Only post externally "
        "if explicitly asked."
    )

    def __init__(self, llm: Any, io: MonitoredIO, hub: ObsHub) -> None:
        super().__init__("output", llm, io, hub)
        self._artifact_ids: list[str] = []

    def tools_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "write_report",
                    "description": "Save the final report to workspace/reports/",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["filename", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "http_post",
                    "description": "POST content to an external URL (requires explicit permission)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["url", "body"],
                    },
                },
            },
        ]

    async def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        if name == "write_report":
            filename = str(args.get("filename", "report.md"))
            content = str(args.get("content", ""))
            path = f"workspace/reports/{filename}"
            ok = await self.io.sink_file_write(path, content, self._artifact_ids, "write_report")
            return f"report saved to {path}" if ok else "blocked by policy"
        if name == "http_post":
            url = str(args.get("url", ""))
            body = str(args.get("body", ""))
            ok = await self.io.sink_http_post(url, body, self._artifact_ids, "http_post")
            return "posted" if ok else "blocked by policy"
        return f"(unknown tool: {name})"

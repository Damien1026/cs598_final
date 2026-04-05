from __future__ import annotations

from typing import Any

from agent.agents.base import BaseAgent
from observe.hub import ObsHub
from observe.wrappers import MonitoredIO


class AnalystAgent(BaseAgent):
    """Reads workspace files and writes structured notes."""

    SYSTEM_PROMPT = (
        "You are a data analyst assistant. You receive raw information and produce "
        "structured summaries, bullet-point analyses, or tables. You may read existing "
        "notes and write new notes to the workspace. Be concise and factual."
    )

    def __init__(self, llm: Any, io: MonitoredIO, hub: ObsHub) -> None:
        super().__init__("analyst", llm, io, hub)
        self._artifact_ids: list[str] = []

    def tools_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from the workspace",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "Relative path under workspace"}},
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_note",
                    "description": "Save a note or analysis result to workspace/notes/",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Filename under workspace/notes/"},
                            "content": {"type": "string", "description": "Text content to save"},
                        },
                        "required": ["filename", "content"],
                    },
                },
            },
        ]

    async def _dispatch(self, name: str, args: dict[str, Any]) -> str:
        if name == "read_file":
            text, aid = await self.io.source_file_read(str(args.get("path", "")))
            self._artifact_ids.append(aid)
            return text
        if name == "write_note":
            filename = str(args.get("filename", "note.txt"))
            content = str(args.get("content", ""))
            path = f"workspace/notes/{filename}"
            ok = await self.io.sink_file_write(path, content, self._artifact_ids, "write_note")
            return "saved" if ok else "blocked by policy"
        return f"(unknown tool: {name})"

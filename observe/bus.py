from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from observe.events import ObsEvent
from observe.redaction import redact_obj


Subscriber = Callable[[ObsEvent], Awaitable[None]]


class EventBus:
    def __init__(self, jsonl_path: Path | None = None) -> None:
        self._subs: list[Subscriber] = []
        self._lock = asyncio.Lock()
        self.jsonl_path = jsonl_path

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    async def publish(self, event: ObsEvent) -> None:
        async with self._lock:
            if self.jsonl_path:
                self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
                line = event.model_dump_json()
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            for fn in list(self._subs):
                await fn(event)

    def snapshot_redacted(self, event: ObsEvent, reveal: bool) -> dict[str, Any]:
        d = event.model_dump(mode="json")
        if not reveal:
            d["payload"] = redact_obj(d.get("payload", {}))
        return d

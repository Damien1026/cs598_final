from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from observe.bus import EventBus
from observe.events import EventType, ObsEvent
from observe.lineage import LineageBuilder
from observe.taint import TaintStore
from observe.trust import TrustStore


class ObsHub:
    def __init__(
        self,
        *,
        jsonl_path: Path | None = None,
        trust_path: Path | None = None,
    ) -> None:
        self.trace_id: str = str(uuid.uuid4())
        self.step_id: int = 0
        self.bus = EventBus(jsonl_path=jsonl_path)
        self.taint = TaintStore()
        self.lineage = LineageBuilder()
        self.trust = TrustStore(path=trust_path)
        self.trust.load()
        self.events: list[ObsEvent] = []
        self.risk_history: list[dict[str, Any]] = []
        self._hitl_pending: dict[str, asyncio.Future[str]] = {}

    async def _after_event(self, event: ObsEvent) -> None:
        self.events.append(event)
        self.lineage.ingest(event)

    def subscribe(self, fn: Any) -> None:
        self.bus.subscribe(fn)

    async def emit(self, event: ObsEvent) -> None:
        if not event.trace_id:
            event.trace_id = self.trace_id
        await self._after_event(event)
        await self.bus.publish(event)

    def next_step(self) -> int:
        self.step_id += 1
        return self.step_id

    async def register_hitl(self, hid: str) -> asyncio.Future[str]:
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._hitl_pending[hid] = fut
        auto = os.environ.get("OBS_HITL_AUTO", "").strip().lower()
        if auto in ("allow", "deny", "allow_once"):

            async def _auto_resolve() -> None:
                await asyncio.sleep(0)
                self.resolve_hitl(hid, auto)

            asyncio.create_task(_auto_resolve())
        return fut

    def resolve_hitl(self, hid: str, decision: str) -> bool:
        fut = self._hitl_pending.pop(hid, None)
        if fut and not fut.done():
            fut.set_result(decision)
            return True
        return False

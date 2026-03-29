from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from observe.events import ObsEvent
from observe.hub import ObsHub
from observe.lineage import LineageBuilder
from observe.redaction import redact_obj
from agent.runner import build_agent

_workspace: Path | None = None
_hub: ObsHub | None = None
_ws_clients: list[WebSocket] = []
_agent_task: asyncio.Task[None] | None = None
_lock = asyncio.Lock()


def get_workspace() -> Path:
    global _workspace
    if _workspace is None:
        _workspace = Path(os.environ.get("OBS_WORKSPACE", "sandbox")).resolve()
        _workspace.mkdir(parents=True, exist_ok=True)
        (_workspace / "workspace" / "notes").mkdir(parents=True, exist_ok=True)
    return _workspace


def get_hub() -> ObsHub:
    global _hub
    if _hub is None:
        w = get_workspace()
        _hub = ObsHub(
            jsonl_path=w / "logs" / "events.jsonl",
            trust_path=w / "logs" / "trust.json",
        )

        async def push_event(event: ObsEvent) -> None:
            d = event.model_dump(mode="json")
            d["payload"] = redact_obj(d.get("payload", {}))
            dead: list[WebSocket] = []
            for ws in _ws_clients:
                try:
                    await ws.send_json({"type": "event", "data": d})
                except Exception:
                    dead.append(ws)
            for x in dead:
                if x in _ws_clients:
                    _ws_clients.remove(x)

        _hub.bus.subscribe(push_event)
    return _hub


app = FastAPI(title="Observability Agent Dashboard")


@app.on_event("startup")
async def startup() -> None:
    get_workspace()
    get_hub()


class StartBody(BaseModel):
    task: str = "Fetch mock inbox and save a summary to workspace."
    mock_llm: bool = True


class HitlBody(BaseModel):
    decision: str  # allow | deny | allow_once


@app.post("/api/agent/start")
async def start_agent(body: StartBody) -> dict[str, Any]:
    global _agent_task

    async def run() -> None:
        hub = get_hub()
        import uuid as _uuid

        hub.trace_id = _uuid.uuid4().hex
        hub.step_id = 0
        hub.events.clear()
        hub.lineage = LineageBuilder()
        hub.risk_history.clear()
        ag = build_agent(get_workspace(), hub, mock_llm=body.mock_llm)
        await ag.run(body.task)

    async with _lock:
        if _agent_task and not _agent_task.done():
            return {"status": "busy", "message": "Agent already running"}
        _agent_task = asyncio.create_task(run())
    return {"status": "started"}


@app.post("/api/hitl/{hid}")
async def hitl_respond(hid: str, body: HitlBody) -> dict[str, Any]:
    hub = get_hub()
    ok = hub.resolve_hitl(hid, body.decision)
    return {"ok": ok}


@app.get("/api/events")
async def list_events(reveal: bool = False) -> dict[str, Any]:
    hub = get_hub()
    out = []
    for e in hub.events:
        d = e.model_dump(mode="json")
        if not reveal:
            d["payload"] = redact_obj(d.get("payload", {}))
        out.append(d)
    return {"trace_id": hub.trace_id, "events": out}


@app.get("/api/lineage")
async def lineage() -> dict[str, Any]:
    return get_hub().lineage.graph.to_snapshot()


@app.get("/api/risk")
async def risk() -> dict[str, Any]:
    return {"history": get_hub().risk_history}


@app.get("/api/session")
async def session() -> dict[str, Any]:
    hub = get_hub()
    return {
        "trace_id": hub.trace_id,
        "step_id": hub.step_id,
        "event_count": len(hub.events),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.append(ws)
    hub = get_hub()
    try:
        for e in hub.events:
            d = e.model_dump(mode="json")
            d["payload"] = redact_obj(d.get("payload", {}))
            await ws.send_json({"type": "event", "data": d})
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=120.0)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


ui_dir = Path(__file__).resolve().parent.parent / "ui" / "static"
if ui_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")


@app.get("/")
async def index() -> FileResponse:
    idx = ui_dir / "index.html"
    return FileResponse(idx)

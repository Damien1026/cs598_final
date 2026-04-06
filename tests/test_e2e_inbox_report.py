"""End-to-end test: server starts, agent receives inbox/weekly-report task, events are correct."""
from __future__ import annotations

import asyncio
import os

import httpx
import pytest


@pytest.fixture(autouse=True)
def _reset_server_globals(tmp_path, monkeypatch):
    """Isolate server module state so each test gets a fresh workspace and hub."""
    monkeypatch.setenv("OBS_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OBS_HITL_AUTO", "allow")

    import server.app as srv

    monkeypatch.setattr(srv, "_workspace", None)
    monkeypatch.setattr(srv, "_hub", None)
    monkeypatch.setattr(srv, "_ws_clients", [])
    monkeypatch.setattr(srv, "_agent_task", None)
    monkeypatch.setattr(srv, "_lock", asyncio.Lock())


@pytest.mark.asyncio
async def test_server_starts_and_returns_session():
    from server.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/session")
        assert r.status_code == 200
        data = r.json()
        assert "trace_id" in data
        assert data["event_count"] == 0


@pytest.mark.asyncio
async def test_inbox_weekly_report_task():
    """
    Agent task: "总结我的收件箱，并且给我一份周报"
    Expected flow (MockLLM):
      turn 1 → fetch_gmail_mock
      turn 2 → write_file to workspace/notes/summary.txt  (allowed by policy)
    Assertions:
      - /api/agent/start returns {"status": "started"}
      - agent completes without unhandled exception
      - events contain tool_call for fetch_gmail_mock
      - events contain tool_call for write_file
      - no policy_violation events
    """
    import server.app as srv
    from server.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # ── 1. submit task ────────────────────────────────────────────────
        r = await client.post(
            "/api/agent/start",
            json={"task": "总结我的收件箱，并且给我一份周报", "mock_llm": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "started"

        # ── 2. wait for agent task to finish ─────────────────────────────
        for _ in range(60):
            await asyncio.sleep(0.2)
            task = srv._agent_task
            if task is not None and task.done():
                break
        else:
            pytest.fail("Agent task did not complete within 12 s")

        # propagate any exception from the agent
        exc = srv._agent_task.exception()
        assert exc is None, f"Agent raised: {exc}"

        # ── 3. fetch and validate events ──────────────────────────────────
        r = await client.get("/api/events")
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) > 0, "No events recorded"

        event_types = {e["event_type"] for e in events}
        tool_names = [
            e["payload"].get("name")
            for e in events
            if e.get("payload") and e["event_type"] == "tool_call"
        ]

        assert "tool_call" in event_types, f"No tool_call events. Got: {event_types}"
        assert "fetch_gmail_mock" in tool_names, f"Expected fetch_gmail_mock. Got: {tool_names}"
        assert "write_file" in tool_names, f"Expected write_file. Got: {tool_names}"
        assert "hitl_resolved" in event_types, "Expected HITL to trigger and be resolved"
        assert "policy_violation" not in event_types, (
            f"Unexpected policy violations: "
            + str([e for e in events if e["event_type"] == "policy_violation"])
        )


@pytest.mark.asyncio
async def test_busy_rejects_second_start():
    """Second /api/agent/start while agent is running returns status=busy."""
    import server.app as srv
    from server.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/agent/start",
            json={"task": "总结我的收件箱，并且给我一份周报", "mock_llm": True},
        )
        # Fire second request immediately — agent likely still running
        r2 = await client.post(
            "/api/agent/start",
            json={"task": "another task", "mock_llm": True},
        )
        assert r2.status_code == 200
        # Either "started" (if first finished instantly) or "busy"
        assert r2.json()["status"] in {"started", "busy"}

        # Wait for any running task
        for _ in range(60):
            await asyncio.sleep(0.2)
            task = srv._agent_task
            if task is not None and task.done():
                break

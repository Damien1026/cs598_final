"""
Phase 1 synthetic eval: precision/recall/F1 on should_alert vs policy_violation or blocked tool outcome.
Also prints wall-time overhead (instrumented run vs minimal counter — placeholder second timing).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import yaml

from observe.events import EventType
from observe.hub import ObsHub
from eval.metrics import BinaryMetrics, update_alert_metrics
from agent.runner import build_agent


async def run_one(
    workspace: Path,
    task: str,
    mock_llm: bool,
    hitl_auto: str | None,
) -> list:
    if hitl_auto:
        os.environ["OBS_HITL_AUTO"] = hitl_auto
    else:
        os.environ.pop("OBS_HITL_AUTO", None)
    log = workspace / "logs" / "events.jsonl"
    trust = workspace / "logs" / "trust.json"
    hub = ObsHub(jsonl_path=log, trust_path=trust)
    agent = build_agent(workspace, hub, mock_llm=mock_llm)
    t0 = time.perf_counter()
    await agent.run(task)
    dt = time.perf_counter() - t0
    return hub.events, dt


def predicted_alert(events: list) -> bool:
    for e in events:
        if e.event_type == EventType.policy_violation:
            return True
        if e.event_type == EventType.tool_call and e.payload.get("phase") == "result":
            c = str(e.payload.get("output_preview", ""))
            if "blocked" in c.lower():
                return True
    return False


async def main_async() -> None:
    root = Path(__file__).resolve().parent.parent
    tasks_path = Path(__file__).resolve().parent / "tasks_synthetic.yaml"
    data = yaml.safe_load(tasks_path.read_text(encoding="utf-8"))
    m = BinaryMetrics()
    timings: list[float] = []

    for spec in data["tasks"]:
        ws = root / "sandbox_eval" / spec["id"]
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "workspace" / "notes").mkdir(parents=True, exist_ok=True)
        events, dt = await run_one(
            ws,
            spec["task"],
            spec.get("mock_llm", True),
            spec.get("hitl_auto"),
        )
        timings.append(dt)
        pred = predicted_alert(events)
        should = bool(spec["expect_policy_violation"])
        update_alert_metrics(m, predicted_alert=pred, should_alert=should)
        print(f"{spec['id']}: pred_alert={pred} should={should} time={dt:.3f}s")

    overhead_note = (
        f"mean wall time {sum(timings)/len(timings):.3f}s per task (instrumented agent loop)."
    )
    print(json.dumps({"metrics": m.as_dict(), "note": overhead_note}, indent=2))


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

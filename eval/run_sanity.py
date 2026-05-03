"""
Sanity-check anchoring eval — runs all 6 baseline scenarios and prints a
human-readable table showing Expected vs Observed outcome, risk score, and
the policy rule that fired (or — for clean-pass cases).

Usage:
    python3 -m eval.run_sanity
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import yaml

from agent.runner import build_agent
from observe.events import EventType
from observe.hub import ObsHub

# Canonical display order matching the README anchoring table
CANONICAL_ORDER = [
    "safe_public_write",
    "safe_public_get",
    "exfil_post_blocked",
    "credential_get_hitl",
    "rag_write_blocked",
    "benign_inbox_save",
]

SCENARIO_LABELS = {
    "safe_public_write":    "public read → allowlisted write",
    "safe_public_get":      "public HTTP GET",
    "exfil_post_blocked":   "pii → http_post_external",
    "credential_get_hitl":  "credential → http_get_external",
    "rag_write_blocked":    "internal_doc → outside allowlist",
    "benign_inbox_save":    "pii → allowlisted file write",
}


async def run_one(workspace: Path, task: str, mock_llm: bool, hitl_auto: str | None) -> list:
    if hitl_auto:
        os.environ["OBS_HITL_AUTO"] = hitl_auto
    else:
        os.environ.pop("OBS_HITL_AUTO", None)
    log = workspace / "logs" / "events.jsonl"
    trust = workspace / "logs" / "trust.json"
    hub = ObsHub(jsonl_path=log, trust_path=trust)
    agent = build_agent(workspace, hub, mock_llm=mock_llm)
    await agent.run(task)
    return hub.events


def observed_outcome(events: list) -> tuple[str, str, float]:
    """Return (outcome, rule, max_risk) derived from the event stream."""
    outcome = "allow"
    rule = "—"
    max_risk = 0.0
    for e in events:
        if e.event_type == EventType.risk_update:
            max_risk = max(max_risk, float(e.payload.get("risk", 0.0)))
        if e.event_type == EventType.policy_violation:
            outcome = "deny"
            rule = e.payload.get("rule", "?")
        if e.event_type == EventType.hitl_request and outcome != "deny":
            outcome = "hitl"
            rule = e.payload.get("rule", "?")
    return outcome, rule, max_risk


async def main_async() -> None:
    root = Path(__file__).resolve().parent.parent
    tasks_path = Path(__file__).resolve().parent / "tasks_synthetic.yaml"
    data = yaml.safe_load(tasks_path.read_text(encoding="utf-8"))
    task_map = {t["id"]: t for t in data["tasks"]}

    rows: list[tuple[str, str, str, str, str, str]] = []  # (scenario, expected, observed, match, risk, rule)

    for tid in CANONICAL_ORDER:
        spec = task_map[tid]
        ws = root / "sandbox_sanity" / tid
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "workspace" / "notes").mkdir(parents=True, exist_ok=True)

        events = await run_one(ws, spec["task"], spec.get("mock_llm", True), spec.get("hitl_auto"))
        obs_out, obs_rule, max_risk = observed_outcome(events)
        exp_out = spec.get("expected_outcome", "?")
        exp_rule = spec.get("expected_rule", "?")
        match = "PASS" if obs_out == exp_out else "FAIL"
        label = SCENARIO_LABELS.get(tid, tid)
        rows.append((label, exp_out.upper(), obs_out.upper(), match, f"{max_risk:.2f}", obs_rule or exp_rule))

    # ── Print table ────────────────────────────────────────────────────────────
    col_w = [max(len(r[i]) for r in rows + [("Scenario", "Expected", "Observed", "Match", "Risk", "Rule")])
             for i in range(6)]
    col_w[0] = max(col_w[0], len("Scenario"))

    def fmt_row(cells: tuple) -> str:
        return "| " + " | ".join(str(c).ljust(col_w[i]) for i, c in enumerate(cells)) + " |"

    sep = "|-" + "-|-".join("-" * w for w in col_w) + "-|"
    header = ("Scenario", "Expected", "Observed", "Match", "Risk", "Rule")

    print()
    print(fmt_row(header))
    print(sep)
    for row in rows:
        print(fmt_row(row))
    print()

    passes = sum(1 for r in rows if r[3] == "PASS")
    print(f"Result: {passes}/{len(rows)} scenarios matched expected outcome.")
    print()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

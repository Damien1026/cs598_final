# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run dashboard (interactive mode)
uvicorn server.app:app --reload --host 127.0.0.1 --port 8765

# Run agent via CLI (mock LLM, no Ollama needed)
python3 -m agent.cli --task "Summarize my inbox and save notes" --mock-llm

# Run agent with Ollama
OLLAMA_MODEL=llama3.2 python3 -m agent.cli --task "Your task"

# Run tests
python3 -m pytest tests/ -v

# Run a single test file
python3 -m pytest tests/test_policy.py -v

# Evaluation
python3 -m eval.run_synthetic       # Phase 1: precision/recall/F1
python3 -m eval.run_practical       # Phase 2: interrupt rate / signal-to-noise
python3 scripts/repro_figures.py    # Both phases combined
```

Key env vars:
- `OBS_WORKSPACE` (default `sandbox`) — workspace root; agent reads/writes under `{workspace}/workspace/`, logs to `{workspace}/logs/`
- `OBS_HITL_AUTO` — set to `allow`/`deny`/`allow_once` to bypass interactive HITL (required for eval/CI)
- `REDACT_SECRETS` — set to `0` to see raw secrets in API responses

## Architecture

The framework wraps a tool-calling LLM agent loop with a full observability layer. Every I/O action flows through `MonitoredIO` (`observe/wrappers.py`), which applies taint tracking, policy evaluation, risk scoring, and optional HITL before the action executes.

### Observability Pipeline (`observe/`)

All components are coordinated by **`ObsHub`** (`hub.py`), which holds singleton references to:
- **`EventBus`** (`bus.py`) — pub/sub dispatcher; persists all events to JSONL; broadcasts to WebSocket clients
- **`TaintStore`** (`taint.py`) — manages `Artifact` objects with sensitivity labels (`public < internal_doc < pii < credential`); unions labels on data merge; infers labels from text heuristics
- **`LineageBuilder`** (`lineage.py`) — ingests events to build a source→tool→sink provenance graph
- **`TrustStore`** (`trust.py`) — per-action fingerprint (SHA256 of tool+args+sink) trust scores; decays 0.99×/step; adjusted +0.15 (allow), −0.2 (deny), +0.05 (allow_once)

The policy/risk/HITL decision sequence in `wrappers._apply_policy_hitl()`:
1. `evaluate_sink()` (`policy.py`) — hard rules → `allow`/`deny`/`hitl`
2. `compute_risk()` (`risk.py`) — `sensitivity×0.55 + sink×0.35 + depth×0.10 − trust_offset`; if risk ≥ HITL threshold, escalate even allowed actions
3. If `hitl`: `hub.register_hitl()` creates an async future; agent loop suspends until `/api/hitl/{hid}` resolves it
4. `trust.adjust()` updates the fingerprint score based on the decision

### Agent Loop (`agent/`)

**`MonitoredAgent.run()`** (`runner.py`) is a multi-turn loop:
- Calls LLM with messages + tools schema → gets `(content, tool_calls)`
- Dispatches each tool call through `MonitoredIO`; tool results are tagged with `[[artifacts:id1,id2,...]]` so artifact IDs propagate into subsequent LLM turns
- `MockLLM` (`llm.py`) follows a hardcoded keyword-based sequence (turn 1: fetch, turn 2: write/post) — used for all eval and CI

### Dashboard (`server/app.py` + `ui/static/`)

FastAPI server with a WebSocket at `/ws` that broadcasts every event in real time. HITL flow: agent emits `hitl_request` event → WebSocket pushes it to browser → user clicks allow/deny → `POST /api/hitl/{hid}` → server resolves the async future → agent resumes.

### Evaluation (`eval/`)

- **Synthetic** (`run_synthetic.py`): loads `tasks_synthetic.yaml` (3 ground-truth tasks), runs each with `MockLLM` + `OBS_HITL_AUTO`, checks for `policy_violation` events against expected outcomes → precision/recall/F1
- **Practical** (`run_practical.py`): runs one long-context task 3× and reports HITL interrupt rate and violation count

### Taint Label Rules (from `policy.py`)

| Label | Sink | Decision |
|---|---|---|
| `credential` / `pii` | `http_post_external` | deny |
| `internal_doc` | `http_post_external` | hitl |
| `credential` | `http_get_external` | hitl |
| `internal_doc` / `pii` | `file_write` outside allowlist | deny / hitl |

Allowlist defaults: `workspace/`, `notes/`, `./`

# Privacy & Security Observability for Local LLM Agents

Runtime monitoring for a local tool-calling LLM agent: **dynamic taint tracking**, **visual data lineage**, **context-risk scoring**, **human-in-the-loop (HITL) review**, and a **real-time web dashboard**.

## Overview

LLM agents with OS-level access can fetch private data via APIs or RAG pipelines, but standard logs only record *what* happened — not *why* or whether it was safe. This framework provides runtime observability that tracks data provenance, scores risk in real time, and pauses the agent for human review when ambiguous privacy/security actions are detected.

### Key Features

- **Dynamic Taint Tracking & Data Lineage** — sensitive data (PII, credentials, internal docs) is tagged at ingestion and tracked through every tool call and sink write (e.g., Gmail API -> Agent Context -> File Write)
- **Context-Risk Scoring** — live risk score based on data sensitivity, sink severity, chain depth, and a personalized trust offset
- **Human-in-the-Loop (HITL) Gates** — the agent pauses on ambiguous actions for user review; responses adjust a per-action trust score over time
- **Policy Engine** — configurable deny/allow/HITL rules for sinks (external HTTP posts, file writes outside allowlist, etc.)
- **Web Dashboard** — real-time timeline, lineage graph, risk meter, and HITL interaction panel via WebSocket

## Prerequisites

- **Python 3.11+** (check with `python3 --version`)
- **Ollama** (optional, only needed for real LLM mode) — install from [ollama.com](https://ollama.com)

## Quick Start

### 1. Clone and set up

```bash
git clone <your-repo-url>
cd cs598_final
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the dashboard (recommended)

This starts the FastAPI server with the web dashboard and agent controls:

```bash
uvicorn server.app:app --reload --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765 in your browser. Use the **Start demo agent** button or POST to `/api/agent/start`:

```bash
curl -X POST http://127.0.0.1:8765/api/agent/start \
  -H "Content-Type: application/json" \
  -d '{"task": "Fetch mock inbox and save a summary to workspace.", "mock_llm": true}'
```

### 3. Run via CLI (mock LLM, no Ollama needed)

```bash
python3 -m agent.cli --task "Summarize my inbox and save notes" --mock-llm
```

### 4. Run via CLI with Ollama

Make sure Ollama is running (`ollama serve`), then:

```bash
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3.2          # optional, defaults to llama3.2
python3 -m agent.cli --task "Your task"
```

### 5. Non-interactive HITL (for eval / CI)

Auto-resolve all HITL prompts without user interaction:

```bash
export OBS_HITL_AUTO="allow"   # options: allow | deny | allow_once
python3 -m agent.cli --task "Summarize my inbox and save notes" --mock-llm
```

## Evaluation

### Phase 1: Synthetic benchmarks (precision / recall / F1)

Runs tasks with ground-truth expectations from `eval/tasks_synthetic.yaml`:

```bash
python3 -m eval.run_synthetic
```

### Phase 2: Practical workloads (interrupt rate, signal-to-noise)

Runs long-context tasks 3 times and reports HITL interrupt rate and violation counts:

```bash
python3 -m eval.run_practical
```

### Both phases (for report generation)

```bash
python3 scripts/repro_figures.py
```

## Running Tests

```bash
python3 -m pytest tests/ -v
```

## Project Layout

| Path | Role |
|------|------|
| `observe/` | Core observability engine: events, event bus, taint store, lineage builder, policy engine, risk scorer, trust store, redaction |
| `observe/hub.py` | Central `ObsHub` coordinating all observability components |
| `observe/taint.py` | Sensitivity labels (`public`, `internal_doc`, `pii`, `credential`), artifact tracking, label inference heuristics |
| `observe/policy.py` | Sink policy rules (deny PII external posts, HITL for ambiguous writes, allowlist enforcement) |
| `observe/risk.py` | Weighted risk score: sensitivity (0.55) + sink severity (0.35) + chain depth (0.10) - trust offset |
| `observe/wrappers.py` | `MonitoredIO` — all I/O wrapped with taint tracking and policy enforcement |
| `observe/lineage.py` | Builds source -> tool -> sink lineage graph from events |
| `observe/trust.py` | Per-action trust scores with decay, adjusted by HITL decisions |
| `agent/` | Agent loop, LLM adapters (Ollama + mock), CLI entry point |
| `agent/runner.py` | `MonitoredAgent` — agentic loop dispatching tool calls through `MonitoredIO` |
| `agent/llm.py` | `OllamaLLM` (real) and `MockLLM` (deterministic tool-calling sequences for testing) |
| `server/app.py` | FastAPI dashboard: REST API + WebSocket for real-time event streaming |
| `ui/static/` | Dashboard frontend (timeline, lineage, risk meter, HITL panel) |
| `eval/` | Evaluation scripts: synthetic benchmarks and practical workload analysis |
| `tests/` | Unit tests for policy engine |
| [docs/DESIGN.md](docs/DESIGN.md) | Threat model, sources/sinks, sensitivity labels, leak rules, HITL policy |
| [docs/HARDENING.md](docs/HARDENING.md) | Security hardening recommendations and known limitations |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/agent/start` | Start the agent with `{"task": "...", "mock_llm": true}` |
| `POST` | `/api/hitl/{hid}` | Respond to HITL prompt with `{"decision": "allow\|deny\|allow_once"}` |
| `GET` | `/api/events?reveal=false` | List all session events (redacted by default) |
| `GET` | `/api/lineage` | Get the data lineage graph (nodes + edges) |
| `GET` | `/api/risk` | Get risk score history |
| `GET` | `/api/session` | Get current session metadata |
| `WS` | `/ws` | Real-time event stream via WebSocket |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBS_WORKSPACE` | `sandbox` | Workspace root directory |
| `OBS_HITL_AUTO` | *(unset)* | Auto-resolve HITL: `allow`, `deny`, or `allow_once` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `REDACT_SECRETS` | `1` | Set to `0` to disable secret redaction in API responses |

## Risk Score Formula

```
risk = sensitivity_weight * 0.55 + sink_weight * 0.35 + chain_depth * 0.10 - trust_offset
```

- **Sensitivity weight**: public=0.0, internal_doc=0.25, pii=0.5, credential=1.0
- **Sink weight**: http_post_external=1.0, file_write=0.45, http_get_external=0.25, http_post_internal=0.15, tool_result=0.1
- **Chain depth bonus**: min(step_id * 0.03, 0.2)
- **Trust offset**: trust_score * 0.15 (range 0..0.15)

Final score clamped to [0, 1]. When risk >= HITL threshold, even allowed actions are escalated for human review.

## Limitations

- Taint is applied at **controlled I/O boundaries**, not arbitrary process memory
- The mock LLM follows hardcoded tool-calling sequences; real LLM behavior may differ
- Trust scores persist locally in `trust.json` — not designed for multi-user deployments
- See [docs/DESIGN.md](docs/DESIGN.md) and [docs/HARDENING.md](docs/HARDENING.md) for full details

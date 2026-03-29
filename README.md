# Privacy & Security Observability for Local LLM Agents

Runtime monitoring for a local tool-calling LLM agent: **taint tracking**, **lineage**, **risk scoring**, **human-in-the-loop** gates, and a **web dashboard**.

## Quick start

```bash
cd f:\cs598_final
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Dashboard + agent (single process)

```bash
uvicorn server.app:app --reload --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765 — use **Start demo agent** or POST `/api/agent/start` with a JSON body.

### CLI (mock LLM, no Ollama)

```bash
python -m agent.cli --task "Summarize my inbox and save notes" --mock-llm
```

### Non-interactive HITL (eval / CI)

```powershell
$env:OBS_HITL_AUTO = "allow"   # or deny | allow_once
python -m agent.cli --task "..." --mock-llm
```

### CLI with Ollama

Set `OLLAMA_MODEL` (default `llama3.2`) and ensure Ollama is running:

```bash
set OLLAMA_BASE_URL=http://127.0.0.1:11434
python -m agent.cli --task "Your task"
```

## Layout

| Path | Role |
|------|------|
| [docs/DESIGN.md](docs/DESIGN.md) | Threat model, sources/sinks, HITL policy |
| `observe/` | Events, bus, taint, policy, lineage, risk, trust |
| `agent/` | Tools, LLM adapter, monitored agent loop |
| `server/` | FastAPI, WebSocket, HITL API |
| `ui/static/` | Dashboard (timeline, lineage, risk, HITL) |
| `eval/` | Synthetic + practical evaluation scripts |

## Evaluation

```bash
python -m eval.run_synthetic
python -m eval.run_practical
```

## Risk score weights

Documented in [observe/risk.py](observe/risk.py): weighted sum of max sensitivity in context, sink severity, chain length, and trust offset.

## Limitations

Taint is applied at **controlled I/O boundaries**, not arbitrary process memory. See DESIGN.md.

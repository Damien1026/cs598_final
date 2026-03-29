# Observer hardening & limitations

## Security of the observer

- **Bind locally**: Run the dashboard on `127.0.0.1` only in untrusted networks (`uvicorn --host 127.0.0.1`).
- **Redaction**: Default `REDACT_SECRETS=1` masks `sk-…` and long base64-like strings in API/WebSocket payloads. Disable only on trusted dev machines.
- **Raw view**: The dashboard `Raw payloads` toggle maps to `?reveal=1` on `/api/events`. Do not enable on shared hosts.
- **Trust store**: `sandbox/logs/trust.json` persists HITL-derived scores; treat as sensitive if it encodes organizational patterns.

## Reproducibility

- Pin dependencies via `requirements.txt` / `pyproject.toml`.
- Set `OBS_WORKSPACE` to a clean directory per run for eval.
- Use `--mock-llm` for deterministic CI; Ollama results vary by model and temperature.

## Limitations (report-ready)

- Taint and policy enforcement apply at **instrumented wrappers**, not kernel memory.
- **Heuristic labels** (`infer_labels_from_text`) reduce false negatives when the LLM omits `artifact_ids` but are not sound.
- **HITL** is usability-focused, not a formal verification gate.

## Demo video

Record: start `uvicorn server.app:app`, open `/`, run a task that triggers lineage + one HITL, resolve it, show risk meter. (Script left to the team.)

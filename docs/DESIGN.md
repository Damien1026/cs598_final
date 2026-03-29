# Design: Privacy & Security Observability for Local LLM Agents

## Threat model (course scope)

We assume a **local Python agent** with tools that read private-ish data (mock Gmail, RAG, files) and may write to **sinks** (files, HTTP). Threats of interest:

1. **Unintended exfiltration**: Sensitive labels (`pii`, `credential`, `internal_doc`) reaching **external HTTP** or **non-allowlisted file paths**.
2. **Opaque actions**: Users cannot see **why** a tool ran or **where** data in the context came from.
3. **Over-automation**: High-risk tool chains without human confirmation.

We do **not** claim kernel-level information flow control or protection against a malicious agent process that bypasses our wrappers.

## Instrumented sources

| Source        | Description                    | Default labels        |
|---------------|--------------------------------|------------------------|
| `gmail_mock`  | Mock inbox API                 | `pii`                  |
| `rag_search`  | Mock retrieval over repo index | `internal_doc`       |
| `file_read`   | Read under workspace sandbox   | Inherit path policy   |
| `http_get`    | GET to allowlisted/mock URLs   | `public` or configured |
| `env`         | Simulated env/secret injection | `credential`          |

## Instrumented sinks

| Sink           | Severity (for risk score) |
|----------------|---------------------------|
| `http_post_external` | High (3)            |
| `http_get_external`  | Medium (2)            |
| `file_write`         | Medium–High (2–3)     |
| `tool_result`        | Low (1)               |

## Sensitivity labels

- `public` — No restriction for MVP demos.
- `internal_doc` — Should not leave workspace without review.
- `pii` — Must not be posted externally; file writes outside allowlist blocked or HITL.
- `credential` — Same as `pii`, higher risk weight.

**Propagation**: Union of labels when strings are concatenated or passed as tool arguments. Each artifact gets a stable `artifact_id` and provenance (`origin`).

## Leak rules (MVP)

1. `credential` or `pii` → `http_post_external`: **deny** (or HITL if configured soft).
2. `internal_doc` → path outside `allow_write_prefixes`: **deny** or HITL.
3. `credential` in content → `file_write` outside allowlist: **deny**.

## HITL policy

Pause and prompt the user when:

1. **Ambiguous policy**: Soft mode — `pii`/`internal_doc` → `file_write` **inside** allowlist still triggers HITL once per `(tool, sink_fingerprint)` until trusted.
2. **High risk score**: `risk_score >= hitl_threshold` (default 0.75, adjusted by trust).
3. **Explicit rule** `hitl` outcome from policy engine instead of `deny`.

User actions: **Allow**, **Deny**, **Allow once** (stored with decaying trust).

## Personalized trust

- Key: `policy_id` + `action_fingerprint` (hash of tool name + normalized args + sink).
- Score in `[0, 1]` updated by Allow (+0.15), Deny (−0.2), Allow-once (+0.05).
- Decay: multiply by 0.99 per session step (cap effects in implementation).
- Effect: raises `hitl_threshold` when trust is high (fewer interrupts); lowers when trust is low.

## Redaction

Events stored and sent to UI use **redacted** payloads by default (`REDACT_SECRETS=1`): replace sequences matching `sk-[A-Za-z0-9]+` and long base64-like tokens. Raw view is **dev-only** via query flag `?reveal=1` on API (localhost only recommended).

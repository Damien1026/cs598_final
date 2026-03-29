"""
Risk score: transparent weighted sum (documented for course report).

Weights:
- max_sensitivity_in_context: 0..3 mapped to 0, 0.25, 0.5, 1.0
- sink_severity: http_post_external=1.0, file_write=0.45, http_get=0.25, tool=0.1
- chain_depth_bonus: min(step_id * 0.03, 0.2)
- trust_offset: subtract trust_score * 0.15 (0..0.15)

Final score clamped to [0, 1].
"""
from __future__ import annotations

from observe.taint import Sensitivity


SINK_WEIGHT = {
    "http_post_external": 1.0,
    "file_write": 0.45,
    "http_get_external": 0.25,
    "tool_result": 0.1,
}


def sensitivity_weight(max_s: Sensitivity) -> float:
    return {Sensitivity.public: 0.0, Sensitivity.internal_doc: 0.25, Sensitivity.pii: 0.5, Sensitivity.credential: 1.0}[
        max_s
    ]


def compute_risk(
    max_s: Sensitivity,
    sink: str | None,
    step_id: int,
    trust_score: float,
) -> float:
    w_s = sensitivity_weight(max_s)
    w_k = SINK_WEIGHT.get(sink or "", 0.15)
    chain = min(step_id * 0.03, 0.2)
    trust_off = min(max(trust_score, 0.0), 1.0) * 0.15
    raw = w_s * 0.55 + w_k * 0.35 + chain * 0.1 - trust_off
    return max(0.0, min(1.0, raw))

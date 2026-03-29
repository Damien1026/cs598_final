from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from observe.taint import Sensitivity


class PolicyOutcome(str, Enum):
    allow = "allow"
    deny = "deny"
    hitl = "hitl"


@dataclass
class PolicyResult:
    outcome: PolicyOutcome
    rule_id: str
    reason: str


# Allowlisted path prefixes for file writes (relative to workspace)
DEFAULT_WRITE_PREFIXES: tuple[str, ...] = ("workspace/", "notes/", "./")


def _sens_max(labels: set[str]) -> Sensitivity:
    m = Sensitivity.public
    for lab in labels:
        if lab in Sensitivity.__members__:
            m = max(m, Sensitivity[lab])
    return m


def _path_allowed(path: str, prefixes: tuple[str, ...]) -> bool:
    p = path.replace("\\", "/").lstrip("/")
    return any(p.startswith(pref) or p == pref.rstrip("/") for pref in prefixes)


def evaluate_sink(
    sink: str,
    labels: set[str],
    *,
    sink_meta: dict[str, Any] | None = None,
    write_prefixes: tuple[str, ...] = DEFAULT_WRITE_PREFIXES,
    soft_file_hitl: bool = True,
) -> PolicyResult:
    """MVP policy: deny obvious leaks; HITL for ambiguous file writes with sensitive labels."""
    sink_meta = sink_meta or {}
    max_s = _sens_max(labels)

    if sink == "http_post_external":
        if max_s >= Sensitivity.pii:
            return PolicyResult(
                PolicyOutcome.deny,
                "R1",
                "pii/credential cannot be posted externally",
            )
        if max_s >= Sensitivity.internal_doc:
            return PolicyResult(PolicyOutcome.hitl, "R1b", "internal_doc external post review")

    if sink == "http_get_external":
        if max_s >= Sensitivity.credential:
            return PolicyResult(PolicyOutcome.hitl, "R2", "credential-adjacent external GET review")

    if sink == "file_write":
        path = str(sink_meta.get("path", ""))
        allowed = _path_allowed(path, write_prefixes)
        if not allowed and max_s >= Sensitivity.internal_doc:
            return PolicyResult(
                PolicyOutcome.deny,
                "R3",
                "internal_doc/pii/credential file write outside allowlist",
            )
        if not allowed and max_s >= Sensitivity.public and len(labels) == 0:
            return PolicyResult(
                PolicyOutcome.hitl,
                "R3u",
                "write outside allowlist with unknown sensitivity — review",
            )
        if allowed and soft_file_hitl and max_s >= Sensitivity.pii:
            return PolicyResult(
                PolicyOutcome.hitl,
                "R4",
                "pii write to allowlisted path needs confirmation",
            )

    return PolicyResult(PolicyOutcome.allow, "OK", "allowed")


def action_fingerprint(tool: str, args: dict[str, Any], sink: str) -> str:
    import hashlib
    import json

    norm = json.dumps({"tool": tool, "args": args, "sink": sink}, sort_keys=True)
    return hashlib.sha256(norm.encode()).hexdigest()[:16]

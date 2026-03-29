from __future__ import annotations

import os
import re
from typing import Any

_SK = re.compile(r"sk-[A-Za-z0-9]{20,}")
_B64ISH = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")


def redact_obj(obj: Any, *, enabled: bool | None = None) -> Any:
    if enabled is None:
        enabled = os.environ.get("REDACT_SECRETS", "1") not in ("0", "false", "False")
    if not enabled:
        return obj
    if isinstance(obj, str):
        s = _SK.sub("[REDACTED_SECRET]", obj)
        s = _B64ISH.sub("[REDACTED_TOKEN]", s)
        return s
    if isinstance(obj, dict):
        return {k: redact_obj(v, enabled=enabled) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(x, enabled=enabled) for x in obj]
    return obj

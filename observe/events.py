from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    source_fetch = "source_fetch"
    llm_call = "llm_call"
    tool_call = "tool_call"
    sink_write = "sink_write"
    policy_violation = "policy_violation"
    hitl_request = "hitl_request"
    hitl_resolved = "hitl_resolved"
    session_start = "session_start"
    session_end = "session_end"
    risk_update = "risk_update"
    context_usage = "context_usage"
    context_warning = "context_warning"


class ObsEvent(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=utc_now)
    trace_id: str = ""
    step_id: int = 0
    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, Any] = Field(default_factory=dict)

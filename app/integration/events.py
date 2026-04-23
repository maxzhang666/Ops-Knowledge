"""Shared event envelope + channel constant for the cross-domain bus.

Single multiplex channel keeps subscription management trivial (one Redis
connection per process). Filter-on-read at subscriber side. Fine for expected
1b volume (~10 events/s). Revisit per-channel routing if sustained >100/s.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventName = Literal[
    "document.completed",
    "document.failed",
    "kb.reindex_completed",
    "workflow.execution_completed",
    "workflow.execution_failed",
    "governance.alert",
]

CHANNEL = "opsk:events"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: EventName
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    data: dict[str, Any] = Field(default_factory=dict)

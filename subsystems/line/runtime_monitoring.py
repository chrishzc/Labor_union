"""Runtime health contracts, debounce policy, and LINE alert projection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RuntimeHealthStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


@dataclass(frozen=True, slots=True)
class RuntimeHealthObservation:
    check_name: str
    component: str
    status: RuntimeHealthStatus
    message: str
    details: dict[str, object]
    checked_at: datetime
    response_ms: int | None = None

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(
            [self.check_name, self.status.value, self.message, self.checked_at.isoformat()],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RuntimeHealthRecord:
    check_name: str
    component: str
    status: str
    raw_status: str
    message: str
    response_ms: int | None
    consecutive_failures: int
    consecutive_successes: int
    checked_at: datetime
    status_changed_at: datetime
    details: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeHealthEvent:
    event_id: int
    check_name: str
    component: str
    transition_type: str
    before_status: str | None
    resulting_status: str
    message: str
    occurred_at: datetime


__all__ = [
    "RuntimeHealthEvent",
    "RuntimeHealthObservation",
    "RuntimeHealthRecord",
    "RuntimeHealthStatus",
]

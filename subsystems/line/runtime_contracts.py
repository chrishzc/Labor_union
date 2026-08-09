"""Typed runtime health and security facts for the independent LINE worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class LineRuntimeMode(StrEnum):
    LEGACY = "legacy"
    CANONICAL = "canonical"
    COMPATIBILITY = "compatibility"


class LineWorkerHealthStatus(StrEnum):
    HEALTHY = "healthy"
    STALE = "stale"
    MISSING = "missing"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class LineWebhookVerificationOutcome(StrEnum):
    VERIFIED = "verified"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_PAYLOAD = "invalid_payload"
    STORAGE_FAILED = "storage_failed"


@dataclass(frozen=True, slots=True)
class LineWorkerHeartbeat:
    worker_identity: str
    process_id: int
    host_name: str
    runtime_mode: LineRuntimeMode
    component_status_json: str
    heartbeat_at: datetime
    last_cycle_at: datetime | None = None
    stopped_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


@dataclass(frozen=True, slots=True)
class LineWebhookSecurityReceipt:
    request_fingerprint: str
    signature_present: bool
    outcome: LineWebhookVerificationOutcome
    event_count: int
    correlation_id: str
    occurred_at: datetime


__all__ = [
    "LineRuntimeMode",
    "LineWebhookSecurityReceipt",
    "LineWebhookVerificationOutcome",
    "LineWorkerHealthStatus",
    "LineWorkerHeartbeat",
]

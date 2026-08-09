"""Pure health classification for persisted LINE worker heartbeats."""

from __future__ import annotations

from datetime import datetime, timezone


def classify_line_worker_health(
    heartbeat,
    *,
    stale_after_seconds: float,
    now: datetime | None = None,
) -> dict[str, object]:
    if heartbeat is None:
        return {"status": "missing", "running": False}
    current_time = now or datetime.now(timezone.utc)
    age_seconds = max(0.0, (current_time - heartbeat.heartbeat_at).total_seconds())
    status = _status(heartbeat, age_seconds, stale_after_seconds)
    return {
        "status": status,
        "running": status == "healthy",
        "worker_identity": heartbeat.worker_identity,
        "runtime_mode": heartbeat.runtime_mode.value,
        "heartbeat_age_seconds": round(age_seconds, 1),
        "last_error_code": heartbeat.last_error_code,
    }


def _status(heartbeat, age_seconds: float, stale_after_seconds: float) -> str:
    if heartbeat.stopped_at is not None:
        return "stopped"
    if heartbeat.last_error_code:
        return "degraded"
    if age_seconds > stale_after_seconds:
        return "stale"
    return "healthy"


__all__ = ["classify_line_worker_health"]

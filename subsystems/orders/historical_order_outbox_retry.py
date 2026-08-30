"""Shared retry policy for Orders-owned historical outbox consumers."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol


HISTORICAL_ORDER_OUTBOX_MAX_ATTEMPTS = 3
HISTORICAL_ORDER_OUTBOX_RETRY_DELAY_SECONDS = 1
HISTORICAL_ORDER_OUTBOX_RETRY_READY_SQL = (
    "(last_error IS NULL OR JSON_VALID(last_error)=0 OR "
    "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(last_error,'$.retry_after_epoch')) "
    "AS DECIMAL(20,6)),0)<=UNIX_TIMESTAMP(UTC_TIMESTAMP(6)))"
)


class HistoricalOrderOutboxRuntime(Protocol):
    """Outer composition required for the independent failure transaction."""

    def failure_unit_of_work(self, connection: Any) -> Any: ...


def require_historical_order_outbox_runtime(
    runtime: HistoricalOrderOutboxRuntime | None,
) -> HistoricalOrderOutboxRuntime:
    if runtime is None or not callable(getattr(runtime, "failure_unit_of_work", None)):
        raise RuntimeError("historical_order_outbox_runtime_not_composed")
    return runtime


def historical_order_outbox_error_code(error: Exception) -> str:
    """Return a bounded, non-sensitive retry error identity."""

    message = str(error).strip()
    digest = hashlib.sha256(
        f"{type(error).__name__}:{message}".encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_order_outbox_failed:{digest}"


__all__ = [
    "HISTORICAL_ORDER_OUTBOX_MAX_ATTEMPTS",
    "HISTORICAL_ORDER_OUTBOX_RETRY_DELAY_SECONDS",
    "HISTORICAL_ORDER_OUTBOX_RETRY_READY_SQL",
    "HistoricalOrderOutboxRuntime",
    "historical_order_outbox_error_code",
    "require_historical_order_outbox_runtime",
]

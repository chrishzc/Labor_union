"""Fixed-size, in-memory API timing summary with no request-level retention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from threading import RLock

_LATENCY_BUCKET_UPPER_BOUNDS = (100, 250, 500, 750, 1000, 2000, 5000, None)


@dataclass(frozen=True, slots=True)
class ApiPerformanceSnapshot:
    started_at: datetime
    request_count: int
    average_response_time_ms: float | None
    p50_response_time_upper_bound_ms: int | None
    p95_response_time_upper_bound_ms: int | None
    maximum_response_time_ms: float | None


class InMemoryApiPerformanceRecorder:
    """Store aggregate counters only; individual request timings are never retained."""

    def __init__(self) -> None:
        self._started_at = datetime.now(UTC)
        self._bucket_counts = [0] * len(_LATENCY_BUCKET_UPPER_BOUNDS)
        self._request_count = 0
        self._total_response_time_ms = 0.0
        self._maximum_response_time_ms = 0.0
        self._lock = RLock()

    def record_response_time(self, elapsed_milliseconds: float) -> None:
        if elapsed_milliseconds < 0:
            raise ValueError("elapsed_milliseconds must not be negative")
        with self._lock:
            self._request_count += 1
            self._total_response_time_ms += elapsed_milliseconds
            self._maximum_response_time_ms = max(self._maximum_response_time_ms, elapsed_milliseconds)
            self._bucket_counts[_bucket_index(elapsed_milliseconds)] += 1

    def snapshot(self) -> ApiPerformanceSnapshot:
        with self._lock:
            request_count = self._request_count
            return ApiPerformanceSnapshot(
                started_at=self._started_at,
                request_count=request_count,
                average_response_time_ms=_average_response_time(request_count, self._total_response_time_ms),
                p50_response_time_upper_bound_ms=self._percentile_upper_bound(0.50),
                p95_response_time_upper_bound_ms=self._percentile_upper_bound(0.95),
                maximum_response_time_ms=_maximum_response_time(request_count, self._maximum_response_time_ms),
            )

    def _percentile_upper_bound(self, percentile: float) -> int | None:
        if not self._request_count:
            return None
        requested_rank = ceil(self._request_count * percentile)
        observed_count = 0
        for bound, bucket_count in zip(_LATENCY_BUCKET_UPPER_BOUNDS, self._bucket_counts):
            observed_count += bucket_count
            if observed_count >= requested_rank:
                return bound
        return None


def _bucket_index(elapsed_milliseconds: float) -> int:
    for index, upper_bound in enumerate(_LATENCY_BUCKET_UPPER_BOUNDS):
        if upper_bound is None or elapsed_milliseconds <= upper_bound:
            return index
    raise AssertionError("unreachable latency bucket")


def _average_response_time(request_count: int, total_response_time_ms: float) -> float | None:
    if not request_count:
        return None
    return round(total_response_time_ms / request_count, 1)


def _maximum_response_time(request_count: int, maximum_response_time_ms: float) -> float | None:
    if not request_count:
        return None
    return round(maximum_response_time_ms, 1)


api_performance_snapshot = InMemoryApiPerformanceRecorder()


__all__ = ["ApiPerformanceSnapshot", "InMemoryApiPerformanceRecorder", "api_performance_snapshot"]

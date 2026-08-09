"""Expose per-response API timing without creating persistent telemetry logs."""

from __future__ import annotations

from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware

from shared_kernel.performance_snapshot import api_performance_snapshot

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class ApiPerformanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started_at = perf_counter()
        response = await call_next(request)
        elapsed_milliseconds = (perf_counter() - started_at) * 1000
        response.headers["Server-Timing"] = (
            f"application;dur={elapsed_milliseconds:.1f}"
        )
        response.headers["X-Response-Time-Ms"] = (
            f"{elapsed_milliseconds:.1f}"
        )
        if request.method in _MUTATING_METHODS:
            response.headers["Cache-Control"] = "no-store"
        api_performance_snapshot.record_response_time(elapsed_milliseconds)
        return response


__all__ = ["ApiPerformanceMiddleware"]

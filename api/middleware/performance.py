"""Bounded API timing telemetry without request or response payload logging."""

from __future__ import annotations

import json
import os
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware

_DEFAULT_SLOW_REQUEST_MILLISECONDS = 750.0
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
        _log_if_slow(request, response, elapsed_milliseconds)
        return response


def _log_if_slow(request, response, elapsed_milliseconds):
    threshold = _slow_request_threshold()
    if elapsed_milliseconds < threshold:
        return
    print(
        json.dumps(
            {
                "event": "slow_api_request",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_milliseconds": round(elapsed_milliseconds, 1),
                "threshold_milliseconds": threshold,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _slow_request_threshold():
    raw_value = os.getenv("API_SLOW_REQUEST_MS", "").strip()
    if not raw_value:
        return _DEFAULT_SLOW_REQUEST_MILLISECONDS
    try:
        threshold = float(raw_value)
    except ValueError:
        return _DEFAULT_SLOW_REQUEST_MILLISECONDS
    if threshold <= 0:
        return _DEFAULT_SLOW_REQUEST_MILLISECONDS
    return threshold


__all__ = ["ApiPerformanceMiddleware"]

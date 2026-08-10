from __future__ import annotations

import pytest

from ui.api_clients.system_status_api_client import (
    SystemStatusApiClient,
    SystemStatusApiError,
)


class _Transport:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, str | None]] = []

    def request(self, method: str, path: str, *, token: str | None) -> object:
        self.calls.append((method, path, token))
        return self.payload


def test_performance_snapshot_uses_global_status_route_and_returns_typed_view():
    transport = _Transport(
        {
            "started_at": "2026-08-10T00:00:00Z",
            "request_count": 4,
            "average_response_time_ms": 725.0,
            "p50_response_time_upper_bound_ms": 250,
            "p95_response_time_upper_bound_ms": 5000,
            "maximum_response_time_ms": 2100.0,
        }
    )

    snapshot = SystemStatusApiClient(transport).performance_snapshot("session-token")

    assert snapshot.request_count == 4
    assert transport.calls == [
        ("GET", "/api/v1/system/status/performance-snapshot", "session-token")
    ]


def test_performance_snapshot_rejects_invalid_response_shape():
    transport = _Transport({"request_count": "not-an-integer"})

    with pytest.raises(SystemStatusApiError):
        SystemStatusApiClient(transport).performance_snapshot("session-token")

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ui.api_clients.scheduling_current_api_client import SchedulingCurrentApiClient


@dataclass
class _Response:
    payload: dict
    status_code: int = 200

    @property
    def ok(self) -> bool:
        return True

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self) -> None:
        self.request = None

    def get(self, url, *, headers, params, timeout):
        self.request = {"url": url, "headers": headers, "params": params}
        return _Response({"success": True, "data": _projection()})


def test_current_projection_query_uses_typed_bounded_endpoint() -> None:
    session = _Session()
    client = SchedulingCurrentApiClient(
        base_url="http://api.test", headers={"X-Legacy-Shared-Key": "test"}, session=session
    )

    result = client.query(5, date(2026, 8, 1), date(2026, 8, 2))

    assert result.staff_id == 5
    assert session.request["url"].endswith("/staff/5/current-calendar")
    assert session.request["params"] == {"range_start": "2026-08-01", "range_end": "2026-08-02"}


def _projection() -> dict:
    return {
        "staff_id": 5,
        "range_start": "2026-08-01",
        "range_end": "2026-08-02",
        "evaluated_at": "2026-08-01T00:00:00",
        "assignments": [],
        "days": [
            {"calendar_date": "2026-08-01", "available": True, "entries": []},
            {"calendar_date": "2026-08-02", "available": True, "entries": []},
        ],
        "case_versions": [],
        "projection_token": "a" * 64,
    }

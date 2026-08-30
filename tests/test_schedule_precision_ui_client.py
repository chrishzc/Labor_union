from __future__ import annotations

import pytest

from api.schemas.schedule_precision import SchedulePrecisionResultView
from ui.api_clients.schedule_precision_api_client import (
    SchedulePrecisionApiClient,
    SchedulePrecisionApiError,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payload)


def _result_payload():
    return {
        "actual_start_date": "2026-09-12",
        "actual_end_date": "2026-09-12",
        "target_service_days": 1,
        "total_calendar_days": 1,
        "actual_work_days_count": 1,
        "rest_days_count": 0,
        "national_holidays_found": [],
        "total_estimated_salary": None,
        "weekly_stats": [
            {
                "week_num": 1,
                "start_date": "2026-09-12",
                "end_date": "2026-09-12",
                "work_days": 1,
                "rest_days": 0,
                "holiday_days": 0,
            }
        ],
        "day_by_day": [
            {
                "date": "2026-09-12",
                "day_num": 1,
                "is_work_day": True,
                "is_rest_day": False,
                "holiday_name": None,
            }
        ],
    }


def test_schedule_precision_client_returns_typed_projection_and_preserves_request():
    session = _Session(
        {"success": True, "message": "ok", "data": _result_payload()}
    )
    client = SchedulePrecisionApiClient(
        base_url="http://api.test",
        headers={"Authorization": "Bearer test"},
        session=session,
    )

    result = client.preview(
        {
            "actual_start_date": "2026-09-12",
            "target_service_days": 1,
            "service_mode": "週休2日",
            "custom_work_dates": ["2026-09-12"],
        }
    )

    assert isinstance(result, SchedulePrecisionResultView)
    assert result.actual_end_date.isoformat() == "2026-09-12"
    assert session.calls[0][1]["json"] == {
        "actual_start_date": "2026-09-12",
        "target_service_days": 1,
        "service_mode": "週休2日",
        "custom_work_dates": ["2026-09-12"],
    }


def test_schedule_precision_client_blocks_schema_drift_before_render():
    malformed = {**_result_payload(), "raw_schedule_row": {"id": 99}}
    client = SchedulePrecisionApiClient(
        base_url="http://api.test",
        headers={},
        session=_Session({"success": True, "message": "ok", "data": malformed}),
    )

    with pytest.raises(SchedulePrecisionApiError):
        client.preview(
            {
                "actual_start_date": "2026-09-12",
                "target_service_days": 1,
                "service_mode": "週休2日",
            }
        )

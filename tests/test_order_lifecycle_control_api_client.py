"""
File: test_order_lifecycle_control_api_client.py
Description: 驗證 Streamlit 月曆使用 strict typed 生命週期控制查詢，拒絕投影漂移。
"""

from __future__ import annotations

import pytest

from ui.api_clients.order_lifecycle_control_api_client import (
    OrderLifecycleControlApiClient,
    OrderLifecycleControlApiError,
)


class _Response:
    ok = True
    status_code = 200

    def __init__(self, data: object) -> None:
        self._data = data

    def json(self) -> object:
        return {"success": True, "data": self._data}


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.url = ""

    def get(self, url: str, *, headers: object, timeout: float) -> _Response:
        self.url = url
        return self.response


def _payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "case_no": "C-1",
        "lifecycle_version": 3,
        "canonical_status": "訂單成立",
        "actual_start_reconfirmation": {
            "state": "not_required",
            "required_date": None,
            "current_actual_start_date": "2026-08-01",
            "blockers": ["enter_service.actual_start_reconfirmation_inactive"],
            "can_reconfirm": False,
        },
    }
    payload.update(changes)
    return payload


def test_calendar_control_client_uses_existing_read_only_route() -> None:
    session = _Session(_Response(_payload()))

    result = OrderLifecycleControlApiClient(
        base_url="http://api.test",
        headers={},
        session=session,  # type: ignore[arg-type]
    ).query("C-1")

    assert result.actual_start_reconfirmation.state == "not_required"
    assert session.url.endswith("/api/v1/orders/C-1/lifecycle-control-state")


def test_calendar_control_client_fails_closed_on_unknown_projection_field() -> None:
    session = _Session(_Response(_payload(unexpected=True)))
    client = OrderLifecycleControlApiClient(
        base_url="http://api.test",
        headers={},
        session=session,  # type: ignore[arg-type]
    )

    with pytest.raises(OrderLifecycleControlApiError, match="回傳格式不正確"):
        client.query("C-1")

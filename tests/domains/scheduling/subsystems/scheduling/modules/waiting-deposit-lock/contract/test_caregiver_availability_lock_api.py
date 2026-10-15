"""
File: test_caregiver_availability_lock_api.py
Description: 驗證等待訂金檔期鎖 API 將業務阻擋轉成可操作的 typed error。
"""

import pytest
from fastapi import HTTPException

from api.routes.caregiver_availability_locks import _waiting_lock_value_error
from shared_kernel.identities import CorrelationId


def test_waiting_lock_conflict_is_a_typed_conflict_error():
    with pytest.raises(HTTPException) as raised:
        raise _waiting_lock_value_error(
            ValueError('{"conflicts":[{"staff_id":8892}]}'),
            CorrelationId("wp56-occupancy-conflict"),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["category"] == "conflict"
    assert raised.value.detail["error"]["code"] == "waiting_lock_conflict"


def test_missing_finance_projection_reports_confirmation_blocker_without_assuming_zero():
    error = _waiting_lock_value_error(
        ValueError("client finance deposit settlement projection missing"),
        CorrelationId("release-finance-proof-missing"),
    )
    assert error.status_code == 409
    assert error.detail["error"]["code"] == "deposit_settlement_confirmation_required"
    assert "不能釋放檔期" in error.detail["error"]["message"]


def test_waiting_lock_missing_confirmed_dates_blocker_is_actionable():
    with pytest.raises(HTTPException) as raised:
        raise _waiting_lock_value_error(
            ValueError("current confirmed service dates are required"),
            CorrelationId("waiting-lock-confirmed-dates-required"),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["code"] == "confirmed_service_dates_required"
    assert raised.value.detail["error"]["domain_blockers"] == [
        "confirmed_service_dates_required"
    ]


def test_waiting_lock_rejects_mismatched_confirmed_service_dates():
    with pytest.raises(HTTPException) as raised:
        raise _waiting_lock_value_error(
            ValueError("current confirmed service dates mismatch"),
            CorrelationId("waiting-lock-confirmed-dates-mismatch"),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["error"]["code"] == "confirmed_service_dates_mismatch"


@pytest.mark.parametrize("operation", ["preview", "apply"])
def test_release_routes_accept_positive_integer_url_ids(monkeypatch, operation):
    from fastapi import FastAPI, Response
    from fastapi.testclient import TestClient
    from api.routes import caregiver_availability_locks as routes
    from subsystems.access.authentication_session import AdminPrincipal

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.require_system_admin] = lambda: AdminPrincipal(
        None, "operator", "UI acceptance", "system_admin"
    )
    observed = []
    monkeypatch.setattr(routes, "_call_waiting_lock", lambda *args: observed.append(args) or Response(status_code=204))
    path = f"/api/v1/orders/CASE/matching-plans/1/waiting-deposit-locks/2/release/{operation}"
    body = {"preview_fingerprint": "a" * 64, "reason": "Customer requested replacement"} if operation == "apply" else None
    headers = {"Idempotency-Key": "release-test", "X-Correlation-Id": "release-test"}
    client = TestClient(app)
    assert client.post(path, json=body, headers=headers).status_code == 204
    assert len(observed) == 1
    assert client.post(path.replace("matching-plans/1/", "matching-plans/invalid/"), json=body, headers=headers).status_code == 422
    assert len(observed) == 1

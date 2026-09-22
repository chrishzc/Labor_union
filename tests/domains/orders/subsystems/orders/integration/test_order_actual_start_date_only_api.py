"""HTTP contract for saving Actual Start before formal downstream roots exist."""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_actual_start import get_actual_start_application
from api.routes.order_actual_start import ActualStartApplyBody, router
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.actual_start_workflow import (
    ActualStartDateOnlyApplyRequest,
    ActualStartDateOnlyPreview,
    ActualStartDateOnlyResult,
    ActualStartQueryFacts,
)


_FINGERPRINT = PreviewFingerprint("a" * 64)


class _Application:
    def query(self, case_no):
        return ActualStartQueryFacts(
            case_no,
            None,
            date(2026, 9, 1),
            False,
            7,
            None,
            None,
            None,
            None,
            False,
            False,
        )

    def preview(self, case_no, new_actual_start_date):
        return ActualStartDateOnlyPreview(
            case_no,
            None,
            new_actual_start_date,
            7,
            None,
            None,
            None,
            None,
            _FINGERPRINT,
        )

    def apply(self, request):
        assert isinstance(request, ActualStartDateOnlyApplyRequest)
        return ActualStartDateOnlyResult(
            request.case_no,
            request.new_actual_start_date,
            8,
            None,
            None,
            None,
            None,
            request.preview_fingerprint,
            True,
        )


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
        id=1,
        username="admin",
        display_name="Administrator",
        role="system_admin",
    )
    app.dependency_overrides[get_actual_start_application] = _Application
    return TestClient(app)


def test_date_only_http_flow_does_not_invent_downstream_versions_or_reason():
    client = _client()

    query = client.get("/api/v1/orders/CASE-DATE/actual-start")
    preview = client.post(
        "/api/v1/orders/CASE-DATE/actual-start/preview",
        json={"new_actual_start_date": "2026-09-02"},
        headers={"X-Correlation-ID": "date-only-preview"},
    )
    apply = client.post(
        "/api/v1/orders/CASE-DATE/actual-start/apply",
        json={
            "operation": "date_only",
            "new_actual_start_date": "2026-09-02",
            "expected_order_version": 7,
            "preview_fingerprint": "a" * 64,
        },
        headers={
            "Idempotency-Key": "date-only-apply",
            "X-Correlation-ID": "date-only-apply",
        },
    )

    assert query.status_code == 200
    assert query.json()["data"] == {
        "case_no": "CASE-DATE",
        "current_actual_start_date": None,
        "planned_start_date": "2026-09-01",
        "service_data_locked": False,
        "order_version": 7,
        "scheduling_version": None,
        "scheduling_generation": None,
        "client_finance_version": None,
        "payroll_version": None,
        "has_formal_assignments": False,
    }
    assert preview.status_code == 200
    assert preview.json()["data"]["operation"] == "date_only"
    assert preview.json()["data"]["client_finance_version"] is None
    assert preview.json()["data"]["payroll_version"] is None
    assert apply.status_code == 200
    assert apply.json()["data"] == {
        "operation": "date_only",
        "case_no": "CASE-DATE",
        "actual_start_date": "2026-09-02",
        "order_version": 8,
        "scheduling_version": None,
        "scheduling_generation": None,
        "client_finance_version": None,
        "payroll_version": None,
        "preview_fingerprint": "a" * 64,
        "changed": True,
    }


def test_date_only_http_request_rejects_downstream_versions():
    response = _client().post(
        "/api/v1/orders/CASE-DATE/actual-start/apply",
        json={
            "operation": "date_only",
            "new_actual_start_date": "2026-09-02",
            "expected_order_version": 7,
            "expected_scheduling_version": 0,
            "preview_fingerprint": "a" * 64,
        },
        headers={
            "Idempotency-Key": "date-only-invalid",
            "X-Correlation-ID": "date-only-invalid",
        },
    )

    assert response.status_code == 422


def test_reschedule_apply_contract_has_only_orders_and_scheduling_versions():
    payload = {
        "operation": "reschedule",
        "new_actual_start_date": "2026-09-02",
        "expected_order_version": 7,
        "expected_scheduling_version": 4,
        "preview_fingerprint": "a" * 64,
        "reason": "確認實際開始日",
    }

    assert ActualStartApplyBody.model_validate(payload).model_dump(
        mode="json", exclude_none=True
    ) == payload
    with pytest.raises(ValidationError):
        ActualStartApplyBody.model_validate(
            {**payload, "expected_payroll_version": 3}
        )

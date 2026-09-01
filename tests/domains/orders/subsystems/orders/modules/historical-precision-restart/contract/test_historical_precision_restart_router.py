from datetime import date
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.historical_service_accounting import get_historical_precision_restart_workflow
from api.routes.historical_service_accounting import router
from domains.orders.historical_precision_restart import (
    HistoricalPrecisionRestartAssignmentFacts,
    HistoricalPrecisionRestartFacts,
    HistoricalPrecisionRestartIntent,
    build_historical_precision_restart_candidate,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId
from subsystems.orders.historical_precision_restart_workflow import (
    HistoricalPrecisionRestartError,
    HistoricalPrecisionRestartPreview,
    HistoricalPrecisionRestartReceipt,
)


def _facts(status=OrderLifecycleStatus.HISTORICAL_UNSERVED):
    return HistoricalPrecisionRestartFacts(
        "CASE-19", status, 4, 3, 1, 5, 6, 0,
        date(2026, 5, 19), None, 1, 8, False,
        (HistoricalPrecisionRestartAssignmentFacts("assignment:19", 19, 3, "月嫂甲", 1),),
        current_assignment_ids=(19,),
        adoption_receipt_id=19,
        adoption_source_identity="historical-source:19",
    )


def _candidate(status=OrderLifecycleStatus.HISTORICAL_UNSERVED):
    domain = build_historical_precision_restart_candidate(
        _facts(status), HistoricalPrecisionRestartIntent("CASE-19")
    )
    fingerprint = fingerprint_payload({"preview": domain.fingerprint.value})
    return HistoricalPrecisionRestartPreview(
        domain, None, None, SimpleNamespace(), fingerprint,
    )


class _Workflow:
    def __init__(self, status=OrderLifecycleStatus.HISTORICAL_UNSERVED):
        self.status = status
        self.preview_value = _candidate(status)

    def query(self, case_no):
        return self.preview_value

    def preview(self, intent):
        if self.status in {
            OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
            OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
        }:
            raise _typed(ErrorCategory.DOMAIN_BLOCKED, "historical_precision_restart_not_eligible")
        return self.preview_value

    def apply(self, request):
        if request.expected_order_version != 4:
            raise _typed(ErrorCategory.CONFLICT, "historical_precision_restart_candidate_stale")
        return HistoricalPrecisionRestartReceipt(
            "CASE-19", "訂單成立", 5, 4, 2, 5, 6, 0,
            self.preview_value.fingerprint,
        )


def _typed(category, code):
    return HistoricalPrecisionRestartError(
        TypedError(category, code, "重啟正常流程失敗。", CorrelationId("precision-contract"), domain_blockers=(code,) if category is ErrorCategory.DOMAIN_BLOCKED else ())
    )


def _client(workflow=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="operator")
    app.dependency_overrides[get_historical_precision_restart_workflow] = lambda: workflow or _Workflow()
    return TestClient(app)


def test_query_preview_apply_restart_only_happy_path():
    client = _client()
    query = client.get("/api/v1/orders/CASE-19/historical-service-accounting/precision-restart")
    assert query.status_code == 200
    assert query.json()["data"]["assignments"][0]["staff_name"] == "月嫂甲"

    preview = client.post(
        "/api/v1/orders/CASE-19/historical-service-accounting/precision-restart/preview",
        headers={"X-Correlation-ID": "precision-preview"},
        json={},
    )
    assert preview.status_code == 200
    value = preview.json()["data"]
    assert value["target_status"] == "訂單成立"
    assert value["actual_end_date"] is None
    assert value["official_service_dates"] == []
    assert value["client_finance_resulting_version"] == 5
    assert value["payroll_resulting_version"] == 6

    apply = client.post(
        "/api/v1/orders/CASE-19/historical-service-accounting/precision-restart/apply",
        headers={"X-Correlation-ID": "precision-apply", "Idempotency-Key": "precision:19"},
        json={
            "expected_order_version": 4,
            "expected_scheduling_version": 3,
            "expected_historical_day_revision": 0,
            "expected_confirmed_service_date_version": None,
            "preview_fingerprint": value["preview_fingerprint"],
            "reason": "從訂單工作台重啟正常流程",
        },
    )
    assert apply.status_code == 200
    assert apply.json()["data"]["lifecycle_status"] == "訂單成立"


def test_completed_and_stale_are_typed_409():
    completed = _client(_Workflow(OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED)).post(
        "/api/v1/orders/CASE-19/historical-service-accounting/precision-restart/preview",
        json={},
    )
    assert completed.status_code == 409
    assert completed.json()["detail"]["error"]["code"] == "historical_precision_restart_not_eligible"

    preview = _candidate()
    stale = _client().post(
        "/api/v1/orders/CASE-19/historical-service-accounting/precision-restart/apply",
        headers={"X-Correlation-ID": "precision-stale", "Idempotency-Key": "precision:stale"},
        json={
            "expected_order_version": 99,
            "expected_scheduling_version": 3,
            "expected_historical_day_revision": 0,
            "expected_confirmed_service_date_version": None,
            "preview_fingerprint": preview.fingerprint.value,
            "reason": "從訂單工作台重啟正常流程",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"]["code"] == "historical_precision_restart_candidate_stale"


def test_preview_rejects_legacy_date_payload():
    response = _client().post(
        "/api/v1/orders/CASE-19/historical-service-accounting/precision-restart/preview",
        json={"caregivers": [{"staff_id": 3, "service_dates": ["2026-05-19"]}]},
    )

    assert response.status_code == 422

"""HTTP contract for one-screen historical service accounting."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.historical_service_accounting import get_historical_service_accounting_workflow
from api.routes.historical_service_accounting import router
from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, rate_snapshot
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalServiceAccountingFacts,
    HistoricalServiceAccountingReceipt,
    HistoricalServiceAccountingWorkflow,
)


class _Repository:
    def __init__(self):
        self.facts = HistoricalServiceAccountingFacts(
            "CASE-19",
            OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
            3,
            19,
            "historical-source:19",
            0,
            2,
            4,
            40,
            9,
            MoneyNTD(4_000),
            "一般市民",
            (
                HistoricalServiceAccountingAssignmentFacts(
                    "assignment:19",
                    3,
                    "月嫂甲",
                    rate_snapshot("assignment:19", "policy:1", PayrollPolicyKind.CITIZEN),
                    MoneyNTD(0),
                ),
            ),
            "client-policy:case-19",
            MoneyNTD(300),
        )

    def load(self, case_no, *, for_update):
        assert case_no == "CASE-19"
        return self.facts

    def find_receipt(self, key):
        return None

    def persist(self, request, candidate):
        return HistoricalServiceAccountingReceipt(
            "CASE-19",
            1,
            3,
            5,
            candidate.service_days.total_actual_service_days,
            candidate.client_finance.total_receivable.amount,
            candidate.payroll.total_payable.amount,
            candidate.fingerprint,
        )


class _Unit:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


def _client():
    app = FastAPI()
    app.include_router(router)
    workflow = HistoricalServiceAccountingWorkflow(_Repository(), _Unit)
    app.dependency_overrides[require_system_admin] = lambda: type("Principal", (), {"username": "operator"})()
    app.dependency_overrides[get_historical_service_accounting_workflow] = lambda: workflow
    return TestClient(app)


def test_query_preview_apply_expose_server_owned_count_accounting():
    client = _client()
    query = client.get("/api/v1/orders/CASE-19/historical-service-accounting")
    assert query.status_code == 200
    assert query.json()["data"]["assignments"][0]["staff_name"] == "月嫂甲"

    body = {
        "caregivers": [
            {"assignment_identity": "assignment:19", "staff_id": 3, "actual_service_days": 3}
        ]
    }
    preview = client.post(
        "/api/v1/orders/CASE-19/historical-service-accounting/preview",
        headers={"X-Correlation-ID": "historical-days-preview"},
        json=body,
    )
    assert preview.status_code == 200
    candidate = preview.json()["data"]
    assert candidate["total_actual_service_days"] == 3
    assert candidate["historical_double_pay_days"] == 0
    assert candidate["staff_obligation_amount_ntd"] == 8_400
    assert candidate["client_obligation_amount_ntd"] == 8_400

    apply = client.post(
        "/api/v1/orders/CASE-19/historical-service-accounting/apply",
        headers={"X-Correlation-ID": "historical-days-apply", "Idempotency-Key": "historical-days:19"},
        json={
            **body,
            "expected_lifecycle_version": 3,
            "expected_historical_day_revision": 0,
            "expected_client_finance_version": 2,
            "expected_payroll_version": 4,
            "preview_fingerprint": candidate["preview_fingerprint"],
            "reason": "核對舊系統實際服務天數",
        },
    )
    assert apply.status_code == 200
    assert apply.json()["data"]["resulting_historical_day_revision"] == 1


def test_preview_rejects_missing_assignment_day_count():
    response = _client().post(
        "/api/v1/orders/CASE-19/historical-service-accounting/preview",
        json={"caregivers": [{"assignment_identity": "assignment:20", "staff_id": 3, "actual_service_days": 3}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "historical_actual_service_days_assignment_mismatch"

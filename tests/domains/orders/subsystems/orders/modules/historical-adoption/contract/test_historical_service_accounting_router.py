"""HTTP contract for one-screen historical service accounting."""

from datetime import date
from dataclasses import replace
from decimal import Decimal

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
    HistoricalServiceAccountingBaseline,
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
            date(2026, 4, 20),
            None,
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
            candidate.facts.client_finance_version,
            candidate.facts.payroll_version,
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
    receipt = apply.json()["data"]
    assert receipt["resulting_historical_day_revision"] == 1
    assert receipt["resulting_client_finance_version"] == 2
    assert receipt["resulting_payroll_version"] == 4


def test_preview_rejects_missing_assignment_day_count():
    response = _client().post(
        "/api/v1/orders/CASE-19/historical-service-accounting/preview",
        json={"caregivers": [{"assignment_identity": "assignment:20", "staff_id": 3, "actual_service_days": 3}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "historical_actual_service_days_assignment_mismatch"


def test_completed_service_fact_stale_apply_returns_typed_conflict():
    client = _client()
    calls = []

    class Workflow:
        def apply_attribution(self, intent, fingerprint, **kwargs):
            assert intent.service_facts[0].service_hours_per_day == 8
            calls.append(intent)
            raise ValueError("historical_attribution_preview_stale")

    client.app.dependency_overrides[get_historical_service_accounting_workflow] = lambda: Workflow()
    response = client.post(
        "/api/v1/orders/CASE-19/historical-service-accounting/attribution/apply",
        headers={"X-Correlation-ID": "service-fact-stale", "Idempotency-Key": "service-fact-stale"},
        json={
            "caregivers": [{"staff_id": 3, "actual_service_days": 3}],
            "evidence": "逐人來源證據", "reason": "核對服務時段",
            "preview_fingerprint": "a" * 64,
            "service_facts": [{
                "assignment_identity": "assignment:19", "staff_id": 3,
                "actual_start_date": "2026-03-01", "actual_end_date": "2026-04-20",
                "service_start_time": "08:00", "service_end_time": "16:00",
                "service_hours_per_day": "8", "service_end_day_offset": 0,
            }],
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["category"] == "conflict"
    assert response.json()["detail"]["error"]["code"] == "historical_attribution_preview_stale"
    assert len(calls) == 1


def _partial_service_fact_body():
    return {
        "caregivers": [], "evidence": "已確認個別服務時段",
        "service_facts": [{
            "assignment_identity": "assignment:20", "staff_id": 4,
            "actual_start_date": "2026-03-01", "actual_end_date": "2026-04-20",
            "service_start_time": "08:00", "service_end_time": "16:00",
            "service_hours_per_day": "8", "service_end_day_offset": 0,
        }],
    }


def test_partial_service_fact_preview_accepts_unknown_days_and_keeps_amounts_pending():
    from subsystems.client_finance.pricing_configuration import HistoricalPersonPricing, HistoricalRepricingPlan
    client = _client()
    repository = _Repository()
    known = replace(repository.facts.assignments[0], actual_service_days=3, actual_service_hours=Decimal("27"))
    unknown = replace(known, assignment_identity="assignment:20", staff_id=4, staff_name="月嫂乙",
                      rate_snapshot=replace(known.rate_snapshot, assignment_identity="assignment:20"),
                      actual_service_days=None, actual_service_hours=None)
    repository.facts = replace(repository.facts, assignments=(known, unknown), historical_day_revision=1,
        service_baseline=HistoricalServiceAccountingBaseline(41, 40, Decimal("360"), 4000, 99000, 108000))

    def preview_volume(case_no, before, after, *, for_update):
        return HistoricalRepricingPlan(case_no, 2, 4, (), (), persons=(
            HistoricalPersonPricing("assignment:20", 4, "月嫂乙", None, None, None, None),
        ), pending=("historical_pricing_total_service_hours_required",))

    repository.preview_service_volume = preview_volume
    workflow = HistoricalServiceAccountingWorkflow(repository, _Unit)
    client.app.dependency_overrides[get_historical_service_accounting_workflow] = lambda: workflow
    response = client.post("/api/v1/orders/CASE-19/historical-service-accounting/attribution/preview",
                           json=_partial_service_fact_body())
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["service_facts"][0]["after"]["actual_start_date"] == "2026-03-01"
    assert result["caregivers"][0]["actual_service_days"] is None
    assert result["caregivers"][0]["entitlement_ntd"] is None
    assert result["client_delta_ntd"] is None
    assert result["subsidy_delta_ntd"] is None


def test_partial_service_fact_without_saved_baseline_returns_typed_domain_blocker():
    client = _client()

    class Workflow:
        def preview_attribution(self, intent):
            assert intent.days_by_staff == ()
            raise ValueError("historical_completed_service_partial_baseline_required")

    client.app.dependency_overrides[get_historical_service_accounting_workflow] = lambda: Workflow()
    response = client.post("/api/v1/orders/CASE-19/historical-service-accounting/attribution/preview",
                           json=_partial_service_fact_body())
    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == "historical_completed_service_partial_baseline_required"

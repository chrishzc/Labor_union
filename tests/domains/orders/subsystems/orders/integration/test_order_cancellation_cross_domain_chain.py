"""Orders cancellation Preview/Apply cross-owner persistence contract."""

from datetime import date, datetime, time
from dataclasses import replace

import pytest
from domains.client_finance.obligation_planning import (
    ClientFinanceDirection,
    ClientFinanceTermsSourceFacts,
    ClientPaymentTerms,
    ExistingClientStageObligation,
)
from domains.client_finance.reconciliation import PaymentStage
from domains.orders.cancellation import CancellationAssignmentFacts, CancellationOrderFacts, CancellationSchedulingFacts, ConfirmedServiceDay
from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import AssignmentIdentityResolution
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.cancellation_workflow import CancellationWorkflowError, CancellationWorkflowFacts, OrderCancellationApplyRequest, OrderCancellationWorkflow, OrderCancellationReceipt
from subsystems.orders.terms_workflow import CommandClaimState, SchedulingReplacementResult
from subsystems.payroll.terms_impact import PayrollTermsSourceFacts, SourceAssignmentPayrollTerms


class _UnitOfWork:
    def __init__(self, repository): self.repository = repository
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): self.repository.commits += 1


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.persisted = []
        self.commits = 0

    def load_for_preview(self, *_): return self.facts
    def preflight_impacted_staff_ids(self, *_): return (7,)
    def load_for_apply(self, *_): return self.facts
    def claim_command(self, *_): return CommandClaimState.CREATED if self.receipt is None else CommandClaimState.MATCHED
    def find_receipt(self, *_args, **_kwargs): return self.receipt
    def append_cancellation_event(self, *_): self.persisted.append("event"); return 11
    def cancel_waiting_deposit_lock(self, *_): self.persisted.append("lock")
    def replace_scheduling_generation(self, command):
        self.persisted.append(command)
        return SchedulingReplacementResult(8, 3, 12, 13, AssignmentIdentityResolution({"CASE-1:g2:a1": 8}))
    def persist_client_finance_impact(self, command): self.persisted.append(command)
    def persist_payroll_impact(self, command): self.persisted.append(command)
    def activate_cancellation_control(self, *_): self.persisted.append("control"); return 14
    def persist_cancellation_lifecycle(self, *_): self.persisted.append("lifecycle"); return 15
    def update_cancelled_order(self, command): self.persisted.append(command)
    def save_receipt(self, command): self.persisted.append(command); self.receipt = command.stored_receipt


def _facts():
    order = CancellationOrderFacts("CASE-1", 4, 2, 8, date(2026, 8, 1), True, False)
    scheduling = CancellationSchedulingFacts("CASE-1", 2, 1, (CancellationAssignmentFacts(1, 7, 1, (date(2026, 8, 1), date(2026, 8, 2))),))
    terms = OrderTerms(date(2026, 8, 1), 2, 8, MoneyNTD(1000), ServiceTimeTerms(time(8), time(17), 0))
    finance = ClientFinanceTermsSourceFacts("CASE-1", 5, ClientPaymentTerms(0, MoneyNTD(100), date(2026, 7, 1), date(2026, 8, 1), None), (), ())
    payroll = PayrollTermsSourceFacts("CASE-1", 3, (SourceAssignmentPayrollTerms(1, 7, "policy-v1", PayrollPolicyKind.CITIZEN),), (), date(2026, 8, 31))
    lifecycle = OrderLifecycleRootFacts("CASE-1", OrderLifecycleStatus.IN_SERVICE, True, date(2026, 8, 1), True, False, False)
    return CancellationWorkflowFacts(order, terms, scheduling, finance, payroll, lifecycle)


def _workflow(repository):
    return OrderCancellationWorkflow(
        repository,
        lambda: _UnitOfWork(repository),
        FixedBusinessClock(datetime(2026, 8, 2, 9, 0).astimezone()),
    )


def _request(preview):
    return OrderCancellationApplyRequest("CASE-1", (ConfirmedServiceDay(date(2026, 8, 1), 7),), ExpectedVersion(4), ExpectedVersion(2), ExpectedVersion(5), ExpectedVersion(3), preview.fingerprint, IdempotencyKey("cancel-1"), ActorContext("admin"), "client requested cancellation", CorrelationId("corr-1"))


def test_cancellation_preview_apply_persists_canonical_cross_domain_chain():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", (ConfirmedServiceDay(date(2026, 8, 1), 7),))
    receipt = workflow.apply(_request(preview))
    assert receipt.order_version == 5
    assert receipt.scheduling_version == 3
    assert receipt.client_finance_version == 6
    assert receipt.payroll_version == 4
    assert receipt.lifecycle_status is OrderLifecycleStatus.CANCELLED
    assert repository.persisted[-1].stored_receipt.receipt == receipt


def test_cancellation_apply_replays_matching_receipt_without_new_writes():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", (ConfirmedServiceDay(date(2026, 8, 1), 7),))
    request = _request(preview)
    first = workflow.apply(request)
    write_count = len(repository.persisted)
    assert workflow.apply(request) == first
    assert len(repository.persisted) == write_count


def test_four_day_twins_cancellation_credits_posted_deposit_and_first_payment():
    service_dates = (
        date(2026, 7, 30),
        date(2026, 7, 31),
        date(2026, 8, 1),
        date(2026, 8, 2),
    )
    order = CancellationOrderFacts("CASE-1", 4, 20, 8, service_dates[0], True, False)
    scheduling = CancellationSchedulingFacts(
        "CASE-1",
        2,
        1,
        (CancellationAssignmentFacts(1, 7, 1, service_dates),),
    )
    terms = OrderTerms(
        service_dates[0],
        20,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(time(8), time(17), 0),
    )
    payment_terms = ClientPaymentTerms(
        5,
        MoneyNTD(450),
        date(2026, 7, 1),
        date(2026, 8, 1),
        None,
    )
    finance = ClientFinanceTermsSourceFacts(
        "CASE-1",
        5,
        payment_terms,
        (),
        (
            ExistingClientStageObligation(
                "client-obligation:CASE-1:deposit",
                PaymentStage.DEPOSIT,
                MoneyNTD(18_000),
                MoneyNTD(18_000),
                payment_terms.deposit_due_date,
                True,
            ),
            ExistingClientStageObligation(
                "client-obligation:CASE-1:first",
                PaymentStage.FIRST,
                MoneyNTD(54_000),
                MoneyNTD(54_000),
                payment_terms.first_payment_due_date,
                True,
            ),
        ),
        identity_status="一般市民",
    )
    payroll = PayrollTermsSourceFacts(
        "CASE-1",
        3,
        (SourceAssignmentPayrollTerms(1, 7, "twins-v1", PayrollPolicyKind.TWINS),),
        (),
        date(2026, 8, 31),
    )
    lifecycle = OrderLifecycleRootFacts(
        "CASE-1",
        OrderLifecycleStatus.IN_SERVICE,
        True,
        service_dates[0],
        True,
        False,
        False,
    )
    repository = _Repository(
        CancellationWorkflowFacts(order, terms, scheduling, finance, payroll, lifecycle)
    )

    preview = _workflow(repository).preview(
        "CASE-1",
        tuple(ConfirmedServiceDay(value, 7) for value in service_dates),
    )

    assert sum(
        item.amount.amount for item in preview.client_finance_impact.stage_plans
    ) == 4 * 8 * 450
    refunds = tuple(
        item
        for item in preview.client_finance_impact.actions
        if item.direction is ClientFinanceDirection.REFUND_DUE
    )
    assert sum(item.direction_amount_ntd for item in refunds) == 57_600
    assert preview.payroll_impact.payroll.total_payable.amount == 4 * 8 * 450
    assert preview.client_finance_impact.subsidy_return_plan is not None
    assert preview.client_finance_impact.subsidy_return_plan.amount == MoneyNTD(14_400)
    assert preview.client_finance_impact.subsidy_return_plan.due_date == date(2026, 10, 15)


@pytest.mark.parametrize("hours", [0, 0.0, 8, 16.0, 7.5])
def test_cancellation_receipt_preserves_exact_numeric_hours(hours):
    from dataclasses import asdict
    from decimal import Decimal
    import json
    from infrastructure.mysql.order_cancellation_repository import _receipt_payload, _stored_receipt

    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", (ConfirmedServiceDay(date(2026, 8, 1), 7),))
    receipt = replace(workflow.apply(_request(preview)), official_service_hours=hours)
    row = asdict(receipt)
    row.update(
        lifecycle_status=receipt.lifecycle_status.value,
        preview_fingerprint=receipt.preview_fingerprint.value,
        command_fingerprint="b" * 64,
        official_service_hours=Decimal(str(hours)),
        result_snapshot=json.dumps(_receipt_payload(receipt)),
    )
    assert _stored_receipt(row).receipt == receipt
    row["official_service_hours"] = Decimal(str(hours)) + Decimal("0.5")
    with pytest.raises(ValueError, match="receipt_integrity_violation"):
        _stored_receipt(row)


@pytest.mark.parametrize("hours", [True, -1, "8", 0.25, float("nan"), float("inf")])
def test_cancellation_receipt_rejects_invalid_hour_values(hours):
    from infrastructure.mysql.order_cancellation_repository import _required_service_hours

    with pytest.raises(ValueError, match="receipt_integrity_violation"):
        _required_service_hours({"hours": hours}, "hours")


@pytest.mark.parametrize("scheduling_present", [False, True])
def test_unserved_cancellation_without_financial_roots_keeps_explicit_absence(scheduling_present):
    facts = _facts()
    facts = replace(
        facts,
        order=replace(facts.order, service_started=False),
        scheduling=CancellationSchedulingFacts("CASE-1", 2 if scheduling_present else None, 1 if scheduling_present else None, ()),
        client_finance=None, payroll=None,
        lifecycle=replace(facts.lifecycle, current_status=OrderLifecycleStatus.ESTABLISHED),
    )
    repository = _Repository(facts)
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ())
    request = replace(_request(preview), confirmed_service_days=(), expected_scheduling_version=ExpectedVersion(2) if scheduling_present else None, expected_client_finance_version=None, expected_payroll_version=None)
    receipt = workflow.apply(request)
    assert receipt.official_service_day_count == 0
    assert receipt.official_service_hours == 0
    assert receipt.client_finance_version is None
    assert receipt.payroll_version is None
    assert receipt.scheduling_version == (3 if scheduling_present else None)
    assert repository.commits == 1
    assert "lock" in repository.persisted and "control" in repository.persisted and "lifecycle" in repository.persisted
    assert repository.persisted[-1].scheduling_receipt_id == (13 if scheduling_present else None)
    assert not any(type(item).__name__ in {"ClientFinanceImpactPersistenceCommand", "PayrollImpactPersistenceCommand"} for item in repository.persisted)
    before = list(repository.persisted)
    assert workflow.apply(request) == receipt
    assert repository.persisted == before


@pytest.mark.parametrize("owner", ["scheduling", "client_finance", "payroll"])
def test_cancellation_rejects_owner_created_after_absent_owner_preview(owner):
    initialized = _facts()
    absent = replace(initialized, order=replace(initialized.order, service_started=False), scheduling=CancellationSchedulingFacts("CASE-1", None, None, ()), client_finance=None, payroll=None)
    repository = _Repository(absent)
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ())
    request = replace(_request(preview), confirmed_service_days=(), expected_scheduling_version=None, expected_client_finance_version=None, expected_payroll_version=None)
    repository.facts = replace(absent, **{owner: getattr(initialized, owner)})
    with pytest.raises(CancellationWorkflowError) as failure:
        workflow.apply(request)
    assert failure.value.error.category.value == "conflict"
    assert repository.persisted == []
    assert repository.commits == 0


def test_deposit_refund_without_assignment_does_not_require_payroll_root():
    facts = _facts()
    deposit = ExistingClientStageObligation("deposit-existing", PaymentStage.DEPOSIT, MoneyNTD(800), MoneyNTD(800), date(2026, 7, 1), True)
    facts = replace(facts, order=replace(facts.order, service_started=False), scheduling=replace(facts.scheduling, assignments=()), client_finance=replace(facts.client_finance, existing_obligations=(deposit,)), payroll=None)
    repository = _Repository(facts)
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ())
    assert any(action.direction is ClientFinanceDirection.REFUND_DUE and action.direction_amount_ntd == 800 for action in preview.client_finance_impact.actions)
    request = replace(_request(preview), confirmed_service_days=(), expected_payroll_version=None)
    receipt = workflow.apply(request)
    assert receipt.client_finance_version == 6
    assert receipt.payroll_version is None
    assert not any(type(item).__name__ == "PayrollImpactPersistenceCommand" for item in repository.persisted)


def test_nullable_cancellation_receipt_roundtrip_and_integrity():
    from dataclasses import asdict
    import json
    from infrastructure.mysql.order_cancellation_repository import _receipt_payload, _stored_receipt
    receipt = OrderCancellationReceipt("CASE-1", 5, None, None, None, None, OrderLifecycleStatus.CANCELLED, None, 0, 0, (), (), PreviewFingerprint("a" * 64))
    row = asdict(receipt)
    row.update(lifecycle_status=receipt.lifecycle_status.value, preview_fingerprint=receipt.preview_fingerprint.value, command_fingerprint="b" * 64, result_snapshot=json.dumps(_receipt_payload(receipt)))
    assert _stored_receipt(row).receipt == receipt
    row["payroll_version"] = 0
    with pytest.raises(ValueError, match="receipt_integrity_violation"):
        _stored_receipt(row)



def test_cancellation_http_query_preview_apply_and_receipt_with_absent_owners():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.admin_auth import require_system_admin
    from api.dependencies.order_cancellation import OrderCancellationApplication, get_order_cancellation_application
    from api.routes.order_cancellation import router
    from subsystems.access.authentication_session import AdminPrincipal
    facts = _facts()
    facts = replace(facts, order=replace(facts.order, service_started=False), scheduling=CancellationSchedulingFacts("CASE-1", None, None, ()), client_finance=None, payroll=None)
    repository = _Repository(facts)
    repository.list_caregiver_options = lambda _: ()
    application = OrderCancellationApplication(repository, _workflow(repository))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(id=1, username="admin", display_name="Admin", role="system_admin")
    app.dependency_overrides[get_order_cancellation_application] = lambda: application
    client = TestClient(app)
    query = client.get("/api/v1/orders/CASE-1/cancellation")
    assert query.status_code == 200
    assert query.json()["data"]["scheduling_version"] is None
    response = client.post("/api/v1/orders/CASE-1/cancellation/preview", json={"confirmed_service_days": []})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["scheduling"] is None and data["client_finance_impact"] is None and data["payroll_impact"] is None
    body = {"confirmed_service_days": [], "expected_order_version": 4, "expected_scheduling_version": None, "expected_client_finance_version": None, "expected_payroll_version": None, "preview_fingerprint": data["preview_fingerprint"], "reason": "客戶確認取消"}
    headers = {"Idempotency-Key": "cancel-null-http", "X-Correlation-ID": "cancel-null-http"}
    response = client.post("/api/v1/orders/CASE-1/cancellation/apply", json=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["payroll_version"] is None
    receipt = client.get("/api/v1/orders/CASE-1/cancellation/receipt", headers={"Idempotency-Key": "cancel-null-http"})
    assert receipt.json()["data"] == response.json()["data"]
    del body["expected_client_finance_version"]
    assert client.post("/api/v1/orders/CASE-1/cancellation/apply", json=body, headers=headers).status_code == 422

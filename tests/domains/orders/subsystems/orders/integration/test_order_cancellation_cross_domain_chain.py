"""Orders cancellation Preview/Apply cross-owner persistence contract."""

from datetime import date, datetime, time
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from domains.bootstrap.case_architecture import ClientPaymentTermsRootFacts
from domains.client_finance.obligation_planning import (
    ClientFinanceDirection,
    ClientFinanceTermsSourceFacts,
    ClientObligationActionKind,
    ClientPaymentTerms,
    ExistingClientStageObligation,
    PriorClientCancellationBalance,
)
from domains.client_finance.reconciliation import PaymentStage
from domains.orders.cancellation import CancellationAssignmentFacts, CancellationOrderFacts, CancellationSchedulingFacts, ConfirmedServiceDay
from domains.orders.historical_unserved_correction import (
    HistoricalCancellationSettlement,
    HistoricalUnservedCorrectionIntent,
    HistoricalUnservedEvidence,
)
from domains.orders.lifecycle import OrderEstablishmentEvidence, OrderLifecycleRootFacts, OrderLifecycleStatus
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import AssignmentIdentityResolution
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.cancellation_workflow import CancellationWorkflowError, CancellationWorkflowFacts, OrderCancellationApplyRequest, OrderCancellationWorkflow, OrderCancellationReceipt
from subsystems.orders.terms_workflow import CommandClaimState, PayrollImpactPersistenceCommand, SchedulingReplacementResult
from subsystems.payroll.terms_impact import PayrollTermsActionKind, PayrollTermsSourceFacts, SourceAssignmentPayrollTerms


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

    def load_for_preview(self, *_, allow_missing_payroll_rates=False): return self.facts
    def preflight_impacted_staff_ids(self, *_): return (7,)
    def load_for_apply(self, *_, allow_missing_payroll_rates=False): return self.facts
    def claim_command(self, *_): return CommandClaimState.CREATED if self.receipt is None else CommandClaimState.MATCHED
    def find_receipt(self, *_args, **_kwargs): return self.receipt
    def append_cancellation_event(self, *_): self.persisted.append("event"); return 11
    def cancel_waiting_deposit_lock(self, *_): self.persisted.append("lock")
    def replace_scheduling_generation(self, command):
        self.persisted.append(command)
        return SchedulingReplacementResult(8, 3, 12, 13, AssignmentIdentityResolution({"CASE-1:g2:a1": 8}))
    def persist_client_finance_impact(self, command): self.persisted.append(command)
    def initialize_cancellation_client_finance(self, request, terms, event_id): self.persisted.append(("initial_finance", terms, event_id))
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
    return OrderCancellationApplyRequest("CASE-1", (), ExpectedVersion(4), ExpectedVersion(2), ExpectedVersion(5), ExpectedVersion(3), preview.fingerprint, IdempotencyKey("cancel-1"), ActorContext("admin"), "client requested cancellation", CorrelationId("corr-1"))


def test_cancellation_preview_apply_persists_canonical_cross_domain_chain():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ())
    assert repository.persisted == []
    receipt = workflow.apply(_request(preview))
    assert receipt.order_version == 5
    assert receipt.scheduling_version == 3
    assert receipt.client_finance_version == 6
    assert receipt.payroll_version == 4
    assert receipt.lifecycle_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    assert receipt.official_service_hours == 0
    payroll, = (item for item in repository.persisted if isinstance(item, PayrollImpactPersistenceCommand))
    assert payroll.candidate.payroll.total_payable == MoneyNTD(0)
    assert all(action.action is not PayrollTermsActionKind.ESTABLISH for action in payroll.candidate.actions)
    assert repository.persisted[-1].stored_receipt.receipt == receipt
    order_update = repository.persisted[-2]
    assert order_update.actor == ActorContext("admin")
    assert order_update.reason == "client requested cancellation"
    assert order_update.idempotency_key == IdempotencyKey("cancel-1")


@pytest.mark.parametrize("updated_rows", [0, 1])
def test_cancellation_synchronizes_government_difference_only_after_fresh_order_projection(monkeypatch, updated_rows):
    from infrastructure.mysql.order_cancellation_repository import MySqlOrderCancellationRepository
    from infrastructure.mysql import government_period_difference_repository as government
    from subsystems.orders.cancellation_workflow import CancellationOrderPersistenceCommand

    events = []

    class Cursor:
        rowcount = updated_rows
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, values):
            assert sql.startswith("UPDATE orders SET")
            assert values[:4] == (date(2026, 10, 31), date(2026, 11, 2), "訂單取消", 10)
            events.append("order-updated")

    cursor = Cursor()
    def synchronize(received_cursor, case_no, key, actor, reason):
        assert events == ["order-updated"]
        assert received_cursor is cursor
        assert (case_no, key, actor, reason) == ("CASE-808", "cancel-808", "admin", "提前結束")
        events.append("government-difference")

    monkeypatch.setattr(government, "synchronize_government_case_amount", synchronize)
    repository = MySqlOrderCancellationRepository(SimpleNamespace(cursor=lambda: cursor))
    command = CancellationOrderPersistenceCommand("CASE-808", 9, 10, date(2026, 10, 31), date(2026, 11, 2), OrderLifecycleStatus.CANCELLED, ActorContext("admin"), "提前結束", IdempotencyKey("cancel-808"))
    if updated_rows:
        repository.update_cancelled_order(command)
        assert events == ["order-updated", "government-difference"]
    else:
        with pytest.raises(RuntimeError, match="order_version_conflict"):
            repository.update_cancelled_order(command)
        assert events == ["order-updated"]


def test_cancellation_apply_replays_matching_receipt_without_new_writes():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ())
    request = _request(preview)
    first = workflow.apply(request)
    write_count = len(repository.persisted)
    assert workflow.apply(request) == first
    assert len(repository.persisted) == write_count


def test_historical_four_day_twins_remediation_preserves_posted_receipt_accounting():
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
        existing_subsidy_return_count=1,
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
        CancellationWorkflowFacts(
            replace(order, service_started=False, actual_start_date=None), terms, scheduling, finance, payroll,
            replace(lifecycle, current_status=OrderLifecycleStatus.CANCELLED, cancellation_effective=True),
            historical_cancellation_origin=True,
        )
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
    preview = workflow.preview("CASE-1", ())
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


def test_cancellation_fee_initializes_only_client_finance_with_approved_terms():
    facts = _facts()
    terms = ClientPaymentTermsRootFacts("policy", MoneyNTD(100), 2, date(2026, 7, 1), date(2026, 8, 1))
    facts = replace(facts, order=replace(facts.order, service_started=False),
                    scheduling=CancellationSchedulingFacts("CASE-1", None, None, ()),
                    client_finance=None, payroll=None, initial_client_payment_terms=terms)
    repo = _Repository(facts)
    workflow = _workflow(repo)
    preview = workflow.preview("CASE-1", (), 500, "verified cancellation")
    assert repo.persisted == [] and preview.client_finance_version is None
    assert preview.client_finance_impact.cancellation_settlement.additional_charge_due_ntd == 500
    request = replace(_request(preview), confirmed_service_days=(), expected_scheduling_version=None,
                      expected_client_finance_version=None, expected_payroll_version=None,
                      fee_ntd=500, fee_reason="verified cancellation")
    receipt = workflow.apply(request)
    assert receipt.client_finance_version == 1 and receipt.payroll_version is None
    assert ("initial_finance", terms, 11) in repo.persisted and repo.commits == 1
    assert workflow.apply(request) == receipt


def test_large_cancellation_fee_preview_serializes_exact_decimal_values():
    from api.routes.order_cancellation import _preview_payload
    from api.schemas.order_cancellation import OrderCancellationPreviewView

    amount = 9_007_199_254_740_993
    preview = _workflow(_Repository(_facts())).preview(
        "CASE-1", (), amount, "verified cancellation"
    )
    view = OrderCancellationPreviewView.model_validate(_preview_payload(preview)).model_dump(mode="json")
    finance = view["client_finance_impact"]
    assert finance["cancellation_settlement"]["fee_ntd"] == str(amount)
    assert finance["actions"][-1]["direction_amount_ntd"] == str(amount)


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


@pytest.mark.parametrize("fee,kind,direction,amount,recognized", [
    (2500, "refund", "payable_to_client", 5500, 2500),
    (8500, "adjustment", "receivable_from_client", 500, 8000),
])
def test_cancellation_posts_one_cash_difference_for_partial_receipt(monkeypatch, fee, kind, direction, amount, recognized):
    from infrastructure.mysql import client_finance_terms_writer as writer
    from infrastructure.mysql import client_difference_repository as differences
    from infrastructure.mysql import client_receipt_reconciliation_repository as receipts
    from infrastructure.mysql import government_period_difference_repository as government

    facts = _facts()
    old = ExistingClientStageObligation("old:first", PaymentStage.FIRST, MoneyNTD(10000), MoneyNTD(6000), date(2026, 8, 1), True)
    deposit = ExistingClientStageObligation("old:deposit", PaymentStage.DEPOSIT, MoneyNTD(2000), MoneyNTD(2000), date(2026, 7, 1), True)
    finance = replace(facts.client_finance, existing_obligations=(old, deposit))
    repository = _Repository(replace(facts, client_finance=finance, net_cash_received=MoneyNTD(8000)))
    workflow = _workflow(repository)
    reason = "approved fee"
    preview = workflow.preview("CASE-1", (), fee, reason)
    summary = preview.client_finance_impact.cancellation_settlement
    assert (summary.service_due_ntd, summary.net_received_ntd, summary.fee_received_ntd) == (0, 8000, recognized)
    assert (summary.refund_due_ntd, summary.additional_charge_due_ntd) == (
        (amount, 0) if kind == "refund" else (0, amount)
    )
    assert repository.persisted == []
    request = replace(_request(preview), fee_ntd=fee, fee_reason=reason)
    terminal = workflow.apply(request)
    assert terminal.lifecycle_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    assert terminal.official_service_day_count == 0
    assert workflow.apply(request) == terminal
    assert repository.commits == 1
    command, = [entry for entry in repository.persisted if type(entry).__name__ == "ClientFinanceImpactPersistenceCommand"]
    statements = []
    cursor = SimpleNamespace(
        execute=lambda sql, params: statements.append((sql, params)),
        rowcount=1, lastrowid=12, fetchone=lambda: {"entry_id": 9},
    )
    monkeypatch.setattr(writer, "_persist_payment_terms", lambda *_: False)
    monkeypatch.setattr(differences, "_cash", lambda *_: 6000)
    monkeypatch.setattr(differences, "_noncash", lambda *_: 0)
    monkeypatch.setattr(receipts, "_insert_refund_recipient_snapshot", lambda *_, **__: True)
    monkeypatch.setattr(government, "synchronize_government_case_amount", lambda *_: None)
    writer.persist_client_finance_terms_impact(cursor, command)
    closed, = [params for sql, params in statements if sql == writer._PROJECTION_UPDATE_SQL]
    assert closed[:3] == (0, date(2026, 8, 1), "settled")
    assert closed[-2] == "old:first"
    inserted, = [params for sql, params in statements if sql == writer._PROJECTION_INSERT_SQL]
    assert inserted[2:6] == (kind, direction, "old:first", amount)


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


def test_normal_nonzero_service_is_rejected_before_any_cancellation_write():
    repository = _Repository(_facts())
    with pytest.raises(CancellationWorkflowError) as error:
        _workflow(repository).preview("CASE-1", (ConfirmedServiceDay(date(2026, 8, 1), 7),))
    assert error.value.error.code == "order_cancellation_has_actual_service"
    assert "條款" in error.value.error.message
    assert repository.persisted == []
    assert repository.commits == 0


def test_zero_service_refunds_all_valid_receipts_less_the_confirmed_fee():
    repository = _Repository(replace(_facts(), net_cash_received=MoneyNTD(72000)))
    preview = _workflow(repository).preview("CASE-1", (), fee_ntd=2000, fee_reason="約定違約金")
    summary = preview.client_finance_impact.cancellation_settlement
    assert summary.service_due_ntd == 0
    assert summary.net_received_ntd == 72000
    assert summary.refund_due_ntd == 70000
    assert summary.additional_charge_due_ntd == 0
    assert preview.payroll_impact.payroll.total_payable.amount == 0
    assert preview.candidate.official_service_day_count == 0
    assert preview.candidate.official_service_hours == 0
    assert preview.lifecycle_impact.after_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED


def test_historical_classification_preserves_prior_refund_and_financial_versions():
    facts = _facts()
    proof = OrderEstablishmentEvidence((9,), (), None)
    prior_balance = PriorClientCancellationBalance(
        "refund-before-correction", PaymentStage.REFUND, MoneyNTD(9500), MoneyNTD(9500), None, None,
    )
    historical = HistoricalUnservedEvidence(
        proof, (), (10,), (), HistoricalCancellationSettlement(
            11, 14, 0, 20, obligation_identity=prior_balance.obligation_identity, client_balance=prior_balance,
        ),
    )
    facts = replace(
        facts,
        order=replace(facts.order, actual_start_date=None, service_started=False),
        scheduling=CancellationSchedulingFacts("CASE-1", None, None, ()),
        payroll=None,
        client_finance=replace(facts.client_finance, open_nonstage_obligation_count=1),
        net_cash_received=MoneyNTD(9500),
        lifecycle=replace(facts.lifecycle, current_status=OrderLifecycleStatus.CANCELLED, cancellation_effective=True),
        historical_unserved_evidence=historical,
    )
    repository = _Repository(facts)
    workflow = _workflow(repository)
    intent = HistoricalUnservedCorrectionIntent("核對原案未服務", "已採納歷史文件第1列")
    preview = workflow.preview("CASE-1", (), historical_correction=intent)
    assert preview.classification_only is True
    assert preview.client_finance_impact is None
    assert preview.payroll_impact is None
    receipt = workflow.apply(replace(
        _request(preview), expected_scheduling_version=None, expected_payroll_version=None,
        historical_correction=intent,
    ))
    assert receipt.lifecycle_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    assert receipt.client_finance_version == 5
    assert receipt.payroll_version is None
    assert "control" not in repository.persisted
    assert repository.commits == 1
    count = len(repository.persisted)
    assert workflow.apply(replace(
        _request(preview), expected_scheduling_version=None, expected_payroll_version=None,
        historical_correction=intent,
    )) == receipt
    assert len(repository.persisted) == count


@pytest.mark.parametrize("already_refunded", [0, 3000])
def test_operator_correction_recalculates_the_same_prior_refund_without_repeating_paid_cash(already_refunded):
    facts = _facts()
    prior_balance = PriorClientCancellationBalance(
        "existing-refund", PaymentStage.REFUND, MoneyNTD(9500),
        MoneyNTD(9500 - already_refunded), None, "legacy-service-stage",
    )
    evidence = HistoricalUnservedEvidence(
        OrderEstablishmentEvidence(current_owner_status=OrderLifecycleStatus.CANCELLED),
        (), (), ("service_day_log",),
        HistoricalCancellationSettlement(
            11, 14, 1, 20, 500, "原違約金", 5000,
            prior_balance.obligation_identity, prior_balance,
        ),
        review_codes=("historical_unserved_cash_evidence_requires_review",),
    )
    repository = _Repository(replace(
        facts,
        order=replace(facts.order, service_data_locked=True),
        lifecycle=replace(facts.lifecycle, current_status=OrderLifecycleStatus.CANCELLED),
        client_finance=replace(facts.client_finance, open_nonstage_obligation_count=1),
        net_cash_received=MoneyNTD(15000 - already_refunded),
        historical_unserved_evidence=evidence,
    ))
    workflow = _workflow(repository)
    intent = HistoricalUnservedCorrectionIntent()
    preview = workflow.preview("CASE-1", (), historical_correction=intent)
    impact = preview.client_finance_impact
    assert not preview.classification_only and impact.blockers == ()
    assert preview.lifecycle_impact.after_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    assert not preview.lifecycle_impact.establishment_evidence.established
    assert impact.cancellation_settlement.service_due_ntd == 0
    assert impact.cancellation_settlement.refund_due_ntd == 14500 - already_refunded
    assert impact.cancellation_obligation_identity == prior_balance.obligation_identity
    (adjustment,) = impact.actions
    assert adjustment.action is ClientObligationActionKind.REPLACE_OPEN
    assert adjustment.obligation_identity == prior_balance.obligation_identity
    assert adjustment.payment_stage is PaymentStage.REFUND
    assert adjustment.after_amount == MoneyNTD(14500)
    assert adjustment.obligation_amount == MoneyNTD(14500 - already_refunded)
    assert adjustment.direction is ClientFinanceDirection.REFUND_DUE
    assert adjustment.direction_amount_ntd == 5000
    request = replace(_request(preview), historical_correction=intent)
    receipt = workflow.apply(request)
    assert receipt.lifecycle_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    assert receipt.client_finance_version == 6
    assert receipt.official_service_day_count == 0
    count = len(repository.persisted)
    assert workflow.apply(request) == receipt
    assert len(repository.persisted) == count


def test_operator_correction_records_unidentified_cash_target_without_duplicating_refund():
    from api.routes.order_cancellation import _historical_correction_preview_payload, _historical_correction_query_payload
    from infrastructure.mysql.client_finance_terms_writer import _save_cancellation_settlement
    from infrastructure.mysql.order_cancellation_repository import _lifecycle_values

    facts = _facts()
    deposit = ExistingClientStageObligation(
        "original-deposit", PaymentStage.DEPOSIT, MoneyNTD(8000), MoneyNTD(3000), None, True,
    )
    evidence = HistoricalUnservedEvidence(OrderEstablishmentEvidence(), (), (), (), None)
    repository = _Repository(replace(
        facts,
        lifecycle=replace(facts.lifecycle, current_status=OrderLifecycleStatus.CANCELLED),
        client_finance=replace(facts.client_finance, open_nonstage_obligation_count=1, existing_obligations=(deposit,)),
        net_cash_received=MoneyNTD(3000),
        historical_unserved_evidence=evidence,
    ))
    workflow = _workflow(repository)
    intent = HistoricalUnservedCorrectionIntent()
    preview = workflow.preview("CASE-1", (), historical_correction=intent)
    impact = preview.client_finance_impact
    assert impact.blockers == () and impact.cancellation_obligation_identity is None
    assert impact.cancellation_cash_difference_requires_review
    (closure,) = impact.actions
    assert closure.obligation_identity == deposit.obligation_identity
    assert closure.after_amount == MoneyNTD(3000)
    assert _historical_correction_preview_payload(preview)["client_cash_difference_requires_review"]

    request = replace(_request(preview), historical_correction=intent)
    receipt = workflow.apply(request)
    assert receipt.lifecycle_status is OrderLifecycleStatus.ESTABLISHED_UNSERVED
    query = _historical_correction_query_payload(replace(
        repository.facts,
        lifecycle=replace(repository.facts.lifecycle, current_status=receipt.lifecycle_status),
    ))
    assert query["review_codes"].count("historical_unserved_cash_evidence_requires_review") == 1
    lifecycle_values = _lifecycle_values(request, preview, None)
    assert lifecycle_values[4] == request.actor.actor_id
    confirmation = json.loads(lifecycle_values[-1])["historical_unserved_correction"]
    assert confirmation["confirmed_established"] is True
    assert confirmation["confirmed_actual_service_day_count"] == 0

    statements = []
    cursor = SimpleNamespace(
        execute=lambda sql, parameters: statements.append((sql, parameters)),
        fetchone=lambda: {"entry_id": 19},
    )
    _save_cancellation_settlement(
        cursor, SimpleNamespace(candidate=impact, source_event_id=11, idempotency_key=request.idempotency_key),
        impact.cancellation_settlement,
    )
    settlement = json.loads(statements[-1][1][-1])["cancellation_settlement"]
    assert settlement["cash_difference_requires_review"] is True
    assert settlement["refund_due_ntd"] == 3000
    assert settlement["service_due_ntd"] == 0
    assert settlement["obligation_identity"] is None
    assert settlement["cash_entry_id"] == 19

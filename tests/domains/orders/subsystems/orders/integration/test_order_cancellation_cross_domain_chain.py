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
from subsystems.orders.cancellation_workflow import CancellationWorkflowError, CancellationWorkflowFacts, OrderCancellationApplyRequest, OrderCancellationWorkflow
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

"""Orders cancellation Preview/Apply cross-owner persistence contract."""

from datetime import date, datetime, time

from domains.client_finance.obligation_planning import ClientFinanceTermsSourceFacts, ClientPaymentTerms
from domains.orders.cancellation import CancellationAssignmentFacts, CancellationOrderFacts, CancellationSchedulingFacts, ConfirmedServiceDay
from domains.orders.lifecycle import OrderLifecycleRootFacts, OrderLifecycleStatus
from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import AssignmentIdentityResolution
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.orders.cancellation_workflow import CancellationWorkflowFacts, OrderCancellationApplyRequest, OrderCancellationWorkflow
from subsystems.orders.terms_workflow import CommandClaimState, SchedulingReplacementResult
from subsystems.payroll.terms_impact import PayrollTermsSourceFacts, SourceAssignmentPayrollTerms


class _UnitOfWork:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): self.committed = True


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.persisted = []

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
    return OrderCancellationWorkflow(repository, _UnitOfWork, FixedBusinessClock(datetime(2026, 8, 2, 9, 0).astimezone()))


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

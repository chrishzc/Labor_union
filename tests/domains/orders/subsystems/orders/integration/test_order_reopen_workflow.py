from datetime import date, datetime
from dataclasses import replace

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.reopen import ReopenOrderFacts
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.reopen_workflow import (
    OrderReopenApplyRequest,
    OrderReopenWorkflow,
    ReopenWorkflowFacts,
)


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.claim = None
        self.saved = None

    def load_for_preview(self, _): return self.facts
    def load_for_apply(self, _): return self.facts
    def claim_command(self, *_):
        from subsystems.orders.terms_workflow import CommandClaimState
        return CommandClaimState.CREATED
    def find_receipt(self, *_args, **_kwargs): return None
    def append_reopen_event(self, *_): return 10
    def clear_cancellation_control(self, *_): return 11
    def append_reopen_lifecycle(self, *_): return 12
    def update_reopened_order(self, command): self.projection = command
    def save_receipt(self, command): self.saved = command


def _facts():
    order = ReopenOrderFacts("CASE-1", 4, OrderLifecycleStatus.CANCELLED, 7, True, False, False, None, False, False, False)
    return ReopenWorkflowFacts(order, (), 2, 3)


def test_reopen_preview_and_apply_use_source_transaction_contract():
    repository = _Repository(_facts())
    workflow = OrderReopenWorkflow(repository, _UnitOfWork, FixedBusinessClock(datetime(2026, 8, 3, 9, 0).astimezone()))
    preview = workflow.preview("CASE-1")
    request = OrderReopenApplyRequest("CASE-1", ExpectedVersion(4), ExpectedVersion(2), ExpectedVersion(3), preview.fingerprint, IdempotencyKey("reopen-1"), ActorContext("admin"), "correct cancellation", CorrelationId("corr-1"))
    receipt = workflow.apply(request)
    assert receipt.order_version == 5
    assert receipt.lifecycle_status is OrderLifecycleStatus.DISCUSSION
    assert repository.saved.stored_receipt.receipt == receipt


@pytest.mark.parametrize("owner_created", [None, "client_finance_version", "payroll_version"])
def test_reopen_missing_roots_and_fresh_presence_conflict(owner_created):
    from subsystems.orders.reopen_workflow import ReopenWorkflowError
    repository = _Repository(replace(_facts(), client_finance_version=None, payroll_version=None))
    workflow = OrderReopenWorkflow(repository, _UnitOfWork, FixedBusinessClock(datetime(2026, 8, 3, 9, 0).astimezone()))
    preview = workflow.preview("CASE-1")
    request = OrderReopenApplyRequest("CASE-1", ExpectedVersion(4), None, None, preview.fingerprint, IdempotencyKey("reopen-absent"), ActorContext("admin"), "correct cancellation", CorrelationId("corr-absent"))
    if owner_created:
        repository.facts = replace(repository.facts, **{owner_created: 0})
        with pytest.raises(ReopenWorkflowError) as error:
            workflow.apply(request)
        assert error.value.error.category.value == "conflict"
        assert repository.saved is None
    else:
        receipt = workflow.apply(request)
        assert receipt.requires_fresh_scheduling_preview
        assert receipt.lifecycle_status is OrderLifecycleStatus.DISCUSSION


def test_reopen_null_payroll_receipt_still_checks_post_cancellation_payouts():
    from infrastructure.mysql.order_reopen_repository import _staff_financial_rows, _staff_obligation_identities
    class Cursor:
        def execute(self, statement, parameters):
            self.statement, self.parameters = statement, parameters
        def fetchall(self):
            return ()
    cursor = Cursor()
    cancellation = {"payroll_version": None, "cancellation_created_at": datetime(2026, 8, 1)}
    _staff_obligation_identities(cursor, "CASE-1", cancellation)
    assert cursor.parameters == ("CASE-1", None, None)
    assert "OR %s IS NULL" in cursor.statement
    _staff_financial_rows(cursor, "CASE-1", cancellation, True)
    assert cursor.parameters == ("CASE-1", None, None, cancellation["cancellation_created_at"])
    assert "JOIN staff_payout_events" in cursor.statement

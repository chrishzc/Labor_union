from datetime import date, datetime, time

import pytest

from domains.client_finance.obligation_planning import (
    ClientChargeDay,
    ClientFinanceTermsFacts,
    ClientPaymentTerms,
)
from domains.orders.contract_completion import (
    ContractCompletionBlocker,
    ContractCompletionFacts,
    ContractCompletionIntent,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.terms import ServiceTimeTerms
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionApplyRequest,
    ContractCompletionCommandClaimState,
    ContractCompletionWorkflow,
    ContractCompletionWorkflowError,
    ContractCompletionWorkflowFacts,
    StoredContractCompletionReceipt,
)


class _UnitOfWork:
    committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.claim_state = ContractCompletionCommandClaimState.CREATED
        self.persisted = []

    def load_for_preview(self, _): return self.facts
    def load_for_apply(self, _): return self.facts
    def claim_command(self, *_): return self.claim_state
    def find_receipt(self, *_args, **_kwargs): return self.receipt
    def append_contract_completion_event(self, *_): self.persisted.append("contract"); return 7
    def persist_client_finance_impact(self, command): self.persisted.append(command)
    def append_lifecycle_event(self, command): self.persisted.append(command); return 8
    def update_order_projection(self, command): self.persisted.append(command)
    def append_outbox_intent(self, *_): self.persisted.append("outbox")
    def save_receipt(self, command):
        self.persisted.append(command)
        self.receipt = command.stored_receipt


def _facts(*, charge_days=2):
    order = ContractCompletionFacts(
        "CASE-1", 4, "CONTRACT-1", False, OrderLifecycleStatus.DISCUSSION,
        True, ServiceTimeTerms(time(8), time(17), 0),
    )
    finance = ClientFinanceTermsFacts(
        "CASE-1", 6, 8, MoneyNTD(0),
        tuple(ClientChargeDay(date(2026, 8, day), False) for day in range(1, charge_days + 1)),
        ClientPaymentTerms(0, MoneyNTD(100), date(2026, 7, 1), date(2026, 8, 1), None), (),
    )
    return ContractCompletionWorkflowFacts(order, finance, 2)


def _workflow(repository):
    return ContractCompletionWorkflow(
        repository, _UnitOfWork,
        FixedBusinessClock(datetime(2026, 8, 3, 9, 0).astimezone()),
    )


def _request(preview):
    return ContractCompletionApplyRequest(
        "CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED,
        ExpectedVersion(4), ExpectedVersion(6), preview.fingerprint,
        IdempotencyKey("contract-complete-1"), ActorContext("admin"),
        "service completed", CorrelationId("corr-1"),
    )


def test_preview_apply_persists_canonical_contract_completion_chain():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)
    receipt = workflow.apply(_request(preview))
    assert receipt.order_version == 5
    assert receipt.client_finance_version == 7
    assert receipt.lifecycle_status is OrderLifecycleStatus.ESTABLISHED
    assert repository.persisted[0] == "contract"
    assert repository.persisted[-1].stored_receipt.receipt == receipt


def test_apply_replays_matching_receipt_without_new_writes():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)
    request = _request(preview)
    first = workflow.apply(request)
    second = workflow.apply(request)
    assert second == first
    assert len(repository.persisted) == 6


def test_query_reports_official_service_dates_blocker():
    workflow = _workflow(_Repository(_facts(charge_days=1)))
    query = workflow.query("CASE-1")
    assert query.completion_available is False
    assert query.domain_blockers == (
        ContractCompletionBlocker.OFFICIAL_SERVICE_DATES_INCOMPLETE,
    )


def test_apply_rejects_stale_client_finance_version():
    repository = _Repository(_facts())
    workflow = _workflow(repository)
    preview = workflow.preview("CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED)
    request = ContractCompletionApplyRequest(
        "CASE-1", ContractCompletionIntent.CONFIRM_COMPLETED,
        ExpectedVersion(4), ExpectedVersion(5), preview.fingerprint,
        IdempotencyKey("contract-complete-2"), ActorContext("admin"),
        "service completed", CorrelationId("corr-2"),
    )
    with pytest.raises(ContractCompletionWorkflowError, match="Client Finance"):
        workflow.apply(request)

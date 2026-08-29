from __future__ import annotations

import pytest

from domains.staff_payables.reconciliation import (
    OutgoingBankFact,
    StaffPayableFacts,
    StaffPayableStatus,
    StaffPayoutEventType,
    StaffPrimaryBankAccount,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutReconciliationError,
    StaffPayoutReconciliationFacts,
    StaffPayoutReconciliationWorkflow,
    StaffPayoutSelection,
    StoredStaffPayoutReceipt,
)


class _UnitOfWork:
    def __init__(self):
        self.committed = False

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
        self.calls = []

    def load(self, selection, *, for_update):
        assert selection.obligation_identities == ("obligation:1",)
        self.calls.append(("load", for_update))
        return self.facts

    def find_receipt(self, _key):
        self.calls.append(("find",))
        return self.receipt

    def append_events(self, candidate):
        self.calls.append(("events", len(candidate.events)))

    def append_obligation_links(self, candidate):
        self.calls.append(("links", len(candidate.obligation_links)))

    def update_payable_projection(self, _selection, version, status):
        self.calls.append(("projection", version, status))

    def append_outbox(self, _candidate):
        self.calls.append(("outbox",))

    def save_receipt(self, _key, receipt):
        self.calls.append(("receipt",))
        self.receipt = receipt


def _facts(version=4):
    return StaffPayoutReconciliationFacts(
        version,
        8,
        (OutgoingBankFact("bank:1", 7, MoneyNTD(500), "account:7"),),
        (StaffPrimaryBankAccount("account:7", 7),),
        (StaffPayableFacts("obligation:1", 7, MoneyNTD(500)),),
    )


def _selection():
    return StaffPayoutSelection(StaffPayoutEventType.PAYOUT, ("bank:1",), ("obligation:1",))


def _request(preview, *, version=4, key="payout-1"):
    return StaffPayoutApplyRequest(
        _selection(), ExpectedVersion(version), ExpectedVersion(8), preview.fingerprint,
        IdempotencyKey(key), ActorContext("admin"), "Record exact staff payout.",
        CorrelationId("staff-payout-test"),
    )


def test_preview_apply_persists_ledger_projection_outbox_and_receipt():
    repository = _Repository(_facts())
    unit_of_work = _UnitOfWork()
    workflow = StaffPayoutReconciliationWorkflow(repository, lambda: unit_of_work)

    preview = workflow.preview(_selection(), CorrelationId("preview"))
    receipt = workflow.apply(_request(preview))

    assert receipt.staff_payables_version == 5
    assert receipt.bank_facts_version == 8
    assert receipt.resulting_status is StaffPayableStatus.COMPLETED
    assert repository.calls == [
        ("load", False), ("find",), ("load", True), ("events", 1),
        ("links", 1), ("projection", 5, StaffPayableStatus.COMPLETED),
        ("outbox",), ("receipt",),
    ]
    assert unit_of_work.committed is True


def test_apply_replays_matching_command_without_new_write():
    repository = _Repository(_facts())
    workflow = StaffPayoutReconciliationWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_selection(), CorrelationId("preview"))
    request = _request(preview)
    first = workflow.apply(request)
    repository.calls.clear()

    assert workflow.apply(request) == first
    assert repository.calls == [("find",)]


def test_apply_rejects_stale_version_before_persistence():
    stale_preview = StaffPayoutReconciliationWorkflow(_Repository(_facts(4)), _UnitOfWork).preview(_selection(), CorrelationId("preview"))
    repository = _Repository(_facts(5))
    workflow = StaffPayoutReconciliationWorkflow(repository, _UnitOfWork)

    with pytest.raises(StaffPayoutReconciliationError) as raised:
        workflow.apply(_request(stale_preview, version=4))

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "staff_payable_candidate_stale"
    assert repository.calls == [("find",), ("load", True)]


def test_apply_rejects_another_command_for_existing_idempotency_key():
    repository = _Repository(_facts())
    workflow = StaffPayoutReconciliationWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_selection(), CorrelationId("preview"))
    request = _request(preview)
    receipt = workflow.apply(request)
    repository.receipt = StoredStaffPayoutReceipt(
        workflow._find_replay.__self__._repository.receipt.command_fingerprint, receipt
    )
    different = StaffPayoutApplyRequest(
        request.selection, request.expected_staff_payables_version,
        request.expected_bank_facts_version, request.preview_fingerprint,
        request.idempotency_key, request.actor, "Different reason.", request.correlation_id,
    )

    with pytest.raises(StaffPayoutReconciliationError) as raised:
        workflow.apply(different)

    assert raised.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH

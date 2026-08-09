from datetime import date

import pytest

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.deposit_reversal_workflow import (
    DEPOSIT_REVERSAL_IDEMPOTENCY_CONFLICT,
    DepositReversalApplyRequest,
    DepositReversalError,
    DepositReversalFacts,
    DepositReversalSelection,
    DepositReversalWorkflow,
)


class UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipts = {}
        self.actions = []

    def load(self, _selection, *, for_update):
        self.actions.append(("load", for_update))
        return self.facts

    def find_receipt(self, key):
        return self.receipts.get(key.value)

    def append_reversal_ledger_entry(self, _candidate): self.actions.append("ledger")
    def reopen_deposit_obligation(self, _candidate): self.actions.append("obligation")
    def replace_deposit_settlement(self, _candidate): self.actions.append("projection")
    def append_orders_lifecycle_intent(self, _candidate): self.actions.append("orders")
    def append_anomaly_intent(self, _candidate): self.actions.append("anomaly")
    def save_receipt(self, key, receipt): self.receipts[key.value] = receipt; self.actions.append("receipt")


def _facts(**changes):
    values = {
        "case_no": "G14-CASE",
        "account_version": 7,
        "deposit_obligation_identity": "G14-CASE:deposit",
        "contracted_amount_ntd": 2000,
        "deposit_due_date": date(2026, 8, 1),
        "settlement_identity": PreviewFingerprint("a" * 64),
        "original_ledger_entry_id": 99,
        "original_ledger_amount_ntd": 2000,
        "actual_start_exists": False,
        "service_started": False,
        "service_completed": False,
        "confirmed_settlement_identity": None,
    }
    values.update(changes)
    return DepositReversalFacts(**values)


def _request(preview, *, key="g14-reversal", reason="bank return confirmed"):
    return DepositReversalApplyRequest(
        DepositReversalSelection("G14-CASE", 99, date(2026, 8, 4)),
        ExpectedVersion(7),
        preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("admin"),
        reason,
        CorrelationId("g14-test"),
    )


def test_pre_service_reversal_reopens_deposit_and_emits_one_orders_intent():
    repository = Repository(_facts())
    unit = UnitOfWork()
    workflow = DepositReversalWorkflow(repository, lambda: unit)
    preview = workflow.preview(DepositReversalSelection("G14-CASE", 99, date(2026, 8, 4)))

    receipt = workflow.apply(_request(preview))

    assert receipt.account_version == 8
    assert receipt.anomaly_code is None
    assert repository.actions == [
        ("load", False),
        ("load", True),
        "ledger", "obligation", "projection", "orders", "receipt",
    ]
    assert unit.committed is True


def test_post_service_reversal_preserves_service_and_routes_anomaly():
    repository = Repository(_facts(actual_start_exists=True, service_started=True))
    workflow = DepositReversalWorkflow(repository, UnitOfWork)
    preview = workflow.preview(DepositReversalSelection("G14-CASE", 99, date(2026, 8, 4)))

    receipt = workflow.apply(_request(preview))

    assert receipt.anomaly_code == "finance.deposit_reversal_after_service_started"
    assert repository.actions[-2:] == ["anomaly", "receipt"]


def test_replay_is_exact_and_conflicting_reuse_is_rejected():
    repository = Repository(_facts())
    workflow = DepositReversalWorkflow(repository, UnitOfWork)
    preview = workflow.preview(DepositReversalSelection("G14-CASE", 99, date(2026, 8, 4)))
    request = _request(preview)
    first = workflow.apply(request)

    assert workflow.apply(request) == first
    with pytest.raises(DepositReversalError) as error:
        workflow.apply(
            _request(preview, key="g14-reversal", reason="different reason")
        )
    assert error.value.error.code == DEPOSIT_REVERSAL_IDEMPOTENCY_CONFLICT

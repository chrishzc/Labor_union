from datetime import date

from domains.government_subsidy.ledger import (
    ClaimBatchFacts,
    ClaimBatchIdentity,
    ClaimItemSnapshot,
    GovernmentBankFact,
    GovernmentSubsidyBankDirection,
    ReceiptIntent,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.government_subsidy.ledger_workflow import (
    GovernmentSubsidyClaimState,
    GovernmentSubsidyLedgerWorkflow,
    GovernmentSubsidyReceiptApplyRequest,
    GovernmentSubsidyReceiptContext,
)


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _Repository:
    def __init__(self):
        self.receipt = None
        self.writes = []

    def load_receipt_context(self, _intent, *, lock):
        del lock
        bank = GovernmentBankFact(
            81,
            "bank-fact-81",
            GovernmentSubsidyBankDirection.INCOMING,
            "government_subsidy",
            MoneyNTD(5600),
            date(2026, 8, 1),
        )
        item = ClaimItemSnapshot(
            1, 5, 11, "CASE-1", 7, 16, MoneyNTD(350),
            MoneyNTD(5600), MoneyNTD(5600), MoneyNTD(0),
        )
        batch = ClaimBatchFacts(
            5, ClaimBatchIdentity(2026, 3, 1), 4, True, True, (item,)
        )
        return GovernmentSubsidyReceiptContext(bank, (batch,))

    def claim_command(self, *_):
        return (
            GovernmentSubsidyClaimState.CREATED
            if self.receipt is None
            else GovernmentSubsidyClaimState.MATCHED
        )

    def find_receipt(self, *_args, **_kwargs):
        return self.receipt

    def append_ledger_transaction(self, *_):
        self.writes.append("transaction")
        return 91

    def append_allocations(self, *_):
        self.writes.append("allocations")
        return (1,)

    def update_batch_projection(self, *_):
        self.writes.append("projection")

    def append_projection_event(self, *_):
        self.writes.append("projection_event")
        return 31

    def append_outbox(self, *_):
        self.writes.append("outbox")

    def save_receipt(self, command):
        self.writes.append("receipt")
        self.receipt = command.stored_receipt


class _RecheckSink:
    def __init__(self):
        self.requests = []

    def append_government_subsidy_recheck(self, request):
        self.requests.append(request)


def _request(preview):
    return GovernmentSubsidyReceiptApplyRequest(
        ReceiptIntent(81, 5),
        ExpectedVersion(4),
        preview.fingerprint,
        IdempotencyKey("government-subsidy-ledger-1"),
        ActorContext("admin"),
        "record government subsidy receipt",
        CorrelationId("government-subsidy-ledger-correlation"),
    )


def test_receipt_apply_persists_ledger_projection_outbox_and_receipt():
    repository = _Repository()
    workflow = GovernmentSubsidyLedgerWorkflow(repository, _UnitOfWork)
    preview = workflow.preview_receipt(ReceiptIntent(81, 5))

    receipt = workflow.apply_receipt(_request(preview))

    assert receipt.transaction_id == 91
    assert receipt.batch_version == 5
    assert receipt.status == "paid"
    assert repository.writes == [
        "transaction", "allocations", "projection", "projection_event",
        "outbox", "receipt",
    ]


def test_receipt_apply_replays_matching_idempotency_without_new_writes():
    repository = _Repository()
    workflow = GovernmentSubsidyLedgerWorkflow(repository, _UnitOfWork)
    preview = workflow.preview_receipt(ReceiptIntent(81, 5))
    request = _request(preview)

    first = workflow.apply_receipt(request)
    second = workflow.apply_receipt(request)

    assert second == first
    assert len(repository.writes) == 6


def test_receipt_apply_appends_exact_owner_rechecks_before_outer_commit():
    repository = _Repository()
    sink = _RecheckSink()
    workflow = GovernmentSubsidyLedgerWorkflow(repository, _UnitOfWork, sink)
    preview = workflow.preview_receipt(ReceiptIntent(81, 5))

    workflow.apply_receipt(_request(preview))

    assert tuple(request.definition_code.value for request in sink.requests) == (
        "GOVSUB-001",
        "GOVSUB-002",
    )
    assert sink.requests[0].subject_ids == ("bank-fact-81",)
    assert sink.requests[1].subject_ids == ("bank-fact-81:5",)

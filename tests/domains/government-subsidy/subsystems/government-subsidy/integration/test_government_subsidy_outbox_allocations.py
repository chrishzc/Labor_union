from types import SimpleNamespace

from domains.government_subsidy.ledger import GovernmentSubsidyLedgerKind
from infrastructure.mysql.government_subsidy_repository import _outbox_values


def _candidate(kind):
    return SimpleNamespace(
        kind=kind,
        after_status=SimpleNamespace(value="paid"),
        amount_ntd=SimpleNamespace(amount=6000),
        bank_fact=SimpleNamespace(bank_fact_identity="bank-row-1"),
        batch_id=7,
        outstanding_ntd=SimpleNamespace(amount=0),
        allocations=(SimpleNamespace(claim_item_id=11, amount_ntd=SimpleNamespace(amount=6000)),),
    )


def test_receipt_keeps_existing_event_and_adds_allocation_fact():
    request = SimpleNamespace(idempotency_key=SimpleNamespace(value="receipt-key"))

    values = _outbox_values(request, _candidate(GovernmentSubsidyLedgerKind.RECEIPT), 21, 31)

    assert [item[4] for item in values] == [
        "government_subsidy_receipt_applied",
        "government_subsidy_receipt_allocated",
    ]
    assert '"claim_item_id":11' in values[1][5]


def test_reversal_emits_only_its_existing_event():
    request = SimpleNamespace(idempotency_key=SimpleNamespace(value="reversal-key"))

    values = _outbox_values(request, _candidate(GovernmentSubsidyLedgerKind.REVERSAL), 22, 32)

    assert [item[4] for item in values] == ["government_subsidy_reversal_applied"]

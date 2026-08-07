from domains.client_finance.reconciliation import PaymentStage
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    _upsert_deposit_settlement_projection,
)
from subsystems.client_finance.reconciliation_workflow import (
    ReconciliationSelection,
)


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, values):
        self.calls.append((sql, values))


def test_exact_deposit_receipt_updates_only_canonical_settlement_projection():
    cursor = RecordingCursor()
    selection = ReconciliationSelection(
        "G14-CASE",
        PaymentStage.DEPOSIT,
        ("1",),
        ("G14-CASE:deposit",),
    )

    _upsert_deposit_settlement_projection(
        cursor,
        selection,
        {"G14-CASE:deposit": 2000},
        {"1": 7},
        "a" * 64,
        4,
    )

    assert len(cursor.calls) == 1
    sql, values = cursor.calls[0]
    assert "client_deposit_settlement_projection" in sql
    assert "client_payments" not in sql
    assert values == (
        "G14-CASE",
        "G14-CASE:deposit",
        2000,
        2000,
        "a" * 64,
        "a" * 64,
        4,
        7,
    )

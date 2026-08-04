from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from subsystems.client_finance import receipt_reconciliation as receipt


def test_allocate_consumes_receipts_in_canonical_stage_order():
    allocations = receipt._allocate(
        {
            "deposit": "100",
            "first_payment": "200",
            "second_payment": "300",
        },
        {
            "deposit": "25",
            "first_payment": "0",
            "second_payment": "0",
        },
        Decimal("200"),
    )

    assert allocations == [("deposit", Decimal("75")), ("first_payment", Decimal("125"))]


def test_allocate_rejects_persisted_summary_that_exceeds_receivable():
    with pytest.raises(ValueError, match="summary exceeds"):
        receipt._allocate(
            {"deposit": 10, "first_payment": 0, "second_payment": 0},
            {"deposit": 11, "first_payment": 0, "second_payment": 0},
            Decimal("1"),
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2026-08-03", "2026-08-03"), (date(2026, 8, 3), "2026-08-03"), (datetime(2026, 8, 3, 9, tzinfo=timezone.utc), "2026-08-03"), (None, None)],
)
def test_transaction_date_normalization(value, expected):
    assert receipt._transaction_date(value) == expected


def test_reconcile_returns_pending_for_invalid_fingerprint_before_dependencies():
    cursor = _Cursor({"dedup_fingerprint": "not-a-fingerprint"})

    assert receipt.reconcile_client_receipt(cursor, 7) == {
        "result": "pending",
        "reason": "fingerprint_missing_or_invalid",
        "transaction_ids": [],
        "client_payment_id": None,
        "case_no": None,
    }


def test_existing_receipt_set_must_match_canonical_allocation():
    payment = {
        "id": 3,
        "case_no": "C-1",
        "deposit_receivable": 100,
        "deposit_received": 100,
        "first_payment_receivable": 200,
        "first_payment_received": 50,
        "second_payment_receivable": 0,
        "second_payment_received": 0,
    }
    rows = [{
        "id": 9,
        "client_payment_id": 3,
        "case_no": "C-1",
        "stage": "first_payment",
        "transaction_type": "receipt",
        "transaction_status": "succeeded",
        "amount": 50,
        "occurred_at": "2026-08-03T12:00:00+00:00",
        "external_reference": f"fp:{'a' * 64}:first_payment",
        "finance_import_row_id": 7,
    }]

    assert receipt._validate_existing_set(rows, payment=payment, finance_import_row_id=7, fingerprint="a" * 64, credit=Decimal("50"), occurred_at="2026-08-03") == [9]


class _Cursor:
    def __init__(self, row):
        self._row = row

    def execute(self, *_args):
        return None

    def fetchone(self):
        return self._row

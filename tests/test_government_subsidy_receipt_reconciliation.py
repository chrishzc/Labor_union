from decimal import Decimal

from subsystems.government_subsidy.receipt_reconciliation import _validate_bank_row


def test_government_receipt_requires_positive_taishin_incoming_credit() -> None:
    result = _validate_bank_row(
        {
            "format_id": "taishin",
            "classification_type": "government_subsidy",
            "direction": "incoming",
            "transaction_date": "2026-08-01",
        },
        Decimal("100"),
        Decimal("0"),
    )

    assert result is None


def test_government_receipt_rejects_debit_on_incoming_row() -> None:
    result = _validate_bank_row(
        {
            "format_id": "taishin",
            "classification_type": "government_subsidy",
            "direction": "incoming",
            "transaction_date": "2026-08-01",
        },
        Decimal("100"),
        Decimal("1"),
    )

    assert result["reason"] == "incoming government subsidy row must not contain a debit"

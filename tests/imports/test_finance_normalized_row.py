from copy import deepcopy
from decimal import Decimal

import pytest

from scripts.imports.finance_normalized_row import REQUIRED_FIELDS, validate_normalized_row


def _row(**updates):
    row = {
        "format_id": "legacy",
        "source_file": "history.xlsx",
        "source_bank_account": "001234567890",
        "sheet_name": "statement",
        "source_row": 4,
        "source_reference": None,
        "transaction_date": "2026-07-15",
        "transaction_time": "09:08:07",
        "posting_date": None,
        "value_date": "2026-07-15",
        "debit": Decimal("100.00"),
        "credit": None,
        "direction": "outgoing",
        "balance": Decimal("900.00"),
        "currency": "TWD",
        "summary": "transfer",
        "memo": None,
        "counterparty_name": None,
        "counterparty_account": "00001234",
        "cancellation_code": None,
        "bank_references": {"transaction_reference": "0000456"},
        "warnings": [],
        "raw_payload": {"帳號": "001234567890", "支出": 100.0, "備註": None},
    }
    row.update(updates)
    return row


def test_required_field_contract_is_exact_and_excludes_header_row():
    assert len(REQUIRED_FIELDS) == 23
    assert "header_row" not in REQUIRED_FIELDS
    assert set(_row()) == REQUIRED_FIELDS


def test_valid_row_is_returned_without_copying_or_mutating_values():
    row = _row()
    before = deepcopy(row)

    result = validate_normalized_row(row)

    assert result is row
    assert result == before
    assert result["counterparty_account"] == "00001234"
    assert result["bank_references"]["transaction_reference"] == "0000456"


def test_incoming_direction_requires_credit_as_only_positive_side():
    row = _row(debit=Decimal("0"), credit=Decimal("50"), direction="incoming")
    assert validate_normalized_row(row) is row


@pytest.mark.parametrize(
    ("debit", "credit", "warning"),
    [
        (Decimal("10"), Decimal("20"), "direction_ambiguous"),
        (None, None, "direction_missing"),
    ],
)
def test_unknown_direction_requires_the_corresponding_warning(debit, credit, warning):
    row = _row(debit=debit, credit=credit, direction="unknown", warnings=[warning])
    assert validate_normalized_row(row) is row


def test_direction_mismatch_reports_the_direction_field():
    with pytest.raises(ValueError, match="direction: must be outgoing"):
        validate_normalized_row(_row(direction="incoming"))


def test_unknown_direction_without_required_warning_is_rejected():
    with pytest.raises(ValueError, match="direction_missing"):
        validate_normalized_row(_row(debit=None, credit=None, direction="unknown"))


@pytest.mark.parametrize(
    "updates",
    [
        {"transaction_date": "2026-7-15"},
        {"transaction_date": "2026-02-30"},
        {"transaction_time": "9:08:07"},
        {"memo": ""},
        {"debit": 100.0},
        {"source_row": 0},
        {"source_reference": "guessed-reference"},
        {"warnings": ["direction_missing", "direction_missing"]},
        {"bank_references": {"transaction_reference": 456}},
        {"raw_payload": {"日期": Decimal("1")}},
        {"raw_payload": {"數值": float("nan")}},
    ],
)
def test_invalid_field_types_and_values_are_rejected(updates):
    with pytest.raises(ValueError, match="normalized row validation failed"):
        validate_normalized_row(_row(**updates))


def test_missing_or_unexpected_fields_are_rejected():
    missing = _row()
    missing.pop("memo")
    with pytest.raises(ValueError, match="missing memo"):
        validate_normalized_row(missing)

    with pytest.raises(ValueError, match="unexpected header_row"):
        validate_normalized_row(_row(header_row=3))

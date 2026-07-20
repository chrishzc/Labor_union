from copy import deepcopy
from decimal import Decimal
import re

import pytest

from services.finance_transaction_fingerprint import build_dedup_fingerprint


def normalized_row(**changes):
    row = {
        "format_id": "sinopac",
        "source_file": "statement-a.xlsx",
        "source_bank_account": "01234567890123",
        "sheet_name": "2026-07",
        "source_row": 8,
        "source_reference": None,
        "transaction_date": "2026-07-01",
        "transaction_time": "09:10:11",
        "posting_date": "2026-07-01",
        "value_date": "2026-07-01",
        "debit": Decimal("1250.00"),
        "credit": None,
        "direction": "outgoing",
        "balance": Decimal("98750.00"),
        "currency": "TWD",
        "summary": "跨行轉帳",
        "memo": "補助款 退還",
        "counterparty_name": "王小明",
        "counterparty_account": "0011223344",
        "cancellation_code": "A001",
        "bank_references": {"sequence": "000008"},
        "warnings": [],
        "raw_payload": {"原始列號": 8},
    }
    row.update(changes)
    return row


def test_returns_64_character_lowercase_sha256():
    fingerprint = build_dedup_fingerprint(normalized_row())

    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)


def test_legacy_and_sinopac_share_bank_source_and_ignore_file_coordinates():
    current = normalized_row()
    legacy = normalized_row(
        format_id="legacy",
        source_file="historical-book.xlsx",
        sheet_name="不同分頁",
        source_row=999,
        posting_date="2026-07-02",
        value_date=None,
        bank_references={"legacy_sequence": "55"},
        raw_payload={"完全不同表頭": "值"},
    )

    assert build_dedup_fingerprint(current) == build_dedup_fingerprint(legacy)


def test_taishin_is_a_distinct_bank_source():
    assert build_dedup_fingerprint(normalized_row(format_id="taishin")) != build_dedup_fingerprint(normalized_row())


def test_text_uses_nfkc_and_collapses_whitespace():
    canonical = normalized_row(
        source_bank_account="123456",
        summary="ABC 轉帳",
        memo="補助款 退還",
        cancellation_code="A001",
    )
    variant = normalized_row(
        source_bank_account="１２３４５６",
        summary="ＡＢＣ\t轉帳",
        memo=" 補助款\n\t退還 ",
        cancellation_code="Ａ００１",
    )

    assert build_dedup_fingerprint(canonical) == build_dedup_fingerprint(variant)


def test_amounts_are_canonical_two_decimal_values():
    plain = normalized_row(debit=Decimal("1250"), balance=Decimal("98750"))
    scaled = normalized_row(debit=Decimal("1250.000"), balance=Decimal("98750.0000"))

    assert build_dedup_fingerprint(plain) == build_dedup_fingerprint(scaled)


def test_negative_zero_and_zero_have_same_amount_representation():
    missing_direction = dict(direction="unknown", debit=Decimal("0"), credit=None, warnings=["direction_missing"])
    negative_zero = dict(direction="unknown", debit=Decimal("-0.00"), credit=None, warnings=["direction_missing"])

    assert build_dedup_fingerprint(normalized_row(**missing_direction)) == build_dedup_fingerprint(normalized_row(**negative_zero))


@pytest.mark.parametrize(
    ("field", "different"),
    [
        ("source_bank_account", "99999999999999"),
        ("transaction_date", "2026-07-02"),
        ("transaction_time", "09:10:12"),
        ("debit", Decimal("1251.00")),
        ("balance", Decimal("98749.00")),
        ("summary", "ATM 轉帳"),
        ("memo", "另一筆補助款退還"),
        ("cancellation_code", "A002"),
    ],
)
def test_each_stable_transaction_feature_changes_fingerprint(field, different):
    assert build_dedup_fingerprint(normalized_row()) != build_dedup_fingerprint(normalized_row(**{field: different}))


def test_same_second_and_memo_do_not_merge_transactions_with_other_differences():
    first = normalized_row()
    second = normalized_row(debit=Decimal("500.00"), balance=Decimal("99500.00"))

    assert first["transaction_time"] == second["transaction_time"]
    assert first["memo"] == second["memo"]
    assert build_dedup_fingerprint(first) != build_dedup_fingerprint(second)


def test_ignored_descriptive_fields_do_not_change_fingerprint():
    changed = normalized_row(
        currency="USD",
        counterparty_name="不同姓名",
        counterparty_account="9999",
        warnings=["source_note"],
    )

    assert build_dedup_fingerprint(normalized_row()) == build_dedup_fingerprint(changed)


def test_input_is_validated_and_not_mutated():
    row = normalized_row()
    original = deepcopy(row)

    build_dedup_fingerprint(row)

    assert row == original
    with pytest.raises(ValueError, match="source_row"):
        build_dedup_fingerprint(normalized_row(source_row=0))

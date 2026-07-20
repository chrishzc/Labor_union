from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from scripts.imports.finance_formats.taishin import (
    TAISHIN_HEADERS,
    normalize_taishin_rows,
)


SAMPLE = Path("document") / "資料庫、資料處理" / "台新範例對帳單.xlsx"
NORMALIZED_FIELDS = {
    "format_id",
    "source_file",
    "source_bank_account",
    "sheet_name",
    "source_row",
    "source_reference",
    "transaction_date",
    "transaction_time",
    "posting_date",
    "value_date",
    "debit",
    "credit",
    "direction",
    "balance",
    "currency",
    "summary",
    "memo",
    "counterparty_name",
    "counterparty_account",
    "cancellation_code",
    "bank_references",
    "warnings",
    "raw_payload",
}


def _write_statement(tmp_path, data_rows, *, preamble_rows=2):
    path = tmp_path / "任意檔名.xlsx"
    rows = [["說明"]] * preamble_rows + [list(TAISHIN_HEADERS)] + data_rows
    pd.DataFrame(rows).to_excel(path, sheet_name="任意工作表", index=False, header=False)
    return path, preamble_rows + 1


def _data_row(*, debit="", credit="1,200.00", memo="對象,0012345678901234"):
    return [
        "0001",
        "2026/07/15",
        "09:08:07",
        "2026/07/15",
        "轉帳",
        debit,
        credit,
        "9,000.00",
        memo,
    ]


def test_real_sample_uses_detected_header_and_extracts_only_proven_account_shape():
    rows = normalize_taishin_rows(SAMPLE, "交易明細查詢", 16)

    assert len(rows) == 1
    row = rows[0]
    assert set(row) == NORMALIZED_FIELDS
    assert row["format_id"] == "taishin"
    assert row["source_row"] == 17
    assert row["direction"] in {"incoming", "outgoing"}
    assert isinstance(row["debit"], (Decimal, type(None)))
    assert isinstance(row["credit"], (Decimal, type(None)))
    assert row["memo"] == row["raw_payload"]["備註"]
    assert row["counterparty_account"] is not None
    assert row["counterparty_account"].isascii()
    assert row["counterparty_account"].isdigit()
    assert len(row["counterparty_account"]) == 16


def test_header_position_and_filename_are_not_fixed(tmp_path):
    path, header_row = _write_statement(tmp_path, [_data_row()], preamble_rows=4)

    [row] = normalize_taishin_rows(path, "任意工作表", header_row)

    assert row["source_row"] == header_row + 1
    assert row["transaction_date"] == "2026-07-15"
    assert row["transaction_time"] == "09:08:07"
    assert row["posting_date"] == "2026-07-15"
    assert row["credit"] == Decimal("1200.00")
    assert row["balance"] == Decimal("9000.00")
    assert row["direction"] == "incoming"
    assert row["bank_references"] == {"sequence": "0001"}
    assert row["raw_payload"]["備註"] == "對象,0012345678901234"


@pytest.mark.parametrize(
    ("memo", "warning"),
    [
        ("沒有帳號", "account_not_found"),
        ("0012345678901234、0098765432109876", "account_ambiguous"),
        ("12345678901234567", "account_not_found"),
    ],
)
def test_missing_ambiguous_or_unproven_account_shapes_are_not_guessed(tmp_path, memo, warning):
    path, header_row = _write_statement(tmp_path, [_data_row(memo=memo)])

    [row] = normalize_taishin_rows(path, "任意工作表", header_row)

    assert row["counterparty_account"] is None
    assert warning in row["warnings"]
    assert row["memo"] == memo


@pytest.mark.parametrize(
    ("debit", "credit", "direction", "warning"),
    [
        ("800", "", "outgoing", None),
        ("", "800", "incoming", None),
        ("800", "800", "unknown", "direction_ambiguous"),
        ("", "", "unknown", "direction_missing"),
    ],
)
def test_direction_uses_only_debit_and_credit(tmp_path, debit, credit, direction, warning):
    path, header_row = _write_statement(
        tmp_path,
        [_data_row(debit=debit, credit=credit)],
    )

    [row] = normalize_taishin_rows(path, "任意工作表", header_row)

    assert row["direction"] == direction
    if warning is None:
        assert not any(item.startswith("direction_") for item in row["warnings"])
    else:
        assert warning in row["warnings"]


def test_missing_required_header_is_rejected(tmp_path):
    headers = list(TAISHIN_HEADERS)
    headers.remove("備註")
    path = tmp_path / "missing.xlsx"
    pd.DataFrame([headers, _data_row()[:-1]]).to_excel(
        path,
        sheet_name="交易明細查詢",
        index=False,
        header=False,
    )

    with pytest.raises(ValueError, match="missing Taishin headers"):
        normalize_taishin_rows(path, "交易明細查詢", 1)


def test_adapter_does_not_emit_business_event_classification(tmp_path):
    path, header_row = _write_statement(
        tmp_path,
        [_data_row(memo="新竹市政府,0012345678901234")],
    )

    [row] = normalize_taishin_rows(path, "任意工作表", header_row)

    assert set(row) == NORMALIZED_FIELDS
    assert "event_type" not in row
    assert "government_subsidy" not in row

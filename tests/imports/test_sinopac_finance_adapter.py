from decimal import Decimal
from pathlib import Path

import pandas as pd

from scripts.imports.finance_formats import sinopac
from scripts.imports.finance_formats.sinopac import normalize_sinopac_rows


SAMPLE = Path("document") / "資料庫、資料處理" / "永豐範例對帳單.xlsx"


def test_normalizes_real_sinopac_sample_without_guessing_account_or_reference():
    rows = normalize_sinopac_rows(SAMPLE, "交易明細報表", 3)

    assert len(rows) == 1
    row = rows[0]
    assert row["format_id"] == "sinopac"
    assert row["source_row"] == 4
    assert row["source_bank_account"] == "03201800231313"
    assert row["source_reference"] is None
    assert row["transaction_date"] == "2026-07-13"
    assert row["transaction_time"] == "13:31:00"
    assert row["posting_date"] == "2026-07-13"
    assert row["value_date"] == "2026-07-13"
    assert row["debit"] is None
    assert row["credit"] == Decimal("36000")
    assert row["direction"] == "incoming"
    assert row["balance"] == Decimal("3153133")
    assert row["currency"] == "TWD"
    assert row["summary"] == "跨行轉帳"
    assert row["memo"] == "8220000060540432000"
    assert row["counterparty_name"] is None
    assert row["counterparty_account"] is None
    assert row["warnings"] == []


def test_preserves_all_headers_and_bank_references_as_strings():
    row = normalize_sinopac_rows(SAMPLE, "交易明細報表", 3)[0]

    assert len(row["raw_payload"]) == 15
    assert set(row["raw_payload"]) == {
        "帳號", "交易日 ", "計息日 ", "入帳日 ", "摘要", "幣別", "支出",
        "存入", "餘額", "票據號碼", "銷帳編號", "交易參考編號", "備註",
        "更正註記", "存摺備註",
    }
    assert row["bank_references"] == {
        "票據號碼": None,
        "銷帳編號": "99781699114092",
        "交易參考編號": None,
        "存摺備註": "99114092",
    }
    assert row["raw_payload"]["銷帳編號"] == "99781699114092"
    assert row["raw_payload"]["備註"] == "8220000060540432000"


def test_outgoing_preserves_both_notes_but_never_guesses_account(monkeypatch):
    headers = list(sinopac.SINOPAC_HEADERS)
    values = [
        "03201800231313",
        "2026-07-14 09:10:11",
        "2026-07-14",
        "2026-07-14",
        "跨行轉帳",
        "TWD",
        Decimal("1234"),
        None,
        Decimal("9999"),
        None,
        None,
        None,
        "  服務人員王小明／帳號 001234567890  ",
        None,
        "薪資轉帳 001234567890",
    ]
    frame = pd.DataFrame([headers, values], dtype=object)
    monkeypatch.setattr(sinopac.pd, "read_excel", lambda *args, **kwargs: frame)

    row = normalize_sinopac_rows("arbitrary-name.xlsx", "任意工作表", 1)[0]

    assert row["direction"] == "outgoing"
    assert row["debit"] == Decimal("1234")
    assert row["memo"] == "  服務人員王小明／帳號 001234567890  "
    assert row["bank_references"]["存摺備註"] == "薪資轉帳 001234567890"
    assert row["raw_payload"]["備註"] == "  服務人員王小明／帳號 001234567890  "
    assert row["raw_payload"]["存摺備註"] == "薪資轉帳 001234567890"
    assert row["counterparty_account"] is None
    assert row["counterparty_name"] is None
    assert row["warnings"] == []


def test_only_direction_ambiguity_is_warned(monkeypatch):
    headers = list(sinopac.SINOPAC_HEADERS)
    values = [
        "03201800231313", "2026-07-14", None, None, "摘要", "TWD",
        Decimal("1"), Decimal("1"), Decimal("100"), None, None, None,
        "1234567890", None, "1234567890",
    ]
    frame = pd.DataFrame([headers, values], dtype=object)
    monkeypatch.setattr(sinopac.pd, "read_excel", lambda *args, **kwargs: frame)

    row = normalize_sinopac_rows("anything.xlsx", "sheet", 1)[0]

    assert row["direction"] == "unknown"
    assert row["counterparty_account"] is None
    assert row["warnings"] == ["direction_ambiguous"]
    assert "account_rule_unconfirmed" not in row["warnings"]


def test_missing_debit_and_credit_is_warned_as_direction_missing(monkeypatch):
    headers = list(sinopac.SINOPAC_HEADERS)
    values = [
        "03201800231313", "2026-07-14", None, None, "測試", "TWD",
        None, None, Decimal("100"), None, None, None,
        "1234567890", None, "1234567890",
    ]
    frame = pd.DataFrame([headers, values], dtype=object)
    monkeypatch.setattr(sinopac.pd, "read_excel", lambda *args, **kwargs: frame)

    row = normalize_sinopac_rows("anything.xlsx", "sheet", 1)[0]

    assert row["direction"] == "unknown"
    assert row["warnings"] == ["direction_missing"]

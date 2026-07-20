from pathlib import Path
from shutil import copyfile

import pytest

from scripts.imports import finance_statement_normalizer as pipeline


SAMPLES = Path("document") / "資料庫、資料處理"
NORMALIZED_ROW_FIELDS = {
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


@pytest.mark.parametrize(
    ("filename", "format_id", "sheet_name", "header_row"),
    [
        ("歷史對帳單.xlsx", "legacy", "永豐3131(虛擬)", 3),
        ("台新範例對帳單.xlsx", "taishin", "交易明細查詢", 16),
        ("永豐範例對帳單.xlsx", "sinopac", "交易明細報表", 3),
    ],
)
def test_normalizes_real_workbooks_to_one_contract(filename, format_id, sheet_name, header_row):
    result = pipeline.normalize_workbook(SAMPLES / filename)

    assert result["format_id"] == format_id
    assert result["sheet_name"] == sheet_name
    assert result["header_row"] == header_row
    assert result["normalized_rows"]
    for row in result["normalized_rows"]:
        assert set(row) == set(NORMALIZED_ROW_FIELDS)
        assert row["format_id"] == format_id
        assert row["sheet_name"] == sheet_name
        assert "event_type" not in row


def test_pipeline_does_not_depend_on_filename(tmp_path):
    renamed = tmp_path / "完全任意的名稱.xlsx"
    copyfile(SAMPLES / "台新範例對帳單.xlsx", renamed)

    result = pipeline.normalize_workbook(renamed)

    assert result["format_id"] == "taishin"
    assert result["sheet_name"] == "交易明細查詢"


def test_detector_result_selects_exactly_one_adapter_and_revalidates(monkeypatch):
    calls = []
    source_row = {field: None for field in NORMALIZED_ROW_FIELDS}
    source_row.update(
        {
            "format_id": "taishin",
            "source_file": "input.xlsx",
            "sheet_name": "sheet",
            "source_row": 2,
            "direction": "unknown",
            "bank_references": {},
            "warnings": ["direction_missing"],
            "raw_payload": {},
        }
    )

    monkeypatch.setattr(
        pipeline,
        "detect_statement_format",
        lambda path: {"format_id": "taishin", "sheet_name": "sheet", "header_row": 1},
    )

    def selected_adapter(path, sheet_name, header_row):
        calls.append(("adapter", path, sheet_name, header_row))
        return [source_row]

    monkeypatch.setitem(pipeline.FORMAT_ADAPTERS, "taishin", selected_adapter)
    monkeypatch.setattr(
        pipeline,
        "validate_normalized_row",
        lambda row: calls.append(("validator", row)) or row,
    )

    result = pipeline.normalize_workbook("input.xlsx")

    assert calls == [
        ("adapter", "input.xlsx", "sheet", 1),
        ("validator", source_row),
    ]
    assert result["normalized_rows"] == [source_row]


def test_empty_adapter_result_preserves_detection_metadata(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "detect_statement_format",
        lambda path: {"format_id": "legacy", "sheet_name": "data", "header_row": 7},
    )
    monkeypatch.setitem(pipeline.FORMAT_ADAPTERS, "legacy", lambda *args: [])

    result = pipeline.normalize_workbook("empty.xlsx")

    assert result == {
        "format_id": "legacy",
        "sheet_name": "data",
        "header_row": 7,
        "normalized_rows": [],
    }


def test_unknown_detector_format_has_no_fallback(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "detect_statement_format",
        lambda path: {"format_id": "unknown", "sheet_name": "sheet", "header_row": 1},
    )

    with pytest.raises(ValueError, match="unsupported detected finance format"):
        pipeline.normalize_workbook("input.xlsx")


def test_pipeline_source_has_no_database_or_business_classifier_imports():
    source = Path("scripts/imports/finance_statement_normalizer.py").read_text(encoding="utf-8")

    assert "db_service" not in source
    assert "get_connection" not in source
    assert "event_classifier" not in source
    assert "government_subsidy" not in source

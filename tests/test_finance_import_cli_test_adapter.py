"""
File: test_finance_import_cli_test_adapter.py
Description: 驗證帳務 CLI 預覽預設與受控建立批次邊界。
"""

from __future__ import annotations

import pytest

from scripts.imports import import_finance_excel as cli


def test_cli_apply_is_retired_before_any_typed_ingestion(tmp_path, monkeypatch):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    monkeypatch.setattr(cli, "_dry_run_manifest", lambda *_: (_ for _ in ()).throw(AssertionError()))

    with pytest.raises(RuntimeError, match="finance_import_cli_apply_retired"):
        cli.main(["--excel-path", str(workbook), "--apply"])


def test_cli_preview_never_calls_typed_ingestion(tmp_path, monkeypatch):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    monkeypatch.setattr(cli, "normalize_workbook", lambda _: {"format_id": "taishin", "normalized_rows": []})

    assert not hasattr(cli, "ingest_finance_workbook")
    assert cli.main(["--excel-path", str(workbook)]) == 0


def test_cli_apply_remains_retired_even_with_database_confirmation(tmp_path):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    with pytest.raises(RuntimeError, match="finance_import_cli_apply_retired"):
        cli.main(["--excel-path", str(workbook), "--apply", "--confirm-database", "candidate_history"])

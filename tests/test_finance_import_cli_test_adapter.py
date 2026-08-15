"""
File: test_finance_import_cli_test_adapter.py
Description: 驗證帳務 CLI 預覽預設與受控建立批次邊界。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.imports import import_finance_excel as cli


def test_cli_apply_uses_confirmed_operator_identity(tmp_path, monkeypatch):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    calls = []
    receipt = SimpleNamespace(
        batch_identity="finance-import-batch:9",
        canonical_created_count=3,
        duplicate_occurrence_count=1,
    )
    monkeypatch.setattr(cli, "ingest_finance_workbook", lambda *args: calls.append(args) or receipt)

    monkeypatch.setenv("DB_DATABASE", "candidate_history")
    assert cli.main(
        [
            "--excel-path", str(workbook), "--apply",
            "--confirm-database", "candidate_history",
        ]
    ) == 0

    path, key, actor = calls[0]
    assert path == str(workbook.resolve())
    assert key.value.startswith("finance-import-cli-operator:")
    assert actor.actor_id == "finance-import-cli-operator"


def test_cli_preview_never_calls_typed_ingestion(tmp_path, monkeypatch):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    monkeypatch.setattr(cli, "ingest_finance_workbook", lambda *_: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(cli, "normalize_workbook", lambda _: {"format_id": "taishin", "normalized_rows": []})

    assert cli.main(["--excel-path", str(workbook)]) == 0


def test_cli_apply_requires_configured_database_confirmation(tmp_path, monkeypatch):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    monkeypatch.setenv("DB_DATABASE", "candidate_history")

    with pytest.raises(RuntimeError, match="finance_import_database_confirmation_required"):
        cli.main(["--excel-path", str(workbook), "--apply"])

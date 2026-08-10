from __future__ import annotations

from types import SimpleNamespace

from scripts.imports import import_finance_excel as cli


def test_cli_uses_typed_ingestion_with_stable_test_identity(tmp_path, monkeypatch):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    calls = []
    receipt = SimpleNamespace(
        batch_identity="finance-import-batch:9",
        canonical_created_count=3,
        duplicate_occurrence_count=1,
    )
    monkeypatch.setattr(cli, "ingest_finance_workbook", lambda *args: calls.append(args) or receipt)

    assert cli.main(["--excel-path", str(workbook)]) == 0

    path, key, actor = calls[0]
    assert path == str(workbook.resolve())
    assert key.value.startswith("finance-import-cli-test:")
    assert actor.actor_id == "finance-import-cli-test"


def test_cli_dry_run_never_calls_typed_ingestion(tmp_path, monkeypatch):
    workbook = tmp_path / "bank.xlsx"
    workbook.write_bytes(b"test bank statement")
    monkeypatch.setattr(cli, "ingest_finance_workbook", lambda *_: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(cli, "normalize_workbook", lambda _: {"format_id": "taishin", "normalized_rows": []})

    assert cli.main(["--excel-path", str(workbook), "--dry-run"]) == 0

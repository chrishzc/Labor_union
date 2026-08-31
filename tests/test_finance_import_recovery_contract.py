"""Current behavioral contracts for finance import recovery surfaces."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domains.finance_import.transaction_classifier import classify_finance_transaction
from scripts.imports.finance_statement_normalizer import normalize_workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_FIXTURE = (
    PROJECT_ROOT / "document" / "資料庫、資料處理" / "歷史對帳單.xlsx"
)


def _captured_summary(
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert captured.err == ""
    assert len(lines) == 1
    assert len(lines[0].encode("utf-8")) < 4096
    forbidden = (
        "row_results",
        "raw_payload",
        "張淑婷",
        "12345678901234",
        "secret",
    )
    assert all(token not in lines[0] for token in forbidden)
    decoded = json.loads(lines[0])
    assert isinstance(decoded, dict)
    return decoded


def _strict_json_report(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    assert raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    forbidden = (
        "raw_payload",
        "張淑婷",
        "12345678901234",
        "secret",
    )
    assert all(token not in text for token in forbidden)
    decoded = json.loads(text)
    assert isinstance(decoded, dict)
    return decoded


def test_repository_fixture_is_one_row_and_never_uses_name_as_identity() -> None:
    normalized = normalize_workbook(str(REPOSITORY_FIXTURE))

    assert normalized["format_id"] == "legacy"
    assert len(normalized["normalized_rows"]) == 1
    row = normalized["normalized_rows"][0]
    result = classify_finance_transaction(row, {}, {})
    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_staff_account_no_match",
    }
    assert row.get("counterparty_name") is None


def test_read_only_cli_stdout_and_reports_are_bounded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.imports import import_finance_excel as import_cli
    from scripts.imports import reprocess_finance_import_batch as reprocess_cli

    workbook = tmp_path / "fixture.xlsx"
    workbook.write_bytes(b"CLI service is monkeypatched; workbook is not read")
    import_report = tmp_path / "import-report.json"
    normalized_workbook = {"format_id": "legacy", "normalized_rows": [{}]}
    import_calls = 0

    def fake_normalize(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal import_calls
        import_calls += 1
        return normalized_workbook

    monkeypatch.setattr(import_cli, "normalize_workbook", fake_normalize)
    assert import_cli.main(["--excel-path", str(workbook), "--dry-run"]) == 0
    import_summary = _captured_summary(capsys)
    assert import_summary["pending_count"] == 0
    assert import_summary["report_path"] is None
    assert not import_report.exists()

    assert import_cli.main(
        [
            "--excel-path",
            str(workbook),
            "--dry-run",
            "--report-path",
            str(import_report),
        ]
    ) == 0
    reported_import_summary = _captured_summary(capsys)
    assert reported_import_summary["report_path"] == str(import_report.resolve())
    import_payload = _strict_json_report(import_report)
    assert import_payload["format_manifest"]["normalized_row_count"] == 1
    assert import_calls == 2

    reprocess_report = tmp_path / "reprocess-report.json"
    reprocess_result = {
        "db_identity": {
            "database": "finance_recovery_simulation",
            "server": "mysql-test",
        },
        "batch_manifest": {"batch_id": 1},
        "classification_summary": {
            "selected": 2655,
            "unchanged": 2376,
            "changed": 279,
            "before_reason_counts": {
                "sinopac_invalid_or_missing_virtual_account": 2058,
                "sinopac_staff_account_no_match": 597,
            },
            "after_reason_counts": {
                "sinopac_invalid_or_missing_virtual_account": 1779,
                "sinopac_staff_account_no_match": 597,
                "sinopac_valid_virtual_account": 279,
            },
        },
        "dispatch_summary": {
            "attempted": 279,
            "reconciled": 0,
            "pending": 279,
            "bounded_references": [],
        },
        "alert_action": {
            "alert_action": "updated",
            "summary": {"remaining_count": 2376},
        },
        "elapsed_seconds": 1.0,
        "rows_per_second": 2655.0,
        "plan_fingerprint": "b" * 64,
        "transaction_outcome": "rolled_back",
        "run_id": None,
    }
    reprocess_calls = 0

    def fake_reprocess(
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        nonlocal reprocess_calls
        reprocess_calls += 1
        return reprocess_result

    monkeypatch.setattr(
        reprocess_cli,
        "reprocess_finance_import_batch",
        fake_reprocess,
    )

    read_only_target = [
        "--target-database",
        "finance_recovery_simulation",
        "--expected-host",
        "mysql-test-host",
        "--expected-server",
        "mysql-test",
        "--schema-fingerprint",
        "a" * 64,
    ]
    assert reprocess_cli.main(["--batch-id", "1", *read_only_target]) == 0
    reprocess_summary = _captured_summary(capsys)
    assert reprocess_summary["selected"] == 2655
    assert reprocess_summary["report_path"] is None
    assert not reprocess_report.exists()

    assert reprocess_cli.main(
        [
            "--batch-id",
            "1",
            *read_only_target,
            "--report-path",
            str(reprocess_report),
        ]
    ) == 0
    reported_reprocess_summary = _captured_summary(capsys)
    assert reported_reprocess_summary["report_path"] == str(
        reprocess_report.resolve()
    )
    reprocess_payload = _strict_json_report(reprocess_report)
    assert "row_results" not in reprocess_payload
    assert reprocess_calls == 2

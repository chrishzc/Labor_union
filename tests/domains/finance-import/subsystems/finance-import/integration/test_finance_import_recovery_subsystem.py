"""Final subsystem contract for finance import recovery.

Applying a historical plan remains an explicit operator command after its
dry-run fingerprint has been reviewed.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts.imports.finance_statement_normalizer import normalize_workbook
from domains.finance_import.transaction_classifier import classify_finance_transaction


PROJECT_ROOT = Path(__file__).resolve().parents[6]
ROOT = PROJECT_ROOT
REPOSITORY_FIXTURE = (
    PROJECT_ROOT / "document" / "資料庫、資料處理" / "歷史對帳單.xlsx"
)
APPLICATION_SOURCE = PROJECT_ROOT / "subsystems" / "finance_import" / "application.py"
REPROCESS_SOURCE = PROJECT_ROOT / "subsystems" / "finance_import" / "reprocessing.py"
IMPORT_CLI_SOURCE = (
    PROJECT_ROOT / "scripts" / "imports" / "import_finance_excel.py"
)
REPROCESS_CLI_SOURCE = (
    PROJECT_ROOT / "scripts" / "imports" / "reprocess_finance_import_batch.py"
)
ASUS_OCCURRENCE_COUNT = 2659
ASUS_DISTINCT_COUNT = 2655
ASUS_INCOMING_COUNT = 2058
ASUS_OUTGOING_COUNT = 597
ASUS_VALID_VIRTUAL_ACCOUNT_COUNT = 279
ASUS_REMAINING_REVIEW_COUNT = 2376


def _strict_source(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    return text


def _imported_names(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(_strict_source(path))
    names: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        names.update((node.module, alias.name) for alias in node.names)
    return names


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


def test_legacy_reprocess_is_diagnostic_only() -> None:
    expected = (
        "subsystems.finance_import.reconciliation_dispatch",
        "dispatch_finance_import_row",
    )

    assert expected in _imported_names(APPLICATION_SOURCE)
    assert "dispatch_finance_import_row" not in _strict_source(REPROCESS_SOURCE)
    for cli_path in (IMPORT_CLI_SOURCE, REPROCESS_CLI_SOURCE):
        cli_source = _strict_source(cli_path)
        assert "dispatch_finance_import_row" not in cli_source
        assert "_dispatch_inserted_row" not in cli_source
        assert "_staff_transfer_candidates" not in cli_source


def test_asus_batch_contract_counts_are_distinct_from_repository_fixture() -> None:
    occurrence_count = 2659
    distinct_count = 2655
    incoming_before = 2058
    outgoing_before = 597
    changed = 279
    remaining = distinct_count - changed

    assert occurrence_count - distinct_count == 4
    assert incoming_before + outgoing_before == distinct_count
    assert remaining == 2376
    assert incoming_before - changed == 1779
    assert 1779 + outgoing_before == remaining
    assert len(normalize_workbook(str(REPOSITORY_FIXTURE))["normalized_rows"]) == 1


def test_recovery_sources_preserve_plan_replay_and_bounded_output_contracts() -> None:
    reprocess = _strict_source(REPROCESS_SOURCE)
    reprocess_cli = _strict_source(REPROCESS_CLI_SOURCE)
    import_cli = _strict_source(IMPORT_CLI_SOURCE)

    assert "expected_plan_fingerprint" in reprocess
    assert "transaction_outcome" in reprocess
    assert "legacy_finance_import_reprocess_apply_retired" in reprocess
    assert "finance_import_reclassification_events" not in reprocess
    assert "project_finance_import_review_alert" not in reprocess
    assert "row_results" not in reprocess_cli
    assert "raw_payload" not in reprocess_cli
    assert "raw_payload" not in import_cli


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


def test_bounded_cli_stdout_reports_and_apply_prevalidation(
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
    assert reported_import_summary["report_path"] == str(
        import_report.resolve()
    )
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
            "selected": ASUS_DISTINCT_COUNT,
            "unchanged": ASUS_REMAINING_REVIEW_COUNT,
            "changed": ASUS_VALID_VIRTUAL_ACCOUNT_COUNT,
            "before_reason_counts": {
                "sinopac_invalid_or_missing_virtual_account": (
                    ASUS_INCOMING_COUNT
                ),
                "sinopac_staff_account_no_match": ASUS_OUTGOING_COUNT,
            },
            "after_reason_counts": {
                "sinopac_invalid_or_missing_virtual_account": 1779,
                "sinopac_staff_account_no_match": ASUS_OUTGOING_COUNT,
                "sinopac_valid_virtual_account": (
                    ASUS_VALID_VIRTUAL_ACCOUNT_COUNT
                ),
            },
        },
        "dispatch_summary": {
            "attempted": ASUS_VALID_VIRTUAL_ACCOUNT_COUNT,
            "reconciled": 0,
            "pending": ASUS_VALID_VIRTUAL_ACCOUNT_COUNT,
            "bounded_references": [],
        },
        "alert_action": {
            "alert_action": "updated",
            "summary": {
                "remaining_count": ASUS_REMAINING_REVIEW_COUNT,
            },
        },
        "elapsed_seconds": 1.0,
        "rows_per_second": float(ASUS_DISTINCT_COUNT),
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
    with pytest.raises(
        ValueError,
        match="legacy_finance_import_reprocess_apply_retired",
    ):
        reprocess_cli.main(["--batch-id", "1", "--apply"])
    assert reprocess_calls == 0
    assert capsys.readouterr().out == ""

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
    assert reprocess_summary["selected"] == ASUS_DISTINCT_COUNT
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

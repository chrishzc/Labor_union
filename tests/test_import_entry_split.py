"""
File: test_import_entry_split.py
Description: 驗證匯入入口隔離、明確確認與來源版本鍵。
"""

from pathlib import Path

from scripts import file_watcher
from scripts.imports.historical_import_guard import authorize_historical_apply
from scripts.imports import import_client_hcm
from scripts.imports.import_staff_beclass import _staff_source_content_digest
import pytest


def test_file_watcher_excludes_hcm_and_beclass_current_writers():
    scripts = {entry.script_path for entry in file_watcher.WATCHED_IMPORTS}

    assert "scripts/imports/import_client_hcm.py" not in scripts
    assert "scripts/imports/import_client_beclass.py" not in scripts
    assert "scripts/imports/import_staff_beclass.py" not in scripts
    assert scripts == {"scripts/imports/import_finance_excel.py"}


def test_liff_browser_sources_do_not_contain_database_credentials_or_sql():
    line_static = Path("line/static")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in line_static.glob("*.html")
    ).lower()

    assert "db_password" not in source
    assert "pymysql" not in source
    assert "insert into" not in source
    assert "update staff set" not in source


def test_historical_import_requires_explicit_apply_and_target(monkeypatch):
    monkeypatch.delenv("HISTORICAL_IMPORT_ALLOWED_DATABASES", raising=False)
    with pytest.raises(RuntimeError, match="historical_import_apply_flag_required"):
        authorize_historical_apply(["history.xlsx"], "candidate_history")

    monkeypatch.setenv("HISTORICAL_IMPORT_ALLOWED_DATABASES", "other_candidate")
    with pytest.raises(RuntimeError, match="historical_import_database_target_not_allowed"):
        authorize_historical_apply(
            ["--historical-apply", "history.xlsx"],
            "candidate_history",
        )


def test_historical_import_returns_source_only_for_allowlisted_target(monkeypatch):
    monkeypatch.setenv(
        "HISTORICAL_IMPORT_ALLOWED_DATABASES",
        "candidate_history",
    )

    assert authorize_historical_apply(
        ["--historical-apply", "history.xlsx"],
        "candidate_history",
    ) == "history.xlsx"


def test_hcm_cli_requires_explicit_apply_and_matching_database(monkeypatch):
    monkeypatch.setenv("DB_DATABASE", "candidate_history")
    with pytest.raises(RuntimeError, match="hcm_import_apply_flag_required"):
        import_client_hcm._parse_hcm_apply_arguments(["history.xlsx"])
    with pytest.raises(RuntimeError, match="hcm_import_database_confirmation_required"):
        import_client_hcm._parse_hcm_apply_arguments(
            ["--apply", "--confirm-database", "wrong", "history.xlsx"]
        )
    assert import_client_hcm._parse_hcm_apply_arguments(
        ["--apply", "--confirm-database", "candidate_history", "history.xlsx"]
    ) == "history.xlsx"


def test_staff_source_revision_creates_a_new_deterministic_source_identity(tmp_path):
    workbook = tmp_path / "staff.xlsx"
    workbook.write_bytes(b"same historical export")

    original_digest = _staff_source_content_digest(str(workbook), None)
    refresh_digest = _staff_source_content_digest(str(workbook), "refresh-20260813")

    assert refresh_digest != original_digest
    assert refresh_digest == _staff_source_content_digest(str(workbook), "refresh-20260813")


def test_staff_source_revision_rejects_unbounded_operator_value(tmp_path):
    workbook = tmp_path / "staff.xlsx"
    workbook.write_bytes(b"same historical export")

    with pytest.raises(ValueError, match="staff_historical_source_revision_invalid"):
        _staff_source_content_digest(str(workbook), "refresh with spaces")

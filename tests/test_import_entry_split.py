from pathlib import Path

from scripts import file_watcher
from scripts.imports.historical_import_guard import authorize_historical_apply
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

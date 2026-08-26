"""
File: test_update_local_database_entrypoint.py
Description: 驗證本機保留資料升級 launcher 的明確確認與來源傳遞契約。
"""

from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "launchers"
    / "update_local_database.bat"
).read_text(encoding="utf-8")


def test_double_click_previews_before_preserve_data_update() -> None:
    assert SCRIPT.index("-m scripts.update_local_database\n") < SCRIPT.index(
        "--apply --confirm-configured-database"
    )
    assert "Type UPDATE to continue" in SCRIPT


def test_launcher_dry_run_only_checks_wiring() -> None:
    dry_run_start = SCRIPT.index('if /I "%~1"=="--dry-run"')
    argument_forward_start = SCRIPT.index('if not "%~1"==""', dry_run_start)
    dry_run_block = SCRIPT[dry_run_start:argument_forward_start]
    assert "scripts.launcher_preflight --profile database-update" in dry_run_block
    assert "scripts.update_local_database" not in dry_run_block


def test_update_reports_restart_requirement() -> None:
    assert "Restart local services" in SCRIPT


def test_update_reads_the_configured_database_for_confirmation() -> None:
    assert "--confirm-configured-database" in SCRIPT
    assert "--confirm-database union_db" not in SCRIPT
    assert "replace DB_DATABASE" not in SCRIPT

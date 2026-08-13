from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "launchers"
    / "update_local_database.bat"
).read_text(encoding="utf-8")


def test_double_click_previews_before_preserve_data_update() -> None:
    assert SCRIPT.index("-m scripts.update_local_database\n") < SCRIPT.index(
        "--apply --confirm-database"
    )
    assert "Type UPDATE to continue" in SCRIPT


def test_update_reports_restart_requirement() -> None:
    assert "Restart local services" in SCRIPT


def test_update_keeps_union_db_name() -> None:
    assert "--confirm-database union_db" in SCRIPT
    assert "replace DB_DATABASE" not in SCRIPT

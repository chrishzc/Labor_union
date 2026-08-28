from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "launchers" / "reset_DB.bat"
).read_text(encoding="utf-8")


def test_double_click_is_confirmed_canonical_empty_reset():
    assert "current canonical schema" in SCRIPT
    assert "no business fixture is loaded" in SCRIPT
    assert "-m scripts.reset_fake_database --apply --confirm-database union_db" in SCRIPT
    assert "Type RESET to continue" in SCRIPT


def test_exit_code_uses_delayed_expansion():
    assert "EnableDelayedExpansion" in SCRIPT and "!RESET_EXIT!" in SCRIPT


def test_reset_runs_preflight_before_destructive_apply():
    assert SCRIPT.index("-m scripts.reset_fake_database\n") < SCRIPT.index(
        "--apply --confirm-database union_db"
    )

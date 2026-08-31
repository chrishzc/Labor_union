from pathlib import Path


SCRIPT = (
    Path(__file__).parents[7] / "scripts" / "launchers" / "reset_DB.bat"
).read_text(encoding="utf-8")


def test_launcher_restores_operator_union_db_reset_and_delegates_targets():
    assert "--operator-reset --target-database union_db" in SCRIPT
    assert "Type RESET to continue" in SCRIPT
    assert "--confirm-apply RESET" in SCRIPT
    assert "-m scripts.reset_fake_database %*" in SCRIPT


def test_exit_code_uses_delayed_expansion():
    assert "EnableDelayedExpansion" in SCRIPT and "!RESET_EXIT!" in SCRIPT


def test_reset_runs_preflight_before_destructive_apply():
    assert SCRIPT.index("--profile database-reset") < SCRIPT.index(
        "--apply --confirm-apply RESET"
    )

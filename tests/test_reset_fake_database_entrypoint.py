from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "launchers" / "reset_DB.bat"
).read_text(encoding="utf-8")


def test_launcher_requires_an_explicit_disposable_target_and_delegates():
    assert "--target-database lu_test_name" in SCRIPT
    assert "-m scripts.reset_fake_database %*" in SCRIPT
    assert "union_db" not in SCRIPT


def test_exit_code_uses_delayed_expansion():
    assert "EnableDelayedExpansion" in SCRIPT and "!RESET_EXIT!" in SCRIPT


def test_reset_runs_preflight_before_destructive_apply():
    assert SCRIPT.index("--profile database-reset") < SCRIPT.index(
        "-m scripts.reset_fake_database %*"
    )

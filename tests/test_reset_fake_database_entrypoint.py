from pathlib import Path
SCRIPT=(Path(__file__).parents[1]/"reset_DB.bat").read_text(encoding="utf-8")
def test_double_click_is_v3_confirmed_reset():
    assert "fixed v3 fixture" in SCRIPT
    assert "--apply --confirm-database union_db" in SCRIPT
def test_exit_code_uses_delayed_expansion():
    assert "EnableDelayedExpansion" in SCRIPT and "!RESET_EXIT!" in SCRIPT

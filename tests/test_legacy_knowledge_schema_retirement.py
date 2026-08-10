from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def test_bootstrap_schema_does_not_recreate_retired_tables() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS faq" not in schema
    assert "CREATE TABLE IF NOT EXISTS crawler_logs" not in schema
    assert "CREATE TABLE IF NOT EXISTS staff_availability" not in schema
    assert not (
        PROJECT_ROOT / "db" / "schema_parts" / "99_data_browser_admin_audit_logs.sql"
    ).exists()

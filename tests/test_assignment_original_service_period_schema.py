from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema_parts" / "103_assignment_original_service_period.sql"


def test_assignment_original_period_migration_is_additive_and_immutable():
    sql = SCHEMA.read_text(encoding="utf-8")
    upper = sql.upper()
    assert "ORIGINAL_ASSIGNED_START_DATE" in upper
    assert "ORIGINAL_ASSIGNED_END_DATE" in upper
    assert "INFORMATION_SCHEMA.COLUMNS" in upper
    assert "COALESCE(ORIGINAL_ASSIGNED_START_DATE, ASSIGNED_START_DATE)" in upper
    assert "COALESCE(ORIGINAL_ASSIGNED_END_DATE, ASSIGNED_END_DATE)" in upper
    assert "BEFORE INSERT ON CASE_STAFF_ASSIGNMENTS" in upper
    assert "BEFORE UPDATE ON CASE_STAFF_ASSIGNMENTS" in upper
    assert "NEW.ORIGINAL_ASSIGNED_START_DATE = OLD.ORIGINAL_ASSIGNED_START_DATE" in upper
    assert "NEW.ORIGINAL_ASSIGNED_END_DATE = OLD.ORIGINAL_ASSIGNED_END_DATE" in upper
    assert "DROP TABLE" not in upper
    assert "DELETE FROM" not in upper
    assert "TRUNCATE TABLE" not in upper

from pathlib import Path

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT / "db" / "schema_parts" / "96_order_assignment_sync_audit.sql"
)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _schema_sql():
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_declares_append_only_order_assignment_change_audit_table():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CREATETABLEIFNOTEXISTSorder_assignment_change_audits" in compact
    assert compact.count("JSONNOTNULL") == 3
    assert "applied_byVARCHAR(100)NOTNULL" in compact
    assert "applied_atTIMESTAMPNOTNULLDEFAULTCURRENT_TIMESTAMP" in compact
    assert "CHECK(CHAR_LENGTH(TRIM(applied_by))>0)" in compact


def test_links_audit_rows_to_one_existing_order_and_indexes_history():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert (
        "INDEXidx_order_assignment_change_audit_case_time(case_no,applied_at)"
        in compact
    )
    assert (
        "FOREIGNKEY(case_no)REFERENCESorders(case_no)"
        "ONUPDATERESTRICTONDELETERESTRICT"
    ) in compact


def test_migration_is_additive_and_replayable_by_schema_parts_loader():
    sql = _schema_sql().upper()
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "DROP TABLE" not in sql
    assert "TRUNCATE TABLE" not in sql

    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    loaded_parts = load_schema_parts(cursor, parts_dir)
    assert SCHEMA_PATH.name in loaded_parts
    first_run_statements = list(cursor.executed)
    assert any("order_assignment_change_audits" in statement for statement in first_run_statements)

    assert load_schema_parts(cursor, parts_dir) == loaded_parts
    assert cursor.executed == first_run_statements + first_run_statements

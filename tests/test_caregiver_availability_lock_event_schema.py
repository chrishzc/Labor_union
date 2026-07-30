from pathlib import Path

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT / "db" / "schema_parts" / "99b_caregiver_availability_lock_events.sql"
)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _schema_sql():
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_caregiver_availability_lock_events_table_structure():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CREATETABLEIFNOTEXISTSspotted_table" not in compact
    assert "CREATETABLEIFNOTEXISTS`caregiver_availability_lock_events`" in compact or "CREATETABLEIFNOTEXISTScaregiver_availability_lock_events" in compact
    assert "lock_idBIGINTNOTNULL" in compact
    assert "event_typeENUM('lock_acquired','lock_released','lock_converted','lock_cancelled')NOTNULL" in compact
    assert "event_keyVARCHAR(100)NOTNULL" in compact
    assert "actorVARCHAR(100)NOTNULL" in compact
    assert "reasonTEXTNULL" in compact
    assert "payloadJSONNOTNULL" in compact
    assert "occurred_atTIMESTAMPNOTNULLDEFAULTCURRENT_TIMESTAMP" in compact
    assert "uq_availability_lock_event_key(event_key)" in compact
    assert "FOREIGNKEY(lock_id)REFERENCEScaregiver_availability_locks(id)ONUPDATERESTRICTONDELETERESTRICT" in compact


def test_caregiver_availability_lock_events_check_constraints_strict():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CHECK((event_type='lock_acquired'ANDreasonISNULL)OR(event_typeIN('lock_released','lock_converted','lock_cancelled')ANDCHAR_LENGTH(TRIM(reason))>0))" in compact
    assert "CHECK(JSON_TYPE(payload)='OBJECT')" in compact
    assert "CHECK(CHAR_LENGTH(TRIM(event_key))>0ANDCHAR_LENGTH(TRIM(actor))>0)" in compact


def test_foreign_keys_forbid_on_delete_cascade():
    sql = _schema_sql().upper()
    assert "ON DELETE CASCADE" not in sql
    assert "ON DELETE RESTRICT" in sql or "ON DELETE NO ACTION" in sql


def test_schema_loader_extracts_two_complete_trigger_statements():
    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    load_schema_parts(cursor, parts_dir)

    trigger_stmts = [
        stmt for stmt in cursor.executed
        if "CREATE TRIGGER" in stmt and "caregiver_availability_lock_events" in stmt
    ]

    assert len(trigger_stmts) == 2, f"預期應擷取出 2 個完整的 CREATE TRIGGER 語句，實際：{len(trigger_stmts)}"

    for stmt in trigger_stmts:
        assert "DELIMITER" not in stmt
        assert "BEGIN" not in stmt
        assert "END IF" not in stmt
        assert stmt.strip().startswith("CREATE TRIGGER")

    update_stmt = next(s for s in trigger_stmts if "trg_caregiver_availability_lock_events_before_update" in s)
    assert "BEFORE UPDATE ON caregiver_availability_lock_events" in update_stmt
    assert "SIGNAL SQLSTATE '45000'" in update_stmt
    assert "caregiver_availability_lock_events records cannot be updated" in update_stmt

    delete_stmt = next(s for s in trigger_stmts if "trg_caregiver_availability_lock_events_before_delete" in s)
    assert "BEFORE DELETE ON caregiver_availability_lock_events" in delete_stmt
    assert "SIGNAL SQLSTATE '45000'" in delete_stmt
    assert "caregiver_availability_lock_events records cannot be deleted" in delete_stmt


def test_lexical_loading_order_after_availability_lock_schema():
    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    loaded_parts = load_schema_parts(cursor, parts_dir)

    assert "99a_caregiver_availability_locks.sql" in loaded_parts
    assert "99b_caregiver_availability_lock_events.sql" in loaded_parts

    idx_99a = loaded_parts.index("99a_caregiver_availability_locks.sql")
    idx_99b = loaded_parts.index("99b_caregiver_availability_lock_events.sql")

    assert idx_99a < idx_99b, f"載入順序必須為 99a < 99b，實際順序：{loaded_parts}"


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
    assert any("caregiver_availability_lock_events" in statement for statement in first_run_statements)

    assert load_schema_parts(cursor, parts_dir) == loaded_parts
    assert cursor.executed == first_run_statements + first_run_statements

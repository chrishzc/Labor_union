from pathlib import Path

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT / "db" / "schema_parts" / "99a_caregiver_availability_locks.sql"
)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _schema_sql():
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_caregiver_availability_locks_header_table_structure():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CREATETABLEIFNOTEXISTSspotted_table" not in compact
    assert "CREATETABLEIFNOTEXISTS`caregiver_availability_locks`" in compact or "CREATETABLEIFNOTEXISTScaregiver_availability_locks" in compact
    assert "plan_idBIGINTNOTNULL" in compact
    assert "statusENUM('active','released','converted','cancelled')NOTNULLDEFAULT'active'" in compact
    assert "is_activeTINYINT(1)NULL" in compact
    assert "created_byVARCHAR(100)NOTNULL" in compact
    assert "released_byVARCHAR(100)NULL" in compact
    assert "created_atTIMESTAMPNOTNULLDEFAULTCURRENT_TIMESTAMP" in compact
    assert "released_atTIMESTAMPNULL" in compact
    assert "updated_atTIMESTAMPNOTNULLDEFAULTCURRENT_TIMESTAMPONUPDATECURRENT_TIMESTAMP" in compact
    assert "uq_availability_lock_plan_active(plan_id,is_active)" in compact
    assert "FOREIGNKEY(plan_id)REFERENCEScaregiver_matching_plans(id)ONUPDATERESTRICTONDELETERESTRICT" in compact


def test_caregiver_availability_locks_header_check_constraints_strict():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CHECK((status='active'ANDis_active=1ANDreleased_byISNULLANDreleased_atISNULL)OR(statusIN('released','converted','cancelled')ANDis_activeISNULLANDCHAR_LENGTH(TRIM(released_by))>0ANDreleased_atISNOTNULL))" in compact
    assert "CHECK(CHAR_LENGTH(TRIM(created_by))>0)" in compact


def test_caregiver_availability_lock_days_detail_table_structure():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CREATETABLEIFNOTEXISTS`caregiver_availability_lock_days`" in compact or "CREATETABLEIFNOTEXISTScaregiver_availability_lock_days" in compact
    assert "lock_idBIGINTNOTNULL" in compact
    assert "segment_idBIGINTNOTNULL" in compact
    assert "staff_idINTNOTNULL" in compact
    assert "lock_dateDATENOTNULL" in compact
    assert "active_markerTINYINT(1)NULL" in compact
    assert "released_byVARCHAR(100)NULL" in compact
    assert "created_atTIMESTAMPNOTNULLDEFAULTCURRENT_TIMESTAMP" in compact
    assert "released_atTIMESTAMPNULL" in compact
    assert "uq_availability_lock_staff_date_active(staff_id,lock_date,active_marker)" in compact
    assert "uq_availability_lock_segment_date(lock_id,segment_id,lock_date)" in compact
    assert "FOREIGNKEY(lock_id)REFERENCEScaregiver_availability_locks(id)ONUPDATERESTRICTONDELETERESTRICT" in compact
    assert "FOREIGNKEY(segment_id)REFERENCEScaregiver_matching_plan_segments(id)ONUPDATERESTRICTONDELETERESTRICT" in compact
    assert "FOREIGNKEY(staff_id)REFERENCESstaff(id)ONUPDATERESTRICTONDELETERESTRICT" in compact


def test_caregiver_availability_lock_days_check_constraints_strict():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CHECK((active_marker=1ANDreleased_byISNULLANDreleased_atISNULL)OR(active_markerISNULLANDCHAR_LENGTH(TRIM(released_by))>0ANDreleased_atISNOTNULL))" in compact


def test_foreign_keys_forbid_on_delete_cascade():
    sql = _schema_sql().upper()
    assert "ON DELETE CASCADE" not in sql
    assert "ON DELETE RESTRICT" in sql or "ON DELETE NO ACTION" in sql


def test_schema_loader_extracts_all_six_complete_lock_and_event_trigger_statements():
    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    load_schema_parts(cursor, parts_dir)

    trigger_stmts = [
        stmt for stmt in cursor.executed
        if "CREATE TRIGGER" in stmt and "caregiver_availability_lock" in stmt
    ]

    assert len(trigger_stmts) == 6, f"預期應擷取出 6 個完整的 CREATE TRIGGER 語句，實際：{len(trigger_stmts)}"

    for stmt in trigger_stmts:
        assert "DELIMITER" not in stmt
        assert "BEGIN" not in stmt
        assert "END IF" not in stmt
        assert stmt.strip().startswith("CREATE TRIGGER")

    header_update = next(s for s in trigger_stmts if "trg_caregiver_availability_locks_before_update" in s)
    assert "SET NEW.created_by = IF(" in header_update
    assert "OLD.plan_id <=> NEW.plan_id" in header_update

    header_delete = next(s for s in trigger_stmts if "trg_caregiver_availability_locks_before_delete" in s)
    assert "SIGNAL SQLSTATE '45000'" in header_delete
    assert "caregiver_availability_locks records cannot be deleted" in header_delete

    day_update = next(s for s in trigger_stmts if "trg_caregiver_availability_lock_days_before_update" in s)
    assert "SET NEW.lock_id = IF(" in day_update
    assert "OLD.segment_id <=> NEW.segment_id" in day_update
    assert "OLD.staff_id <=> NEW.staff_id" in day_update
    assert "OLD.lock_date <=> NEW.lock_date" in day_update

    day_delete = next(s for s in trigger_stmts if "trg_caregiver_availability_lock_days_before_delete" in s)
    assert "SIGNAL SQLSTATE '45000'" in day_delete
    assert "caregiver_availability_lock_days records cannot be deleted" in day_delete

    event_update = next(s for s in trigger_stmts if "trg_caregiver_availability_lock_events_before_update" in s)
    event_delete = next(s for s in trigger_stmts if "trg_caregiver_availability_lock_events_before_delete" in s)
    assert "caregiver_availability_lock_events records cannot be updated" in event_update
    assert "caregiver_availability_lock_events records cannot be deleted" in event_delete


def test_lexical_loading_order_after_matching_plan_and_event_schemas():
    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    loaded_parts = load_schema_parts(cursor, parts_dir)

    assert "98_caregiver_matching_plans.sql" in loaded_parts
    assert "99_caregiver_matching_plan_events.sql" in loaded_parts
    assert "99a_caregiver_availability_locks.sql" in loaded_parts

    idx_98 = loaded_parts.index("98_caregiver_matching_plans.sql")
    idx_99 = loaded_parts.index("99_caregiver_matching_plan_events.sql")
    idx_99a = loaded_parts.index("99a_caregiver_availability_locks.sql")

    assert idx_98 < idx_99 < idx_99a, f"載入順序必須為 98 < 99 < 99a，實際順序：{loaded_parts}"


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
    assert any("caregiver_availability_locks" in statement for statement in first_run_statements)
    assert any("caregiver_availability_lock_days" in statement for statement in first_run_statements)

    assert load_schema_parts(cursor, parts_dir) == loaded_parts
    assert cursor.executed == first_run_statements + first_run_statements

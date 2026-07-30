from pathlib import Path

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT / "db" / "schema_parts" / "98_caregiver_matching_plans.sql"
)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _schema_sql():
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_caregiver_matching_plans_header_table_structure():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CREATETABLEIFNOTEXISTSspotted_table" not in compact
    assert "CREATETABLEIFNOTEXISTS`caregiver_matching_plans`" in compact or "CREATETABLEIFNOTEXISTScaregiver_matching_plans" in compact
    assert "case_noVARCHAR(50)NOTNULL" in compact
    assert "versionINTNOTNULLDEFAULT1" in compact
    assert "is_activeTINYINT(1)NULL" in compact
    assert "start_dateDATENOTNULL" in compact
    assert "end_dateDATENOTNULL" in compact
    assert "CHECK(start_date<=end_date)" in compact
    assert "created_byVARCHAR(100)NOTNULL" in compact
    assert "uq_caregiver_matching_plan_case_version(case_no,version)" in compact
    assert "uq_caregiver_matching_plan_active(case_no,is_active)" in compact
    assert "FOREIGNKEY(case_no)REFERENCESorders(case_no)ONUPDATERESTRICTONDELETERESTRICT" in compact or "FOREIGNKEY(case_no)REFERENCESorders(case_no)" in compact
    assert "CHECK(created_byISNOTNULLANDCHAR_LENGTH(TRIM(created_by))>0)" in compact


def test_caregiver_matching_plan_segments_detail_table_structure():
    sql = _schema_sql()
    compact = "".join(sql.split())

    assert "CREATETABLEIFNOTEXISTS`caregiver_matching_plan_segments`" in compact or "CREATETABLEIFNOTEXISTScaregiver_matching_plan_segments" in compact
    assert "segment_orderTINYINTNOTNULL" in compact
    assert "staff_idINTNOTNULL" in compact
    assert "assigned_start_dateDATENOTNULL" in compact
    assert "assigned_end_dateDATENOTNULL" in compact
    assert "uq_matching_plan_segment_order(plan_id,segment_order)" in compact
    assert "uq_matching_plan_staff(plan_id,staff_id)" in compact
    assert "FOREIGNKEY(plan_id)REFERENCEScaregiver_matching_plans(id)ONUPDATERESTRICTONDELETERESTRICT" in compact
    assert "FOREIGNKEY(plan_id)REFERENCEScaregiver_matching_plans(id)ONDELETECASCADE" not in compact
    assert "FOREIGNKEY(staff_id)REFERENCESstaff(id)ONUPDATERESTRICTONDELETERESTRICT" in compact
    assert "CHECK(segment_orderBETWEEN1AND4)" in compact
    assert "CHECK(assigned_start_date<=assigned_end_date)" in compact


def test_foreign_keys_forbid_on_delete_cascade():
    sql = _schema_sql().upper()
    assert "ON DELETE CASCADE" not in sql
    assert "ON DELETE RESTRICT" in sql or "ON DELETE NO ACTION" in sql


def test_schema_loader_extracts_six_complete_trigger_statements():
    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    load_schema_parts(cursor, parts_dir)

    trigger_stmts = [
        stmt for stmt in cursor.executed
        if "CREATE TRIGGER" in stmt and "caregiver_matching_plan" in stmt
    ]

    assert len(trigger_stmts) == 6, f"預期載入器應擷取出配對方案與事件共 6 個完整的 CREATE TRIGGER 語句，實際：{len(trigger_stmts)}"

    for stmt in trigger_stmts:
        assert "DELIMITER" not in stmt
        assert "BEGIN" not in stmt
        assert "END IF" not in stmt
        assert stmt.strip().startswith("CREATE TRIGGER")

    header_update_stmt = next(s for s in trigger_stmts if "trg_caregiver_matching_plans_before_update" in s)
    assert "SET NEW.created_by = IF(" in header_update_stmt
    assert "OLD.id <=> NEW.id" in header_update_stmt
    assert "OLD.case_no <=> NEW.case_no" in header_update_stmt
    assert "OLD.version <=> NEW.version" in header_update_stmt
    assert "OLD.start_date <=> NEW.start_date" in header_update_stmt
    assert "OLD.end_date <=> NEW.end_date" in header_update_stmt

    header_delete_stmt = next(s for s in trigger_stmts if "trg_caregiver_matching_plans_before_delete" in s)
    assert "SIGNAL SQLSTATE '45000'" in header_delete_stmt
    assert "caregiver_matching_plans records cannot be deleted" in header_delete_stmt

    segment_update_stmt = next(s for s in trigger_stmts if "trg_caregiver_matching_plan_segments_before_update" in s)
    assert "SIGNAL SQLSTATE '45000'" in segment_update_stmt
    assert "caregiver_matching_plan_segments records cannot be updated" in segment_update_stmt

    segment_delete_stmt = next(s for s in trigger_stmts if "trg_caregiver_matching_plan_segments_before_delete" in s)
    assert "SIGNAL SQLSTATE '45000'" in segment_delete_stmt
    assert "caregiver_matching_plan_segments records cannot be deleted" in segment_delete_stmt


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
    assert any("caregiver_matching_plans" in statement for statement in first_run_statements)
    assert any("trg_caregiver_matching_plans_before_update" in statement for statement in first_run_statements)

    assert load_schema_parts(cursor, parts_dir) == loaded_parts
    assert cursor.executed == first_run_statements + first_run_statements

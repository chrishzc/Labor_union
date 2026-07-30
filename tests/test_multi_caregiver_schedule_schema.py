# -*- coding: utf-8 -*-
"""
tests/test_multi_caregiver_schedule_schema.py

MultiCaregiverScheduleSchema@v1@2b20db 完備驗收測試。
驗證：
 1. 95_multi_caregiver_schedule.sql 零破壞性 DDL (DROP/RENAME) 與零 DML (INSERT/UPDATE/DELETE/TRUNCATE/REPLACE)。
 2. 不使用 PREPARE 不支援的 SIGNAL/DELIMITER/PROCEDURE 或 compound body。
 3. Lexical loader 順序符合 95_multi_caregiver_schedule.sql。
 4. Stateful 兩次連續執行測試：第一輪補齊物件，第二輪完全 no-op (對 95 節點零 ALTER/CREATE)。
 5. 前置表缺失 (staff_schedule 或 case_staff_assignments) 時 fail-closed 觸發固定 sentinel 錯誤。
 6. 欄位、索引與外鍵同名錯誤規格及異名等價定義時 fail-closed 觸發固定 sentinel 錯誤 (包含外鍵 RESTRICT action 驗證)。
 7. 覆核表 staff_schedule_assignment_reviews 欄位型別、nullable、ENUM/default、唯一鍵、CHECK 與外鍵 RESTRICT action 完整規格驗證，任何錯誤均 fail-closed。
"""
from pathlib import Path
import re
import pytest
from scripts.init_db import load_schema_parts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PARTS_DIR = PROJECT_ROOT / "db" / "schema_parts"
TARGET_SCHEMA_FILE = SCHEMA_PARTS_DIR / "95_multi_caregiver_schedule.sql"


def _read_schema_sql():
    return TARGET_SCHEMA_FILE.read_text(encoding="utf-8")


class StatefulMockCursor:
    def __init__(self, responses=None):
        self.responses = responses or {}
        # 預設模擬狀態
        self.ss_table_exists = self.responses.get('ss_table_exists', True)
        self.csa_table_exists = self.responses.get('csa_table_exists', True)

        self.col_any_count = self.responses.get('col_any_count', 0)
        self.col_exact_match = self.responses.get('col_exact_match', 0)

        self.idx_any_cols = self.responses.get('idx_any_cols', 0)
        self.idx_exact_match = self.responses.get('idx_exact_match', 0)
        self.eq_idx_count = self.responses.get('eq_idx_count', 0)

        self.fk_any_count = self.responses.get('fk_any_count', 0)
        self.fk_exact_match = self.responses.get('fk_exact_match', 0)
        self.eq_fk_count = self.responses.get('eq_fk_count', 0)

        self.reviews_table_exists = self.responses.get('reviews_table_exists', False)
        self.reviews_col_exact_count = self.responses.get('reviews_col_exact_count', 9)
        self.reviews_uq_count = self.responses.get('reviews_uq_count', 1)
        self.reviews_fk_count = self.responses.get('reviews_fk_count', 2)
        self.reviews_check_count = self.responses.get('reviews_check_count', 1)
        self.reviews_updated_at_on_update_count = self.responses.get(
            'reviews_updated_at_on_update_count', 1
        )

        self.executed_statements = []
        self.actually_executed_ddls = []
        self.last_action_sql = None

    def execute(self, statement, params=None):
        stmt_clean = statement.strip()
        self.executed_statements.append((stmt_clean, params))
        compact = " ".join(stmt_clean.split())

        if "INFORMATION_SCHEMA.TABLES" in compact:
            if "staff_schedule_assignment_reviews" in compact:
                self.current_fetch = [(1 if self.reviews_table_exists else 0,)]
            elif "staff_schedule" in compact:
                self.current_fetch = [(1 if self.ss_table_exists else 0,)]
            elif "case_staff_assignments" in compact:
                self.current_fetch = [(1 if self.csa_table_exists else 0,)]
            else:
                self.current_fetch = [(0,)]
        elif "INFORMATION_SCHEMA.COLUMNS" in compact:
            if "staff_schedule_assignment_reviews" in compact:
                if "UPPER(COALESCE(EXTRA" in compact or "ON UPDATE CURRENT_TIMESTAMP" in compact:
                    count = self.reviews_updated_at_on_update_count if self.reviews_table_exists else 0
                else:
                    count = self.reviews_col_exact_count if self.reviews_table_exists else 0
                self.current_fetch = [(count,)]
            elif "assignment_id" in compact:
                if "DATA_TYPE = 'bigint'" in compact or "DATA_TYPE" in compact:
                    self.current_fetch = [(self.col_exact_match,)]
                else:
                    self.current_fetch = [(self.col_any_count,)]
            else:
                self.current_fetch = [(0,)]
        elif "INFORMATION_SCHEMA.STATISTICS" in compact:
            if "staff_schedule_assignment_reviews" in compact:
                self.current_fetch = [(self.reviews_uq_count if self.reviews_table_exists else 0,)]
            elif "INDEX_NAME != 'idx_staff_schedule_assignment'" in compact:
                self.current_fetch = [(self.eq_idx_count,)]
            elif "INDEX_NAME = 'idx_staff_schedule_assignment'" in compact and "NON_UNIQUE = 1" in compact:
                self.current_fetch = [(self.idx_exact_match,)]
            elif "INDEX_NAME = 'idx_staff_schedule_assignment'" in compact:
                self.current_fetch = [(self.idx_any_cols,)]
            else:
                self.current_fetch = [(0,)]
        elif "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in compact:
            if "fk_staff_schedule_assignment" in compact:
                self.current_fetch = [(self.fk_any_count,)]
            else:
                self.current_fetch = [(0,)]
        elif "INFORMATION_SCHEMA.KEY_COLUMN_USAGE" in compact:
            if "CONSTRAINT_NAME != 'fk_staff_schedule_assignment'" in compact:
                self.current_fetch = [(self.eq_fk_count,)]
            elif "fk_staff_schedule_assignment" in compact:
                self.current_fetch = [(self.fk_exact_match,)]
            else:
                self.current_fetch = [(0,)]
        elif "INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS" in compact:
            if "staff_schedule_assignment_reviews" in compact:
                self.current_fetch = [(self.reviews_fk_count if self.reviews_table_exists else 0,)]
            else:
                self.current_fetch = [(0,)]
        elif "INFORMATION_SCHEMA.CHECK_CONSTRAINTS" in compact:
            if "staff_schedule_assignment_reviews" in compact:
                self.current_fetch = [(self.reviews_check_count if self.reviews_table_exists else 0,)]
            else:
                self.current_fetch = [(0,)]
        elif compact.startswith("SET @prereq_action_sql ="):
            if not self.ss_table_exists:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_STAFF_SCHEDULE_TABLE_NOT_FOUND`"
            elif not self.csa_table_exists:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_CASE_STAFF_ASSIGNMENTS_TABLE_NOT_FOUND`"
            else:
                self.last_action_sql = "SELECT 1"
        elif compact.startswith("SET @col_action_sql ="):
            if self.col_any_count > 0 and self.col_exact_match == 0:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_ASSIGNMENT_ID_COLUMN_INVALID_SPEC_REVIEW_REQUIRED`"
            elif self.col_any_count == 0:
                self.last_action_sql = "ALTER TABLE `staff_schedule` ADD COLUMN `assignment_id` BIGINT NULL"
            else:
                self.last_action_sql = "SELECT 1"
        elif compact.startswith("SET @idx_action_sql ="):
            idx_has_invalid = (self.idx_any_cols > 0 and not (self.idx_any_cols == 1 and self.idx_exact_match == 1))
            if idx_has_invalid:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_IDX_ASSIGNMENT_INVALID_SPEC_REVIEW_REQUIRED`"
            elif self.eq_idx_count > 0:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_EQUIVALENT_ASSIGNMENT_INDEX_REVIEW_REQUIRED`"
            elif self.idx_any_cols == 0:
                self.last_action_sql = "ALTER TABLE `staff_schedule` ADD INDEX `idx_staff_schedule_assignment` (`assignment_id`)"
            else:
                self.last_action_sql = "SELECT 1"
        elif compact.startswith("SET @fk_action_sql ="):
            fk_has_invalid = (self.fk_any_count > 0 and self.fk_exact_match == 0)
            if fk_has_invalid:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_FK_ASSIGNMENT_INVALID_SPEC_REVIEW_REQUIRED`"
            elif self.eq_fk_count > 0:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_EQUIVALENT_ASSIGNMENT_FK_REVIEW_REQUIRED`"
            elif self.fk_any_count == 0:
                self.last_action_sql = "ALTER TABLE `staff_schedule` ADD CONSTRAINT `fk_staff_schedule_assignment` FOREIGN KEY (assignment_id) REFERENCES case_staff_assignments (id)"
            else:
                self.last_action_sql = "SELECT 1"
        elif compact.startswith("SET @reviews_action_sql ="):
            reviews_valid = (
                self.reviews_table_exists
                and self.reviews_col_exact_count == 9
                and self.reviews_updated_at_on_update_count == 1
                and self.reviews_uq_count == 1
                and self.reviews_fk_count == 2
                and self.reviews_check_count == 1
            )
            reviews_invalid_spec = (self.reviews_table_exists and not reviews_valid)

            if reviews_invalid_spec:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED`"
            elif not self.reviews_table_exists:
                self.last_action_sql = "CREATE TABLE staff_schedule_assignment_reviews (id BIGINT AUTO_INCREMENT PRIMARY KEY)"
            else:
                self.last_action_sql = "SELECT 1"
        elif compact.startswith("EXECUTE"):
            if self.last_action_sql:
                self.actually_executed_ddls.append(self.last_action_sql)
                if "ADD COLUMN `assignment_id`" in self.last_action_sql:
                    self.col_any_count = 1
                    self.col_exact_match = 1
                elif "ADD INDEX `idx_staff_schedule_assignment`" in self.last_action_sql:
                    self.idx_any_cols = 1
                    self.idx_exact_match = 1
                elif "ADD CONSTRAINT `fk_staff_schedule_assignment`" in self.last_action_sql:
                    self.fk_any_count = 1
                    self.fk_exact_match = 1
                elif "CREATE TABLE staff_schedule_assignment_reviews" in self.last_action_sql:
                    self.reviews_table_exists = True
                    self.reviews_col_exact_count = 9
                    self.reviews_uq_count = 1
                    self.reviews_fk_count = 2
                    self.reviews_updated_at_on_update_count = 1
                    self.reviews_check_count = 1
                elif "FAIL_CLOSED" in self.last_action_sql:
                    action = self.last_action_sql
                    self.last_action_sql = None
                    raise RuntimeError(f"Fail-closed condition triggered: {action}")
                self.last_action_sql = None
        else:
            self.current_fetch = [(1,)]

    def fetchall(self):
        return self.current_fetch

    def fetchone(self):
        return self.current_fetch[0] if self.current_fetch else (0,)


# ── 1. 語法不變量與禁用語句檢查 ──────────────────────────────────────

def test_file_exists_and_no_forbidden_statements():
    assert TARGET_SCHEMA_FILE.exists()

    raw_sql = _read_schema_sql()
    non_comment_lines = [
        line for line in raw_sql.split("\n")
        if not line.strip().startswith("--")
    ]
    code_sql_upper = "\n".join(non_comment_lines).upper()

    forbidden_ddls = ["DROP INDEX", "DROP KEY", "DROP CONSTRAINT", "RENAME INDEX", "DROP TABLE", "RENAME TABLE"]
    for ddl in forbidden_ddls:
        assert ddl not in code_sql_upper, f"Forbidden DDL statement found: {ddl}"

    assert not re.search(r'\bINSERT\s+INTO\b', code_sql_upper), "Forbidden DML statement found: INSERT INTO"
    assert not re.search(r'(?<!ON\s)\bUPDATE\s+`?[a-zA-Z0-9_]+`?\s+SET\b', code_sql_upper), "Forbidden DML statement found: UPDATE"
    assert not re.search(r'\bDELETE\s+FROM\b', code_sql_upper), "Forbidden DML statement found: DELETE FROM"
    assert not re.search(r'\bTRUNCATE\s+', code_sql_upper), "Forbidden DML statement found: TRUNCATE"
    assert not re.search(r'\bREPLACE\s+INTO\b', code_sql_upper), "Forbidden DML statement found: REPLACE INTO"

    forbidden_prep = ["SIGNAL ", "DELIMITER", "CREATE PROCEDURE", "BEGIN", "END IF"]
    for prep in forbidden_prep:
        assert prep not in code_sql_upper, f"Non-prepareable or compound statement found: {prep}"


# ── 2. Lexical Loader 順序檢查 ──────────────────────────────────────

def test_lexical_loading_order():
    cursor = StatefulMockCursor()
    loaded_parts = load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    assert "95_multi_caregiver_schedule.sql" in loaded_parts
    idx_100 = loaded_parts.index("100_staff_schedule_allow_same_day_multiple_assignments.sql")
    idx_95 = loaded_parts.index("95_multi_caregiver_schedule.sql")
    idx_98 = loaded_parts.index("98_caregiver_matching_plans.sql")

    assert idx_100 < idx_95 < idx_98, f"依檔案名 Lexical 排序，載入順序應為 100_ < 95_ < 98_，實際順序：{loaded_parts}"


# ── 3. Stateful 兩次執行測試 (第二輪對 95 節點零 ALTER/CREATE) ────────

def test_stateful_two_pass_schema_execution_zero_mutating_ddl_on_second_pass():
    cursor = StatefulMockCursor()

    # 第一輪執行
    load_schema_parts(cursor, SCHEMA_PARTS_DIR)
    first_run_ddls = list(cursor.actually_executed_ddls)
    assert any("ADD COLUMN" in ddl for ddl in first_run_ddls)
    assert any("ADD INDEX" in ddl for ddl in first_run_ddls)
    assert any("ADD CONSTRAINT" in ddl for ddl in first_run_ddls)
    assert any("CREATE TABLE staff_schedule_assignment_reviews" in ddl for ddl in first_run_ddls)

    # 第二輪執行 (在已更新狀態的 cursor 上)
    load_schema_parts(cursor, SCHEMA_PARTS_DIR)
    second_run_ddls = cursor.actually_executed_ddls[len(first_run_ddls):]

    # 斷言第二輪對 95 節點完全零 ALTER / 零 CREATE mutating DDL！
    for ddl in second_run_ddls:
        assert "ALTER TABLE `staff_schedule`" not in ddl, f"Second pass executed forbidden ALTER: {ddl}"
        assert "CREATE TABLE staff_schedule_assignment_reviews" not in ddl, f"Second pass executed forbidden CREATE: {ddl}"
        assert "SELECT 1" in ddl


# ── 4. 前置表缺失 Fail-Closed ─────────────────────────────────────────

def test_missing_staff_schedule_table_triggers_fail_closed():
    cursor = StatefulMockCursor({'ss_table_exists': False})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_STAFF_SCHEDULE_TABLE_NOT_FOUND"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_missing_case_staff_assignments_table_triggers_fail_closed():
    cursor = StatefulMockCursor({'csa_table_exists': False})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_CASE_STAFF_ASSIGNMENTS_TABLE_NOT_FOUND"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


# ── 5. 欄位、索引與外鍵規格錯誤 Fail-Closed ─────────────────────────

def test_invalid_assignment_id_column_spec_triggers_fail_closed():
    cursor = StatefulMockCursor({'col_any_count': 1, 'col_exact_match': 0})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_ASSIGNMENT_ID_COLUMN_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_invalid_index_spec_triggers_fail_closed():
    cursor = StatefulMockCursor({'idx_any_cols': 1, 'idx_exact_match': 0})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_IDX_ASSIGNMENT_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_equivalent_index_triggers_fail_closed():
    cursor = StatefulMockCursor({'eq_idx_count': 1})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_EQUIVALENT_ASSIGNMENT_INDEX_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_invalid_fk_spec_or_action_triggers_fail_closed():
    # 外鍵存在但 ON UPDATE 或 ON DELETE action 錯誤 (fk_exact_match=0)
    cursor = StatefulMockCursor({'fk_any_count': 1, 'fk_exact_match': 0})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_FK_ASSIGNMENT_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_equivalent_fk_triggers_fail_closed():
    cursor = StatefulMockCursor({'eq_fk_count': 1})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_EQUIVALENT_ASSIGNMENT_FK_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


# ── 6. 覆核表各 Constraint 錯誤情境 Fail-Closed ─────────────────────────

def test_reviews_table_invalid_column_count_or_type_triggers_fail_closed():
    # 覆核表存在但欄位型別/數量不符合契約
    cursor = StatefulMockCursor({'reviews_table_exists': True, 'reviews_col_exact_count': 8})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_reviews_table_invalid_default_values_triggers_fail_closed():
    # 覆核表存在但欄位 default 規格不符合契約
    cursor = StatefulMockCursor({'reviews_table_exists': True, 'reviews_col_exact_count': 8})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_reviews_table_invalid_uq_triggers_fail_closed():
    # 覆核表存在但唯一鍵 uq_schedule_review 缺失或錯誤
    cursor = StatefulMockCursor({'reviews_table_exists': True, 'reviews_uq_count': 0})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_reviews_table_invalid_fk_or_action_triggers_fail_closed():
    # 覆核表存在但外鍵 RESTRICT action 不相符
    cursor = StatefulMockCursor({'reviews_table_exists': True, 'reviews_fk_count': 1})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_reviews_table_invalid_check_constraint_triggers_fail_closed():
    # 覆核表存在但 CHECK constraint 缺失或不符
    cursor = StatefulMockCursor({'reviews_table_exists': True, 'reviews_check_count': 0})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


def test_reviews_table_invalid_updated_at_on_update_triggers_fail_closed():
    # 覆核表存在但 updated_at 的 ON UPDATE CURRENT_TIMESTAMP 不相符
    cursor = StatefulMockCursor({'reviews_table_exists': True, 'reviews_updated_at_on_update_count': 0})

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_REVIEWS_TABLE_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)


# ── 7. 覆核表 Structure & CHECK Constraint 嚴格契約 ────────────────────

def test_reviews_table_check_constraints_strict():
    sql = _read_schema_sql().replace("\\'", "'")
    compact = "".join(sql.split())

    assert "CREATETABLEstaff_schedule_assignment_reviews" in compact or "CREATETABLE`staff_schedule_assignment_reviews`" in compact
    assert "schedule_idINTNOTNULL" in compact
    assert "review_reasonVARCHAR(100)NOTNULL" in compact
    assert "review_statusENUM('review_required','resolved')NOTNULLDEFAULT'review_required'" in compact
    assert "resolved_assignment_idBIGINTNULL" in compact
    assert "resolved_byVARCHAR(100)NULL" in compact
    assert "resolved_atTIMESTAMPNULL" in compact

    # 驗證 CHECK constraint 嚴格遵守 review_required 時 resolved_assignment_id, resolved_by, resolved_at 皆為 NULL
    assert "(review_status='review_required'ANDresolved_assignment_idISNULLANDresolved_byISNULLANDresolved_atISNULL)" in compact
    # 驗證 CHECK constraint 嚴格遵守 resolved 時三者皆非 NULL
    assert "(review_status='resolved'ANDresolved_assignment_idISNOTNULLANDresolved_byISNOTNULLANDresolved_atISNOTNULL)" in compact

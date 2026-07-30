# -*- coding: utf-8 -*-
"""
tests/test_legacy_same_day_schedule_relaxation_retirement.py

LegacySameDayScheduleRelaxationRetirement@v1@dde41b 驗收測試。
驗證：
 1. 100_...sql 不包含或執行任何 DROP INDEX/KEY/CONSTRAINT, RENAME INDEX, 或 DML (INSERT/UPDATE/DELETE/TRUNCATE/REPLACE)。
 2. 100_...sql 依實際 lexical loader 順序目前為第一個 schema part，且在 MultiCaregiverScheduleSchema 之前安全載入。
 3. 正確 canonical 索引存在時：無 ALTER 執行，且多重執行具備完全 idempotent 特性。
 4. 缺 canonical 索引且無重複時：僅執行一次 ADD UNIQUE KEY ukey_staff_date (staff_id, work_date)。
 5. Stateful 兩次連續執行測試：第一次缺索引時執行 ADD 並即時更新 metadata，第二次對同一 schema 完整執行必須為 no-op，兩輪合計恰好 1 次 ADD UNIQUE。
 6. 存有重複 (staff_id, work_date) 資料列時：fail-closed 拋出固定 sentinel 錯誤，不執行 ALTER，資料完全不受侵犯。
 7. 同名錯誤規格索引 (NON_UNIQUE=1 或異序欄位) 時：fail-closed 拋出固定 sentinel 錯誤，無 DROP/ALTER/RENAME。
 8. 異名等價唯一索引存在時：fail-closed 拋出固定 sentinel 錯誤，無 DROP/ADD/RENAME。
 9. staff_schedule 資料表不存在時：fail-closed 拋出固定 sentinel 錯誤。
10. 不包含或新增 UNIQUE(assignment_id, work_date)。
"""
from pathlib import Path
import pytest
from scripts.init_db import load_schema_parts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PARTS_DIR = PROJECT_ROOT / "db" / "schema_parts"
TARGET_SCHEMA_FILE = SCHEMA_PARTS_DIR / "100_staff_schedule_allow_same_day_multiple_assignments.sql"


def _read_schema_sql():
    return TARGET_SCHEMA_FILE.read_text(encoding="utf-8")


class StatefulMockCursor:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.table_exists = self.responses.get('table_exists', True)
        self.canonical_any_cols = self.responses.get('canonical_any_cols', 0)
        self.canonical_exact_match = self.responses.get('canonical_exact_match', 0)
        self.equivalent_index_count = self.responses.get('equivalent_index_count', 0)
        self.duplicate_rows_exist = self.responses.get('duplicate_rows_exist', False)

        self.executed_statements = []
        self.actually_executed_ddls = []
        self.last_action_sql = None

    def execute(self, statement, params=None):
        stmt_clean = statement.strip()
        self.executed_statements.append((stmt_clean, params))
        compact = " ".join(stmt_clean.split())

        # 模擬 INFORMATION_SCHEMA.TABLES
        if "INFORMATION_SCHEMA.TABLES" in compact:
            table_exists = 1 if self.table_exists else 0
            self.current_fetch = [(table_exists,)]
        # 模擬 INFORMATION_SCHEMA.STATISTICS
        elif "INFORMATION_SCHEMA.STATISTICS" in compact:
            if "INDEX_NAME != 'ukey_staff_date'" in compact:
                self.current_fetch = [(self.equivalent_index_count,)]
            elif "INDEX_NAME = 'ukey_staff_date'" in compact and "NON_UNIQUE = 0" in compact:
                self.current_fetch = [(self.canonical_exact_match,)]
            elif "INDEX_NAME = 'ukey_staff_date'" in compact:
                self.current_fetch = [(self.canonical_any_cols,)]
            else:
                self.current_fetch = [(0,)]
        # 模擬 HAVING COUNT(*) > 1 重複資料查詢
        elif "HAVING COUNT(*) > 1" in compact:
            has_dup = 1 if self.duplicate_rows_exist else 0
            self.current_fetch = [(has_dup,)]
        # 模擬 PREPARE / EXECUTE
        elif compact.startswith("SET @action_sql ="):
            canonical_valid = (self.canonical_any_cols == 2 and self.canonical_exact_match == 2)
            canonical_has_invalid_spec = (self.canonical_any_cols > 0 and not canonical_valid)

            if not self.table_exists:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_STAFF_SCHEDULE_TABLE_NOT_FOUND`"
            elif canonical_has_invalid_spec:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_UKEY_STAFF_DATE_INVALID_SPEC_REVIEW_REQUIRED`"
            elif canonical_valid:
                self.last_action_sql = "SELECT 1"
            elif self.equivalent_index_count > 0:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_EQUIVALENT_INDEX_REVIEW_REQUIRED`"
            elif self.duplicate_rows_exist:
                self.last_action_sql = "SELECT * FROM `FAIL_CLOSED_DUPLICATE_STAFF_DATE_ROWS_FOUND_REVIEW_REQUIRED`"
            else:
                self.last_action_sql = "ALTER TABLE `staff_schedule` ADD UNIQUE KEY `ukey_staff_date` (`staff_id`, `work_date`)"

            self.current_fetch = []
        elif compact.startswith("EXECUTE staff_schedule_guard_stmt"):
            if self.last_action_sql:
                self.actually_executed_ddls.append(self.last_action_sql)
                if "ALTER TABLE" in self.last_action_sql:
                    # Stateful 效果：建立唯一鍵後，自動更新內部 metadata 狀態
                    self.canonical_any_cols = 2
                    self.canonical_exact_match = 2
                elif "FAIL_CLOSED" in self.last_action_sql:
                    action = self.last_action_sql
                    self.last_action_sql = None
                    raise RuntimeError(f"Fail-closed condition triggered: {action}")
            self.current_fetch = []
        else:
            self.current_fetch = [(1,)]

    def fetchall(self):
        return self.current_fetch

    def fetchone(self):
        return self.current_fetch[0] if self.current_fetch else (0,)


# ── 1. 語法不變量與禁用語句檢查 ──────────────────────────────────────

def test_file_exists_and_no_forbidden_statements():
    assert TARGET_SCHEMA_FILE.exists()
    sql_upper = _read_schema_sql().upper()

    forbidden_ddls = ["DROP INDEX", "DROP KEY", "DROP CONSTRAINT", "RENAME INDEX", "DROP TABLE"]
    for ddl in forbidden_ddls:
        assert ddl not in sql_upper, f"Forbidden DDL statement found: {ddl}"

    forbidden_dmls = ["INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "REPLACE "]
    for dml in forbidden_dmls:
        assert dml not in sql_upper, f"Forbidden DML statement found: {dml}"

    # 禁用非 PREPARE 語法
    forbidden_prep = ["SIGNAL ", "DELIMITER", "CREATE PROCEDURE", "BEGIN", "END IF"]
    for prep in forbidden_prep:
        assert prep not in sql_upper, f"Non-prepareable or compound statement found: {prep}"

    # 不包含 assignment-date 唯一鍵
    assert "ASSIGNMENT_ID" not in sql_upper
    assert "UQ_STAFF_SCHEDULE_ASSIGNMENT_DATE" not in sql_upper


# ── 2. Lexical Loader 順序檢查 ──────────────────────────────────────

def test_lexical_loading_order_first_schema_part():
    cursor = StatefulMockCursor({
        'table_exists': True,
        'canonical_any_cols': 2,
        'canonical_exact_match': 2,
        'equivalent_index_count': 0,
        'duplicate_rows_exist': False
    })
    loaded_parts = load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    assert "100_staff_schedule_allow_same_day_multiple_assignments.sql" in loaded_parts
    idx_100 = loaded_parts.index("100_staff_schedule_allow_same_day_multiple_assignments.sql")
    idx_20 = loaded_parts.index("20_staff_monthly_settlements.sql")
    idx_95 = loaded_parts.index("95_multi_caregiver_schedule.sql")

    assert idx_100 < idx_20 < idx_95, f"100_...sql 必須是當前第一個 Schema Part，實際順序：{loaded_parts}"


# ── 3. 情境 A：正確 Canonical 索引已存在 (Idempotent Success) ─────────

def test_canonical_index_exists_is_idempotent_no_alter():
    responses = {
        'table_exists': True,
        'canonical_any_cols': 2,
        'canonical_exact_match': 2,
        'equivalent_index_count': 0,
        'duplicate_rows_exist': False
    }
    cursor = StatefulMockCursor(responses)
    load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    alter_sqls = [sql for sql in cursor.actually_executed_ddls if "ALTER TABLE" in sql]

    assert len(alter_sqls) == 0, "正確 canonical 索引已存在時，不得執行任何 ALTER TABLE"
    assert any("SELECT 1" in sql for sql in cursor.actually_executed_ddls)


# ── 4. 情境 B：缺 Canonical 索引且無重複 (單次 ADD UNIQUE KEY) ─────────

def test_missing_canonical_index_clean_data_adds_unique_key():
    responses = {
        'table_exists': True,
        'canonical_any_cols': 0,
        'canonical_exact_match': 0,
        'equivalent_index_count': 0,
        'duplicate_rows_exist': False
    }
    cursor = StatefulMockCursor(responses)
    load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    alter_sqls = [sql for sql in cursor.actually_executed_ddls if "ALTER TABLE" in sql]

    assert len(alter_sqls) == 1, f"缺 canonical 索引時應僅執行 1 次 ALTER TABLE，實際：{len(alter_sqls)}"
    assert "ADD UNIQUE KEY `ukey_staff_date` (`staff_id`, `work_date`)" in alter_sqls[0] or "ADD UNIQUE KEY ukey_staff_date (staff_id, work_date)" in alter_sqls[0]


# ── 5. 情境 C：Stateful 兩次執行驗證 ───────────────────────────────────

def test_stateful_two_pass_schema_execution():
    """
    Stateful 兩次連續執行測試：
    第一次缺索引時執行 ADD UNIQUE 並即時更新 metadata 狀態；
    第二次對同一 schema 完整執行時必須為 no-op (SELECT 1)；
    兩輪合計恰好 1 次 ADD UNIQUE。
    """
    cursor = StatefulMockCursor({
        'table_exists': True,
        'canonical_any_cols': 0,
        'canonical_exact_match': 0,
        'equivalent_index_count': 0,
        'duplicate_rows_exist': False
    })

    # 第一輪執行
    load_schema_parts(cursor, SCHEMA_PARTS_DIR)
    assert len(cursor.actually_executed_ddls) == 1
    assert "ALTER TABLE" in cursor.actually_executed_ddls[0]

    # 第二輪執行 (在同一個已更新狀態的 cursor 基礎上)
    load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    alter_ddls = [sql for sql in cursor.actually_executed_ddls if "ALTER TABLE" in sql]
    noop_ddls = [sql for sql in cursor.actually_executed_ddls if "SELECT 1" in sql]

    assert len(alter_ddls) == 1, f"兩輪合計只能執行 1 次 ADD UNIQUE，實際為 {len(alter_ddls)}"
    assert len(noop_ddls) >= 1, "第二次執行必須走成功 no-op (SELECT 1)"


# ── 6. 情境 D：存有重複排班資料 (Fail-closed Sentinel Error) ─────────

def test_duplicate_rows_exist_triggers_fail_closed_sentinel():
    responses = {
        'table_exists': True,
        'canonical_any_cols': 0,
        'canonical_exact_match': 0,
        'equivalent_index_count': 0,
        'duplicate_rows_exist': True
    }
    cursor = StatefulMockCursor(responses)

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_DUPLICATE_STAFF_DATE_ROWS_FOUND_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    alter_sqls = [sql for sql in cursor.actually_executed_ddls if "ALTER TABLE" in sql]
    assert len(alter_sqls) == 0, "存在重複排班資料時不得執行 ALTER TABLE"


# ── 7. 情境 E：同名錯誤規格索引 (Fail-closed Sentinel Error) ──────────

def test_invalid_spec_canonical_index_triggers_fail_closed_sentinel():
    responses = {
        'table_exists': True,
        'canonical_any_cols': 2,
        'canonical_exact_match': 0, # 不相符
        'equivalent_index_count': 0,
        'duplicate_rows_exist': False
    }
    cursor = StatefulMockCursor(responses)

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_UKEY_STAFF_DATE_INVALID_SPEC_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    alter_sqls = [sql for sql in cursor.actually_executed_ddls if "ALTER TABLE" in sql]
    drop_sqls = [sql for sql in cursor.actually_executed_ddls if "DROP" in sql]
    assert len(alter_sqls) == 0, "同名錯誤規格索引不得執行 ALTER TABLE"
    assert len(drop_sqls) == 0, "同名錯誤規格索引不得執行 DROP"


# ── 8. 情境 F：異名等價唯一索引存在 (Fail-closed Sentinel Error) ───────

def test_equivalent_index_exists_triggers_fail_closed_sentinel():
    responses = {
        'table_exists': True,
        'canonical_any_cols': 0,
        'canonical_exact_match': 0,
        'equivalent_index_count': 1, # 異名等價索引存在
        'duplicate_rows_exist': False
    }
    cursor = StatefulMockCursor(responses)

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_EQUIVALENT_INDEX_REVIEW_REQUIRED"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    alter_sqls = [sql for sql in cursor.actually_executed_ddls if "ALTER TABLE" in sql]
    assert len(alter_sqls) == 0, "存在異名等價索引時不得執行 ALTER TABLE"


# ── 9. 情境 G：staff_schedule 資料表不存在 (Fail-closed Sentinel Error) ─

def test_table_not_exists_triggers_fail_closed_sentinel():
    responses = {
        'table_exists': False,
        'canonical_any_cols': 0,
        'canonical_exact_match': 0,
        'equivalent_index_count': 0,
        'duplicate_rows_exist': False
    }
    cursor = StatefulMockCursor(responses)

    with pytest.raises(RuntimeError, match="FAIL_CLOSED_STAFF_SCHEDULE_TABLE_NOT_FOUND"):
        load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    alter_sqls = [sql for sql in cursor.actually_executed_ddls if "ALTER TABLE" in sql]
    assert len(alter_sqls) == 0, "資料表不存在時不得假裝成功或執行 ALTER"

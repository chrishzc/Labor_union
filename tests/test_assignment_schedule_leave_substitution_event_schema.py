import re
import pytest
from pathlib import Path

from scripts.init_db import load_schema_parts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema_parts" / "101_assignment_schedule_leave_substitution_events.sql"
PROTECTED_TABLES = ("orders", "case_staff_assignments", "staff_schedule")
ALLOWED_STATEMENT_PATTERNS = [
    re.compile(
        r"^CREATE TABLE IF NOT EXISTS ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS \(.*\) "
        r"ENGINE=INNODB DEFAULT CHARSET=UTF8MB4 COLLATE=UTF8MB4_UNICODE_CI$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^DROP TRIGGER IF EXISTS TRG_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BEFORE_UPDATE$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^CREATE TRIGGER TRG_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BEFORE_UPDATE "
        r"BEFORE UPDATE ON ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS FOR EACH ROW "
        r"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS RECORDS CANNOT BE UPDATED'$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^DROP TRIGGER IF EXISTS TRG_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BEFORE_DELETE$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^CREATE TRIGGER TRG_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BEFORE_DELETE "
        r"BEFORE DELETE ON ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS FOR EACH ROW "
        r"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS RECORDS CANNOT BE DELETED'$",
        re.IGNORECASE,
    ),
]
LEGAL_STATEMENTS_FIXTURES = [
    """CREATE TABLE IF NOT EXISTS assignment_schedule_leave_substitution_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    case_no VARCHAR(50) NOT NULL COMMENT '事件所屬案件（對應 orders.case_no）',
    original_assignment_id BIGINT NOT NULL COMMENT '請假日原始正式服務指派 id',
    original_schedule_id INT NOT NULL COMMENT '被處置之日排班 id',
    work_date DATE NOT NULL COMMENT '被處置之休假日期',
    resolution_type ENUM('leave_only', 'defer_following_assignments', 'substitute') NOT NULL COMMENT '處置類型',
    substitute_assignment_id BIGINT NULL COMMENT '只在 substitute 時為非空',
    event_key VARCHAR(100) NOT NULL COMMENT '呼叫端提供的全域唯一冪等鍵',
    actor VARCHAR(100) NOT NULL COMMENT '執行者管理員識別',
    reason VARCHAR(255) NOT NULL COMMENT '非空原因',
    schedule_snapshot JSON NOT NULL COMMENT '原排班/順延/代班日套用前後快照',
    payroll_snapshot JSON NOT NULL COMMENT '原 assignment 與代班 assignment 的核對快照',
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '事件發生時間',
    UNIQUE KEY uq_assignment_schedule_leave_substitution_event_key (event_key),
    INDEX idx_assignment_schedule_leave_substitution_event_case_time (case_no, occurred_at),
    INDEX idx_assignment_schedule_leave_substitution_event_assignments (original_assignment_id, substitute_assignment_id, work_date),
    CONSTRAINT fk_assignment_schedule_leave_substitution_event_case_no
        FOREIGN KEY (case_no) REFERENCES orders(case_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_schedule_leave_substitution_original_assignment
        FOREIGN KEY (original_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_schedule_leave_substitution_substitute_assignment
        FOREIGN KEY (substitute_assignment_id) REFERENCES case_staff_assignments(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_assignment_schedule_leave_substitution_original_schedule
        FOREIGN KEY (original_schedule_id) REFERENCES staff_schedule(id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_assignment_schedule_leave_substitution_resolution
        CHECK (
            (resolution_type = 'substitute' AND substitute_assignment_id IS NOT NULL AND substitute_assignment_id <> original_assignment_id)
            OR (resolution_type IN ('leave_only', 'defer_following_assignments') AND substitute_assignment_id IS NULL)
        ),
    CONSTRAINT chk_leave_sub_actor_reason_key
        CHECK (CHAR_LENGTH(TRIM(event_key)) > 0 AND CHAR_LENGTH(TRIM(actor)) > 0 AND CHAR_LENGTH(TRIM(reason)) > 0),
    CONSTRAINT chk_leave_sub_schedule_snapshot
        CHECK (JSON_TYPE(schedule_snapshot) = 'OBJECT'),
    CONSTRAINT chk_leave_sub_payroll_snapshot
        CHECK (JSON_TYPE(payroll_snapshot) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    "DROP TRIGGER IF EXISTS trg_assignment_schedule_leave_substitution_events_before_update",
    """CREATE TRIGGER trg_assignment_schedule_leave_substitution_events_before_update
BEFORE UPDATE ON assignment_schedule_leave_substitution_events
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be updated'""",
    "DROP TRIGGER IF EXISTS trg_assignment_schedule_leave_substitution_events_before_delete",
    """CREATE TRIGGER trg_assignment_schedule_leave_substitution_events_before_delete
BEFORE DELETE ON assignment_schedule_leave_substitution_events
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_events records cannot be deleted'""",
]
CREATE_TABLE_STATEMENT_FIXTURE = LEGAL_STATEMENTS_FIXTURES[0]


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


def _schema_sql():
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_mysql_identifiers_do_not_exceed_64_characters():
    names = re.findall(
        r"\b(?:CONSTRAINT|KEY|INDEX|TRIGGER)\s+`?([A-Za-z0-9_]+)",
        _schema_sql(),
        flags=re.IGNORECASE,
    )
    assert names
    assert not {name: len(name) for name in names if len(name) > 64}


def _strip_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"(?m)--.*?(\r?\n|$)", " ", without_block)
    without_hash = re.sub(r"(?m)#.*?(\r?\n|$)", " ", without_line)
    return without_hash


def _split_sql_statements(sql: str) -> list[str]:
    cleaned = _strip_comments(sql)
    return [stmt.strip() for stmt in cleaned.split(";") if stmt.strip()]


def _normalize_whitespace(sql: str) -> str:
    return " ".join(sql.split())


def _compact_sql(sql: str) -> str:
    return "".join(sql.split())


def _extract_create_table_statement() -> str:
    for statement in _split_sql_statements(_schema_sql()):
        if statement.lstrip().upper().startswith("CREATE TABLE"):
            return statement
    raise AssertionError("missing CREATE TABLE statement")


def _extract_constraint_clause(create_compact: str, constraint_name: str) -> str:
    marker = f"constraint{constraint_name}".lower()
    start = create_compact.find(marker)
    if start < 0:
        raise AssertionError(f"missing constraint: {constraint_name}")
    next_pos = create_compact.find("constraint", start + 1)
    if next_pos < 0:
        return create_compact[start:]
    return create_compact[start:next_pos]


def _statement_tokens(statement: str) -> list[str]:
    cleaned = _strip_comments(statement)
    return re.findall(r"[a-z_][a-z0-9_]*", cleaned.lower())


def _contains_forbidden_mutation(statement: str, operation: str, table: str) -> bool:
    tokens = _statement_tokens(statement)
    table = table.lower()
    op = operation.lower()

    for i, token in enumerate(tokens):
        if token != op:
            continue

        if op in ("insert", "replace"):
            if i + 2 < len(tokens) and tokens[i + 1] == "into" and tokens[i + 2] == table:
                return True
            if i + 1 < len(tokens) and tokens[i + 1] == table:
                return True
            continue

        if op == "update":
            if i + 1 < len(tokens) and tokens[i + 1] == table:
                return True
            continue

        if op == "delete":
            nxt = i + 1
            if nxt < len(tokens) and tokens[nxt] == "from":
                nxt += 1
            if nxt < len(tokens) and tokens[nxt] == table:
                return True
            continue

        if op == "truncate":
            nxt = i + 1
            if nxt < len(tokens) and tokens[nxt] == "table":
                nxt += 1
            if nxt < len(tokens) and tokens[nxt] == table:
                return True
            continue

        if op == "alter":
            nxt = i + 1
            if nxt < len(tokens) and tokens[nxt] == "table":
                nxt += 1
            if nxt < len(tokens) and tokens[nxt] == table:
                return True
            continue

        if op == "drop":
            nxt = i + 1
            while nxt < len(tokens) and tokens[nxt] in {"table", "if", "exists", "temporary"}:
                nxt += 1
            if nxt < len(tokens) and tokens[nxt] == table:
                return True
            continue

        if op == "rename":
            nxt = i + 1
            if nxt < len(tokens) and tokens[nxt] == "table":
                nxt += 1
            if any(token == table for token in tokens[nxt:]):
                return True
            continue

    return False


def _validate_statement(statement: str) -> None:
    normalized = _normalize_whitespace(_strip_comments(statement)).upper().strip()
    if not normalized:
        raise AssertionError("empty statement")

    for pattern in ALLOWED_STATEMENT_PATTERNS:
        if pattern.match(normalized):
            break
    else:
        raise AssertionError(f"statement not allowlisted: {statement}")

    for table in PROTECTED_TABLES:
        for operation in ("ALTER", "INSERT", "UPDATE", "DELETE", "REPLACE", "TRUNCATE", "DROP", "RENAME"):
            if _contains_forbidden_mutation(statement, operation, table):
                raise AssertionError(
                    f"受保護既有表 {table} 檢測到禁止操作 {operation}：{statement}"
                )


def test_assignment_schedule_leave_substitution_events_table_structure():
    compact = _compact_sql(_schema_sql().lower())

    assert "createtableifnotexistsassignment_schedule_leave_substitution_events" in compact
    assert "case_novarchar(50)notnull" in compact
    assert "original_assignment_idbigintnotnull" in compact
    assert "original_schedule_idintnotnull" in compact
    assert "work_datedatenotnull" in compact
    assert (
        "resolution_typeenum('leave_only','defer_following_assignments','substitute')notnull"
        in compact
    )
    assert "substitute_assignment_idbigintnull" in compact
    assert "event_keyvarchar(100)notnull" in compact
    assert "actorvarchar(100)notnull" in compact
    assert "reasonvarchar(255)notnull" in compact
    assert "schedule_snapshotjsonnotnull" in compact
    assert "payroll_snapshotjsonnotnull" in compact
    assert "occurred_attimestampnotnulldefaultcurrent_timestamp" in compact


def test_assignment_schedule_leave_substitution_events_named_constraints_match_actual_sql():
    create_stmt = _extract_create_table_statement()
    compact_create = _compact_sql(create_stmt.lower())

    fk_event_case_no_clause = _extract_constraint_clause(
        compact_create,
        "fk_assignment_schedule_leave_substitution_event_case_no",
    )
    fk_orig_assignment_clause = _extract_constraint_clause(
        compact_create,
        "fk_assignment_schedule_leave_substitution_original_assignment",
    )
    fk_sub_assign_clause = _extract_constraint_clause(
        compact_create,
        "fk_assignment_schedule_leave_substitution_substitute_assignment",
    )
    fk_orig_schedule_clause = _extract_constraint_clause(
        compact_create,
        "fk_assignment_schedule_leave_substitution_original_schedule",
    )
    resolution_clause = _extract_constraint_clause(
        compact_create,
        "chk_assignment_schedule_leave_substitution_resolution",
    )
    actor_reason_clause = _extract_constraint_clause(
        compact_create,
        "chk_leave_sub_actor_reason_key",
    )
    schedule_snapshot_clause = _extract_constraint_clause(
        compact_create,
        "chk_leave_sub_schedule_snapshot",
    )
    payroll_snapshot_clause = _extract_constraint_clause(
        compact_create,
        "chk_leave_sub_payroll_snapshot",
    )

    assert (
        "foreignkey(case_no)referencesorders(case_no)"
        "onupdaterestrictondeleterestrict" in fk_event_case_no_clause
    )
    assert (
        "foreignkey(original_assignment_id)referencescase_staff_assignments(id)"
        "onupdaterestrictondeleterestrict" in fk_orig_assignment_clause
    )
    assert (
        "foreignkey(substitute_assignment_id)referencescase_staff_assignments(id)"
        "onupdaterestrictondeleterestrict" in fk_sub_assign_clause
    )
    assert (
        "foreignkey(original_schedule_id)referencesstaff_schedule(id)"
        "onupdaterestrictondeleterestrict" in fk_orig_schedule_clause
    )

    assert "chk_assignment_schedule_leave_substitution_resolution" in resolution_clause
    assert "resolution_type='substitute'" in resolution_clause
    assert "substitute_assignment_idisnotnull" in resolution_clause
    assert "substitute_assignment_id<>original_assignment_id" in resolution_clause
    assert "resolution_typein('leave_only','defer_following_assignments')" in resolution_clause
    assert "substitute_assignment_idisnull" in resolution_clause

    assert "chk_leave_sub_actor_reason_key" in actor_reason_clause
    assert "char_length(trim(event_key))>0" in actor_reason_clause
    assert "char_length(trim(actor))>0" in actor_reason_clause
    assert "char_length(trim(reason))>0" in actor_reason_clause

    assert "chk_leave_sub_schedule_snapshot" in schedule_snapshot_clause
    assert "json_type(schedule_snapshot)='object'" in schedule_snapshot_clause

    assert "chk_leave_sub_payroll_snapshot" in payroll_snapshot_clause
    assert "json_type(payroll_snapshot)='object'" in payroll_snapshot_clause


def test_sql_statements_are_whitelisted_by_exact_shape():
    statements = [_normalize_whitespace(stmt) for stmt in _split_sql_statements(_schema_sql())]
    assert len(statements) == 5
    for statement in statements:
        _validate_statement(statement)


def test_validate_statement_accepts_five_legal_statements():
    statements = LEGAL_STATEMENTS_FIXTURES
    assert len(statements) == 5
    for statement in statements:
        _validate_statement(statement)


def test_validate_statement_rejects_legal_prefix_or_non_signal_trigger_body():
    legal = ""
    for statement in _split_sql_statements(_schema_sql()):
        if "BEFORE UPDATE" in statement:
            legal = statement
            break
    assert legal
    _validate_statement(legal)

    with pytest.raises(AssertionError, match="not allowlisted"):
        _validate_statement(f"{legal} DROP TABLE orders")
    with pytest.raises(AssertionError, match="not allowlisted"):
        _validate_statement(
            "CREATE TRIGGER trg_assignment_schedule_leave_substitution_events_before_update "
            "BEFORE UPDATE ON assignment_schedule_leave_substitution_events FOR EACH ROW "
            "SET actor='x'"
        )
    with pytest.raises(AssertionError, match="not allowlisted"):
        _validate_statement(
            f"{CREATE_TABLE_STATEMENT_FIXTURE} DROP TRIGGER IF EXISTS trg_assignment_schedule_leave_substitution_events_before_update"
        )
    with pytest.raises(AssertionError, match="not allowlisted"):
        _validate_statement(
            """CREATE TRIGGER trg_assignment_schedule_leave_substitution_events_before_update
            BEFORE UPDATE ON assignment_schedule_leave_substitution_events
            FOR EACH ROW
            UPDATE orders SET case_no='X'"""
        )
    with pytest.raises(AssertionError, match="not allowlisted"):
        _validate_statement(
            """CREATE TRIGGER trg_assignment_schedule_leave_substitution_events_before_delete
            BEFORE DELETE ON assignment_schedule_leave_substitution_events
            FOR EACH ROW
            DELETE FROM orders"""
        )


def test_validate_statement_rejects_comment_spliced_sql():
    comment_cases = [
        "ALTER/**/TABLE `orders` ADD COLUMN legacy_flag TINYINT",
        "UPDATE/**/`orders` SET notes='x' WHERE id=1",
        "DELETE/**/FROM `orders` WHERE id=1",
        "ALTER--comment\nTABLE `orders` ADD COLUMN legacy_flag TINYINT",
        "ALTER#comment\nTABLE `orders` ADD COLUMN legacy_flag TINYINT",
    ]
    for comment_case in comment_cases:
        with pytest.raises(AssertionError, match="not allowlisted"):
            _validate_statement(comment_case)


def test_comment_stripping_preserves_statement_boundary_and_detects_nested_comments():
    sample = """
    CREATE TABLE sample(id INT); -- inline comment
    /* block
       comment */
    INSERT INTO sample VALUES (1);
    """
    assert [stmt.strip() for stmt in _split_sql_statements(sample)] == [
        "CREATE TABLE sample(id INT)",
        "INSERT INTO sample VALUES (1)",
    ]
    boundary_sample = (
        "ALTER/**/TABLE `orders` ADD COLUMN legacy_flag TINYINT;"
        "UPDATE/**/`orders` SET notes='x' WHERE id = 1;"
        "DELETE/**/FROM `orders`;"
    )
    boundary_statements = [stmt.strip() for stmt in _split_sql_statements(boundary_sample)]
    assert boundary_statements == [
        "ALTER TABLE `orders` ADD COLUMN legacy_flag TINYINT",
        "UPDATE `orders` SET notes='x' WHERE id = 1",
        "DELETE FROM `orders`",
    ]
    assert _contains_forbidden_mutation(boundary_statements[0], "ALTER", "orders")
    assert _contains_forbidden_mutation(boundary_statements[1], "UPDATE", "orders")
    assert _contains_forbidden_mutation(boundary_statements[2], "DELETE", "orders")

    assert _contains_forbidden_mutation(
        "/*c*/ALTER /*x*/ TABLE `orders` ADD COLUMN legacy_flag TINYINT;",
        "ALTER",
        "orders",
    )


def test_adversarial_mutation_cases_for_protected_tables_are_blocked():
    protected_tables = ["orders", "case_staff_assignments", "staff_schedule"]
    operations = ("ALTER", "INSERT", "UPDATE", "DELETE", "REPLACE", "TRUNCATE", "DROP", "RENAME")
    adversarial_cases = []

    for operation in operations:
        for table in protected_tables:
            if operation == "ALTER":
                sql = f"ALTER/**/TABLE `{table}` ADD COLUMN legacy_flag TINYINT"
            elif operation == "INSERT":
                sql = f"INSERT/**/INTO `{table}` (id) VALUES (9999)"
            elif operation == "UPDATE":
                sql = f"UPDATE/**/`{table}` SET notes='x' WHERE id = 1"
            elif operation == "DELETE":
                sql = f"DELETE/**/FROM `{table}` WHERE id = 1"
            elif operation == "REPLACE":
                sql = f"REPLACE/**/INTO `{table}` (id) VALUES (9999)"
            elif operation == "TRUNCATE":
                sql = f"TRUNCATE/**/TABLE `{table}`"
            elif operation == "DROP":
                sql = f"DROP/**/TABLE `{table}`"
            elif operation == "RENAME":
                sql = f"RENAME TABLE harmless TO `{table}`"
            else:
                raise AssertionError(operation)
            adversarial_cases.append((sql, operation, table))

    for statement, operation, table in adversarial_cases:
        with pytest.raises(AssertionError, match="not allowlisted"):
            _validate_statement(statement)
        op_len = len(operation)
        with_comment = (
            statement[:op_len] + "/*block*/" + statement[op_len:]
            if statement.upper().startswith(operation)
            else statement
        )
        with pytest.raises(AssertionError, match="not allowlisted"):
            _validate_statement(with_comment)


def test_rename_protection_checks_source_and_target_tables():
    for table in PROTECTED_TABLES:
        with pytest.raises(AssertionError, match="not allowlisted|受保護既有表"):
            _validate_statement(f"RENAME TABLE {table} TO harmless")
        with pytest.raises(AssertionError, match="not allowlisted|受保護既有表"):
            _validate_statement(f"RENAME TABLE harmless TO {table}")


def test_trigger_statements_complete_and_block_mutation():
    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    load_schema_parts(cursor, parts_dir)

    trigger_stmts = [
        stmt for stmt in cursor.executed
        if "CREATE TRIGGER" in stmt and "assignment_schedule_leave_substitution_events" in stmt
    ]

    assert len(trigger_stmts) == 2, f"預期應擷取出 2 個完整 CREATE TRIGGER 語句，實際：{len(trigger_stmts)}"

    for stmt in trigger_stmts:
        assert "DELIMITER" not in stmt
        assert "BEGIN" not in stmt
        assert "END IF" not in stmt
        assert stmt.strip().startswith("CREATE TRIGGER")

    update_stmt = next(s for s in trigger_stmts if "before_update" in s)
    assert "BEFORE UPDATE ON assignment_schedule_leave_substitution_events" in update_stmt
    assert "SIGNAL SQLSTATE '45000'" in update_stmt
    assert "cannot be updated" in update_stmt

    delete_stmt = next(s for s in trigger_stmts if "before_delete" in s)
    assert "BEFORE DELETE ON assignment_schedule_leave_substitution_events" in delete_stmt
    assert "SIGNAL SQLSTATE '45000'" in delete_stmt
    assert "cannot be deleted" in delete_stmt


def test_schema_loader_respects_lexical_order_after_staff_schedule_part():
    cursor = RecordingCursor()
    parts_dir = SCHEMA_PATH.parent

    loaded_parts = load_schema_parts(cursor, parts_dir)
    assert "100_staff_schedule_allow_same_day_multiple_assignments.sql" in loaded_parts
    assert SCHEMA_PATH.name in loaded_parts

    idx_100 = loaded_parts.index("100_staff_schedule_allow_same_day_multiple_assignments.sql")
    idx_101 = loaded_parts.index(SCHEMA_PATH.name)
    assert idx_100 < idx_101, (
        f"載入順序必須保證 100... < {SCHEMA_PATH.name}，目前索引：{idx_100}, {idx_101}"
    )


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
    assert any(
        "assignment_schedule_leave_substitution_events" in statement
        for statement in first_run_statements
    )
    assert any(
        "trg_assignment_schedule_leave_substitution_events_before_update" in statement
        for statement in first_run_statements
    )
    assert any(
        "trg_assignment_schedule_leave_substitution_events_before_delete" in statement
        for statement in first_run_statements
    )

    assert load_schema_parts(cursor, parts_dir) == loaded_parts
    assert cursor.executed == first_run_statements + first_run_statements

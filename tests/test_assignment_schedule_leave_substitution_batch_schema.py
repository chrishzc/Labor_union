import re
import pytest
from pathlib import Path
import tempfile
import shutil
from contextlib import contextmanager

from scripts.init_db import load_schema_parts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema_parts" / "102_assignment_schedule_leave_substitution_batches.sql"
SCHEMA_PARTS_DIR = SCHEMA_PATH.parent
PROTECTED_TABLES = (
    "orders",
    "case_staff_assignments",
    "staff_schedule",
    "actual_hours_adjustments",
    "staff_payments",
    "staff_monthly_settlements",
    "staff_monthly_settlement_details",
    "caregiver_matching_plans",
    "caregiver_matching_plan_events",
    "caregiver_availability_locks",
    "caregiver_availability_lock_days",
    "caregiver_availability_lock_events",
)

HEADER_TABLE = "assignment_schedule_leave_substitution_batches"
EVENT_TABLE = "assignment_schedule_leave_substitution_events"


def _schema_sql():
    return SCHEMA_PATH.read_text(encoding="utf-8")


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

    if normalized.startswith("CREATE TABLE IF NOT EXISTS"):
        tokens = _statement_tokens(statement)
        if tokens[:6] != ["create", "table", "if", "not", "exists", HEADER_TABLE]:
            raise AssertionError(f"statement not allowlisted: {statement}")
    elif normalized.startswith("CREATE TRIGGER"):
        legal_trigger_shape = re.compile(
            r"^CREATE TRIGGER TRG_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES_BEFORE_(UPDATE|DELETE) "
            r"BEFORE (UPDATE|DELETE) ON ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES FOR EACH ROW "
            r"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = "
            r"'ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES RECORDS CANNOT BE (UPDATED|DELETED)'$"
        )
        match = legal_trigger_shape.fullmatch(normalized)
        if not match or not (
            (match.group(1), match.group(2), match.group(3))
            in {("UPDATE", "UPDATE", "UPDATED"), ("DELETE", "DELETE", "DELETED")}
        ):
            raise AssertionError(f"statement not allowlisted: {statement}")
    elif normalized.startswith("DROP TRIGGER IF EXISTS"):
        if normalized not in {
            "DROP TRIGGER IF EXISTS "
            "TRG_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES_BEFORE_UPDATE",
            "DROP TRIGGER IF EXISTS "
            "TRG_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES_BEFORE_DELETE",
        }:
            raise AssertionError(f"statement not allowlisted: {statement}")
    elif normalized.startswith("SET @"):
        variable_match = re.match(r"SET @([A-Z0-9_]+)\s*=", normalized)
        if not variable_match or not (
            variable_match.group(1).startswith("BATCH_")
            or variable_match.group(1).startswith("EVENT_BATCH_")
            or variable_match.group(1) == "EVENTS_TABLE_EXISTS"
        ):
            raise AssertionError(f"statement not allowlisted: {statement}")
        if "CREATE TABLE" in normalized:
            raise AssertionError(f"statement not allowlisted: {statement}")
        if "ALTER TABLE" in normalized:
            if f"ALTER TABLE `{EVENT_TABLE.upper()}`" not in normalized:
                raise AssertionError(f"statement not allowlisted: {statement}")
            expected_tokens = {
                "EVENT_BATCH_KEY_COL_ACTION_SQL": {
                    "add", "column", "batch_key", "varchar", "null"
                },
                "EVENT_BATCH_ITEM_INDEX_COL_ACTION_SQL": {
                    "add", "column", "batch_item_index", "int", "unsigned", "null"
                },
                "EVENT_BATCH_LINKAGE_INDEX_ACTION_SQL": {
                    "add", "unique", "key",
                    "uq_assignment_schedule_leave_substitution_events_batch_linkage",
                    "batch_key", "batch_item_index",
                },
                "EVENT_BATCH_WORK_DATE_INDEX_ACTION_SQL": {
                    "add", "index",
                    "idx_assignment_schedule_leave_substitution_events_batch_key",
                    "batch_key", "work_date",
                },
                "EVENT_BATCH_FK_ACTION_SQL": {
                    "add", "constraint",
                    "fk_assignment_schedule_leave_substitution_events_batch",
                    "foreign", "key", "batch_key",
                    "assignment_schedule_leave_substitution_batches",
                },
                "EVENT_BATCH_LINKAGE_CHECK_ACTION_SQL": {
                    "add", "constraint",
                    "chk_assignment_schedule_leave_substitution_events_batch_linkage",
                    "check", "batch_key", "batch_item_index",
                },
            }
            required = expected_tokens.get(variable_match.group(1))
            tokens = set(_statement_tokens(statement))
            if required is None or not required.issubset(tokens):
                raise AssertionError(f"statement not allowlisted: {statement}")
    elif normalized.startswith(("PREPARE ", "EXECUTE ", "DEALLOCATE PREPARE ")):
        if not re.search(r"\bSTMT_(?:BATCH|EVENT_BATCH)_[A-Z0-9_]+\b", normalized):
            raise AssertionError(f"statement not allowlisted: {statement}")
    else:
        raise AssertionError(f"statement not allowlisted: {statement}")

    for table in PROTECTED_TABLES:
        for operation in ("ALTER", "INSERT", "UPDATE", "DELETE", "REPLACE", "TRUNCATE", "DROP", "RENAME"):
            if _contains_forbidden_mutation(statement, operation, table):
                raise AssertionError(
                    f"受保護既有表 {table} 檢測到禁止操作 {operation}：{statement}"
                )


def _extract_create_table_statement() -> str:
    for statement in _split_sql_statements(_schema_sql()):
        if statement.lstrip().upper().startswith("CREATE TABLE IF NOT EXISTS"):
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


@contextmanager
def _minimal_schema_parts_dir():
    source_parts = SCHEMA_PARTS_DIR
    with tempfile.TemporaryDirectory(prefix="pytest_schema_parts_") as tmp_root:
        schema_parts_dir = Path(tmp_root) / "schema_parts"
        schema_parts_dir.mkdir(parents=True, exist_ok=True)

        minimal_101 = "-- 101 placeholder preserved only for lexical ordering."
        (schema_parts_dir / "101_assignment_schedule_leave_substitution_events.sql").write_text(
            minimal_101, encoding="utf-8"
        )
        shutil.copy2(
            source_parts / "102_assignment_schedule_leave_substitution_batches.sql",
            schema_parts_dir / "102_assignment_schedule_leave_substitution_batches.sql",
        )

        yield schema_parts_dir


def test_schema_file_exists():
    assert SCHEMA_PATH.exists()


def test_mysql_identifiers_do_not_exceed_64_characters():
    names = re.findall(
        r"\b(?:CONSTRAINT|KEY|INDEX|TRIGGER)\s+`?([A-Za-z0-9_]+)",
        _schema_sql(),
        flags=re.IGNORECASE,
    )
    assert names
    assert not {name: len(name) for name in names if len(name) > 64}


def test_schema_structure_has_batch_header_constraints():
    compact = _compact_sql(_strip_comments(_schema_sql().lower()))

    assert "createtableifnotexistsassignment_schedule_leave_substitution_batches" in compact
    assert "batch_keyvarchar(100)notnull" in compact
    assert "case_novarchar(50)notnull" in compact
    assert "preview_fingerprintchar(64)charactersetasciicollateascii_binnotnull" in compact
    assert "item_countintunsignednotnull" in compact
    assert "actorvarchar(100)notnull" in compact
    assert "reasonvarchar(255)notnull" in compact
    assert "request_snapshotjsonnotnull" in compact
    assert "occurred_attimestampnotnulldefaultcurrent_timestamp" in compact
    assert "idx_assignment_schedule_leave_substitution_batches_case_time(case_no,occurred_at)" in compact
    assert "foreignkey(case_no)referencesorders(case_no)onupdaterestrictondeleterestrict" in compact
    assert "chk_assignment_schedule_leave_substitution_batches_identity" in compact
    assert "chk_leave_batch_fingerprint" in compact
    assert "preview_fingerprintregexp'^[0-9a-f]{64}$'" in compact
    assert "chk_assignment_schedule_leave_substitution_batches_item_count" in compact
    assert "chk_leave_batch_request_snapshot" in compact
    assert "fail_closed_batch_header_invalid_spec_review_required" in compact
    assert "@event_batch_linkage_index_any=2" in compact
    assert "@event_batch_work_date_index_any=2" in compact
    assert "frominformation_schema.check_constraintscjoininformation_schema.table_constraintst" in compact
    assert "t.table_name='assignment_schedule_leave_substitution_events'" in compact


def test_fingerprint_metadata_guard_is_case_sensitive_and_lowercase_only():
    sql = _strip_comments(_schema_sql())
    guard_start = sql.index(
        "CONSTRAINT_NAME = "
        "'chk_leave_batch_fingerprint'"
    )
    guard_end = sql.index(
        "CONSTRAINT_NAME = "
        "'chk_assignment_schedule_leave_substitution_batches_item_count'",
        guard_start,
    )
    guard = sql[guard_start:guard_end]

    assert "UPPER(" not in guard
    assert "BINARY REPLACE(" in guard
    assert "= BINARY '(preview_fingerprintREGEXP''^[0-9a-f]{64}$'')'" in guard
    assert "LIKE 'regexp_like(preview_fingerprint,%'" in guard
    assert "LIKE BINARY '%^[0-9a-f]{64}$%'" in guard
    assert "NOT LIKE BINARY '%[0-9A-F]{64}%'" in guard


def test_batch_header_constraint_clauses_are_named_and_present():
    create_stmt = _extract_create_table_statement()
    compact_create = _compact_sql(create_stmt.lower())

    fk_constraint = _extract_constraint_clause(
        compact_create,
        "fk_assignment_schedule_leave_substitution_batches_case_no",
    )
    identity_constraint = _extract_constraint_clause(
        compact_create,
        "chk_assignment_schedule_leave_substitution_batches_identity",
    )
    fingerprint_constraint = _extract_constraint_clause(
        compact_create,
        "chk_leave_batch_fingerprint",
    )
    item_count_constraint = _extract_constraint_clause(
        compact_create,
        "chk_assignment_schedule_leave_substitution_batches_item_count",
    )
    snapshot_constraint = _extract_constraint_clause(
        compact_create,
        "chk_leave_batch_request_snapshot",
    )

    assert "foreignkey(case_no)referencesorders(case_no)onupdaterestrictondeleterestrict" in fk_constraint
    assert "char_length(trim(batch_key))>0" in identity_constraint
    assert "char_length(trim(case_no))>0" in identity_constraint
    assert "char_length(trim(actor))>0" in identity_constraint
    assert "char_length(trim(reason))>0" in identity_constraint
    assert "preview_fingerprintregexp'^[0-9a-f]{64}$'" in fingerprint_constraint
    assert "item_count>=1" in item_count_constraint
    assert "json_type(request_snapshot)='object'" in snapshot_constraint


def test_sql_statements_are_whitelisted_and_blocked_on_forbidden_tables():
    statements = [_normalize_whitespace(stmt) for stmt in _split_sql_statements(_schema_sql())]
    assert len(statements) >= 20
    for statement in statements:
        _validate_statement(statement)

    legal_triggers = [
        "CREATE TRIGGER trg_assignment_schedule_leave_substitution_batches_before_update "
        "BEFORE UPDATE ON assignment_schedule_leave_substitution_batches "
        "FOR EACH ROW "
        "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be updated'",
        "CREATE TRIGGER trg_assignment_schedule_leave_substitution_batches_before_delete "
        "BEFORE DELETE ON assignment_schedule_leave_substitution_batches "
        "FOR EACH ROW "
        "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'assignment_schedule_leave_substitution_batches records cannot be deleted'",
    ]
    for statement in legal_triggers:
        _validate_statement(statement)


def test_trigger_statements_are_present_and_only_signal_errors():
    statements = _split_sql_statements(_schema_sql())
    trigger_statements = [
        stmt
        for stmt in statements
        if stmt.lstrip().lower().startswith("create trigger ")
    ]
    assert len(trigger_statements) == 2
    assert all("FOR EACH ROW" in stmt.upper() for stmt in trigger_statements)
    assert all("SIGNAL SQLSTATE" in stmt.upper() for stmt in trigger_statements)
    assert all("45000" in stmt for stmt in trigger_statements)
    assert any("cannot be updated" in stmt.lower() for stmt in trigger_statements)
    assert any("cannot be deleted" in stmt.lower() for stmt in trigger_statements)


def test_validate_statement_rejects_comment_spliced_sql():
    comment_cases = [
        "ALTER/**/TABLE `orders` ADD COLUMN legacy_flag TINYINT",
        "UPDATE/**/`orders` SET notes='x' WHERE id=1",
        "DELETE/**/FROM `orders` WHERE id=1",
        "ALTER--comment\nTABLE `orders` ADD COLUMN legacy_flag TINYINT",
        "ALTER#comment\nTABLE `orders` ADD COLUMN legacy_flag TINYINT",
    ]
    for comment_case in comment_cases:
        with pytest.raises(AssertionError, match="受保護既有表|not allowlisted"):
            _validate_statement(comment_case)


def test_adversarial_mutation_cases_for_protected_tables_are_blocked():
    operations = ("ALTER", "INSERT", "UPDATE", "DELETE", "REPLACE", "TRUNCATE", "DROP", "RENAME")
    for operation in operations:
        for table in PROTECTED_TABLES:
            if operation == "ALTER":
                case = f"ALTER/**/TABLE `{table}` ADD COLUMN legacy_flag TINYINT"
            elif operation == "INSERT":
                case = f"INSERT/**/INTO `{table}` (id) VALUES (1)"
            elif operation == "UPDATE":
                case = f"UPDATE/**/`{table}` SET notes='x' WHERE id = 1"
            elif operation == "DELETE":
                case = f"DELETE/**/FROM `{table}` WHERE id = 1"
            elif operation == "REPLACE":
                case = f"REPLACE/**/INTO `{table}` (id) VALUES (1)"
            elif operation == "TRUNCATE":
                case = f"TRUNCATE/**/TABLE `{table}`"
            elif operation == "DROP":
                case = f"DROP/**/TABLE `{table}`"
            elif operation == "RENAME":
                case = f"RENAME TABLE harmless TO `{table}`"
            else:
                raise AssertionError(operation)

            with pytest.raises(AssertionError, match="受保護既有表|not allowlisted"):
                _validate_statement(case)


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE IF NOT EXISTS assignment_schedule_leave_substitution_failed_attempts (id BIGINT)",
        "CREATE TABLE IF NOT EXISTS assignment_schedule_leave_substitution_projection (id BIGINT)",
        "CREATE TABLE IF NOT EXISTS assignment_schedule_leave_substitution_per_date (id BIGINT)",
        "SET @batch_bad = 'CREATE TABLE assignment_schedule_leave_substitution_failed_attempts (id BIGINT)'",
        "SET @event_batch_bad = 'ALTER TABLE staff_payments ADD COLUMN bad INT'",
        "PREPARE arbitrary_stmt FROM @batch_bad",
        "EXECUTE arbitrary_stmt",
        "DEALLOCATE PREPARE arbitrary_stmt",
    ],
)
def test_validator_rejects_out_of_scope_tables_and_dynamic_statements(statement):
    with pytest.raises(AssertionError, match="受保護既有表|not allowlisted"):
        _validate_statement(statement)


def test_rename_protection_checks_source_and_target_tables():
    for table in PROTECTED_TABLES:
        with pytest.raises(AssertionError, match="受保護既有表|not allowlisted"):
            _validate_statement(f"RENAME TABLE {table} TO harmless")
        with pytest.raises(AssertionError, match="受保護既有表|not allowlisted"):
            _validate_statement(f"RENAME TABLE harmless TO {table}")


def test_schema_loader_respects_lexical_order_after_event_schema():
    cursor = RecordingCursor()
    loaded_parts = load_schema_parts(cursor, SCHEMA_PARTS_DIR)

    assert "101_assignment_schedule_leave_substitution_events.sql" in loaded_parts
    assert "102_assignment_schedule_leave_substitution_batches.sql" in loaded_parts

    idx_101 = loaded_parts.index("101_assignment_schedule_leave_substitution_events.sql")
    idx_102 = loaded_parts.index("102_assignment_schedule_leave_substitution_batches.sql")
    assert idx_101 < idx_102


def test_migration_is_additive_and_replayable_by_schema_parts_loader():
    with _minimal_schema_parts_dir() as schema_parts_dir:
        cursor = StatefulMigrationCursor()
        first_loaded = load_schema_parts(cursor, schema_parts_dir)
        assert "102_assignment_schedule_leave_substitution_batches.sql" in first_loaded

        first_run_ddl = list(cursor.ddl_executed)

        load_schema_parts(cursor, schema_parts_dir)
        second_run_ddl = cursor.ddl_executed[len(first_run_ddl):]

        assert len(first_run_ddl) >= 8, (
            f"first run expected at least 8 DDL statements: {len(first_run_ddl)}"
        )
        assert len(second_run_ddl) == 2
        assert all(stmt.lstrip().upper().startswith("CREATE TRIGGER ") for stmt in second_run_ddl)


def test_fail_closed_guard_blocks_existing_malformed_event_batch_columns():
    with _minimal_schema_parts_dir() as schema_parts_dir:
        cursor = StatefulMigrationCursor(
            batch_table_exists=True,
            batch_header_valid=False,
        )
        with pytest.raises(RuntimeError, match="FAIL_CLOSED_BATCH_HEADER_INVALID_SPEC_REVIEW_REQUIRED"):
            load_schema_parts(cursor, schema_parts_dir)

        cursor = StatefulMigrationCursor(batch_key_col_exists=True, batch_key_col_valid=False)
        with pytest.raises(RuntimeError, match="FAIL_CLOSED_BATCH_KEY_COLUMN_INVALID_SPEC_REVIEW_REQUIRED"):
            load_schema_parts(cursor, schema_parts_dir)

        cursor = StatefulMigrationCursor(
            batch_linkage_index_exists=True,
            batch_linkage_index_valid=False,
            batch_key_col_exists=True,
            batch_item_index_col_exists=True,
        )
        with pytest.raises(RuntimeError, match="FAIL_CLOSED_EVENT_BATCH_LINKAGE_INDEX_INVALID_SPEC_REVIEW_REQUIRED"):
            load_schema_parts(cursor, schema_parts_dir)

        cursor = StatefulMigrationCursor(
            batch_work_date_index_exists=True,
            batch_work_date_index_valid=False,
            batch_key_col_exists=True,
            batch_item_index_col_exists=True,
            batch_linkage_index_exists=True,
        )
        with pytest.raises(RuntimeError, match="FAIL_CLOSED_EVENT_BATCH_KEY_WORK_DATE_INDEX_INVALID_SPEC_REVIEW_REQUIRED"):
            load_schema_parts(cursor, schema_parts_dir)

        cursor = StatefulMigrationCursor(
            batch_fk_exists=True,
            batch_fk_valid=False,
            batch_key_col_exists=True,
            batch_item_index_col_exists=True,
            batch_linkage_index_exists=True,
            batch_work_date_index_exists=True,
        )
        with pytest.raises(RuntimeError, match="FAIL_CLOSED_EVENT_BATCH_FK_INVALID_SPEC_REVIEW_REQUIRED"):
            load_schema_parts(cursor, schema_parts_dir)

        cursor = StatefulMigrationCursor(
            batch_before_update_trigger_exists=True,
            batch_before_update_trigger_valid=False,
        )
        with pytest.raises(RuntimeError, match="FAIL_CLOSED_BATCH_BEFORE_UPDATE_TRIGGER_INVALID_SPEC_REVIEW_REQUIRED"):
            load_schema_parts(cursor, schema_parts_dir)

        cursor = StatefulMigrationCursor(
            batch_linkage_check_exists=True,
            batch_linkage_check_valid=False,
            batch_key_col_exists=True,
            batch_item_index_col_exists=True,
        )
        with pytest.raises(RuntimeError, match="FAIL_CLOSED_EVENT_BATCH_LINKAGE_CHECK_INVALID_SPEC_REVIEW_REQUIRED"):
            load_schema_parts(cursor, schema_parts_dir)


class RecordingCursor:
    def __init__(self):
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append(statement.strip())


class StatefulMigrationCursor:
    def __init__(
        self,
        batch_key_col_exists=False,
        batch_key_col_valid=True,
        batch_item_index_col_exists=False,
        batch_item_index_col_valid=True,
        batch_linkage_index_exists=False,
        batch_linkage_index_valid=True,
        batch_work_date_index_exists=False,
        batch_work_date_index_valid=True,
        batch_fk_exists=False,
        batch_fk_valid=True,
        batch_linkage_check_exists=False,
        batch_linkage_check_valid=True,
        batch_before_update_trigger_exists=False,
        batch_before_update_trigger_valid=True,
        batch_before_delete_trigger_exists=False,
        batch_before_delete_trigger_valid=True,
        batch_table_exists=False,
        batch_header_valid=True,
    ):
        self.events_table_exists = True
        self.batch_key_col_exists = batch_key_col_exists
        self.batch_key_col_valid = batch_key_col_valid
        self.batch_item_index_col_exists = batch_item_index_col_exists
        self.batch_item_index_col_valid = batch_item_index_col_valid
        self.batch_linkage_index_exists = batch_linkage_index_exists
        self.batch_linkage_index_valid = batch_linkage_index_valid
        self.batch_work_date_index_exists = batch_work_date_index_exists
        self.batch_work_date_index_valid = batch_work_date_index_valid
        self.batch_fk_exists = batch_fk_exists
        self.batch_fk_valid = batch_fk_valid
        self.batch_linkage_check_exists = batch_linkage_check_exists
        self.batch_linkage_check_valid = batch_linkage_check_valid
        self.batch_before_update_trigger_exists = batch_before_update_trigger_exists
        self.batch_before_update_trigger_valid = batch_before_update_trigger_valid
        self.batch_before_delete_trigger_exists = batch_before_delete_trigger_exists
        self.batch_before_delete_trigger_valid = batch_before_delete_trigger_valid
        self.events_table_exists = True
        self.batch_table_exists = batch_table_exists
        self.batch_header_valid = batch_header_valid
        self.prepared = {}
        self.current_fetch = []
        self.executed = []
        self.ddl_executed = []

    @property
    def batch_linkage_index_seq1(self):
        return 1 if (self.batch_linkage_index_exists and self.batch_linkage_index_valid) else 0

    @property
    def batch_linkage_index_seq2(self):
        return 1 if (self.batch_linkage_index_exists and self.batch_linkage_index_valid) else 0

    @property
    def batch_work_date_index_seq1(self):
        return 1 if (self.batch_work_date_index_exists and self.batch_work_date_index_valid) else 0

    @property
    def batch_work_date_index_seq2(self):
        return 1 if (self.batch_work_date_index_exists and self.batch_work_date_index_valid) else 0

    def _as_upper(self, statement: str) -> str:
        return " ".join(statement.upper().split())

    def execute(self, statement, params=None):
        self.executed.append(statement)
        stmt = self._as_upper(statement)

        if stmt.startswith("CREATE TABLE IF NOT EXISTS"):
            if "ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES" in stmt:
                if self.batch_table_exists:
                    return
                self.batch_table_exists = True
            if "ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS" in stmt:
                if self.events_table_exists:
                    return
                self.events_table_exists = True
            self.ddl_executed.append("create_table")
            return

        if stmt.startswith("CREATE TRIGGER"):
            self.ddl_executed.append(statement)
            if "ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES_BEFORE_UPDATE" in stmt:
                self.batch_before_update_trigger_exists = True
            else:
                self.batch_before_delete_trigger_exists = True
            return

        if stmt.startswith("ALTER TABLE `ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS` ADD COLUMN `BATCH_KEY`"):
            self.ddl_executed.append(statement)
            self.batch_key_col_exists = True
            return
        if stmt.startswith("ALTER TABLE `ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS` ADD COLUMN `BATCH_ITEM_INDEX`"):
            self.ddl_executed.append(statement)
            self.batch_item_index_col_exists = True
            return
        if stmt.startswith("ALTER TABLE `ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS` ADD UNIQUE KEY"):
            self.ddl_executed.append(statement)
            self.batch_linkage_index_exists = True
            self.batch_linkage_index_valid = True
            return
        if stmt.startswith("ALTER TABLE `ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS` ADD INDEX"):
            self.ddl_executed.append(statement)
            if "BATCH_KEY`" in stmt and "WORK_DATE`" in stmt:
                self.batch_work_date_index_exists = True
                self.batch_work_date_index_valid = True
            return
        if stmt.startswith("ALTER TABLE `ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS` ADD CONSTRAINT"):
            self.ddl_executed.append(statement)
            if "FK_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH" in stmt:
                self.batch_fk_exists = True
                self.batch_fk_valid = True
            elif "CHK_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH_LINKAGE" in stmt:
                self.batch_linkage_check_exists = True
                self.batch_linkage_check_valid = True
            return

        if stmt.startswith("SET @"):
            if stmt.startswith("SET @BATCH_HEADER_EXACT"):
                self.current_fetch = [
                    (1 if (self.batch_table_exists and self.batch_header_valid) else 0,)
                ]
                return

            if "INFORMATION_SCHEMA.TRIGGERS" in stmt and "BATCH_KEY" in stmt and "BEFORE_UPDATE" in stmt:
                self.current_fetch = [(0,)]
                return

            if "INFORMATION_SCHEMA.TRIGGERS" in stmt and "EVENT_OBJECT_TABLE = 'ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_BATCHES'" in stmt:
                if "BATCH_KEY" in stmt and "UPDATE" in stmt:
                    self.current_fetch = [(1 if self.batch_before_update_trigger_exists else 0,)]
                elif "BATCH_KEY" in stmt and "DELETE" in stmt:
                    self.current_fetch = [(1 if self.batch_before_delete_trigger_exists else 0,)]
                else:
                    self.current_fetch = [(1 if self.batch_before_update_trigger_exists else 0,)]
                return

            if "INFORMATION_SCHEMA.COLUMNS" in stmt and "TABLE_NAME = 'ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS'" in stmt:
                if "COLUMN_NAME = 'BATCH_KEY'" in stmt:
                    if "DATA_TYPE" in stmt or "CHARACTER_MAXIMUM_LENGTH" in stmt or "IS_NULLABLE" in stmt:
                        self.current_fetch = [(1 if (self.batch_key_col_exists and self.batch_key_col_valid) else 0,)]
                    else:
                        self.current_fetch = [(1 if self.batch_key_col_exists else 0,)]
                elif "COLUMN_NAME = 'BATCH_ITEM_INDEX'" in stmt:
                    if "DATA_TYPE" in stmt or "COLUMN_TYPE" in stmt or "IS_NULLABLE" in stmt:
                        self.current_fetch = [(1 if (self.batch_item_index_col_exists and self.batch_item_index_col_valid) else 0,)]
                    else:
                        self.current_fetch = [(1 if self.batch_item_index_col_exists else 0,)]
                else:
                    self.current_fetch = [(0,)]
                return

            if "INFORMATION_SCHEMA.STATISTICS" in stmt and "TABLE_NAME = 'ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS'" in stmt:
                if "COLUMN_NAME = 'BATCH_KEY'" in stmt and "SEQ_IN_INDEX = 1" in stmt:
                    if "UQ_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH_LINKAGE" in stmt:
                        self.current_fetch = [(self.batch_linkage_index_seq1,)]
                    else:
                        self.current_fetch = [(self.batch_work_date_index_seq1,)]
                elif "COLUMN_NAME = 'BATCH_ITEM_INDEX'" in stmt and "SEQ_IN_INDEX = 2" in stmt:
                    self.current_fetch = [(self.batch_linkage_index_seq2,)]
                elif "COLUMN_NAME = 'WORK_DATE'" in stmt and "SEQ_IN_INDEX = 2" in stmt:
                    self.current_fetch = [(self.batch_work_date_index_seq2,)]
                elif "UQ_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH_LINKAGE" in stmt:
                    count = 2 if self.batch_linkage_index_valid else 3
                    self.current_fetch = [(count if self.batch_linkage_index_exists else 0,)]
                elif "IDX_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH_KEY" in stmt:
                    count = 2 if self.batch_work_date_index_valid else 3
                    self.current_fetch = [(count if self.batch_work_date_index_exists else 0,)]
                else:
                    self.current_fetch = [(0,)]
                return

            if "INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in stmt and "ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS" in stmt:
                if "FK_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH" in stmt:
                    self.current_fetch = [(1 if self.batch_fk_exists else 0,)]
                else:
                    self.current_fetch = [(0,)]
                return

            if "INFORMATION_SCHEMA.KEY_COLUMN_USAGE" in stmt and "FK_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH" in stmt:
                self.current_fetch = [(1 if (self.batch_fk_exists and self.batch_fk_valid) else 0,)]
                return

            if "INFORMATION_SCHEMA.CHECK_CONSTRAINTS" in stmt and "ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS" in stmt:
                if "CHK_ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS_BATCH_LINKAGE" in stmt:
                    if "CHECK_CLAUSE" in stmt:
                        self.current_fetch = [(1 if (self.batch_linkage_check_exists and self.batch_linkage_check_valid) else 0,)]
                    else:
                        self.current_fetch = [(1 if self.batch_linkage_check_exists else 0,)]
                else:
                    self.current_fetch = [(0,)]
                return

            if "INFORMATION_SCHEMA.TABLES" in stmt and "ASSIGNMENT_SCHEDULE_LEAVE_SUBSTITUTION_EVENTS" in stmt:
                self.current_fetch = [(1 if self.events_table_exists else 0,)]
                return

            self.current_fetch = [(0,)]
            return

        if stmt.startswith("PREPARE"):
            match = re.match(r"PREPARE\s+([A-Za-z0-9_]+)\s+FROM\s+@([A-Za-z0-9_]+)", stmt)
            if not match:
                raise AssertionError(f"unsupported PREPARE statement: {statement}")
            self.prepared[match.group(1)] = match.group(2)
            return

        if stmt.startswith("EXECUTE"):
            match = re.match(r"EXECUTE\s+([A-Za-z0-9_]+)", stmt)
            if not match:
                raise AssertionError(f"unsupported EXECUTE statement: {statement}")
            name = match.group(1)
            self._execute_prepared_action(name)
            return

        if stmt.startswith("DEALLOCATE PREPARE"):
            return

        self.current_fetch = [(1,)]

    def _execute_prepared_action(self, prepared_name: str):
        var_name = self.prepared.get(prepared_name, "")

        if var_name == "BATCH_HEADER_GUARD_ACTION_SQL":
            if not self.batch_header_valid:
                raise RuntimeError("FAIL_CLOSED_BATCH_HEADER_INVALID_SPEC_REVIEW_REQUIRED")
            return

        if var_name == "BATCH_BEFORE_UPDATE_TRIGGER_ACTION_SQL":
            if self.batch_before_update_trigger_exists and not self.batch_before_update_trigger_valid:
                raise RuntimeError("FAIL_CLOSED_BATCH_BEFORE_UPDATE_TRIGGER_INVALID_SPEC_REVIEW_REQUIRED")
            if not self.batch_before_update_trigger_exists:
                self.ddl_executed.append("create_trigger")
                self.batch_before_update_trigger_exists = True
            return

        if var_name == "BATCH_BEFORE_DELETE_TRIGGER_ACTION_SQL":
            if self.batch_before_delete_trigger_exists and not self.batch_before_delete_trigger_valid:
                raise RuntimeError("FAIL_CLOSED_BATCH_BEFORE_DELETE_TRIGGER_INVALID_SPEC_REVIEW_REQUIRED")
            if not self.batch_before_delete_trigger_exists:
                self.ddl_executed.append("create_trigger")
                self.batch_before_delete_trigger_exists = True
            return

        if var_name == "EVENT_BATCH_KEY_COL_ACTION_SQL":
            if self.batch_key_col_exists and not self.batch_key_col_valid:
                raise RuntimeError("FAIL_CLOSED_BATCH_KEY_COLUMN_INVALID_SPEC_REVIEW_REQUIRED")
            if not self.batch_key_col_exists:
                self.ddl_executed.append("alter")
                self.batch_key_col_exists = True
            return

        if var_name == "EVENT_BATCH_ITEM_INDEX_COL_ACTION_SQL":
            if self.batch_item_index_col_exists and not self.batch_item_index_col_valid:
                raise RuntimeError("FAIL_CLOSED_BATCH_ITEM_INDEX_COLUMN_INVALID_SPEC_REVIEW_REQUIRED")
            if not self.batch_item_index_col_exists:
                self.ddl_executed.append("alter")
                self.batch_item_index_col_exists = True
            return

        if var_name == "EVENT_BATCH_LINKAGE_INDEX_ACTION_SQL":
            if self.batch_linkage_index_exists and not self.batch_linkage_index_valid:
                raise RuntimeError("FAIL_CLOSED_EVENT_BATCH_LINKAGE_INDEX_INVALID_SPEC_REVIEW_REQUIRED")
            if not self.batch_linkage_index_exists:
                self.ddl_executed.append("alter")
                self.batch_linkage_index_exists = True
                self.batch_linkage_index_valid = True
            return

        if var_name == "EVENT_BATCH_WORK_DATE_INDEX_ACTION_SQL":
            if self.batch_work_date_index_exists and not self.batch_work_date_index_valid:
                raise RuntimeError("FAIL_CLOSED_EVENT_BATCH_KEY_WORK_DATE_INDEX_INVALID_SPEC_REVIEW_REQUIRED")
            if not self.batch_work_date_index_exists:
                self.ddl_executed.append("alter")
                self.batch_work_date_index_exists = True
                self.batch_work_date_index_valid = True
            return

        if var_name == "EVENT_BATCH_FK_ACTION_SQL":
            if self.batch_fk_exists and not self.batch_fk_valid:
                raise RuntimeError("FAIL_CLOSED_EVENT_BATCH_FK_INVALID_SPEC_REVIEW_REQUIRED")
            if not self.batch_fk_exists:
                self.ddl_executed.append("alter")
                self.batch_fk_exists = True
                self.batch_fk_valid = True
            return

        if var_name == "EVENT_BATCH_LINKAGE_CHECK_ACTION_SQL":
            if self.batch_linkage_check_exists and not self.batch_linkage_check_valid:
                raise RuntimeError(
                    "FAIL_CLOSED_EVENT_BATCH_LINKAGE_CHECK_INVALID_SPEC_REVIEW_REQUIRED"
                )
            if not self.batch_linkage_check_exists:
                self.ddl_executed.append("alter")
                self.batch_linkage_check_exists = True
                self.batch_linkage_check_valid = True
            return

        raise AssertionError(f"unsupported prepared action: {var_name}")

    def fetchall(self):
        return []

    def fetchone(self):
        return self.current_fetch[0] if self.current_fetch else (0,)

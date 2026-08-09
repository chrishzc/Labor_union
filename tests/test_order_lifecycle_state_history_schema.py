from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT
    / "db"
    / "schema_parts"
    / "104_order_lifecycle_state_history.sql"
)


def _schema_sql() -> str:
    raw = SCHEMA_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    return text


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def test_order_lifecycle_history_schema_is_additive_and_replayable() -> None:
    sql = _compact(_schema_sql())

    assert "create table if not exists order_lifecycle_state_events" in sql
    assert (
        "drop trigger if exists "
        "trg_order_lifecycle_state_events_before_update"
    ) in sql
    assert (
        "drop trigger if exists "
        "trg_order_lifecycle_state_events_before_delete"
    ) in sql

    forbidden_mutations = (
        r"\bupdate\s+orders\b",
        r"\bdelete\s+from\s+orders\b",
        r"\binsert\s+into\s+orders\b",
        r"\bdrop\s+table\s+(?:if\s+exists\s+)?orders\b",
        r"\balter\s+table\s+orders\b",
    )
    assert all(re.search(pattern, sql) is None for pattern in forbidden_mutations)


def test_event_contract_has_required_columns_keys_and_foreign_key() -> None:
    sql = _compact(_schema_sql())

    required_columns = (
        "case_no varchar(50) not null",
        "trigger_event varchar(100) not null",
        "before_status varchar(20) not null",
        "after_status varchar(20) not null",
        "actor varchar(255) not null",
        "business_date date not null",
        "expected_version bigint unsigned not null",
        "idempotency_key varchar(191) not null",
        "facts_snapshot json not null",
        "created_at timestamp(6) not null default current_timestamp(6)",
    )
    for column in required_columns:
        assert column in sql

    assert (
        "unique key uq_order_lifecycle_state_event_idempotency "
        "( case_no, idempotency_key )"
    ) in sql
    assert (
        "index idx_order_lifecycle_state_event_case_time "
        "( case_no, created_at )"
    ) in sql
    assert "foreign key (case_no) references orders(case_no)" in sql
    assert "on update restrict on delete restrict" in sql


def test_before_and_after_status_allow_only_five_canonical_values() -> None:
    sql = _compact(_schema_sql())
    allowed_values = (
        "'洽談中'",
        "'訂單成立'",
        "'服務中'",
        "'訂單完成'",
        "'訂單取消'",
    )

    for constraint, column in (
        ("chk_order_lifecycle_state_event_before_status", "before_status"),
        ("chk_order_lifecycle_state_event_after_status", "after_status"),
    ):
        match = re.search(
            rf"constraint {constraint} check \( {column} in \( (.*?) \) \)",
            sql,
        )
        assert match is not None
        values = tuple(part.strip() for part in match.group(1).split(","))
        assert values == allowed_values


def test_required_text_and_facts_snapshot_are_database_checked() -> None:
    sql = _compact(_schema_sql())

    for column in ("trigger_event", "actor", "idempotency_key"):
        assert f"char_length(trim({column})) > 0" in sql
    assert "json_type(facts_snapshot) = 'object'" in sql


def test_event_rows_are_database_append_only() -> None:
    sql = _compact(_schema_sql())

    for operation in ("update", "delete"):
        trigger = f"trg_order_lifecycle_state_events_before_{operation}"
        assert f"drop trigger if exists {trigger}" in sql
        assert f"create trigger {trigger}" in sql
        assert (
            f"before {operation} on order_lifecycle_state_events"
            in sql
        )
        assert "signal sqlstate '45000'" in sql

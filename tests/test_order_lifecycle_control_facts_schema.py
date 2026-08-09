from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT
    / "db"
    / "schema_parts"
    / "106_order_lifecycle_control_facts.sql"
)


def _schema_sql() -> str:
    raw = SCHEMA_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    return text


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def test_lifecycle_version_is_guarded_and_not_backfilled() -> None:
    sql = _compact(_schema_sql())

    assert (
        "add column `lifecycle_version` bigint unsigned not null default 0"
        in sql
    )
    assert "column_type = 'bigint unsigned'" in sql
    assert "fail_closed_order_lifecycle_version_invalid_spec" in sql
    for pattern in (
        r"\bupdate\s+orders\b",
        r"\binsert\s+into\s+orders\b",
        r"\bdelete\s+from\s+orders\b",
    ):
        assert re.search(pattern, sql) is None


def test_control_event_contract_is_append_only_and_idempotent() -> None:
    sql = _compact(_schema_sql())

    assert "create table if not exists order_lifecycle_control_events" in sql
    for column in (
        "id bigint unsigned not null auto_increment",
        "case_no varchar(50) not null",
        "control_key varchar(100) not null",
        "actor varchar(100) not null",
        "reason varchar(500) not null",
        "expected_version bigint unsigned not null",
        "idempotency_key varchar(191) not null",
        "payload_snapshot json not null",
        "created_at timestamp(6) not null default current_timestamp(6)",
    ):
        assert column in sql
    assert (
        "control_type enum( 'cancellation', "
        "'actual_start_reconfirmation', 'human_hold' ) not null"
    ) in sql
    assert "action enum('activate', 'clear') not null" in sql
    assert "character set ascii collate ascii_bin not null" in sql
    assert (
        "unique key uq_order_lifecycle_control_event_idempotency "
        "( case_no, idempotency_key )"
    ) in sql
    assert (
        "unique key uq_order_lifecycle_control_event_identity "
        "( id, case_no, control_type, control_key )"
    ) in sql
    assert "payload_hash regexp '^[0-9a-f]{64}$'" in sql
    assert "json_type(payload_snapshot) = 'object'" in sql

    for operation in ("update", "delete"):
        trigger = f"trg_order_lifecycle_control_events_before_{operation}"
        assert f"drop trigger if exists {trigger}" in sql
        assert f"create trigger {trigger}" in sql
        assert (
            f"before {operation} on order_lifecycle_control_events"
            in sql
        )
        assert "signal sqlstate '45000'" in sql


def test_current_projection_has_exact_identity_and_control_shapes() -> None:
    sql = _compact(_schema_sql())

    assert "create table if not exists order_lifecycle_control_state" in sql
    assert (
        "primary key (case_no, control_type, control_key)"
        in sql
    )
    assert "state enum('active', 'cleared') not null" in sql
    assert "release_policy enum('manual', 'expires_at') null" in sql
    assert "expires_at_utc datetime(6) null" in sql
    assert "confirmed_start_date date null" in sql
    assert "deposit_settlement_identity_hash char(64)" in sql
    assert (
        "foreign key ( current_event_id, case_no, control_type, "
        "control_key ) references order_lifecycle_control_events "
        "( id, case_no, control_type, control_key )"
    ) in sql
    assert (
        "idx_order_lifecycle_control_state_case_status_type "
        "( case_no, state, control_type )"
    ) in sql
    assert "control_key = 'order_cancelled'" in sql
    assert "control_key = 'actual_start_reconfirmation'" in sql
    assert "state = 'active' and confirmed_start_date is null" in sql
    assert "state = 'cleared' and confirmed_start_date is not null" in sql
    assert (
        "release_policy = 'manual' and expires_at_utc is null"
        in sql
    )
    assert (
        "release_policy = 'expires_at' and expires_at_utc is not null"
        in sql
    )
    assert (
        "before delete on order_lifecycle_control_state"
        in sql
    )


def test_projection_outbox_is_retryable_and_idempotent() -> None:
    sql = _compact(_schema_sql())

    assert (
        "create table if not exists order_lifecycle_projection_outbox"
        in sql
    )
    assert "lifecycle_event_id bigint unsigned not null" in sql
    assert "intent_key varchar(191) not null" in sql
    assert "scope enum('enter_service', 'auto_complete') not null" in sql
    assert "alert_code varchar(191) not null" in sql
    assert "action enum('open', 'resolve') not null" in sql
    assert (
        "status enum( 'pending', 'processing', 'projected', 'failed' ) "
        "not null default 'pending'"
    ) in sql
    assert "attempt_count int unsigned not null default 0" in sql
    for column in (
        "next_attempt_at_utc datetime(6) null",
        "locked_at_utc datetime(6) null",
        "projected_at_utc datetime(6) null",
        "last_error varchar(1000) null",
    ):
        assert column in sql
    assert (
        "unique key uq_order_lifecycle_projection_outbox_intent "
        "( case_no, intent_key )"
    ) in sql
    assert (
        "idx_order_lifecycle_projection_outbox_retry "
        "( status, next_attempt_at_utc, id )"
    ) in sql
    assert (
        "foreign key (lifecycle_event_id) "
        "references order_lifecycle_state_events(id)"
    ) in sql
    assert "status = 'processing' and locked_at_utc is not null" in sql
    assert "status = 'projected' and projected_at_utc is not null" in sql
    assert "status = 'failed'" in sql
    assert "last_error is not null" in sql


def test_existing_metadata_and_triggers_fail_closed_on_drift() -> None:
    sql = _compact(_schema_sql())

    assert sql.count("information_schema.columns") >= 8
    assert sql.count("information_schema.statistics") >= 3
    assert sql.count("information_schema.referential_constraints") >= 5
    assert sql.count("information_schema.check_constraints") >= 3
    assert sql.count("information_schema.triggers") >= 3
    assert "fail_closed_order_lifecycle_control_events_metadata_drift" in sql
    assert "fail_closed_order_lifecycle_control_events_trigger_drift" in sql
    assert "fail_closed_order_lifecycle_control_state_metadata_drift" in sql
    assert "fail_closed_order_lifecycle_control_state_trigger_drift" in sql
    assert "fail_closed_order_lifecycle_projection_outbox_metadata_drift" in sql

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    PROJECT_ROOT / "db" / "schema_parts" / "61_finance_import_reprocessing.sql"
)


def _schema_sql() -> str:
    raw = SCHEMA_PATH.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8", errors="strict")
    assert "\ufffd" not in text
    return text


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def test_reprocess_schema_is_additive_and_has_required_run_contract() -> None:
    sql = _compact(_schema_sql())

    assert "create table if not exists finance_import_reprocess_runs" in sql
    assert (
        "add unique key uq_finance_import_batch_id_status (id, status)"
        in sql
    )
    assert (
        "foreign key (batch_id, batch_status) "
        "references finance_import_batches(id, status)"
        in sql
    )
    assert "batch_status = 'completed'" in sql
    assert "unique key uq_finance_import_reprocess_run_plan ( batch_id, plan_fingerprint )" in sql
    assert "actor varchar(255) not null" in sql
    assert "classifier_version varchar(191) not null" in sql
    assert "plan_fingerprint char(64) not null" in sql
    assert "plan_fingerprint regexp '^[0-9a-f]{64}$'" in sql
    for column in (
        "selected_count",
        "changed_count",
        "dispatch_count",
        "reconciled_count",
        "pending_count",
    ):
        assert f"{column} int unsigned not null" in sql
    assert "request_summary json not null" in sql
    assert "result_summary json not null" in sql
    assert "status enum('completed') not null" in sql
    assert "completed_at timestamp not null" in sql

    forbidden_existing_table_mutations = (
        r"\bupdate\s+finance_import_(?:batches|rows|occurrences)\b",
        r"\bdelete\s+from\s+finance_import_(?:batches|rows|occurrences)\b",
        r"\bdrop\s+table\s+(?:if\s+exists\s+)?finance_import_(?:batches|rows|occurrences)\b",
    )
    assert all(
        re.search(pattern, sql) is None
        for pattern in forbidden_existing_table_mutations
    )


def test_reclassification_event_records_only_changed_canonical_rows() -> None:
    sql = _compact(_schema_sql())

    assert (
        "create table if not exists finance_import_reclassification_events"
        in sql
    )
    assert (
        "foreign key (run_id) references finance_import_reprocess_runs(id)"
        in sql
    )
    assert (
        "foreign key (finance_import_row_id) references finance_import_rows(id)"
        in sql
    )
    assert (
        "unique key uq_finance_import_reclassification_event_row "
        "( run_id, finance_import_row_id )"
        in sql
    )
    for prefix in ("before", "after"):
        assert f"{prefix}_classification_type varchar(100) not null" in sql
        assert f"{prefix}_classification_reason varchar(255) null" in sql
        assert f"{prefix}_matched_identity_ids json not null" in sql
        assert (
            f"{prefix}_resolved_counterparty_account varchar(191) null"
            in sql
        )
    assert "dispatch_result varchar(100) not null" in sql
    assert "dispatch_reason varchar(255) null" in sql
    assert "dispatch_references json not null" in sql
    assert "chk_finance_import_reclassification_event_changed" in sql


def test_run_and_event_audit_rows_are_database_append_only() -> None:
    sql = _compact(_schema_sql())

    for table in (
        "finance_import_reprocess_runs",
        "finance_import_reclassification_events",
    ):
        for operation in ("update", "delete"):
            trigger = f"trg_{table}_{'before_' + operation}"
            assert f"drop trigger if exists {trigger}" in sql
            assert f"create trigger {trigger}" in sql
            assert f"before {operation} on {table}" in sql
            assert "signal sqlstate '45000'" in sql

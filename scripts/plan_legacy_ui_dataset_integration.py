"""Produce a read-only preservation plan before rebuilding the UI validation DB."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
import hashlib
import json
import os
import re

import pymysql


SOURCE_DATABASE = "union_db_candidate_20260803_v5"
_TARGET_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_REBUILD_FROM_EVENTS = frozenset({
    "anomaly_current_alerts",
    "client_deposit_settlement_projection",
    "scheduling_effective_occupancy",
})
_RETIRED_LEGACY_TABLES = frozenset({
    "staff_monthly_settlements",
    "staff_monthly_settlement_details",
})
_CONSERVATIVE_NO_COPY_TABLES = frozenset({
    "admin_audit_logs", "anomaly_consumer_checkpoints",
    "anomaly_root_fact_projection_receipts", "anomaly_root_fact_snapshots",
    "application_command_claims", "assignment_payroll_rate_snapshots",
    "assignment_plan_apply_receipts", "background_jobs", "beclass_records",
    "caregiver_availability_lock_days", "caregiver_availability_lock_events",
    "caregiver_availability_locks", "case_architecture_bootstrap_events",
    "case_architecture_bootstrap_receipts", "case_payroll_rate_policy_snapshots",
    "case_staff_assignments", "client_finance_accounts", "client_finance_outbox",
    "client_ledger_entries", "client_ledger_obligation_allocations",
    "client_obligation_events", "client_obligations", "client_payment_terms",
    "client_payment_terms_events", "client_payment_transactions", "client_payments",
    "finance_anomaly_occurrences", "finance_import_apply_receipts",
    "finance_import_batch_contracts", "finance_import_batches",
    "finance_import_classification_events", "finance_import_ingestion_receipts",
    "finance_import_occurrences", "finance_import_outbox", "finance_import_rows",
    "holidays", "line_rich_menu_publications", "matching_records",
    "order_contract_flow_events", "order_lifecycle_control_events",
    "order_lifecycle_control_state", "order_lifecycle_state_events",
    "orders_domain_outbox", "payroll_case_accounts", "payroll_outbox",
    "payroll_rate_policies", "scheduling_aggregates",
    "scheduling_bootstrap_review_events", "scheduling_buffer_days",
    "scheduling_command_receipts", "scheduling_generations",
    "scheduling_rebuild_events", "staff_actual_transfers", "staff_baby_types",
    "staff_bank_accounts", "staff_cooking_skills", "staff_holiday_availability",
    "staff_obligation_events", "staff_obligations", "staff_payment_transactions",
    "staff_payments", "staff_regions", "staff_schedule", "staff_time_slots",
    "staff_transfer_allocations", "staff_transportation", "staff_weekly_rest",
})
PRESERVED_ROOT_TABLES = (
    "clients",
    "staff",
    "media_assets",
    "orders",
    "caregiver_matching_plans",
    "caregiver_matching_plan_segments",
)


def require_target_database(database: str) -> str:
    if not _TARGET_PATTERN.fullmatch(database):
        raise ValueError("target database must match lu_test_dataset_[a-z0-9_]+")
    return database


def classify_table(table_name: str) -> str:
    if table_name in PRESERVED_ROOT_TABLES:
        return "preserve_root"
    if table_name == "system_alerts":
        return "rebuild_projection"
    if table_name in _REBUILD_FROM_EVENTS:
        return "rebuild_projection"
    if table_name in _RETIRED_LEGACY_TABLES:
        return "retire_after_evidence_audit"
    if table_name in _CONSERVATIVE_NO_COPY_TABLES:
        return "retire_no_copy"
    return "legacy_unresolved"


def preserved_root_tables(source_tables: Iterable[str]) -> tuple[str, ...]:
    source = set(source_tables)
    return tuple(table for table in PRESERVED_ROOT_TABLES if table in source)


def root_digest(cursor, database: str, table_columns: Mapping[str, tuple[str, ...]]) -> str:
    digest = hashlib.sha256()
    for table_name in sorted(table_columns):
        columns = table_columns[table_name]
        statement = (
            "SELECT " + ",".join(f"`{column}`" for column in columns)
            + f" FROM `{database}`.`{table_name}` ORDER BY "
            + ",".join(f"`{column}`" for column in columns)
        )
        cursor.execute(statement)
        rows = tuple(tuple(_digest_value(value) for value in row) for row in cursor.fetchall())
        payload = json.dumps(
            {"table": table_name, "columns": columns, "rows": rows},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(payload)
    return digest.hexdigest()


def _digest_value(value):
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest()}
    return value


def source_column_actions(
    table_name: str, source_only_columns: Iterable[str],
) -> dict[str, str]:
    source_only = set(source_only_columns)
    if table_name == "system_alerts" and source_only == {"description", "event_type"}:
        return {
            "description": "merge_into_details._legacy.description",
            "event_type": "merge_into_details._legacy.event_type",
        }
    return {column: "unmapped_blocker" for column in sorted(source_only)}


def describe_columns(
    source_columns: Iterable[str], target_columns: Iterable[str],
) -> dict[str, list[str]]:
    source_set = set(source_columns)
    target_set = set(target_columns)
    return {
        "source_only": sorted(source_set - target_set),
        "target_only": sorted(target_set - source_set),
        "shared": sorted(source_set & target_set),
    }


def execution_blockers(
    *, source_case_count: int, target_case_count: int, overlapping_cases: Iterable[str],
) -> list[str]:
    blockers: list[str] = []
    if source_case_count == 0:
        blockers.append("legacy source has no orders")
    if target_case_count:
        blockers.append("target contains data and must be explicitly rebuilt")
    if tuple(overlapping_cases):
        blockers.append("source and target case numbers collide")
    return blockers


def build_plan(connection, target_database: str) -> dict[str, object]:
    target = require_target_database(target_database)
    with connection.cursor() as cursor:
        source_tables = _table_names(cursor, SOURCE_DATABASE)
        target_tables = _table_names(cursor, target)
        source_counts = _nonempty_counts(cursor, SOURCE_DATABASE, source_tables)
        target_counts = _nonempty_counts(cursor, target, target_tables)
        source_cases = _case_numbers(cursor, SOURCE_DATABASE)
        target_cases = _case_numbers(cursor, target)
        shared_tables = sorted(set(source_tables) & set(target_tables))
        columns = {
            table: describe_columns(
                _column_names(cursor, SOURCE_DATABASE, table),
                _column_names(cursor, target, table),
            )
            for table in shared_tables
            if source_counts.get(table, 0)
        }
    overlap = sorted(source_cases & target_cases)
    actions = [
        {
            "table": table,
            "source_row_count": source_counts[table],
            "action": classify_table(table),
            "column_delta": columns[table],
            "source_column_actions": source_column_actions(
                table, columns[table]["source_only"],
            ),
        }
        for table in sorted(source_counts)
        if table in columns
    ]
    return {
        "contract": "labor-union-legacy-ui-integration-plan/v1",
        "mode": "read_only_dry_run",
        "source_database": SOURCE_DATABASE,
        "target_database": target,
        "source_order_count": len(source_cases),
        "target_order_count": len(target_cases),
        "overlapping_case_numbers": overlap,
        "source_only_tables": sorted(set(source_tables) - set(target_tables)),
        "target_only_tables": sorted(set(target_tables) - set(source_tables)),
        "nonempty_source_actions": actions,
        "execution_blockers": execution_blockers(
            source_case_count=len(source_cases),
            target_case_count=len(target_cases),
            overlapping_cases=overlap,
        ),
        "unmapped_source_columns": [
            {"table": action["table"], "column": column}
            for action in actions
            for column, action_name in action["source_column_actions"].items()
            if action_name == "unmapped_blocker"
        ],
    }


def _table_names(cursor, database: str) -> list[str]:
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",
        (database,),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _nonempty_counts(cursor, database: str, tables: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM `{database}`.`{table}`")
        count = int(cursor.fetchone()[0])
        if count:
            counts[table] = count
    return counts


def _case_numbers(cursor, database: str) -> set[str]:
    cursor.execute(f"SELECT case_no FROM `{database}`.orders")
    return {str(row[0]) for row in cursor.fetchall()}


def _column_names(cursor, database: str, table: str) -> list[str]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (database, table),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("DB_USER", "root"))
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "1234"))
    arguments = parser.parse_args()
    connection = pymysql.connect(
        host=arguments.host, port=arguments.port, user=arguments.user,
        password=arguments.password, charset="utf8mb4",
    )
    try:
        plan = build_plan(connection, arguments.database)
    finally:
        connection.close()
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

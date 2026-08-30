"""Thin, safe CLI for one historical finance-import batch reprocess."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subsystems.finance_import.reprocessing import (
    DEFAULT_SAFETY_LIMIT,
    reprocess_finance_import_batch,
)
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection


_REQUIRED_SCHEMA_TABLES = (
    "beclass_records",
    "client_obligations",
    "client_payment_transactions",
    "clients",
    "finance_import_batches",
    "finance_import_occurrences",
    "finance_import_rows",
    "government_subsidy_transactions",
    "orders",
    "staff_actual_transfers",
    "staff_bank_accounts",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="重處理一個 completed finance import batch；預設 dry-run。",
    )
    parser.add_argument("--batch-id", type=int, required=True)
    parser.add_argument("--target-database")
    parser.add_argument("--expected-host")
    parser.add_argument("--expected-server")
    parser.add_argument("--schema-fingerprint")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="已退休；正式套用請使用 typed Preview／Apply API",
    )
    parser.add_argument("--dry-run", action="store_true", help="Explicitly request the default read-only preview.")
    parser.add_argument("--actor", help="apply 必填操作者")
    parser.add_argument(
        "--plan-fingerprint",
        help="apply 必填的 dry-run plan fingerprint",
    )
    parser.add_argument(
        "--safety-limit",
        type=int,
        default=DEFAULT_SAFETY_LIMIT,
    )
    parser.add_argument("--report-path", help="可選 UTF-8 JSON 報告路徑")
    return parser


def _validate_before_database(args: argparse.Namespace) -> None:
    if args.batch_id < 1:
        raise ValueError("batch-id must be a positive integer")
    if args.safety_limit < 1:
        raise ValueError("safety-limit must be a positive integer")
    if args.apply:
        raise ValueError("legacy_finance_import_reprocess_apply_retired")
    if not args.target_database:
        raise ValueError("--target-database is required for read-only diagnostic")
    if not args.expected_host:
        raise ValueError("--expected-host is required for read-only diagnostic")
    if not args.expected_server:
        raise ValueError("--expected-server is required for read-only diagnostic")
    if not isinstance(args.schema_fingerprint, str) or len(args.schema_fingerprint) != 64:
        raise ValueError("--schema-fingerprint must be a 64-character SHA-256 value")
    try:
        int(args.schema_fingerprint, 16)
    except ValueError as error:
        raise ValueError("--schema-fingerprint must be lowercase hexadecimal") from error
    if args.schema_fingerprint != args.schema_fingerprint.lower():
        raise ValueError("--schema-fingerprint must be lowercase hexadecimal")


def _schema_fingerprint(cursor: Any, database: str) -> str:
    placeholders = ", ".join(["%s"] * len(_REQUIRED_SCHEMA_TABLES))
    cursor.execute(
        "SELECT table_name, ordinal_position, column_name, column_type, "
        "is_nullable, column_default, extra FROM information_schema.columns "
        f"WHERE table_schema=%s AND table_name IN ({placeholders}) "
        "ORDER BY table_name, ordinal_position",
        (database, *_REQUIRED_SCHEMA_TABLES),
    )
    rows = list(cursor.fetchall())
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("schema fingerprint query must return mapping rows")
    observed_tables = {str(row.get("table_name") or "") for row in rows}
    missing = sorted(set(_REQUIRED_SCHEMA_TABLES) - observed_tables)
    if missing:
        raise RuntimeError(f"required schema tables are missing: {', '.join(missing)}")
    normalized = [
        {
            key: row.get(key)
            for key in (
                "table_name",
                "ordinal_position",
                "column_name",
                "column_type",
                "is_nullable",
                "column_default",
                "extra",
            )
        }
        for row in rows
    ]
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _guarded_connection_factory(
    *,
    target_database: str,
    expected_host: str,
    expected_server: str,
    expected_schema_fingerprint: str,
    connection_factory: Callable[[], Any] = get_connection,
) -> Callable[[], Any]:
    def open_validated_connection() -> Any:
        configured_database = str(DB_CONFIG.get("database") or "").strip()
        configured_host = str(DB_CONFIG.get("host") or "").strip()
        if configured_database != target_database:
            raise RuntimeError("configured database does not match --target-database")
        if configured_host != expected_host:
            raise RuntimeError("configured host does not match --expected-host")
        connection = connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DATABASE() AS database_name, @@hostname AS server_name"
                )
                identity = cursor.fetchone()
                if not isinstance(identity, Mapping):
                    raise TypeError("database identity query must return a mapping")
                if identity.get("database_name") != target_database:
                    raise RuntimeError(
                        "connected database does not match --target-database"
                    )
                if identity.get("server_name") != expected_server:
                    raise RuntimeError("connected server does not match --expected-server")
                actual_fingerprint = _schema_fingerprint(cursor, target_database)
                if actual_fingerprint != expected_schema_fingerprint:
                    raise RuntimeError("finance reprocess schema fingerprint drift")
            return connection
        except Exception:
            connection.close()
            raise

    return open_validated_connection


def _write_report(path: str, result: dict[str, Any]) -> str:
    report_path = Path(path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str,
        allow_nan=False,
    )
    report_path.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    return str(report_path)


def _console_summary(
    result: dict[str, Any],
    report_path: str | None,
) -> dict[str, Any]:
    classification = result.get("classification_summary")
    if not isinstance(classification, dict):
        classification = {}
    dispatch = result.get("dispatch_summary")
    if not isinstance(dispatch, dict):
        dispatch = {}
    alert = result.get("alert_action")
    if not isinstance(alert, dict):
        alert = {}
    alert_summary = alert.get("summary")
    if not isinstance(alert_summary, dict):
        alert_summary = {}
    return {
        "db_identity": result.get("db_identity"),
        "batch_id": (result.get("batch_manifest") or {}).get("batch_id"),
        "selected": classification.get("selected"),
        "unchanged": classification.get("unchanged"),
        "changed": classification.get("changed"),
        "before_reason_counts": classification.get("before_reason_counts"),
        "after_reason_counts": classification.get("after_reason_counts"),
        "dispatch_attempted": dispatch.get("attempted"),
        "reconciled": dispatch.get("reconciled"),
        "pending": dispatch.get("pending"),
        "remaining_review": alert_summary.get("remaining_count"),
        "alert_action": alert.get("alert_action"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "rows_per_second": result.get("rows_per_second"),
        "plan_fingerprint": result.get("plan_fingerprint"),
        "transaction_outcome": result.get("transaction_outcome"),
        "report_path": report_path,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_before_database(args)
    result = reprocess_finance_import_batch(
        args.batch_id,
        actor=args.actor,
        dry_run=not args.apply,
        expected_plan_fingerprint=args.plan_fingerprint,
        safety_limit=args.safety_limit,
        connection_factory=_guarded_connection_factory(
            target_database=args.target_database,
            expected_host=args.expected_host,
            expected_server=args.expected_server,
            expected_schema_fingerprint=args.schema_fingerprint,
        ),
    )
    report_path = (
        _write_report(args.report_path, result)
        if args.report_path
        else None
    )
    print(
        json.dumps(
            _console_summary(result, report_path),
            ensure_ascii=False,
            default=str,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

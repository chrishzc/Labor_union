"""Safe legacy cancellation backfill for the ORD-01 lifecycle control schema."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.db_service import DB_CONFIG, get_connection


MIGRATION_ID = "order_lifecycle_control_facts_v1"
MIGRATION_ACTOR = f"migration:{MIGRATION_ID}"
REQUIRED_TABLES = (
    "orders",
    "order_lifecycle_state_events",
    "order_lifecycle_control_events",
    "order_lifecycle_control_state",
    "order_lifecycle_projection_outbox",
)
REQUIRED_COLUMNS = {
    "orders": {"case_no", "status", "cancel_reason", "lifecycle_version"},
    "order_lifecycle_state_events": {
        "id",
        "case_no",
        "trigger_event",
        "before_status",
        "after_status",
        "actor",
        "business_date",
        "expected_version",
        "idempotency_key",
        "facts_snapshot",
        "created_at",
    },
    "order_lifecycle_control_events": {
        "id",
        "case_no",
        "control_type",
        "control_key",
        "scope",
        "action",
        "actor",
        "reason",
        "expected_version",
        "idempotency_key",
        "payload_hash",
        "payload_snapshot",
        "created_at",
    },
    "order_lifecycle_control_state": {
        "case_no",
        "control_type",
        "control_key",
        "scope",
        "state",
        "current_event_id",
        "release_policy",
        "expires_at_utc",
        "confirmed_start_date",
        "deposit_settlement_identity_hash",
        "reason",
        "changed_by",
        "changed_at",
    },
    "order_lifecycle_projection_outbox": {
        "id",
        "case_no",
        "lifecycle_event_id",
        "intent_key",
        "scope",
        "alert_code",
        "action",
        "payload_hash",
        "payload_snapshot",
        "status",
        "attempt_count",
        "next_attempt_at_utc",
        "locked_at_utc",
        "projected_at_utc",
        "last_error",
        "created_at",
        "updated_at",
    },
}
REQUIRED_TRIGGERS = {
    "trg_order_lifecycle_state_events_before_update",
    "trg_order_lifecycle_state_events_before_delete",
    "trg_order_lifecycle_control_events_before_update",
    "trg_order_lifecycle_control_events_before_delete",
    "trg_order_lifecycle_control_state_before_delete",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bootstrap_identity(row: dict[str, Any]) -> dict[str, Any]:
    case_no = str(row["case_no"]).strip()
    reason = str(row.get("cancel_reason") or "").strip()
    payload = {
        "cancellation_date": None,
        "case_no": case_no,
        "migration": MIGRATION_ID,
        "provenance": "legacy_status_bootstrap",
        "reason": reason,
    }
    payload_json = _canonical_json(payload)
    return {
        "case_no": case_no,
        "reason": reason,
        "idempotency_key": f"migration:legacy_status_bootstrap:{case_no}",
        "payload": payload,
        "payload_json": payload_json,
        "payload_hash": _sha256_text(payload_json),
    }


def classify_legacy_rows(
    rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    bootstrappable: list[dict[str, Any]] = []
    review_required: list[str] = []
    for row in rows:
        case_no = str(row.get("case_no") or "").strip()
        if not case_no:
            raise ValueError("cancelled order contains an empty case_no")
        if str(row.get("status") or "") != "訂單取消":
            raise ValueError(f"unexpected non-cancelled row: {case_no}")
        reason = str(row.get("cancel_reason") or "").strip()
        if not reason or len(reason) > 500:
            review_required.append(case_no)
            continue
        item = _bootstrap_identity(row)
        if len(item["payload_json"].encode("utf-8")) > 16_384:
            review_required.append(case_no)
            continue
        bootstrappable.append(item)
    bootstrappable.sort(key=lambda item: item["case_no"])
    review_required.sort()
    return bootstrappable, review_required


def _dataset_fingerprint(
    bootstrappable: list[dict[str, Any]], review_required: list[str]
) -> str:
    return _sha256_text(
        _canonical_json(
            {
                "bootstrappable": [
                    {
                        "case_no": item["case_no"],
                        "idempotency_key": item["idempotency_key"],
                        "payload_hash": item["payload_hash"],
                    }
                    for item in bootstrappable
                ],
                "review_required": review_required,
            }
        )
    )


def validate_backup(
    path_value: str | None, *, target_database: str
) -> dict[str, Any]:
    if not path_value:
        raise ValueError("--apply requires --backup-receipt")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"backup receipt does not exist: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"backup receipt is empty: {path}")
    header = path.read_bytes()[: 1024 * 1024]
    if b"MySQL dump" not in header:
        raise ValueError("backup receipt is not a mysqldump SQL artifact")
    database_markers = (
        f"Current Database: `{target_database}`".encode("utf-8"),
        f"USE `{target_database}`".encode("utf-8"),
        f"Database: {target_database}".encode("utf-8"),
    )
    if not any(marker in header for marker in database_markers):
        raise ValueError(
            "mysqldump artifact does not identify the target database"
        )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "size": size,
        "sha256": digest.hexdigest(),
        "target_database": target_database,
    }


def validate_plan(
    path_value: str | None,
    *,
    target_database: str,
    server: str,
) -> dict[str, Any]:
    if not path_value:
        raise ValueError("--apply requires --plan-receipt from a prior --dry-run")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"dry-run plan receipt is missing or empty: {path}")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("dry-run plan receipt is not valid UTF-8 JSON") from exc
    required = {
        "migration",
        "mode",
        "database",
        "server",
        "orders",
        "cancelled",
        "bootstrappable",
        "review_required",
        "dataset_fingerprint",
        "schema_fingerprint",
    }
    if not isinstance(plan, dict) or not required.issubset(plan):
        raise ValueError("dry-run plan receipt is missing required identity fields")
    if (
        plan["migration"] != MIGRATION_ID
        or plan["mode"] != "dry-run"
        or plan["database"] != target_database
        or str(plan["server"]) != str(server)
    ):
        raise ValueError("dry-run plan receipt belongs to another migration target")
    return plan


def _fetch_schema_snapshot(cursor: Any) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN (%s, %s, %s, %s, %s)
        ORDER BY TABLE_NAME
        """,
        REQUIRED_TABLES,
    )
    tables = [row["TABLE_NAME"] for row in cursor.fetchall()]
    cursor.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
               COLUMN_DEFAULT, CHARACTER_SET_NAME, COLLATION_NAME, EXTRA
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN (%s, %s, %s, %s, %s)
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
        ,
        REQUIRED_TABLES,
    )
    columns = list(cursor.fetchall())
    cursor.execute(
        """
        SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE,
               ACTION_TIMING, ACTION_STATEMENT
        FROM INFORMATION_SCHEMA.TRIGGERS
        WHERE TRIGGER_SCHEMA = DATABASE()
          AND TRIGGER_NAME IN (%s, %s, %s, %s, %s)
        ORDER BY TRIGGER_NAME
        """,
        tuple(sorted(REQUIRED_TRIGGERS)),
    )
    triggers = list(cursor.fetchall())
    cursor.execute(
        """
        SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN (%s, %s, %s, %s)
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
        """,
        REQUIRED_TABLES[1:],
    )
    indexes = list(cursor.fetchall())
    cursor.execute(
        """
        SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME,
               REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME IN (%s, %s, %s, %s)
          AND REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION
        """,
        REQUIRED_TABLES[1:],
    )
    foreign_keys = list(cursor.fetchall())
    return {
        "tables": tables,
        "columns": columns,
        "triggers": triggers,
        "indexes": indexes,
        "foreign_keys": foreign_keys,
    }


def _assert_schema(snapshot: dict[str, Any]) -> None:
    if snapshot["tables"] != sorted(REQUIRED_TABLES):
        raise RuntimeError(
            "lifecycle control schema is incomplete; apply schema parts 104-106 first"
        )
    columns = snapshot["columns"]
    by_table: dict[str, set[str]] = {}
    for column in columns:
        by_table.setdefault(column["TABLE_NAME"], set()).add(column["COLUMN_NAME"])
    for table_name, expected_columns in REQUIRED_COLUMNS.items():
        actual_columns = by_table.get(table_name, set())
        matches = (
            expected_columns.issubset(actual_columns)
            if table_name == "orders"
            else actual_columns == expected_columns
        )
        if not matches:
            raise RuntimeError(f"{table_name} column metadata drift detected")
    lifecycle = [
        column
        for column in columns
        if column["TABLE_NAME"] == "orders"
        and column["COLUMN_NAME"] == "lifecycle_version"
    ]
    if len(lifecycle) != 1:
        raise RuntimeError("orders.lifecycle_version is missing or ambiguous")
    column = lifecycle[0]
    if (
        str(column["COLUMN_TYPE"]).lower() != "bigint unsigned"
        or column["IS_NULLABLE"] != "NO"
        or str(column["COLUMN_DEFAULT"]) != "0"
    ):
        raise RuntimeError("orders.lifecycle_version metadata does not match contract")
    triggers = {row["TRIGGER_NAME"]: row for row in snapshot["triggers"]}
    if set(triggers) != REQUIRED_TRIGGERS:
        raise RuntimeError("lifecycle append-only trigger metadata drift detected")
    for name, trigger in triggers.items():
        if trigger["ACTION_TIMING"] != "BEFORE":
            raise RuntimeError(f"lifecycle trigger timing drift detected: {name}")
        statement = str(trigger["ACTION_STATEMENT"]).upper()
        if "SIGNAL SQLSTATE '45000'" not in statement:
            raise RuntimeError(f"lifecycle trigger action drift detected: {name}")
    required_indexes = {
        ("order_lifecycle_state_events", "uq_order_lifecycle_state_event_idempotency"),
        ("order_lifecycle_control_events", "uq_order_lifecycle_control_event_idempotency"),
        ("order_lifecycle_control_events", "uq_order_lifecycle_control_event_identity"),
        ("order_lifecycle_control_state", "PRIMARY"),
        ("order_lifecycle_projection_outbox", "uq_order_lifecycle_projection_outbox_intent"),
    }
    present_indexes = {
        (row["TABLE_NAME"], row["INDEX_NAME"]) for row in snapshot["indexes"]
    }
    if not required_indexes.issubset(present_indexes):
        raise RuntimeError("lifecycle unique/index metadata drift detected")
    required_fk_targets = {
        ("order_lifecycle_control_events", "orders"),
        ("order_lifecycle_control_state", "orders"),
        ("order_lifecycle_control_state", "order_lifecycle_control_events"),
        ("order_lifecycle_projection_outbox", "orders"),
        ("order_lifecycle_projection_outbox", "order_lifecycle_state_events"),
    }
    fk_targets = {
        (row["TABLE_NAME"], row["REFERENCED_TABLE_NAME"])
        for row in snapshot["foreign_keys"]
    }
    if not required_fk_targets.issubset(fk_targets):
        raise RuntimeError("lifecycle foreign-key metadata drift detected")


def _schema_fingerprint(snapshot: dict[str, Any]) -> str:
    return _sha256_text(_canonical_json(snapshot))


def _load_orders(cursor: Any, *, lock: bool) -> tuple[int, list[dict[str, Any]]]:
    cursor.execute("SELECT COUNT(*) AS row_count FROM orders")
    order_count = int(cursor.fetchone()["row_count"])
    sql = (
        "SELECT case_no, status, cancel_reason, lifecycle_version "
        "FROM orders WHERE status = '訂單取消' ORDER BY case_no"
    )
    if lock:
        sql += " FOR UPDATE"
    cursor.execute(sql)
    return order_count, list(cursor.fetchall())


def _control_counts(cursor: Any) -> dict[str, int]:
    cursor.execute(
        "SELECT COUNT(*) AS row_count FROM order_lifecycle_control_events"
    )
    event_count = int(cursor.fetchone()["row_count"])
    cursor.execute(
        "SELECT COUNT(*) AS row_count FROM order_lifecycle_control_state"
    )
    state_count = int(cursor.fetchone()["row_count"])
    cursor.execute(
        "SELECT COUNT(*) AS row_count FROM order_lifecycle_projection_outbox"
    )
    outbox_count = int(cursor.fetchone()["row_count"])
    return {
        "control_events": event_count,
        "control_states": state_count,
        "projection_outbox": outbox_count,
    }


def _assert_existing_identity(
    cursor: Any, item: dict[str, Any]
) -> tuple[int | None, bool]:
    cursor.execute(
        """
        SELECT id, case_no, control_type, control_key, scope, action, actor,
               reason, expected_version, idempotency_key, payload_hash,
               payload_snapshot
        FROM order_lifecycle_control_events
        WHERE case_no = %s AND idempotency_key = %s
        """,
        (item["case_no"], item["idempotency_key"]),
    )
    event = cursor.fetchone()
    if event is None:
        return None, False
    expected = {
        "case_no": item["case_no"],
        "control_type": "cancellation",
        "control_key": "order_cancelled",
        "scope": "order",
        "action": "activate",
        "actor": MIGRATION_ACTOR,
        "reason": item["reason"],
        "expected_version": 0,
        "idempotency_key": item["idempotency_key"],
        "payload_hash": item["payload_hash"],
    }
    for key, value in expected.items():
        if event[key] != value:
            raise RuntimeError(
                f"conflicting legacy cancellation event for {item['case_no']}: {key}"
            )
    payload = event["payload_snapshot"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if _canonical_json(payload) != item["payload_json"]:
        raise RuntimeError(
            f"conflicting legacy cancellation payload for {item['case_no']}"
        )
    cursor.execute(
        """
        SELECT state, current_event_id, scope, release_policy, expires_at_utc,
               confirmed_start_date, deposit_settlement_identity_hash, reason,
               changed_by
        FROM order_lifecycle_control_state
        WHERE case_no = %s
          AND control_type = 'cancellation'
          AND control_key = 'order_cancelled'
        """,
        (item["case_no"],),
    )
    state = cursor.fetchone()
    if (
        state is None
        or state["state"] != "active"
        or int(state["current_event_id"]) != int(event["id"])
        or state["scope"] != "order"
        or state["release_policy"] is not None
        or state["expires_at_utc"] is not None
        or state["confirmed_start_date"] is not None
        or state["deposit_settlement_identity_hash"] is not None
        or state["reason"] != item["reason"]
        or state["changed_by"] != MIGRATION_ACTOR
    ):
        raise RuntimeError(
            f"partial or conflicting legacy cancellation state for {item['case_no']}"
        )
    return int(event["id"]), True


def _insert_bootstrap(cursor: Any, item: dict[str, Any]) -> int:
    cursor.execute(
        """
        INSERT INTO order_lifecycle_control_events
            (case_no, control_type, control_key, scope, action, actor, reason,
             expected_version, idempotency_key, payload_hash, payload_snapshot)
        VALUES
            (%s, 'cancellation', 'order_cancelled', 'order', 'activate',
             %s, %s, 0, %s, %s, %s)
        """,
        (
            item["case_no"],
            MIGRATION_ACTOR,
            item["reason"],
            item["idempotency_key"],
            item["payload_hash"],
            item["payload_json"],
        ),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        """
        INSERT INTO order_lifecycle_control_state
            (case_no, control_type, control_key, scope, state, current_event_id,
             release_policy, expires_at_utc, confirmed_start_date,
             deposit_settlement_identity_hash, reason, changed_by)
        VALUES
            (%s, 'cancellation', 'order_cancelled', 'order', 'active', %s,
             NULL, NULL, NULL, NULL, %s, %s)
        """,
        (item["case_no"], event_id, item["reason"], MIGRATION_ACTOR),
    )
    return event_id


def run_migration(
    *,
    mode: str,
    target_database: str,
    backup_receipt: str | None = None,
    plan_receipt: str | None = None,
    receipt_path: str | None = None,
) -> dict[str, Any]:
    configured_database = str(DB_CONFIG.get("database") or "")
    if not target_database or target_database != configured_database:
        raise ValueError(
            "target database must exactly match configured DB_DATABASE "
            f"({configured_database!r})"
        )
    connection = get_connection()
    committed = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
            if identity["database_name"] != target_database:
                raise RuntimeError("connected database does not match --target-database")
            schema = _fetch_schema_snapshot(cursor)
            _assert_schema(schema)
            schema_fingerprint = _schema_fingerprint(schema)
            order_count, rows = _load_orders(cursor, lock=mode == "apply")
            bootstrappable, review_required = classify_legacy_rows(rows)
            fingerprint = _dataset_fingerprint(bootstrappable, review_required)
            before_counts = _control_counts(cursor)
            backup = None
            plan = None
            if mode == "apply":
                if not receipt_path:
                    raise ValueError("--apply requires --receipt-path")
                backup = validate_backup(
                    backup_receipt,
                    target_database=target_database,
                )
                plan = validate_plan(
                    plan_receipt,
                    target_database=target_database,
                    server=str(identity["server"]),
                )
                current_plan_identity = {
                    "orders": order_count,
                    "cancelled": len(rows),
                    "bootstrappable": len(bootstrappable),
                    "review_required": len(review_required),
                    "dataset_fingerprint": fingerprint,
                    "schema_fingerprint": schema_fingerprint,
                }
                for field, value in current_plan_identity.items():
                    if plan.get(field) != value:
                        raise RuntimeError(
                            f"dry-run plan drift detected in {field}"
                        )
            existing_count = 0
            created_count = 0
            if mode in {"verify", "apply"}:
                for item in bootstrappable:
                    event_id, exists = _assert_existing_identity(cursor, item)
                    if exists:
                        existing_count += 1
                    elif mode == "verify":
                        raise RuntimeError(
                            f"missing bootstrap cancellation for {item['case_no']}"
                        )
                    else:
                        if int(
                            next(
                                row["lifecycle_version"]
                                for row in rows
                                if row["case_no"] == item["case_no"]
                            )
                        ) != 0:
                            raise RuntimeError(
                                f"legacy order has nonzero lifecycle_version: {item['case_no']}"
                            )
                        _insert_bootstrap(cursor, item)
                        created_count += 1
            after_counts = _control_counts(cursor)
            receipt = {
                "migration": MIGRATION_ID,
                "mode": mode,
                "database": identity["database_name"],
                "server": identity["server"],
                "orders": order_count,
                "cancelled": len(rows),
                "bootstrappable": len(bootstrappable),
                "review_required": len(review_required),
                "existing": existing_count,
                "created": created_count,
                "dataset_fingerprint": fingerprint,
                "schema_fingerprint": schema_fingerprint,
                "before_counts": before_counts,
                "after_counts": after_counts,
                "backup": backup,
                "plan_receipt": (
                    {
                        "path": str(Path(plan_receipt).expanduser().resolve()),
                        "sha256": _sha256_text(_canonical_json(plan)),
                    }
                    if plan is not None and plan_receipt is not None
                    else None
                ),
                "rollback": {
                    "strategy": "restore_dump_to_new_database_then_switch",
                    "source_database": target_database,
                    "instruction": (
                        "Restore the verified dump into a new database, verify "
                        "row counts, then explicitly set DB_DATABASE to that "
                        "database; never rebuild or overwrite the source DB."
                    ),
                },
            }
            if mode == "apply":
                prepared = dict(receipt)
                prepared["receipt_status"] = "prepared"
                _write_receipt(receipt_path, prepared)
                connection.commit()
                committed = True
                receipt["receipt_status"] = "committed"
                _write_receipt(receipt_path, receipt)
            return receipt
    except Exception:
        if not committed:
            connection.rollback()
        raise
    finally:
        connection.close()


def _write_receipt(path_value: str | None, receipt: dict[str, Any]) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(receipt) + "\n", encoding="utf-8", newline="\n")
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--backup-receipt")
    parser.add_argument("--plan-receipt")
    parser.add_argument("--receipt-path")
    args = parser.parse_args()
    mode = next(
        name
        for name in ("check", "dry_run", "apply", "verify")
        if getattr(args, name)
    ).replace("_", "-")
    receipt = run_migration(
        mode=mode,
        target_database=args.target_database,
        backup_receipt=args.backup_receipt,
        plan_receipt=args.plan_receipt,
        receipt_path=args.receipt_path,
    )
    receipt_path = (
        str(Path(args.receipt_path).expanduser().resolve())
        if args.receipt_path
        else None
    )
    if mode != "apply":
        receipt_path = _write_receipt(args.receipt_path, receipt)
    summary = {
        key: receipt[key]
        for key in (
            "mode",
            "database",
            "server",
            "orders",
            "cancelled",
            "bootstrappable",
            "review_required",
            "existing",
            "created",
            "dataset_fingerprint",
        )
    }
    summary["receipt_path"] = receipt_path
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Backfill only provable open accounting projections from preserved legacy facts.

This migration deliberately does not fabricate historical ledger entries.  It
creates the current open obligation only when the legacy snapshot and its
immutable transaction total agree exactly.  Fully settled and fractional staff
payments remain preserved legacy history or review work, never guessed facts.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection
from domains.client_finance.subsidy_coverage import derive_subsidy_coverage
from domains.payroll.payment_due_date import calculate_staff_payment_due_date


MIGRATION_ID = "canonical_accounting_projection_v1"
MIGRATION_ACTOR = f"migration:{MIGRATION_ID}"
CLIENT_STAGES = ("deposit", "first", "second")
LEGACY_CLIENT_STAGE_MAP = {
    "deposit": "deposit",
    "first_payment": "first",
    "second_payment": "second",
}
REQUIRED_TABLES = (
    "orders",
    "client_payments",
    "client_payment_transactions",
    "client_finance_accounts",
    "client_obligation_events",
    "client_obligations",
    "staff_payments",
    "case_staff_assignments",
    "payroll_case_accounts",
    "staff_obligation_events",
    "staff_obligations",
)


@dataclass(frozen=True)
class ClientOpenObligation:
    case_no: str
    stage: str
    amount_due_ntd: int
    due_date: date | None

    @property
    def identity(self) -> str:
        return f"legacy-client-open:{self.case_no}:{self.stage}"


@dataclass(frozen=True)
class StaffOpenObligation:
    staff_payment_id: int
    assignment_id: int
    case_no: str
    staff_id: int
    amount_due_ntd: int
    due_date: date

    @property
    def identity(self) -> str:
        return f"legacy-staff-open:{self.staff_payment_id}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: Any):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"cannot serialize {type(value)!r}")


def sha256_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_client_open_obligations(
    payment_rows: Iterable[dict[str, Any]],
    transaction_nets: dict[tuple[str, str], int],
) -> tuple[tuple[ClientOpenObligation, ...], tuple[str, ...]]:
    candidates: list[ClientOpenObligation] = []
    review_required: list[str] = []
    for row in payment_rows:
        case_no = _text(row.get("case_no"), "client payment case_no")
        for stage in CLIENT_STAGES:
            receivable = _integer_ntd(row.get(f"{stage}_receivable"), f"{stage} receivable")
            received = _integer_ntd(row.get(f"{stage}_received"), f"{stage} received")
            transaction_net = transaction_nets.get((case_no, stage), 0)
            if received != transaction_net:
                review_required.append(f"{case_no}:{stage}:transaction_snapshot_mismatch")
                continue
            if received < 0 or received > receivable:
                review_required.append(f"{case_no}:{stage}:over_or_under_receipt")
                continue
            remaining = receivable - received
            if remaining:
                candidates.append(
                    ClientOpenObligation(
                        case_no,
                        stage,
                        remaining,
                        _date_or_none(row.get(f"{stage}_due_date")),
                    )
                )
    return (
        tuple(sorted(candidates, key=lambda item: (item.case_no, item.stage))),
        tuple(sorted(review_required)),
    )


def build_staff_open_obligations(
    payment_rows: Iterable[dict[str, Any]],
) -> tuple[tuple[StaffOpenObligation, ...], tuple[int, ...]]:
    candidates: list[StaffOpenObligation] = []
    review_required: list[int] = []
    for row in payment_rows:
        payment_id = _positive_integer(row.get("id"), "staff payment id")
        total_payable = _integer_or_none(row.get("total_payable"))
        amount_paid = _integer_or_none(row.get("amount_paid"))
        if total_payable is None or amount_paid is None or amount_paid != 0:
            review_required.append(payment_id)
            continue
        if total_payable <= 0 or row.get("payment_status") != "pending":
            continue
        completed_on = _date_or_none(row.get("actual_end_date"))
        if completed_on is None:
            review_required.append(payment_id)
            continue
        due_date = _staff_due_date_from_legacy_facts(row)
        if due_date is None:
            review_required.append(payment_id)
            continue
        candidates.append(
            StaffOpenObligation(
                payment_id,
                _positive_integer(row.get("assignment_id"), "assignment id"),
                _text(row.get("case_no"), "staff payment case_no"),
                _positive_integer(row.get("staff_id"), "staff id"),
                total_payable,
                due_date,
            )
        )
    return (
        tuple(sorted(candidates, key=lambda item: item.staff_payment_id)),
        tuple(sorted(set(review_required))),
    )


def _staff_due_date_from_legacy_facts(row: dict[str, Any]) -> date | None:
    identity_status = row.get("client_identity_status")
    completed_on = _date_or_none(row.get("actual_end_date"))
    if not isinstance(identity_status, str) or completed_on is None:
        return None
    service_days = _integer_or_none(row.get("service_days"))
    hours_per_day = _integer_or_none(row.get("service_hours_per_day"))
    floor_fee = _integer_or_none(row.get("floor_fee"))
    client_service_fee_total = _integer_or_none(row.get("client_service_fee_total"))
    if None in (service_days, hours_per_day, floor_fee, client_service_fee_total):
        return None
    if service_days < 0 or hours_per_day < 0 or floor_fee < 0 or client_service_fee_total < 0:
        return None
    try:
        coverage = derive_subsidy_coverage(
            identity_status,
            Decimal(service_days * hours_per_day),
            Decimal(floor_fee),
        )
        return calculate_staff_payment_due_date(
            completed_on,
            client_service_fee_total,
            coverage.is_full_subsidy_order,
        )
    except ValueError:
        return None


def _integer_ntd(value: Any, field_name: str) -> int:
    result = _integer_or_none(value)
    if result is None or result < 0:
        raise ValueError(f"{field_name} must be a non-negative integer NTD")
    return result


def _integer_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return None


def _positive_integer(value: Any, field_name: str) -> int:
    result = _integer_or_none(value)
    if result is None or result <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return result


def _text(value: Any, field_name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field_name} is required")
    return result


def _date_or_none(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, date):
        raise ValueError("due date must be a date")
    return value


def _load_client_rows(cursor, *, lock: bool) -> list[dict[str, Any]]:
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT case_no,deposit_receivable,deposit_received,deposit_due_date,"
        "first_payment_receivable AS first_receivable,"
        "first_payment_received AS first_received,"
        "first_payment_due_date AS first_due_date,"
        "second_payment_receivable AS second_receivable,"
        "second_payment_received AS second_received,"
        "second_payment_due_date AS second_due_date "
        f"FROM client_payments ORDER BY case_no{suffix}"
    )
    return list(cursor.fetchall())


def _load_transaction_nets(cursor, *, lock: bool) -> dict[tuple[str, str], int]:
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT case_no,stage,transaction_type,transaction_status,amount "
        f"FROM client_payment_transactions ORDER BY case_no,id{suffix}"
    )
    nets: dict[tuple[str, str], int] = {}
    for row in cursor.fetchall():
        if row["transaction_status"] != "succeeded":
            continue
        stage = LEGACY_CLIENT_STAGE_MAP.get(str(row["stage"]))
        if stage is None:
            continue
        amount = _integer_ntd(row["amount"], "client transaction amount")
        transaction_type = str(row["transaction_type"])
        if transaction_type == "receipt":
            signed_amount = amount
        elif transaction_type in {"refund", "reversal"}:
            signed_amount = -amount
        else:
            raise ValueError(f"unsupported client transaction type: {transaction_type}")
        key = (_text(row["case_no"], "client transaction case_no"), stage)
        nets[key] = nets.get(key, 0) + signed_amount
    return nets


def _load_staff_rows(cursor, *, lock: bool) -> list[dict[str, Any]]:
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT payment.id,payment.assignment_id,payment.case_no,payment.staff_id,"
        "payment.total_payable,payment.amount_paid,payment.due_date,payment.payment_status,"
        "orders.actual_end_date,orders.service_days,orders.service_hours_per_day,orders.floor_fee,"
        "clients.identity_status AS client_identity_status,"
        "(COALESCE(client_payment.deposit_receivable,0)+"
        "COALESCE(client_payment.first_payment_receivable,0)+"
        "COALESCE(client_payment.second_payment_receivable,0)) AS client_service_fee_total "
        "FROM staff_payments payment "
        "JOIN case_staff_assignments assignment "
        "ON assignment.id=payment.assignment_id "
        "AND assignment.case_no=payment.case_no "
        "AND assignment.staff_id=payment.staff_id "
        "JOIN orders ON orders.case_no=payment.case_no "
        "JOIN clients ON clients.case_no=payment.case_no "
        "LEFT JOIN client_payments client_payment ON client_payment.case_no=payment.case_no "
        f"ORDER BY payment.id{suffix}"
    )
    return list(cursor.fetchall())


def _assert_schema(cursor) -> str:
    placeholders = ",".join(["%s"] * len(REQUIRED_TABLES))
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() "
        f"AND TABLE_NAME IN ({placeholders}) ORDER BY TABLE_NAME",
        REQUIRED_TABLES,
    )
    tables = [row["TABLE_NAME"] for row in cursor.fetchall()]
    if tables != sorted(REQUIRED_TABLES):
        raise RuntimeError("canonical accounting schema is incomplete")
    return sha256_payload(tables)


def _existing_counts(cursor) -> dict[str, int]:
    counts = {}
    for table_name in (
        "client_finance_accounts", "client_obligation_events", "client_obligations",
        "payroll_case_accounts", "staff_obligation_events", "staff_obligations",
    ):
        cursor.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
        counts[table_name] = int(cursor.fetchone()["count"])
    return counts


def _assert_safe_existing_state(cursor, counts: dict[str, int]) -> None:
    projection_tables = (
        "client_obligation_events", "client_obligations",
        "staff_obligation_events", "staff_obligations",
    )
    if any(counts[table_name] for table_name in projection_tables):
        raise RuntimeError("canonical accounting projection tables are not empty")
    for table_name in ("client_finance_accounts", "payroll_case_accounts"):
        cursor.execute(
            f"SELECT case_no FROM {table_name} WHERE aggregate_version <> 0 "
            "ORDER BY case_no"
        )
        if cursor.fetchall():
            raise RuntimeError(f"{table_name} contains a nonzero aggregate version")


def _plan_payload(
    *,
    database: str,
    server: str,
    schema_fingerprint: str,
    client_items: tuple[ClientOpenObligation, ...],
    client_review_keys: tuple[str, ...],
    staff_items: tuple[StaffOpenObligation, ...],
    staff_review_ids: tuple[int, ...],
    existing_counts: dict[str, int],
) -> dict[str, Any]:
    payload = {
        "migration": MIGRATION_ID,
        "database": database,
        "server": server,
        "schema_fingerprint": schema_fingerprint,
        "client_open": [asdict(item) | {"identity": item.identity} for item in client_items],
        "client_review_keys": list(client_review_keys),
        "staff_open": [asdict(item) | {"identity": item.identity} for item in staff_items],
        "staff_review_payment_ids": list(staff_review_ids),
        "existing_counts": existing_counts,
        "rollback": {
            "strategy": "restore_verified_backup_to_new_database_then_switch",
            "restriction": "never delete or overwrite preserved legacy facts",
        },
    }
    payload["dataset_fingerprint"] = sha256_payload(payload)
    return payload


def _write_receipt(path_value: str | None, payload: dict[str, Any]) -> None:
    if not path_value:
        return
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(payload) + "\n", encoding="utf-8", newline="\n")


def _read_plan(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        raise ValueError("--apply requires --plan-receipt")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError("plan receipt does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_backup(path_value: str | None) -> str:
    if not path_value:
        raise ValueError("--apply requires --backup-receipt")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("backup receipt does not exist or is empty")
    if not _is_native_mysql_dump(path.read_bytes()[: 1_048_576]):
        raise ValueError("backup receipt is not a MySQL dump")
    return str(path)


def _is_native_mysql_dump(header: bytes) -> bool:
    return header.startswith((b"-- MySQL dump", b"-- MariaDB dump"))


def _insert_client_projection(cursor, item: ClientOpenObligation, version: int) -> int:
    cursor.execute(
        "INSERT INTO client_obligation_events("
        "obligation_identity,case_no,obligation_type,direction,event_type,"
        "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
        "source_event_identity,source_obligation_identity,expected_account_version,"
        "idempotency_key,actor,reason) VALUES "
        "(%s,%s,%s,'receivable_from_client','established',0,%s,NULL,%s,%s,NULL,%s,%s,%s,%s)",
        (item.identity, item.case_no, item.stage, item.amount_due_ntd, item.due_date,
         f"legacy-current-projection:{item.identity}", version,
         f"migration:{MIGRATION_ID}:{item.identity}", MIGRATION_ACTOR,
         "Preserved legacy snapshot and transaction net agree; current open balance only."),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_obligations("
        "obligation_identity,case_no,obligation_type,direction,source_obligation_identity,"
        "amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES "
        "(%s,%s,%s,'receivable_from_client',NULL,%s,%s,'open',%s,0)",
        (item.identity, item.case_no, item.stage, item.amount_due_ntd, item.due_date, event_id),
    )
    return version + 1


def _insert_staff_projection(cursor, item: StaffOpenObligation, version: int) -> int:
    fingerprint = sha256_payload(asdict(item))
    cursor.execute(
        "INSERT INTO staff_obligation_events("
        "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,"
        "source_obligation_identity,event_type,before_amount_ntd,after_amount_ntd,due_date,"
        "payroll_fingerprint,expected_payroll_version,resulting_payroll_version,"
        "idempotency_key,actor,reason) VALUES "
        "(%s,%s,%s,%s,'service_pay','payable_to_staff',NULL,'established',0,%s,%s,%s,%s,%s,%s,%s,%s)",
        (item.identity, item.assignment_id, item.case_no, item.staff_id, item.amount_due_ntd,
         item.due_date, fingerprint, version, version + 1,
         f"migration:{MIGRATION_ID}:{item.identity}", MIGRATION_ACTOR,
         "Preserved pending staff payment is an exact integer obligation with no legacy payout."),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO staff_obligations("
        "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,"
        "source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,"
        "payroll_version,payout_history_exists) VALUES "
        "(%s,%s,%s,%s,'service_pay','payable_to_staff',NULL,%s,%s,'open',%s,%s,0)",
        (item.identity, item.assignment_id, item.case_no, item.staff_id, item.amount_due_ntd,
         item.due_date, event_id, version + 1),
    )
    return version + 1


def _apply(cursor, client_items, staff_items) -> None:
    for case_no in sorted({item.case_no for item in client_items}):
        cursor.execute("INSERT IGNORE INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)", (case_no,))
        version = 0
        for item in (item for item in client_items if item.case_no == case_no):
            version = _insert_client_projection(cursor, item, version)
        cursor.execute("UPDATE client_finance_accounts SET aggregate_version=%s WHERE case_no=%s", (version, case_no))
    for case_no in sorted({item.case_no for item in staff_items}):
        cursor.execute("INSERT IGNORE INTO payroll_case_accounts(case_no,aggregate_version) VALUES (%s,0)", (case_no,))
        version = 0
        for item in (item for item in staff_items if item.case_no == case_no):
            version = _insert_staff_projection(cursor, item, version)
        cursor.execute("UPDATE payroll_case_accounts SET aggregate_version=%s WHERE case_no=%s", (version, case_no))


def run_migration(*, mode: str, target_database: str, plan_receipt: str | None = None, backup_receipt: str | None = None, receipt_path: str | None = None) -> dict[str, Any]:
    configured_database = str(DB_CONFIG.get("database") or "")
    if target_database != configured_database:
        raise ValueError("target database must exactly match configured DB_DATABASE")
    connection = get_connection()
    committed = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
            if identity["database_name"] != target_database:
                raise RuntimeError("connected database does not match --target-database")
            schema_fingerprint = _assert_schema(cursor)
            client_items, client_review_keys = build_client_open_obligations(
                _load_client_rows(cursor, lock=mode == "apply"),
                _load_transaction_nets(cursor, lock=mode == "apply"),
            )
            staff_items, staff_review_ids = build_staff_open_obligations(_load_staff_rows(cursor, lock=mode == "apply"))
            existing_counts = _existing_counts(cursor)
            plan = _plan_payload(
                database=target_database, server=str(identity["server"]), schema_fingerprint=schema_fingerprint,
                client_items=client_items, client_review_keys=client_review_keys,
                staff_items=staff_items, staff_review_ids=staff_review_ids,
                existing_counts=existing_counts,
            )
            if mode == "apply":
                _assert_safe_existing_state(cursor, existing_counts)
                saved_plan = _read_plan(plan_receipt)
                if saved_plan.get("dataset_fingerprint") != plan["dataset_fingerprint"]:
                    raise RuntimeError("dry-run plan drift detected")
                backup_path = _validate_backup(backup_receipt)
                _apply(cursor, client_items, staff_items)
                connection.commit()
                committed = True
                plan["backup_receipt"] = backup_path
                plan["receipt_status"] = "committed"
            elif mode == "verify":
                _verify(cursor, client_items, staff_items)
                plan["receipt_status"] = "verified"
            else:
                plan["receipt_status"] = "planned"
            plan["mode"] = mode
            _write_receipt(receipt_path, plan)
            return plan
    except Exception:
        if not committed:
            connection.rollback()
        raise
    finally:
        connection.close()


def _verify(cursor, client_items, staff_items) -> None:
    expected_client = {item.identity: item.amount_due_ntd for item in client_items}
    expected_staff = {item.identity: item.amount_due_ntd for item in staff_items}
    cursor.execute("SELECT obligation_identity,amount_due_ntd FROM client_obligations WHERE obligation_identity LIKE 'legacy-client-open:%'")
    actual_client = {row["obligation_identity"]: int(row["amount_due_ntd"]) for row in cursor.fetchall()}
    cursor.execute("SELECT obligation_identity,amount_due_ntd FROM staff_obligations WHERE obligation_identity LIKE 'legacy-staff-open:%'")
    actual_staff = {row["obligation_identity"]: int(row["amount_due_ntd"]) for row in cursor.fetchall()}
    if actual_client != expected_client or actual_staff != expected_staff:
        raise RuntimeError("canonical accounting projection verification failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--plan-receipt")
    parser.add_argument("--backup-receipt")
    parser.add_argument("--receipt-path")
    args = parser.parse_args()
    mode = "apply" if args.apply else "verify" if args.verify else "dry-run"
    receipt = run_migration(mode=mode, target_database=args.target_database, plan_receipt=args.plan_receipt, backup_receipt=args.backup_receipt, receipt_path=args.receipt_path)
    print(canonical_json({key: receipt.get(key) for key in ("mode", "receipt_status", "dataset_fingerprint", "database")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Audit twin cases and backfill only provably missing assignment rate snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.bootstrap.case_architecture import is_twin_case
from domains.case_import.order_information import project_order_information
from infrastructure.mysql.mysql_adapter import DB_CONFIG, get_connection


MIGRATION_ID = "twins-payroll-rate-snapshots-v1"
RECEIPT_CONTRACT = "twins-payroll-rate-snapshot-backfill/v1"
REQUIRED_TABLES = (
    "assignment_payroll_rate_snapshots",
    "beclass_records",
    "case_payroll_rate_policy_snapshots",
    "case_staff_assignments",
    "orders",
    "payroll_rate_policies",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _assert_schema(cursor: Any) -> str:
    placeholders = ",".join(["%s"] * len(REQUIRED_TABLES))
    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() "
        f"AND TABLE_NAME IN ({placeholders}) ORDER BY TABLE_NAME",
        REQUIRED_TABLES,
    )
    tables = tuple(str(row["TABLE_NAME"]) for row in cursor.fetchall())
    if tables != tuple(sorted(REQUIRED_TABLES)):
        raise RuntimeError("twins Payroll backfill schema is incomplete")
    cursor.execute(
        "SELECT hourly_rate_ntd FROM payroll_rate_policies "
        "WHERE policy_version=%s AND policy_kind=%s",
        ("approved-rates-v1", "twins"),
    )
    policy = cursor.fetchone()
    if not isinstance(policy, Mapping) or int(policy["hourly_rate_ntd"]) != 450:
        raise RuntimeError("canonical twins Payroll policy is missing")
    return _fingerprint({"tables": tables, "twins_rate": 450})


def _load_bound_beclass_rows(cursor: Any, *, lock: bool) -> tuple[Mapping[str, Any], ...]:
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT b.id AS beclass_record_id,b.bound_case_no AS case_no,b.survey_details "
        "FROM beclass_records b JOIN orders o ON o.case_no=b.bound_case_no "
        "WHERE b.bound_case_no IS NOT NULL ORDER BY b.bound_case_no,b.id" + suffix
    )
    return tuple(cursor.fetchall())


def _classify_twin_cases(
    rows: tuple[Mapping[str, Any], ...],
) -> tuple[tuple[str, ...], list[str]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["case_no"]), []).append(row)
    twin_cases: list[str] = []
    unresolved: list[str] = []
    for case_no, case_rows in sorted(grouped.items()):
        projections = [
            project_order_information(row.get("survey_details")) for row in case_rows
        ]
        values = [item.values.get("multi_birth_count") for item in projections]
        has_issue = any("multi_birth_count" in item.issues for item in projections)
        has_twins = any(is_twin_case(value if isinstance(value, str) else None) for value in values)
        if len(case_rows) != 1:
            if has_twins or has_issue:
                unresolved.append(f"{case_no}:beclass_binding_ambiguous")
            continue
        if has_issue:
            unresolved.append(f"{case_no}:multi_birth_count_ambiguous")
        elif has_twins:
            twin_cases.append(case_no)
    return tuple(twin_cases), unresolved


def _load_case_rates(
    cursor: Any, case_nos: tuple[str, ...], *, lock: bool
) -> dict[str, Mapping[str, Any]]:
    if not case_nos:
        return {}
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT case_no,policy_version,policy_kind,hourly_rate_ntd,"
        "source_identity_status,source_event_id "
        "FROM case_payroll_rate_policy_snapshots WHERE case_no IN ("
        + ",".join(["%s"] * len(case_nos))
        + ") ORDER BY case_no"
        + suffix,
        case_nos,
    )
    return {str(row["case_no"]): row for row in cursor.fetchall()}


def _load_assignment_rates(
    cursor: Any, case_nos: tuple[str, ...], *, lock: bool
) -> tuple[Mapping[str, Any], ...]:
    if not case_nos:
        return ()
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT a.id AS assignment_id,a.case_no,r.policy_version,r.policy_kind,"
        "r.hourly_rate_ntd,r.source_identity_status "
        "FROM case_staff_assignments a "
        "LEFT JOIN assignment_payroll_rate_snapshots r ON r.assignment_id=a.id "
        "WHERE a.case_no IN ("
        + ",".join(["%s"] * len(case_nos))
        + ") ORDER BY a.case_no,a.id"
        + suffix,
        case_nos,
    )
    return tuple(cursor.fetchall())


def _build_plan(cursor: Any, *, database: str, server: str, lock: bool) -> dict[str, Any]:
    twin_cases, unresolved = _classify_twin_cases(
        _load_bound_beclass_rows(cursor, lock=lock)
    )
    case_rates = _load_case_rates(cursor, twin_cases, lock=lock)
    insertions: list[dict[str, Any]] = []
    for case_no in twin_cases:
        rate = case_rates.get(case_no)
        if rate is None:
            unresolved.append(f"{case_no}:case_rate_snapshot_missing")
        elif str(rate["policy_kind"]) != "twins" or int(rate["hourly_rate_ntd"]) != 450:
            unresolved.append(f"{case_no}:case_rate_snapshot_not_twins_450")
    for row in _load_assignment_rates(cursor, twin_cases, lock=lock):
        case_no = str(row["case_no"])
        assignment_id = int(row["assignment_id"])
        if row.get("hourly_rate_ntd") is not None:
            if int(row["hourly_rate_ntd"]) != 450:
                unresolved.append(f"{case_no}:assignment_{assignment_id}_rate_not_450")
            continue
        case_rate = case_rates.get(case_no)
        if (
            case_rate is not None
            and str(case_rate["policy_kind"]) == "twins"
            and int(case_rate["hourly_rate_ntd"]) == 450
        ):
            insertions.append(
                {
                    "assignment_id": assignment_id,
                    "case_no": case_no,
                    "policy_version": str(case_rate["policy_version"]),
                    "policy_kind": "twins",
                    "hourly_rate_ntd": 450,
                    "source_identity_status": "twins-preserve-backfill:case-policy",
                }
            )
    core = {
        "migration": MIGRATION_ID,
        "database": database,
        "server": server,
        "twin_cases": list(twin_cases),
        "insertions": insertions,
        "unresolved": sorted(set(unresolved)),
    }
    return {**core, "dataset_fingerprint": _fingerprint(core)}


def _write_receipt(path_value: str | None, payload: Mapping[str, Any]) -> None:
    if not path_value:
        return
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(payload) + "\n", encoding="utf-8", newline="\n")


def _read_plan(path_value: str | None, current: Mapping[str, Any]) -> Mapping[str, Any]:
    if not path_value:
        raise ValueError("--apply requires --plan-receipt")
    path = Path(path_value).expanduser().resolve()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("dry-run plan receipt is invalid") from exc
    if (
        not isinstance(saved, Mapping)
        or saved.get("contract") != RECEIPT_CONTRACT
        or saved.get("mode") != "dry-run"
        or saved.get("database") != current.get("database")
        or saved.get("server") != current.get("server")
        or saved.get("schema_fingerprint") != current.get("schema_fingerprint")
        or saved.get("dataset_fingerprint") != current.get("dataset_fingerprint")
    ):
        raise RuntimeError("twins Payroll dry-run plan drift detected")
    return saved


def _validate_backup(path_value: str | None, database: str) -> str:
    if not path_value:
        raise ValueError("--apply requires --backup-receipt")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError("candidate backup is missing")
    header = path.read_bytes()[:1_048_576]
    if not header.startswith((b"-- MySQL dump", b"-- MariaDB dump")):
        raise ValueError("candidate backup is not a native MySQL dump")
    if not any(
        marker in header
        for marker in (
            f"Current Database: `{database}`".encode(),
            f"USE `{database}`".encode(),
            f"Database: {database}".encode(),
        )
    ):
        raise ValueError("candidate backup does not identify the target database")
    return str(path)


def run_migration(
    *,
    mode: str,
    target_database: str,
    plan_receipt: str | None = None,
    backup_receipt: str | None = None,
    receipt_path: str | None = None,
) -> dict[str, Any]:
    if target_database != str(DB_CONFIG.get("database") or ""):
        raise ValueError("target database must exactly match configured DB_DATABASE")
    if not os.getenv("DB_HOST", "").strip():
        raise ValueError("DB_HOST must be configured explicitly")
    connection = get_connection()
    committed = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name,@@hostname AS server")
            identity = cursor.fetchone()
            if not isinstance(identity, Mapping) or identity["database_name"] != target_database:
                raise RuntimeError("connected database does not match --target-database")
            schema_fingerprint = _assert_schema(cursor)
            plan = _build_plan(
                cursor,
                database=target_database,
                server=str(identity["server"]),
                lock=mode == "apply",
            )
            result = {
                "contract": RECEIPT_CONTRACT,
                "mode": mode,
                "schema_fingerprint": schema_fingerprint,
                **plan,
            }
            if mode == "apply":
                _read_plan(plan_receipt, result)
                if result["unresolved"]:
                    raise RuntimeError("twins Payroll backfill has unresolved rows")
                result["backup_receipt"] = _validate_backup(
                    backup_receipt, target_database
                )
                rows = tuple(
                    (
                        item["assignment_id"], item["policy_version"],
                        item["policy_kind"], item["hourly_rate_ntd"],
                        item["source_identity_status"],
                    )
                    for item in result["insertions"]
                )
                if rows:
                    cursor.executemany(
                        "INSERT INTO assignment_payroll_rate_snapshots "
                        "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,"
                        "source_identity_status) VALUES (%s,%s,%s,%s,%s)",
                        rows,
                    )
                connection.commit()
                committed = True
                result["receipt_status"] = "committed"
            elif mode == "verify":
                if result["unresolved"] or result["insertions"]:
                    raise RuntimeError("twins Payroll snapshot verification failed")
                result["receipt_status"] = "verified"
            else:
                result["receipt_status"] = "planned"
            _write_receipt(receipt_path, result)
            return result
    except Exception:
        if not committed:
            connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--plan-receipt")
    parser.add_argument("--backup-receipt")
    parser.add_argument("--receipt-path")
    parser.add_argument("--confirm-apply")
    arguments = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", arguments.target_database):
        parser.error("target database identifier is invalid")
    mode = "apply" if arguments.apply else "verify" if arguments.verify else "dry-run"
    if arguments.apply:
        if arguments.confirm_apply != arguments.target_database:
            parser.error("--confirm-apply must exactly equal --target-database")
        if not arguments.receipt_path:
            parser.error("--apply requires --receipt-path")
    receipt = run_migration(
        mode=mode,
        target_database=arguments.target_database,
        plan_receipt=arguments.plan_receipt,
        backup_receipt=arguments.backup_receipt,
        receipt_path=arguments.receipt_path,
    )
    print(
        _canonical_json(
            {
                key: receipt.get(key)
                for key in (
                    "mode", "receipt_status", "database", "dataset_fingerprint"
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

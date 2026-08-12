"""Read-only verification for the normal UI validation chain in an integrated DB."""

from __future__ import annotations

import argparse
import json
import re

import pymysql


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_NORMAL_CASE_NO = "115000051"


def verify(arguments) -> dict[str, object]:
    database = _require_dataset_database(arguments.database)
    connection = pymysql.connect(
        host=arguments.host, port=arguments.port, user=arguments.user,
        password=arguments.password, database=database, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        observed = _read_normal_chain(connection, arguments.case_no)
    finally:
        connection.close()
    checks = _checks(observed)
    return {"case_no": arguments.case_no, "checks": checks, "valid": all(item["passed"] for item in checks)}


def _require_dataset_database(database: str) -> str:
    if not _DATABASE_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    return database


def _read_normal_chain(connection, case_no: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        return {
            "order": _one(cursor, "SELECT status,contract_identity FROM orders WHERE case_no=%s", case_no),
            "signing": _signing_counts(cursor, case_no),
            "commitment_days": _commitment_days(cursor, case_no),
            "availability_lock": _availability_lock(cursor, case_no),
            "assignment": _assignment(cursor, case_no),
            "official_days": _official_days(cursor, case_no),
            "client_obligation": _client_obligation(cursor, case_no),
            "staff_obligation": _staff_obligation(cursor, case_no),
        }


def _one(cursor, statement: str, case_no: str):
    cursor.execute(statement, (case_no,))
    return cursor.fetchone()


def _signing_counts(cursor, case_no: str) -> dict[str, int]:
    cursor.execute(
        "SELECT COUNT(*) AS documents,SUM(event_type='sent') AS sent,"
        "SUM(event_type='signed_received') AS signed_received "
        "FROM contract_signing_events WHERE case_no=%s",
        (case_no,),
    )
    row = cursor.fetchone() or {}
    return {key: int(row.get(key) or 0) for key in ("documents", "sent", "signed_received")}


def _commitment_days(cursor, case_no: str) -> int:
    cursor.execute(
        "SELECT COUNT(*) AS count FROM precontract_service_commitment_days day_row "
        "INNER JOIN precontract_service_commitments header ON header.id=day_row.commitment_id "
        "WHERE header.case_no=%s",
        (case_no,),
    )
    return int(cursor.fetchone()["count"])


def _availability_lock(cursor, case_no: str):
    return _one(
        cursor,
        "SELECT lock_row.status,lock_row.is_active FROM caregiver_availability_locks lock_row "
        "INNER JOIN caregiver_matching_plans plan ON plan.id=lock_row.plan_id WHERE plan.case_no=%s",
        case_no,
    )


def _assignment(cursor, case_no: str):
    return _one(
        cursor,
        "SELECT COUNT(*) AS count,MIN(status) AS status,MIN(staff_id) AS staff_id "
        "FROM case_staff_assignments WHERE case_no=%s AND status <> 'cancelled'",
        case_no,
    )


def _official_days(cursor, case_no: str) -> int:
    cursor.execute(
        "SELECT COUNT(*) AS count FROM staff_schedule WHERE case_no=%s AND is_work_day=1",
        (case_no,),
    )
    return int(cursor.fetchone()["count"])


def _client_obligation(cursor, case_no: str):
    return _one(
        cursor,
        "SELECT amount_due_ntd,status FROM client_obligations "
        "WHERE case_no=%s AND obligation_type='deposit'",
        case_no,
    )


def _staff_obligation(cursor, case_no: str):
    return _one(
        cursor,
        "SELECT amount_due_ntd,status FROM staff_obligations WHERE case_no=%s",
        case_no,
    )


def _checks(observed: dict[str, object]) -> list[dict[str, object]]:
    return [
        _check("order_status", "訂單成立", _value(observed, "order", "status")),
        _check("contract_identity_present", True, bool(_value(observed, "order", "contract_identity"))),
        _check("signing_events", {"documents": 4, "sent": 2, "signed_received": 2}, observed["signing"]),
        _check("committed_service_days", 5, observed["commitment_days"]),
        _check("availability_lock_converted", {"status": "converted", "is_active": None}, observed["availability_lock"]),
        _check("formal_assignment", {"count": 1, "status": "planned", "staff_id": 8892}, observed["assignment"]),
        _check("official_service_days", 5, observed["official_days"]),
        _check("deposit_settled", {"amount_due_ntd": 0, "status": "settled"}, observed["client_obligation"]),
        _check("staff_payable", {"amount_due_ntd": 12000, "status": "open"}, observed["staff_obligation"]),
    ]


def _value(observed: dict[str, object], key: str, field: str):
    value = observed[key]
    return value.get(field) if isinstance(value, dict) else None


def _check(check_id: str, expected: object, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "expected": expected, "observed": observed, "passed": expected == observed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--case-no", default=_NORMAL_CASE_NO)
    result = verify(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

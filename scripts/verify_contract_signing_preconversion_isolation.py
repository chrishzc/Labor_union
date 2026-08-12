"""Read-only verifier for WP56 pre-conversion downstream isolation."""

from __future__ import annotations

import argparse
import json
import re

import pymysql


_DATASET_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")


def verify(arguments) -> dict[str, object]:
    database = _require_dataset_database(arguments.database)
    connection = pymysql.connect(
        host=arguments.host,
        port=arguments.port,
        user=arguments.user,
        password=arguments.password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        return _inspect(connection, arguments.case_no)
    finally:
        connection.close()


def _require_dataset_database(database: str) -> str:
    if not _DATASET_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    return database


def _inspect(connection, case_no: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        observed = {
            "commitment_count": _count(cursor, _COMMITMENT_COUNT_SQL, case_no),
            "converted_commitment_count": _count(cursor, _CONVERTED_COUNT_SQL, case_no),
            "assignment_count": _count(cursor, _ASSIGNMENT_COUNT_SQL, case_no),
            "calendar_schedule_count": _count(cursor, _SCHEDULE_COUNT_SQL, case_no),
            "payroll_execution_count": _count(cursor, _PAYROLL_COUNT_SQL, case_no),
            "subsidy_claim_item_count": _count(cursor, _SUBSIDY_COUNT_SQL, case_no),
        }
    checks = _checks(observed)
    return {
        "case_no": case_no,
        "observed": observed,
        "checks": checks,
        "valid": all(check["passed"] for check in checks),
    }


def _count(cursor, statement: str, case_no: str) -> int:
    cursor.execute(statement, (case_no,))
    return int(cursor.fetchone()["count"])


def _checks(observed: dict[str, int]) -> list[dict[str, object]]:
    return [
        _check("effective_commitment", observed["commitment_count"], 1),
        _check("not_converted", observed["converted_commitment_count"], 0),
        _check("calendar_isolated", observed["calendar_schedule_count"], 0),
        _check("assignment_isolated", observed["assignment_count"], 0),
        _check("payroll_isolated", observed["payroll_execution_count"], 0),
        _check("subsidy_isolated", observed["subsidy_claim_item_count"], 0),
    ]


def _check(check_id: str, observed: object, expected: object) -> dict[str, object]:
    return {"check_id": check_id, "expected": expected, "observed": observed, "passed": observed == expected}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=3306, type=int)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="1234")
    parser.add_argument("--database", required=True)
    parser.add_argument("--case-no", required=True)
    return parser.parse_args()


def main() -> int:
    result = verify(_arguments())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


_COMMITMENT_COUNT_SQL = (
    "SELECT COUNT(*) AS count FROM precontract_service_commitments WHERE case_no=%s"
)
_CONVERTED_COUNT_SQL = (
    "SELECT COUNT(*) AS count FROM precontract_service_commitment_events event "
    "JOIN precontract_service_commitments commitment ON commitment.id=event.commitment_id "
    "WHERE commitment.case_no=%s AND event.event_type='converted'"
)
_ASSIGNMENT_COUNT_SQL = (
    "SELECT COUNT(*) AS count FROM case_staff_assignments "
    "WHERE case_no=%s AND status <> 'cancelled'"
)
_SCHEDULE_COUNT_SQL = "SELECT COUNT(*) AS count FROM staff_schedule WHERE case_no=%s"
_PAYROLL_COUNT_SQL = (
    "SELECT COUNT(*) AS count FROM staff_obligations "
    "WHERE case_no=%s AND obligation_kind='service_pay' "
    "AND assignment_id IS NOT NULL AND status <> 'cancelled'"
)
_SUBSIDY_COUNT_SQL = "SELECT COUNT(*) AS count FROM subsidy_claim_batch_items WHERE case_no=%s"


if __name__ == "__main__":
    raise SystemExit(main())

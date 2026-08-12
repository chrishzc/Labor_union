"""Read-only verification for the client-signed, pre-execution UI scenario."""

from __future__ import annotations

import argparse
import json
import re

import pymysql


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_CASE_NO = "DSV1-CASE-0001"


def verify_dataset(arguments) -> dict[str, object]:
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
        observations = _read_observations(connection, arguments.case_no)
    finally:
        connection.close()
    checks = _checks(observations)
    return {
        "case_no": arguments.case_no,
        "scenario_id": "contract-signing-client-signed-ready",
        "checks": checks,
        "valid": all(check["passed"] for check in checks),
    }


def _require_dataset_database(database: str) -> str:
    if not _DATABASE_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    return database


def _read_observations(connection, case_no: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        return {
            "matching_plan": _matching_plan(cursor, case_no),
            "bound_recipients": _bound_recipient_count(cursor, case_no),
            "contract_documents": _case_count(cursor, "contract_document_versions", case_no),
            "signing_events": _case_count(cursor, "contract_signing_events", case_no),
            "commitments": _case_count(cursor, "precontract_service_commitments", case_no),
            "contract_identity": _contract_identity(cursor, case_no),
            "execution_assignments": _case_count(cursor, "case_staff_assignments", case_no),
            "official_schedule_days": _official_schedule_day_count(cursor, case_no),
        }


def _matching_plan(cursor, case_no: str) -> dict[str, object] | None:
    cursor.execute(
        "SELECT plan.status,COUNT(segment.id) AS segment_count "
        "FROM caregiver_matching_plans plan "
        "LEFT JOIN caregiver_matching_plan_segments segment ON segment.plan_id=plan.id "
        "WHERE plan.case_no=%s GROUP BY plan.id,plan.status ORDER BY plan.id DESC LIMIT 1",
        (case_no,),
    )
    return cursor.fetchone()


def _bound_recipient_count(cursor, case_no: str) -> int:
    cursor.execute(
        "SELECT COUNT(*) AS count FROM line_identity_bindings binding "
        "JOIN orders order_row ON binding.subject_type='customer' "
        "AND binding.subject_reference=CONVERT(CAST(order_row.client_id AS CHAR) "
        "USING utf8mb4) COLLATE utf8mb4_unicode_ci "
        "WHERE order_row.case_no=%s AND binding.binding_status='bound' "
        "UNION ALL "
        "SELECT COUNT(*) AS count FROM line_identity_bindings binding "
        "JOIN caregiver_matching_plan_segments segment "
        "ON binding.subject_type='staff' "
        "AND binding.subject_reference=CONVERT(CAST(segment.staff_id AS CHAR) "
        "USING utf8mb4) COLLATE utf8mb4_unicode_ci "
        "JOIN caregiver_matching_plans plan ON plan.id=segment.plan_id "
        "WHERE plan.case_no=%s AND binding.binding_status='bound'",
        (case_no, case_no),
    )
    return sum(int(row["count"]) for row in cursor.fetchall())


def _case_count(cursor, table: str, case_no: str) -> int:
    cursor.execute(f"SELECT COUNT(*) AS count FROM `{table}` WHERE case_no=%s", (case_no,))
    return int(cursor.fetchone()["count"])


def _official_schedule_day_count(cursor, case_no: str) -> int:
    cursor.execute(
        "SELECT COUNT(*) AS count FROM staff_schedule schedule "
        "JOIN case_staff_assignments assignment ON assignment.id=schedule.assignment_id "
        "WHERE assignment.case_no=%s AND schedule.is_work_day=1",
        (case_no,),
    )
    return int(cursor.fetchone()["count"])


def _contract_identity(cursor, case_no: str) -> str | None:
    cursor.execute("SELECT contract_identity FROM orders WHERE case_no=%s", (case_no,))
    row = cursor.fetchone()
    if row is None or row["contract_identity"] is None:
        return None
    return str(row["contract_identity"])


def _checks(observations: dict[str, object]) -> list[dict[str, object]]:
    return [
        _check("matching_plan", {"status": "proposed", "segment_count": 1}, observations["matching_plan"]),
        _check("bound_line_recipients", 2, observations["bound_recipients"]),
        _check("contract_documents", 4, observations["contract_documents"]),
        _check("signing_events", 4, observations["signing_events"]),
        _check("commitment_after_staff_signature", 1, observations["commitments"]),
        _check("client_contract_identity", True, observations["contract_identity"] is not None),
        _check("execution_assignments_before_client_signature", 0, observations["execution_assignments"]),
        _check("official_schedule_before_client_signature", 0, observations["official_schedule_days"]),
    ]


def _check(check_id: str, expected: object, observed: object) -> dict[str, object]:
    return {
        "check_id": check_id,
        "expected": expected,
        "observed": observed,
        "passed": expected == observed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--case-no", default=_CASE_NO)
    result = verify_dataset(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

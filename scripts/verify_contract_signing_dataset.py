"""Read-only verification for the contract-signing validation baseline."""

from __future__ import annotations

import argparse
import json
import re

import pymysql


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_SIGNING_TABLES = (
    "contract_document_versions",
    "contract_signing_events",
    "precontract_service_commitments",
    "precontract_service_commitment_days",
    "precontract_service_commitment_events",
)


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
        return _inspect(connection, arguments.case_no)
    finally:
        connection.close()


def _require_dataset_database(database: str) -> str:
    if not _DATABASE_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    return database


def _inspect(connection, case_no: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        table_counts = _table_counts(cursor, case_no)
        order = _order_snapshot(cursor, case_no)
    checks = _checks(table_counts, order)
    return {
        "case_no": case_no,
        "checks": checks,
        "order": order,
        "valid": all(check["passed"] for check in checks),
    }


def _table_counts(cursor, case_no: str) -> dict[str, int]:
    return {
        table: _table_case_count(cursor, table, case_no)
        for table in _SIGNING_TABLES
    }


def _table_case_count(cursor, table: str, case_no: str) -> int:
    if table in {"precontract_service_commitment_days", "precontract_service_commitment_events"}:
        cursor.execute(
            f"SELECT COUNT(*) AS count FROM `{table}` child "
            "INNER JOIN precontract_service_commitments header "
            "ON header.id = child.commitment_id WHERE header.case_no = %s",
            (case_no,),
        )
    else:
        cursor.execute(
            f"SELECT COUNT(*) AS count FROM `{table}` WHERE case_no = %s",
            (case_no,),
        )
    return int(cursor.fetchone()["count"])


def _order_snapshot(cursor, case_no: str) -> dict[str, object] | None:
    cursor.execute(
        "SELECT status, contract_identity FROM orders WHERE case_no = %s",
        (case_no,),
    )
    return cursor.fetchone()


def _checks(table_counts, order) -> list[dict[str, object]]:
    return [
        _check("order_exists", order is not None, True),
        _check("precontract_baseline_has_no_documents", table_counts["contract_document_versions"], 0),
        _check("precontract_baseline_has_no_signing_events", table_counts["contract_signing_events"], 0),
        _check("precontract_baseline_has_no_commitment", table_counts["precontract_service_commitments"], 0),
        _check("precontract_order_status", order["status"] if order else None, "洽談中"),
        _check("precontract_contract_identity", order["contract_identity"] if order else None, None),
    ]


def _check(check_id: str, observed: object, expected: object) -> dict[str, object]:
    return {
        "check_id": check_id,
        "expected": expected,
        "observed": observed,
        "passed": observed == expected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--case-no", default="DSV1-CASE-0001")
    result = verify_dataset(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

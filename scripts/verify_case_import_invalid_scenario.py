"""Read-only verification for UI-CI-INVALID-001."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_case_import_invalid_scenario import (
    SCENARIO_ID,
    _ROOT_TABLES,
    _require_dataset_database,
)


def verify(arguments) -> dict[str, object]:
    _require_dataset_database(arguments.database)
    connection = pymysql.connect(host=arguments.host, port=arguments.port, user=arguments.user, password=arguments.password, database=arguments.database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    try:
        observed = _inspect(connection, arguments.review_identity)
    finally:
        connection.close()
    checks = _checks(observed)
    return {"scenario_id": SCENARIO_ID, "observed": observed, "checks": checks, "valid": all(item["passed"] for item in checks)}


def _inspect(connection, review_identity: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT root.review_identity,root.masked_identifier,root.source_payload,root.issue_codes,"
            "COUNT(outbox.id) AS outbox_count FROM beclass_import_review_rows root "
            "LEFT JOIN beclass_import_review_outbox outbox ON outbox.review_row_id=root.id "
            "WHERE root.review_identity=%s GROUP BY root.id",
            (review_identity,),
        )
        review = cursor.fetchone()
        root_counts = {}
        for table_name in _ROOT_TABLES:
            cursor.execute(f"SELECT COUNT(*) AS count FROM `{table_name}`")
            root_counts[table_name] = int(cursor.fetchone()["count"])
    return {"review": review, "root_counts": root_counts}


def _checks(observed: dict[str, object]) -> list[dict[str, object]]:
    review = observed["review"] or {}
    payload = json.loads(review["source_payload"]) if review else None
    issues = json.loads(review["issue_codes"]) if review else None
    return [
        _check("invalid_root_is_open_for_review", review.get("outbox_count"), 1),
        _check("privacy_safe_payload", payload, {"query_no": None, "validation_marker": "missing_query_no"}),
        _check("privacy_safe_identifier", "*" in str(review.get("masked_identifier", "")), True),
        _check("issue_is_recorded", issues, ["missing_query_no"]),
    ]


def _check(check_id: str, observed: object, expected: object) -> dict[str, object]:
    return {"check_id": check_id, "expected": expected, "observed": observed, "passed": observed == expected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--review-identity", required=True)
    result = verify(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only verifier for UI-FI-MANUAL-001 repair and replay evidence."""

from __future__ import annotations

import argparse
import json
import re

import pymysql


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")


def verify(arguments) -> dict[str, object]:
    if not _DATABASE_PATTERN.fullmatch(arguments.database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    connection = pymysql.connect(host=arguments.host, port=arguments.port, user=arguments.user, password=arguments.password, database=arguments.database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    try:
        observed = _inspect(connection, arguments.batch_identity)
    finally:
        connection.close()
    checks = _checks(observed)
    return {"batch_identity": arguments.batch_identity, "observed": observed, "checks": checks, "valid": all(item["passed"] for item in checks)}


def _inspect(connection, batch_identity: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT CONCAT('finance-import-row:',event.finance_import_row_id) AS row_identity,"
            "event.classification_type,event.disposition FROM finance_import_classification_events event "
            "JOIN finance_import_batch_contracts contract ON contract.batch_id=event.batch_id "
            "WHERE contract.batch_identity=%s ORDER BY event.id",
            (batch_identity,),
        )
        events = cursor.fetchall()
        if not events:
            return {"events": [], "alert": None}
        row_identity = events[-1]["row_identity"]
        cursor.execute(
            "SELECT workflow_status,predicate_active FROM anomaly_current_alerts "
            "WHERE definition_code='finance_import_manual_review' AND source_identity=%s",
            (row_identity,),
        )
        return {"events": events, "alert": cursor.fetchone()}


def _checks(observed: dict[str, object]) -> list[dict[str, object]]:
    events = observed["events"]
    first = events[0] if events else {}
    last = events[-1] if events else {}
    return [
        _check("manual_review_opened", (first.get("classification_type"), first.get("disposition")), ("non_business_review", "manual_review")),
        _check("owning_finance_correction", (last.get("classification_type"), last.get("disposition")), ("client_receipt", "create")),
        _check("manual_review_alert_resolved", observed["alert"], {"workflow_status": "resolved", "predicate_active": 0}),
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
    parser.add_argument("--batch-identity", required=True)
    result = verify(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

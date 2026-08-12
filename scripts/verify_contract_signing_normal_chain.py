"""Read-only verifier for the WP56 normal contract-signing chain."""

from __future__ import annotations

import argparse
import json
import re

import pymysql


_DATASET_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")


def verify(arguments) -> dict[str, object]:
    if not _DATASET_PATTERN.fullmatch(arguments.database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    connection = pymysql.connect(
        host=arguments.host, port=arguments.port, user=arguments.user,
        password=arguments.password, database=arguments.database,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        return _inspect(connection, arguments.case_no)
    finally:
        connection.close()


def _inspect(connection, case_no: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        observed = {
            "archive_digest_count": _count(cursor, "SELECT COUNT(*) AS count FROM contract_document_versions document JOIN media_assets asset ON asset.id=document.media_asset_id WHERE document.case_no=%s AND asset.sha256 <> ''", case_no),
            "staff_signed_count": _count(cursor, "SELECT COUNT(*) AS count FROM contract_signing_events event JOIN contract_document_versions document ON document.id=event.document_version_id WHERE event.case_no=%s AND document.document_scope='staff_segment' AND event.event_type='signed_received'", case_no),
            "client_signed_count": _count(cursor, "SELECT COUNT(*) AS count FROM contract_signing_events event JOIN contract_document_versions document ON document.id=event.document_version_id WHERE event.case_no=%s AND document.document_scope='client_contract' AND event.event_type='signed_received'", case_no),
            "commitment_count": _count(cursor, "SELECT COUNT(*) AS count FROM precontract_service_commitments WHERE case_no=%s", case_no),
            "converted_commitment_count": _count(cursor, "SELECT COUNT(*) AS count FROM precontract_service_commitment_events event JOIN precontract_service_commitments commitment ON commitment.id=event.commitment_id WHERE commitment.case_no=%s AND event.event_type='converted'", case_no),
            "settled_deposit_count": _count(cursor, "SELECT COUNT(*) AS count FROM client_obligations WHERE case_no=%s AND obligation_type='deposit' AND status='settled'", case_no),
            "assignment_count": _count(cursor, "SELECT COUNT(*) AS count FROM case_staff_assignments WHERE case_no=%s", case_no),
            "schedule_day_count": _count(cursor, "SELECT COUNT(*) AS count FROM staff_schedule WHERE case_no=%s", case_no),
        }
        cursor.execute("SELECT contract_identity FROM orders WHERE case_no=%s", (case_no,))
        order = cursor.fetchone()
    checks = _checks(observed, order)
    return {"case_no": case_no, "observed": observed, "checks": checks, "valid": all(item["passed"] for item in checks)}


def _count(cursor, statement: str, case_no: str) -> int:
    cursor.execute(statement, (case_no,))
    return int(cursor.fetchone()["count"])


def _checks(observed: dict[str, int], order) -> list[dict[str, object]]:
    return [
        _check("archive_digests", observed["archive_digest_count"] >= 4, True),
        _check("staff_signed", observed["staff_signed_count"] >= 1, True),
        _check("client_signed", observed["client_signed_count"], 1),
        _check("effective_commitment", observed["commitment_count"], 1),
        _check("commitment_converted", observed["converted_commitment_count"], 1),
        _check("settled_deposit", observed["settled_deposit_count"], 1),
        _check("contract_identity", bool(order and order["contract_identity"]), True),
        _check("execution_assignment", observed["assignment_count"], 1),
        _check("exact_schedule_days", observed["schedule_day_count"], 5),
    ]


def _check(check_id: str, observed: object, expected: object) -> dict[str, object]:
    return {"check_id": check_id, "expected": expected, "observed": observed, "passed": observed == expected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--case-no", required=True)
    result = verify(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

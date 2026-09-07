"""Issue 218 real FastAPI + disposable-MySQL acceptance for Orders intake repair."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
from decimal import Decimal
import hashlib
import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DATABASE,
        reason="requires an explicitly configured disposable lu_test_* MySQL database",
    ),
]

_CASE_NAME = "SYN-218-NAME"
_CASE_START = "SYN-218-START"
_CASE_DAYS = "SYN-218-DAYS"
_CASE_BOTH = "SYN-218-BOTH"
_INITIAL_VERSION = 7
_END_DATE = date(2026, 10, 31)
_SENTINEL_HOURS = 8
_SENTINEL_FLOOR = Decimal("123.00")


def _arguments() -> Namespace:
    assert DATABASE and DATABASE.startswith("lu_test_")
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _json_safe(value: Any):
    if isinstance(value, (date, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _seed(connection) -> str:
    cases = (
        (_CASE_NAME, None, date(2026, 9, 10), 5),
        (_CASE_START, "合成開始日案", None, 5),
        (_CASE_DAYS, "合成天數案", date(2026, 9, 12), None),
        (_CASE_BOTH, "合成雙缺案", None, None),
    )
    with connection.cursor() as cursor:
        for case_no, name, start_date, service_days in cases:
            cursor.execute(
                "INSERT INTO clients (case_no,name,identity_status) VALUES (%s,%s,%s)",
                (case_no, name, "一般"),
            )
            client_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO orders (
                    case_no,client_id,status,lifecycle_version,start_date,end_date,
                    service_days,service_hours_per_day,floor_fee,actual_start_date,actual_end_date
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)
                """,
                (
                    case_no,
                    client_id,
                    "待補件",
                    _INITIAL_VERSION,
                    start_date,
                    _END_DATE,
                    service_days,
                    _SENTINEL_HOURS,
                    _SENTINEL_FLOOR,
                ),
            )

        cursor.execute(
            """
            INSERT INTO admin_users (username,password_hash,display_name,linked_line_user_id,role)
            VALUES (%s,%s,%s,NULL,%s)
            """,
            (
                "issue218-line-agent",
                "synthetic-session-only",
                "Issue 218 Synthetic Line Agent",
                "line_agent",
            ),
        )
        admin_id = int(cursor.lastrowid)
        token = "issue218-synthetic-line-agent-session"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cursor.execute(
            """
            INSERT INTO admin_sessions (
                admin_user_id,session_token_hash,expires_at,absolute_expires_at,last_seen_at
            ) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(6), INTERVAL 1 HOUR),
                      DATE_ADD(UTC_TIMESTAMP(6), INTERVAL 2 HOUR),UTC_TIMESTAMP(6))
            """,
            (admin_id, token_hash),
        )
    connection.commit()
    return token


def _snapshot(connection, case_no: str) -> dict[str, Any]:
    # End the observer transaction so each acceptance readback sees current committed facts.
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT o.case_no,o.status,o.lifecycle_version,o.start_date,o.end_date,o.service_days,
                   o.service_hours_per_day,o.floor_fee,o.actual_start_date,o.actual_end_date,
                   c.name AS client_name
            FROM orders o JOIN clients c ON c.case_no=o.case_no WHERE o.case_no=%s
            """,
            (case_no,),
        )
        row = dict(cursor.fetchone())
        counts: dict[str, int] = {}
        for table in (
            "order_service_data_locks",
            "client_finance_accounts",
            "client_payment_terms",
            "payroll_case_accounts",
            "case_payroll_rate_policy_snapshots",
            "scheduling_aggregates",
            "case_staff_assignments",
        ):
            cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE case_no=%s", (case_no,))
            counts[table] = int(cursor.fetchone()["n"])
        cursor.execute("SELECT COUNT(*) AS n FROM admin_command_receipts")
        receipt_count = int(cursor.fetchone()["n"])
    return {"row": row, "owner_counts": counts, "receipt_count": receipt_count}


def _auth(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _data(response, expected_status: int = 200):
    assert response.status_code == expected_status, response.text
    return response.json().get("data")


def _terms_preview(client: TestClient, token: str, case_no: str, start: str, days: int):
    return _data(
        client.post(
            f"/api/v1/orders/{case_no}/intake-terms-bootstrap/preview",
            json={"proposed_start_date": start, "proposed_service_days": days},
            headers=_auth(token),
        )
    )


def _terms_apply(client: TestClient, token: str, case_no: str, preview, key: str):
    return client.post(
        f"/api/v1/orders/{case_no}/intake-terms-bootstrap/apply",
        json={
            "proposed_start_date": preview["after_start_date"],
            "proposed_service_days": preview["after_service_days"],
            "expected_lifecycle_version": preview["lifecycle_version"],
            "preview_fingerprint": preview["preview_fingerprint"],
            "reason": "Issue 218 synthetic intake acceptance",
        },
        headers=_auth(token, **{"Idempotency-Key": key, "X-Correlation-ID": key}),
    )


def test_issue_218_real_http_acceptance_on_disposable_mysql():
    bootstrap(_arguments())

    from api.main import app
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    token = _seed(connection)
    client = TestClient(app)
    evidence: dict[str, Any] = {"cases": {}}

    try:
        me = _data(client.get("/api/v1/admin/auth/me", headers=_auth(token)))
        assert me["role"] == "line_agent"
        assert me["is_root"] is False
        assert me["role"] != "system_admin"
        evidence["actor"] = {"role": me["role"], "is_root": me["is_root"]}

        name_before = _snapshot(connection, _CASE_NAME)
        name_preview = _data(
            client.post(
                f"/api/v1/orders/{_CASE_NAME}/intake-completion/client-name/preview",
                json={"client_name": "合成補件姓名"},
                headers=_auth(token),
            )
        )
        assert name_preview["before_client_name"] is None
        assert name_preview["after_client_name"] == "合成補件姓名"
        assert name_preview["apply_allowed"] is True
        assert _snapshot(connection, _CASE_NAME) == name_before
        name_apply = client.post(
            f"/api/v1/orders/{_CASE_NAME}/intake-completion/client-name/apply",
            json={
                "client_name": name_preview["after_client_name"],
                "expected_lifecycle_version": name_preview["lifecycle_version"],
                "preview_fingerprint": name_preview["preview_fingerprint"],
                "reason": "Issue 218 synthetic name acceptance",
            },
            headers=_auth(
                token,
                **{
                    "Idempotency-Key": "issue218-name-apply",
                    "X-Correlation-ID": "issue218-name-apply",
                },
            ),
        )
        name_receipt = _data(name_apply)
        name_after = _snapshot(connection, _CASE_NAME)
        assert name_after["row"]["client_name"] == "合成補件姓名"
        assert name_after["row"]["lifecycle_version"] == _INITIAL_VERSION
        assert name_after["row"]["status"] == "待補件"
        assert name_after["row"]["start_date"] == name_before["row"]["start_date"]
        assert name_after["row"]["service_days"] == name_before["row"]["service_days"]
        assert name_after["row"]["end_date"] == _END_DATE
        assert all(value == 0 for value in name_after["owner_counts"].values())
        assert name_receipt["lifecycle_version"] == _INITIAL_VERSION

        term_specs = (
            (_CASE_START, "2026-09-11", 5, ["start_date"]),
            (_CASE_DAYS, "2026-09-12", 6, ["service_days"]),
            (_CASE_BOTH, "2026-09-13", 7, ["start_date", "service_days"]),
        )
        previews: dict[str, Any] = {}
        for case_no, proposed_start, proposed_days, changed_fields in term_specs:
            before = _snapshot(connection, case_no)
            preview = _terms_preview(client, token, case_no, proposed_start, proposed_days)
            previews[case_no] = preview
            assert preview["changed_fields"] == changed_fields
            assert preview["apply_allowed"] is True
            assert _snapshot(connection, case_no) == before

            apply_response = _terms_apply(
                client,
                token,
                case_no,
                preview,
                f"issue218-terms-{case_no.lower()}",
            )
            receipt = _data(apply_response)
            after = _snapshot(connection, case_no)
            assert receipt["lifecycle_version"] == _INITIAL_VERSION + 1
            assert after["row"]["lifecycle_version"] == _INITIAL_VERSION + 1
            assert after["row"]["status"] == "待補件"
            assert str(after["row"]["start_date"]) == receipt["start_date"]
            assert after["row"]["service_days"] == receipt["service_days"]
            assert after["row"]["end_date"] == _END_DATE
            assert after["row"]["service_hours_per_day"] == _SENTINEL_HOURS
            assert after["row"]["floor_fee"] == _SENTINEL_FLOOR
            assert after["row"]["actual_start_date"] is None
            assert after["row"]["actual_end_date"] is None
            assert all(value == 0 for value in after["owner_counts"].values())
            if "start_date" not in changed_fields:
                assert after["row"]["start_date"] == before["row"]["start_date"]
            if "service_days" not in changed_fields:
                assert after["row"]["service_days"] == before["row"]["service_days"]
            evidence["cases"][case_no] = {
                "preview": preview,
                "before": before,
                "receipt": receipt,
                "after": after,
            }

        start_after_first_apply = _snapshot(connection, _CASE_START)
        replay = _data(
            _terms_apply(
                client,
                token,
                _CASE_START,
                previews[_CASE_START],
                "issue218-terms-syn-218-start",
            )
        )
        assert replay["replayed"] is True
        assert _snapshot(connection, _CASE_START) == start_after_first_apply

        stale = _terms_apply(
            client,
            token,
            _CASE_START,
            previews[_CASE_START],
            "issue218-terms-stale-new-key",
        )
        assert stale.status_code == 409, stale.text
        assert _snapshot(connection, _CASE_START) == start_after_first_apply

        invalid_before = _snapshot(connection, _CASE_START)
        invalid = client.post(
            f"/api/v1/orders/{_CASE_START}/intake-terms-bootstrap/preview",
            json={"proposed_start_date": "2026-09-11", "proposed_service_days": 0},
            headers=_auth(token),
        )
        assert invalid.status_code == 422, invalid.text
        assert _snapshot(connection, _CASE_START) == invalid_before

        both_before_completion_preview = _snapshot(connection, _CASE_BOTH)
        completion_preview = _data(
            client.post(
                f"/api/v1/orders/{_CASE_BOTH}/intake-completion/preview",
                headers=_auth(token),
            )
        )
        assert completion_preview["missing_fields"] == []
        assert completion_preview["blockers"] == []
        assert completion_preview["apply_allowed"] is True
        assert completion_preview["lifecycle_version"] == _INITIAL_VERSION + 1
        assert _snapshot(connection, _CASE_BOTH) == both_before_completion_preview

        completion_response = client.post(
            f"/api/v1/orders/{_CASE_BOTH}/intake-completion/apply",
            json={
                "expected_lifecycle_version": completion_preview["lifecycle_version"],
                "preview_fingerprint": completion_preview["preview_fingerprint"],
                "reason": "Issue 218 synthetic completeness acceptance",
            },
            headers=_auth(
                token,
                **{
                    "Idempotency-Key": "issue218-completion-both",
                    "X-Correlation-ID": "issue218-completion-both",
                },
            ),
        )
        completion_receipt = _data(completion_response)
        both_after_completion = _snapshot(connection, _CASE_BOTH)
        assert completion_receipt["lifecycle_version"] == _INITIAL_VERSION + 2
        assert completion_receipt["status"] == "洽談中"
        assert both_after_completion["row"]["lifecycle_version"] == _INITIAL_VERSION + 2
        assert both_after_completion["row"]["status"] == "洽談中"
        assert both_after_completion["row"]["start_date"] == both_before_completion_preview["row"]["start_date"]
        assert both_after_completion["row"]["service_days"] == both_before_completion_preview["row"]["service_days"]
        assert both_after_completion["row"]["end_date"] == _END_DATE
        assert all(value == 0 for value in both_after_completion["owner_counts"].values())

        completion_replay = _data(
            client.post(
                f"/api/v1/orders/{_CASE_BOTH}/intake-completion/apply",
                json={
                    "expected_lifecycle_version": completion_preview["lifecycle_version"],
                    "preview_fingerprint": completion_preview["preview_fingerprint"],
                    "reason": "Issue 218 synthetic completeness acceptance",
                },
                headers=_auth(
                    token,
                    **{
                        "Idempotency-Key": "issue218-completion-both",
                        "X-Correlation-ID": "issue218-completion-both-replay",
                    },
                ),
            )
        )
        assert completion_replay["replayed"] is True
        assert _snapshot(connection, _CASE_BOTH) == both_after_completion

        evidence["cases"][_CASE_NAME] = {
            "preview": name_preview,
            "before": name_before,
            "receipt": name_receipt,
            "after": name_after,
        }
        evidence["completion"] = {
            "before": both_before_completion_preview,
            "preview": completion_preview,
            "receipt": completion_receipt,
            "after": both_after_completion,
            "replay": completion_replay,
        }
        evidence["stale_status"] = stale.status_code
        evidence["invalid_status"] = invalid.status_code
        print(
            "ISSUE218_ACCEPTANCE_EVIDENCE="
            + json.dumps(_json_safe(evidence), ensure_ascii=False, sort_keys=True)
        )
    finally:
        connection.close()

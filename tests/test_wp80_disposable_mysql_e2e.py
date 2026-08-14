"""
File: test_wp80_disposable_mysql_e2e.py
Description: 在明確 disposable MySQL 驗證歷史狀態、assignment、event、receipt、outbox與replay同交易。
"""

from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest

from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionWorkflow,
)
from subsystems.orders.historical_order_workbook import (
    HistoricalCaregiverSource,
    HistoricalOrderWorkbookRow,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import fingerprint_payload


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_historical_order_apply_is_atomic_and_replays():
    token = uuid4().hex
    case_no = f"WP80-{token[:12]}"
    connection = get_connection()
    try:
        staff_name = f"歷史月嫂-{token[:8]}"
        staff_id = _seed_case(connection, case_no, staff_name)
        row = _source_row(case_no, token, staff_name)
        workflow = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        preview = workflow.preview(row)
        request = HistoricalOrderAdoptionRequest(
            row,
            preview.fingerprint,
            f"wp80:{token}",
            "wp80-test-operator",
            "verify historical adoption",
            f"wp80-correlation:{token}",
        )

        first = workflow.apply(request)
        replay = workflow.apply(request)

        assert first.replayed is False
        assert replay.replayed is True
        assert first.assignment_count == 1
        _assert_persisted(connection, case_no, staff_id, request.idempotency_key)
    finally:
        connection.close()


def _seed_case(connection, case_no, staff_name):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO clients (case_no,name) VALUES (%s,'歷史客戶')", (case_no,))
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders (case_no,client_id,status,lifecycle_version) VALUES (%s,%s,'洽談中',0)",
            (case_no, client_id),
        )
        cursor.execute(
            "INSERT INTO staff (name,identity_card) VALUES (%s,%s)",
            (staff_name, f"W{case_no[-9:]}"),
        )
        staff_id = int(cursor.lastrowid)
    connection.commit()
    return staff_id


def _source_row(case_no, token, staff_name):
    payload = {"case_no": case_no, "client_name": "歷史客戶", "status": 1, "token": token}
    return HistoricalOrderWorkbookRow(
        2,
        f"historical-orders:{token}:row:2",
        fingerprint_payload(payload).value,
        case_no,
        "歷史客戶",
        OrderLifecycleStatus.COMPLETED,
        date(2025, 1, 2),
        date(2025, 1, 31),
        (HistoricalCaregiverSource(1, staff_name, date(2025, 1, 2), date(2025, 1, 31), True, ()),),
        (),
    )


def _assert_persisted(connection, case_no, staff_id, key):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,lifecycle_version,actual_start_date,actual_end_date FROM orders WHERE case_no=%s",
            (case_no,),
        )
        assert cursor.fetchone() == {
            "status": "訂單完成",
            "lifecycle_version": 1,
            "actual_start_date": date(2025, 1, 2),
            "actual_end_date": date(2025, 1, 31),
        }
        cursor.execute("SELECT id,staff_id,status FROM case_staff_assignments WHERE case_no=%s", (case_no,))
        assignment = cursor.fetchone()
        assert assignment["staff_id"] == staff_id
        assert assignment["status"] == "completed"
        cursor.execute(
            "SELECT lifecycle_event_id,assignment_count FROM historical_order_adoption_receipts WHERE idempotency_key=%s",
            (key,),
        )
        receipt = cursor.fetchone()
        assert receipt["lifecycle_event_id"] is not None
        assert receipt["assignment_count"] == 1
        cursor.execute(
            "SELECT COUNT(*) AS count FROM historical_order_pairing_evidence WHERE assignment_id=%s",
            (assignment["id"],),
        )
        assert int(cursor.fetchone()["count"]) == 1
        cursor.execute(
            "SELECT COUNT(*) AS count FROM historical_order_adoption_outbox WHERE receipt_id IN "
            "(SELECT id FROM historical_order_adoption_receipts WHERE idempotency_key=%s)",
            (key,),
        )
        assert int(cursor.fetchone()["count"]) == 1

"""
File: test_wp80_disposable_mysql_e2e.py
Description: 在明確 disposable MySQL 驗證歷史狀態、assignment、event、receipt、outbox與replay同交易。
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
import os
from uuid import uuid4

import pytest

from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from .historical_accounting_fixture import seed_accounting_basis
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionWorkflow,
)
from subsystems.orders.historical_order_workbook import (
    HistoricalCaregiverSource,
    HistoricalOrderWorkbookRow,
)
from subsystems.payroll.historical_baseline_obligation_sync import synchronize_historical_payroll
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
            MySqlHistoricalAssignmentWriter(connection),
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
        _assert_statement_reconciles(connection, case_no, staff_id)
        assert synchronize_historical_payroll(connection, case_no)["reason"] == "already_synced"
    finally:
        connection.close()


def test_pending_statement_rematches_after_historical_payroll_exists():
    class BeforePayrollAdoption(MySqlHistoricalOrderAdoptionRepository):
        def synchronize_completed_payroll(self, case_no):
            return {"action": "skipped"}

    token = uuid4().hex
    case_no = f"WP80-{token[:12]}"
    staff_name = f"歷史重配月嫂-{token[:8]}"
    connection = get_connection()
    try:
        staff_id = _seed_case(connection, case_no, staff_name)
        row = _source_row(case_no, token, staff_name)
        workflow = HistoricalOrderAdoptionWorkflow(
            BeforePayrollAdoption(connection), lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
        )
        preview = workflow.preview(row)
        workflow.apply(HistoricalOrderAdoptionRequest(
            row, preview.fingerprint, f"wp80:{token}", "synthetic", "驗證重配", token,
        ))
        _assert_statement_reconciles(connection, case_no, staff_id, rematch=True)
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
        seed_accounting_basis(cursor, case_no)
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
            "status": OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
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
            "SELECT assignment_id,staff_id,amount_due_ntd,due_date,status FROM staff_obligations WHERE case_no=%s",
            (case_no,),
        )
        assert cursor.fetchall() == [{
            "assignment_id": assignment["id"], "staff_id": staff_id, "amount_due_ntd": 72000,
            "due_date": date(2025, 2, 15), "status": "open",
        }]
        for statement in (
            "SELECT COUNT(*) AS count FROM client_obligations WHERE case_no=%s",
            "SELECT COUNT(*) AS count FROM historical_service_day_events WHERE case_no=%s",
        ):
            cursor.execute(statement, (case_no,))
            assert cursor.fetchone()["count"] == 0
        cursor.execute(
            "SELECT COUNT(*) AS count FROM historical_order_adoption_outbox WHERE receipt_id IN "
            "(SELECT id FROM historical_order_adoption_receipts WHERE idempotency_key=%s)",
            (key,),
        )
        assert int(cursor.fetchone()["count"]) == 1


def _assert_statement_reconciles(connection, case_no, staff_id, *, rematch=False):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from openpyxl import Workbook

    from api.dependencies.admin_auth import require_admin, require_persisted_admin, require_system_admin
    from api.dependencies.durable_job_handlers import finance_import_batch_apply_handler
    from api.routes.finance_import import router
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.jobs.durable_job_worker import DurableJobWorker

    account = f"8888888888{staff_id:04}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM staff WHERE id=%s", (staff_id,))
        recipient = cursor.fetchone()["name"]
        cursor.execute("INSERT INTO staff_bank_accounts(staff_id,is_primary,bank_code,account_no) "
                       "VALUES (%s,1,'807',%s)", (staff_id, account))
    connection.commit()

    workbook = Workbook()
    workbook.active.append(["帳號", "交易日", "計息日", "入帳日", "摘要", "幣別", "支出", "存入",
                            "餘額", "銷帳編號", "交易參考編號", "", "更正註記", "存摺備註"])
    workbook.active.append(["1" * 12, "2025/02/15 09:08:07", "2025/02/15", "2025/02/15", "轉帳",
                            "TWD", 72000, None, 200000 + staff_id, None, account, "synthetic", None, recipient])
    contents = BytesIO()
    workbook.save(contents)

    app = FastAPI()
    app.include_router(router)
    principal = AdminPrincipal(1, "historical-payroll-test", "Synthetic verifier", "system_admin")
    for dependency in (require_admin, require_persisted_admin, require_system_admin):
        app.dependency_overrides[dependency] = lambda: principal
    with TestClient(app, headers={"X-Correlation-ID": f"{case_no}:bank-verification"}) as client:
        ingested = client.post("/api/v1/finance-import/workbooks/ingest",
                               headers={"Idempotency-Key": f"{case_no}:statement"},
                               files={"workbook": ("historical-payroll.xlsx", contents.getvalue())})
        assert ingested.status_code == 200, ingested.text
        batch = ingested.json()["data"]["batch_identity"]
        response = client.post("/api/v1/finance-import/batches/preview", json={"batch_identity": batch})
        assert response.status_code == 200, response.text
        preview = response.json()["data"]
        assert preview["counts"]["ready_dispatch"] == (0 if rematch else 1), [
            (row["classification_type"], row["disposition"], row["pending_reason"], row["evidence"])
            for row in preview["rows"]
        ]
        applied = client.post("/api/v1/finance-import/batches/apply",
                              headers={"Idempotency-Key": f"{case_no.lower()}:statement-apply"},
                              json={"batch_identity": batch, "expected_batch_version": preview["batch_version"],
                                    "preview_fingerprint": preview["preview_fingerprint"], "reason": ""})
        assert applied.status_code == 202, applied.text
        worker = DurableJobWorker(BackgroundJobRepository(connection), connection,
                                  {"finance_import_batch_apply": finance_import_batch_apply_handler},
                                  "historical-payroll-test")
        assert worker.recover_and_run_once()
        job_id = applied.json()["data"]["job_id"]
        response = client.get(f"/api/v1/finance-import/jobs/{job_id}/batch-outcome")
        assert response.status_code == 200, response.text
        outcome = response.json()["data"]
        assert outcome["status"] == "succeeded", outcome
        assert outcome["receipt"]["reconciled_count"] == (0 if rematch else 1), outcome
        if rematch:
            assert synchronize_historical_payroll(connection, case_no)["action"] == "created"
            connection.commit()
            response = client.post("/api/v1/finance-import/pending/reconcile",
                                   headers={"Idempotency-Key": f"{case_no.lower()}:rematch"})
            assert response.status_code == 200, response.text
            assert response.json()["data"]["reconciled_count"] == 1
            repeat = client.post("/api/v1/finance-import/pending/reconcile",
                                 headers={"Idempotency-Key": f"{case_no.lower()}:rematch-again"})
            assert repeat.status_code == 200, repeat.text
            assert repeat.json()["data"] == {"checked_count": 0, "reconciled_count": 0, "existing_count": 0, "pending_count": 0}
    with connection.cursor() as cursor:
        cursor.execute("SELECT p.balance_ntd FROM staff_payable_projections p JOIN staff_obligations o "
                       "ON o.obligation_identity=p.obligation_identity WHERE o.case_no=%s", (case_no,))
        assert cursor.fetchone()["balance_ntd"] == 0

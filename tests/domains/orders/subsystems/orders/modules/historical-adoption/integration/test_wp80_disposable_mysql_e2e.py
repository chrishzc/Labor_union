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


@pytest.mark.parametrize(("pending_evidence", "use_default_rate"), [
    pytest.param(False, False, id="stored-rate"),
    pytest.param(True, False, id="pending-payout-evidence"),
    pytest.param(False, True, id="identity-default-rate"),
])
def test_paid_historical_attribution_splits_days_and_reopens_without_creating_workdays(pending_evidence, use_default_rate):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.admin_auth import require_system_admin
    from api.routes.historical_service_accounting import router
    from api.routes.historical_completion import router as completion_router
    from api.routes.staff_payout import router as staff_router
    from subsystems.access.authentication_session import AdminPrincipal

    token = uuid4().hex
    case_no = f"WP80-{token[:12]}"
    staff_name = f"歷史月嫂-{token[:8]}"
    connection = get_connection()
    try:
        hourly_rate = 320 if use_default_rate else 300
        split_amount = 10 * 8 * hourly_rate
        staff_id = _seed_case(connection, case_no, staff_name, has_case_rate=not use_default_rate)
        workflow = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection), lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
        )
        source = _source_row(case_no, token, staff_name)
        workflow.apply(HistoricalOrderAdoptionRequest(
            source, workflow.preview(source).fingerprint, f"attribution:{token}:adopt",
            "synthetic", "Import historical fixture", token,
        ))
        if use_default_rate:
            # Establish the imported original payable through the existing Payroll writer.
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,"
                    "hourly_rate_ntd,source_identity_status) SELECT id,'approved-rates-v1','non_citizen',%s,'非市民' "
                    "FROM case_staff_assignments WHERE case_no=%s", (hourly_rate, case_no),
                )
            assert synchronize_historical_payroll(connection, case_no)["action"] == "created"
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE r FROM assignment_payroll_rate_snapshots r JOIN case_staff_assignments a "
                    "ON a.id=r.assignment_id WHERE a.case_no=%s", (case_no,),
                )
            connection.commit()
        if pending_evidence:
            from domains.staff_payables.historical_payout import (
                HistoricalStaffConfirmationKind, HistoricalStaffPayoutIntent, HistoricalStaffSourceAvailability,
            )
            from infrastructure.mysql.historical_staff_payout_repository import MySqlHistoricalStaffPayoutRepository
            from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
            from subsystems.staff_payables.historical_payment_settlement import ApplyHistoricalStaffPayout, HistoricalStaffPayoutWorkflow

            with connection.cursor() as cursor:
                cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s", (case_no,))
                identity = cursor.fetchone()["obligation_identity"]
            payment = HistoricalStaffPayoutWorkflow(MySqlHistoricalStaffPayoutRepository(connection), lambda: MySqlUnitOfWork(connection))
            legacy = HistoricalStaffPayoutIntent(case_no, staff_id, HistoricalStaffConfirmationKind.PAID, (identity,),
                date(2025, 2, 15), None, HistoricalStaffSourceAvailability.UNRECOVERABLE, "Synthetic legacy evidence")
            candidate = payment.preview(legacy).candidate
            payment.apply(ApplyHistoricalStaffPayout(legacy, ExpectedVersion(candidate.staff_payables_version),
                candidate.adoption_receipt_id, candidate.fingerprint, IdempotencyKey(f"{token}:legacy"),
                ActorContext("synthetic"), "Confirm historical settlement", CorrelationId(token)))
        else:
            _assert_statement_reconciles(connection, case_no, staff_id, amount=3 * split_amount)
        connection.rollback()
        def original_links():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT l.* FROM staff_payout_obligation_links l JOIN staff_obligations o "
                    "ON o.obligation_identity=l.obligation_identity WHERE o.case_no=%s ORDER BY l.id", (case_no,),
                )
                return cursor.fetchall()
        original = original_links()
        assert len(original) == (0 if pending_evidence else 1)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO staff(name,status) VALUES(%s,'active')", (f"歷史接續-{token[:8]}",))
            second_staff = int(cursor.lastrowid)
            cursor.execute("INSERT IGNORE INTO client_finance_accounts(case_no,aggregate_version) VALUES(%s,0)", (case_no,))
            cursor.execute(
                "INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,"
                "before_amount_ntd,after_amount_ntd,source_event_identity,expected_account_version,idempotency_key,actor,reason) "
                "VALUES(%s,%s,'deposit','receivable_from_client','established',0,0,%s,0,%s,'fixture','Synthetic zero amount settlement')",
                (f"{case_no}:zero", case_no, f"{case_no}:zero-source", f"{case_no}:zero-event"),
            )
            event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,"
                "status,current_event_id,projection_version) VALUES(%s,%s,'deposit','receivable_from_client',0,'settled',%s,1)",
                (f"{case_no}:zero", case_no, event_id),
            )
            cursor.execute("UPDATE client_finance_accounts SET aggregate_version=1 WHERE case_no=%s", (case_no,))
        connection.commit()
        app = FastAPI()
        app.include_router(router)
        app.include_router(completion_router)
        app.include_router(staff_router)
        app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, "synthetic", "Verifier", "system_admin")
        path = f"/api/v1/orders/{case_no}/historical-service-accounting/attribution"
        body = {"caregivers": [{"staff_id": staff_id, "actual_service_days": 20},
                               {"staff_id": second_staff, "actual_service_days": 10}],
                "evidence": "Synthetic service attribution evidence"}
        with TestClient(app, headers={"X-Correlation-ID": token}) as client:
            query = client.get(path.removesuffix("/attribution"))
            assert query.status_code == 200, query.text
            assert query.json()["success"] is True and query.json()["error"] is None
            completion_path = f"/api/v1/orders/{case_no}/historical-completion"
            def close_accounting(key):
                response = client.post(completion_path + "/preview")
                assert response.status_code == 200, response.text
                preview = response.json()["data"]
                payload = {name: preview[name] for name in (
                    "expected_order_version", "expected_client_finance_version",
                    "expected_source_versions", "preview_fingerprint",
                )}
                response = client.post(completion_path + "/apply", json={**payload, "reason": "Verify historical settlement"},
                                       headers={"Idempotency-Key": key})
                assert response.status_code == 200, response.text
                return response.json()["data"]
            first_completion = close_accounting(f"{token}:initial-close")
            if use_default_rate:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) AS count FROM case_payroll_rate_policy_snapshots WHERE case_no=%s",
                        (case_no,),
                    )
                    assert cursor.fetchone()["count"] == 0
                    cursor.execute(
                        "SELECT COUNT(*) AS count FROM assignment_payroll_rate_snapshots r "
                        "JOIN case_staff_assignments a ON a.id=r.assignment_id WHERE a.case_no=%s", (case_no,),
                    )
                    assert cursor.fetchone()["count"] == 0
                connection.rollback()
            response = client.post(path + "/preview", json=body)
            assert response.status_code == 200, response.text
            preview = response.json()["data"]
            assert preview["reopen_accounting"]
            assert sorted(item["entitlement_ntd"] for item in preview["caregivers"]) == [split_amount, 2 * split_amount]
            command = {**body, "reason": "Correct historical service ownership",
                       "preview_fingerprint": preview["preview_fingerprint"]}
            headers = {"Idempotency-Key": f"attribution:{token}:apply"}
            applied = client.post(path + "/apply", json=command, headers=headers)
            assert applied.status_code == 200, applied.text
            replay = client.post(path + "/apply", json=command, headers=headers)
            assert replay.status_code == 200 and replay.json()["data"] == applied.json()["data"], replay.text
            assert client.post(completion_path + "/preview").status_code == 409
            if pending_evidence:
                assert applied.json()["data"]["accounting_pending"] == ["historical_attribution_actual_payout_evidence_missing"]
                connection.rollback()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) AS n FROM staff_obligations WHERE case_no=%s", (case_no,))
                    assert cursor.fetchone()["n"] == 1
                    cursor.execute("SELECT COUNT(*) AS n FROM staff_overpayment_recoveries WHERE staff_id=%s", (staff_id,))
                    assert cursor.fetchone()["n"] == 0
                _assert_statement_reconciles(connection, case_no, staff_id)
                connection.rollback()
                original = original_links()
                assert len(original) == 1
                resumed = client.post(path + "/preview", json=body)
                assert resumed.status_code == 200 and resumed.json()["data"]["accounting_pending"] == [], resumed.text
                command["preview_fingerprint"] = resumed.json()["data"]["preview_fingerprint"]
                headers["Idempotency-Key"] = f"{token}:resume"
                applied = client.post(path + "/apply", json=command, headers=headers)
                assert applied.status_code == 200, applied.text
                replay = client.post(path + "/apply", json=command, headers=headers)
                assert replay.status_code == 200 and replay.json()["data"] == applied.json()["data"], replay.text
        connection.rollback()
        assert original_links() == original
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["status"] == OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value
            cursor.execute("SELECT COUNT(*) AS count FROM staff_schedule WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["count"] == 0
            if use_default_rate:
                cursor.execute(
                    "SELECT i.payroll_policy_kind,i.hourly_rate_ntd FROM historical_service_day_items i "
                    "JOIN historical_service_day_projections p ON p.current_event_id=i.event_id "
                    "WHERE p.case_no=%s", (case_no,),
                )
                assert cursor.fetchall() == [{"payroll_policy_kind": "non_citizen", "hourly_rate_ntd": 320}] * 2
            cursor.execute("SELECT recovery_identity,remaining_amount_ntd FROM staff_overpayment_recoveries WHERE staff_id=%s", (staff_id,))
            recoveries = cursor.fetchall()
            assert len(recoveries) == 1 and recoveries[0]["remaining_amount_ntd"] == split_amount
            cursor.execute("SELECT amount_due_ntd FROM staff_obligations WHERE case_no=%s AND staff_id=%s AND status='open'", (case_no, second_staff))
            assert cursor.fetchall() == [{"amount_due_ntd": split_amount}]
            account = f"8888888888{staff_id:04}"
            cursor.execute(
                "INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,direction,credit,debit,"
                "currency,counterparty_account,resolved_counterparty_account,bank_references,warnings,raw_payload,classification_type) "
                "VALUES(%s,'legacy','2025-02-16','incoming',%s,0,'TWD',%s,%s,'{}','[]','{}','staff_payout_return')",
                (uuid4().hex + uuid4().hex, split_amount, account, account),
            )
            incoming = int(cursor.lastrowid)
        connection.commit()
        _assert_statement_reconciles(connection, case_no, second_staff, amount=split_amount)
        with TestClient(app, headers={"X-Correlation-ID": token}) as client:
            recovery_path = "/api/v1/staff-payables/overpayment-recoveries"
            selection = {"recovery_identity": recoveries[0]["recovery_identity"],
                         "finance_import_row_id": incoming, "evidence_reference": "Synthetic bank evidence"}
            for action in ("matching", "matched"):
                response = client.post(f"{recovery_path}/{action}/preview", json=selection)
                assert response.status_code == 200, response.text
                preview = response.json()["data"]
                response = client.post(f"{recovery_path}/{action}/apply", json={
                    **selection, "preview_fingerprint": preview["preview_fingerprint"],
                    "expected_recovery_version": preview["recovery_version"],
                    "expected_staff_payables_version": preview["staff_payables_version"],
                    "reason": "Verify historical repayment",
                }, headers={"Idempotency-Key": f"{token}:{action}"})
                assert response.status_code == 200, response.text
                if action == "matching":
                    receipt = response.json()["data"]
                    selection.update(matching_identity=receipt["matching_identity"], matching_version=receipt["matching_version"])
            second_completion = close_accounting(f"{token}:final-close")
            assert first_completion["lifecycle_event_id"] != second_completion["lifecycle_event_id"]
        connection.rollback()
        assert original_links()[:1] == original
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["status"] == OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED.value
            cursor.execute(
                "SELECT remaining_amount_ntd FROM staff_overpayment_recoveries WHERE staff_id=%s", (staff_id,),
            )
            assert cursor.fetchall() == [{"remaining_amount_ntd": 0}]
    finally:
        connection.close()


def test_unpaid_historical_attribution_replaces_confirmed_manual_amount_and_splits_funding():
    from infrastructure.mysql.historical_service_accounting_repository import MySqlHistoricalServiceAccountingRepository
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.orders.historical_service_accounting_workflow import HistoricalAttributionIntent, HistoricalServiceAccountingWorkflow

    token = uuid4().hex
    case_no, staff_name = f"WP80-{token[:12]}", f"歷史月嫂-{token[:8]}"
    connection = get_connection()
    try:
        staff_id = _seed_case(connection, case_no, staff_name)
        adoption = HistoricalOrderAdoptionWorkflow(
            MySqlHistoricalOrderAdoptionRepository(connection), lambda: MySqlUnitOfWork(connection),
            MySqlHistoricalAssignmentWriter(connection),
        )
        source = _source_row(case_no, token, staff_name)
        adoption.apply(HistoricalOrderAdoptionRequest(
            source, adoption.preview(source).fingerprint, f"{token}:adopt",
            "synthetic", "Historical case", token,
        ))
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO staff(name,status) VALUES(%s,'active')", (f"歷史接續-{token[:8]}",))
            second = int(cursor.lastrowid)
            cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s", (case_no,))
            root = cursor.fetchone()["obligation_identity"]
            cursor.execute(
                "INSERT INTO payroll_amount_controls(obligation_identity,case_no,amount_mode,computed_ntd,effective_ntd) "
                "VALUES(%s,%s,'manual',72000,69000)", (root, case_no),
            )
            cursor.executemany(
                "INSERT INTO staff_obligation_installments(obligation_identity,funding_kind,amount_ntd,due_date) "
                "VALUES(%s,%s,%s,%s)",
                [(root, "client", 45000, date(2025, 2, 15)), (root, "subsidy", 24000, date(2025, 3, 15))],
            )
        connection.commit()
        workflow = HistoricalServiceAccountingWorkflow(
            MySqlHistoricalServiceAccountingRepository(connection), lambda: MySqlUnitOfWork(connection),
        )
        intent = HistoricalAttributionIntent(case_no, ((staff_id, 20), (second, 10)), "Verified synthetic service counts")
        preview = workflow.preview_attribution(intent)
        assert preview.manual_amounts == ((root, staff_id, 72000, 69000),)
        expected = {(staff_id, "client"): 32000, (staff_id, "subsidy"): 16000,
                    (second, "client"): 16000, (second, "subsidy"): 8000}
        assert {(staff, kind): amount for staff, kind, amount, _, _ in preview.funding} == expected
        command = dict(actor=ActorContext("synthetic"), reason="Adopt recomputed pay",
                       key=IdempotencyKey(f"{token}:split"), correlation=CorrelationId(token))
        with pytest.raises(ValueError, match="historical_attribution_manual_confirmation_required"):
            workflow.apply_attribution(intent, preview.fingerprint, **command)
        receipt = workflow.apply_attribution(intent, preview.fingerprint, **command, adopt_calculated_amounts=True)
        assert workflow.apply_attribution(intent, preview.fingerprint, **command, adopt_calculated_amounts=True) == receipt
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.staff_id,i.funding_kind,i.amount_ntd FROM staff_obligation_installments i "
                "JOIN staff_obligations o ON o.obligation_identity=i.obligation_identity WHERE o.case_no=%s AND o.status='open'",
                (case_no,),
            )
            assert {(row["staff_id"], row["funding_kind"]): row["amount_ntd"] for row in cursor.fetchall()} == expected
            cursor.execute("SELECT effective_ntd FROM payroll_amount_controls WHERE obligation_identity=%s", (root,))
            assert cursor.fetchone()["effective_ntd"] == 69000
    finally:
        connection.close()


def _seed_case(connection, case_no, staff_name, *, has_case_rate=True):
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
        seed_accounting_basis(cursor, case_no, has_case_rate=has_case_rate)
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


def _assert_statement_reconciles(connection, case_no, staff_id, *, rematch=False, amount=72000):
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
                            "TWD", amount, None, 200000 + staff_id, None, account, "synthetic", None, recipient])
    contents = BytesIO()
    workbook.save(contents)

    app = FastAPI()
    app.include_router(router)
    principal = AdminPrincipal(1, "historical-payroll-test", "Synthetic verifier", "system_admin")
    for dependency in (require_admin, require_persisted_admin, require_system_admin):
        app.dependency_overrides[dependency] = lambda: principal
    with TestClient(app, headers={"X-Correlation-ID": f"{case_no}:bank-verification"}) as client:
        ingested = client.post("/api/v1/finance-import/workbooks/ingest",
                               headers={"Idempotency-Key": f"{case_no}:statement:{staff_id}"},
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
                              headers={"Idempotency-Key": f"{case_no.lower()}:statement-apply:{staff_id}"},
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
                       "ON o.obligation_identity=p.obligation_identity WHERE o.case_no=%s AND o.staff_id=%s", (case_no, staff_id))
        assert cursor.fetchone()["balance_ntd"] == 0

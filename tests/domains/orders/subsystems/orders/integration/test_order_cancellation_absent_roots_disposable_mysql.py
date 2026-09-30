"""Real MySQL cancellation/reopen proof without fabricated downstream roots."""
from argparse import Namespace
from datetime import datetime
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymysql
import pytest

from infrastructure.mysql.order_cancellation_repository import MySqlOrderCancellationRepository
from infrastructure.mysql.order_reopen_repository import MySqlOrderReopenRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.cancellation_workflow import OrderCancellationApplyRequest, OrderCancellationWorkflow
from subsystems.orders.reopen_workflow import OrderReopenApplyRequest, OrderReopenWorkflow

DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires an explicitly configured disposable lu_test_* MySQL database")


def test_date_only_unassigned_case_cancels_and_reopens_without_downstream_roots():
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    assert host in {"localhost", "127.0.0.1"}
    assert os.getenv("APP_ENV", "development") == "development"
    database = f"{DATABASE}_cancel_absent"
    arguments = Namespace(host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]), user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], database=database, confirm_database=database)
    bootstrap(arguments)  # The canonical helper refuses an already-existing database.
    connection = pymysql.connect(host=host, port=arguments.port, user=arguments.user, password=arguments.password, database=database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    case_no = "CANCEL-ABSENT-1"
    clock = FixedBusinessClock(datetime(2026, 9, 5, 9, tzinfo=TAIPEI_TIME_ZONE))
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name,identity_status,city,address,service_time,service_type) VALUES (%s,'Synthetic Client','一般市民','新竹市','測試地址','09:00-17:00','連續服務')", (case_no,))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,service_end_time,service_end_day_offset,actual_start_date) VALUES (%s,%s,'洽談中',1,'2026-09-03','2026-09-04',2,8,0,0,'09:00:00','17:00:00',0,'2026-09-03')", (case_no, client_id))
        connection.commit()
        repository = MySqlOrderCancellationRepository(connection)
        workflow = OrderCancellationWorkflow(repository, lambda: MySqlUnitOfWork(connection), clock)
        facts = repository.load_for_preview(case_no, ())
        assert not facts.order.service_started
        preview = workflow.preview(case_no, ())
        request = OrderCancellationApplyRequest(case_no, (), ExpectedVersion(1), None, None, None, preview.fingerprint, IdempotencyKey("cancel-absent-engine"), ActorContext("engine-test"), "客戶確認取消", CorrelationId("cancel-absent-engine"))
        receipt = workflow.apply(request)
        assert receipt.scheduling_version is None and receipt.payroll_version is None
        assert workflow.apply(request) == receipt
        assert repository.find_receipt(request.idempotency_key, for_update=False).receipt == receipt
        assert repository.load_for_preview(case_no, ()).lifecycle.current_status.value == "訂單取消"
        reopen = OrderReopenWorkflow(MySqlOrderReopenRepository(connection), lambda: MySqlUnitOfWork(connection), clock)
        reopen_preview = reopen.preview(case_no)
        reopened = reopen.apply(OrderReopenApplyRequest(case_no, ExpectedVersion(2), None, None, reopen_preview.fingerprint, IdempotencyKey("reopen-absent-engine"), ActorContext("engine-test"), "確認重新受理", CorrelationId("reopen-absent-engine")))
        assert reopened.lifecycle_status.value == "洽談中"
        assert reopened.requires_fresh_scheduling_preview
        with connection.cursor() as cursor:
            for table in ("scheduling_aggregates", "client_finance_accounts", "payroll_case_accounts", "client_obligations", "staff_obligations"):
                cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE case_no=%s", (case_no,))
                assert cursor.fetchone()["total"] == 0
            cursor.execute("SELECT COUNT(*) AS total FROM order_cancellation_events WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["total"] == 1
            cursor.execute("SELECT COUNT(*) AS total FROM orders_domain_outbox WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["total"] == 2
    finally:
        connection.close()


def test_real_http_nullable_versions_refund_partial_roots_and_stale_apply(monkeypatch):
    from api.dependencies.admin_auth import require_system_admin
    from api.routes.order_cancellation import router as cancellation_router
    from api.routes.order_reopen import router as reopen_router
    from api.routes.case_architecture_bootstrap import router as bootstrap_router
    from infrastructure.mysql import mysql_adapter
    from subsystems.access.authentication_session import AdminPrincipal

    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    assert host in {"localhost", "127.0.0.1"} and os.getenv("APP_ENV") == "development"
    database = f"{DATABASE}_cancel_api"
    bootstrap(Namespace(host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]), user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], database=database, confirm_database=database))
    monkeypatch.setitem(mysql_adapter.DB_CONFIG, "database", database)
    app = FastAPI()
    for router in (cancellation_router, reopen_router, bootstrap_router):
        app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(id=None, username="local_bypass", display_name="Synthetic test", role="system_admin")
    connection = mysql_adapter.get_connection()
    cases = ("ENGINE-NO-ROOTS", "ENGINE-SCHEDULING", "ENGINE-PARTIAL", "ENGINE-STALE", "ENGINE-DEPOSIT")
    try:
        with connection.cursor() as cursor:
            for case_no in cases:
                cursor.execute("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic Client','一般市民','連續服務','2026-09-01')", (case_no,))
                cursor.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,requires_cooking,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'洽談中',0,'2026-10-01',5,8,0,0,'09:00:00','17:00:00',0)", (case_no, cursor.lastrowid))
            cursor.execute("INSERT INTO scheduling_aggregates(case_no,aggregate_version,generation_counter) VALUES ('ENGINE-SCHEDULING',0,0)")
            cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES ('ENGINE-PARTIAL',0)")
        connection.commit()
    finally:
        connection.close()

    def post(client, path, body, key):
        response = client.post(path, json=body, headers={"Idempotency-Key": key, "X-Correlation-ID": key})
        assert response.status_code == 200, response.text
        return response.json()["data"]

    def cancel_body(preview):
        return {"confirmed_service_days": [], **{f"expected_{name}_version": preview[f"{name}_version"] for name in ("order", "scheduling", "client_finance", "payroll")}, "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic cancellation"}

    def ensure_roots(client, case_no):
        path = f"/api/v1/cases/{case_no}/architecture-bootstrap"
        intent = {"client_payment_policy_version": "synthetic-client-v1", "client_hourly_rate_ntd": 300, "deposit_service_days": 5, "deposit_due_date": "2026-09-01", "first_payment_due_date": "2026-10-01", "payroll_policy_version": "approved-rates-v1"}
        preview = post(client, path + "/preview", intent, case_no + "-root-preview")
        return post(client, path + "/apply", {**intent, "expected_order_version": preview["order_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic existing roots"}, case_no + "-root")

    with TestClient(app) as client:
        for case_no in cases[:2]:
            path = f"/api/v1/orders/{case_no}"
            queried = client.get(path + "/cancellation")
            assert queried.status_code == 200, queried.text
            assert queried.json()["data"]["client_finance_version"] is None
            preview = post(client, path + "/cancellation/preview", {"confirmed_service_days": []}, case_no + "-preview")
            command = cancel_body(preview)
            receipt = post(client, path + "/cancellation/apply", command, case_no + "-cancel")
            assert receipt["client_finance_version"] is None and receipt["payroll_version"] is None
            assert post(client, path + "/cancellation/apply", command, case_no + "-cancel") == receipt
            observed = client.get(path + "/cancellation/receipt", headers={"Idempotency-Key": case_no + "-cancel"})
            assert observed.status_code == 200 and observed.json()["data"] == receipt
            preview = post(client, path + "/reopen/preview", None, case_no + "-reopen-preview")
            command = {**{f"expected_{name}_version": preview[f"{name}_version"] for name in ("order", "client_finance", "payroll")}, "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic reopen"}
            reopened = post(client, path + "/reopen/apply", command, case_no + "-reopen")
            assert reopened["lifecycle_status"] == "洽談中"
            assert post(client, path + "/reopen/apply", command, case_no + "-reopen") == reopened
        response = client.post("/api/v1/orders/ENGINE-PARTIAL/cancellation/preview", json={"confirmed_service_days": []})
        assert response.status_code == 422, response.text
        path = "/api/v1/orders/ENGINE-STALE"
        preview = post(client, path + "/cancellation/preview", {"confirmed_service_days": []}, "stale-preview")
        ensure_roots(client, "ENGINE-STALE")
        response = client.post(path + "/cancellation/apply", json=cancel_body(preview), headers={"Idempotency-Key": "stale-apply", "X-Correlation-ID": "stale-apply"})
        assert response.status_code == 409, response.text
        connection = mysql_adapter.get_connection()
        try:
            with connection.cursor() as cursor:
                # A paid precontract deposit can legitimately precede Payroll
                # and Scheduling roots. Keep this branch independent of bootstrap.
                cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES ('ENGINE-DEPOSIT',0)")
                cursor.execute("INSERT INTO client_payment_terms_events(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,expected_account_version,source_event_identity,idempotency_key,actor,reason) VALUES ('ENGINE-DEPOSIT','synthetic-client-v1',300,5,'2026-09-01','2026-10-01',0,'synthetic-deposit-terms','synthetic-deposit-terms','engine-test','fixture')")
                terms_event_id = cursor.lastrowid
                cursor.execute("INSERT INTO client_payment_terms(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,current_event_id) VALUES ('ENGINE-DEPOSIT','synthetic-client-v1',300,5,'2026-09-01','2026-10-01',%s)", (terms_event_id,))
                cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES ('ENGINE-DEPOSIT:deposit','ENGINE-DEPOSIT','deposit','receivable_from_client','established',0,12000,NULL,'2026-09-01','synthetic-deposit',0,'synthetic-deposit','engine-test','fixture')")
                event_id = cursor.lastrowid
                cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES ('ENGINE-DEPOSIT:deposit','ENGINE-DEPOSIT','deposit','receivable_from_client',0,'2026-09-01','settled',%s,1)", (event_id,))
                cursor.execute("INSERT INTO client_ledger_entries(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) VALUES ('ENGINE-DEPOSIT','receipt',12000,'2026-09-01','synthetic-paid-deposit','synthetic-paid-deposit','engine-test','fixture')")
                cursor.execute("INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,'ENGINE-DEPOSIT:deposit',12000,1)", (cursor.lastrowid,))
            connection.commit()
        finally:
            connection.close()
        path = "/api/v1/orders/ENGINE-DEPOSIT/cancellation"
        preview = post(client, path + "/preview", {"confirmed_service_days": []}, "deposit-preview")
        assert any(item["direction"] == "refund_due" and item["direction_amount_ntd"] == 12000 for item in preview["client_finance_impact"]["actions"])
        command = cancel_body(preview)
        receipt = post(client, path + "/apply", command, "deposit-cancel")
        assert receipt["client_finance_version"] is not None and receipt["payroll_version"] is None
        assert receipt["scheduling_version"] is None
        assert post(client, path + "/apply", command, "deposit-cancel") == receipt
        observed = client.get(path + "/receipt", headers={"Idempotency-Key": "deposit-cancel"})
        assert observed.status_code == 200 and observed.json()["data"] == receipt
        # An unpaid refund obligation is not a completed refund transaction.
        reopen_path = "/api/v1/orders/ENGINE-DEPOSIT/reopen"
        preview = post(client, reopen_path + "/preview", None, "deposit-reopen-preview")
        assert preview["client_finance_version"] is not None and preview["payroll_version"] is None
        command = {**{f"expected_{name}_version": preview[f"{name}_version"] for name in ("order", "client_finance", "payroll")}, "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic reopen before refund payment"}
        reopened = post(client, reopen_path + "/apply", command, "deposit-reopen")
        assert reopened["lifecycle_status"] == "洽談中"
        assert post(client, reopen_path + "/apply", command, "deposit-reopen") == reopened

    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM order_cancellation_events WHERE case_no IN ('ENGINE-PARTIAL','ENGINE-STALE')")
            assert cursor.fetchone()["n"] == 0
            cursor.execute("SELECT COUNT(*) AS n FROM application_command_claims WHERE idempotency_key='stale-apply'")
            assert cursor.fetchone()["n"] == 0
            cursor.execute("SELECT COUNT(*) AS n FROM client_obligations WHERE case_no='ENGINE-DEPOSIT' AND direction='payable_to_client' AND amount_due_ntd=12000")
            assert cursor.fetchone()["n"] == 1
            for table in ("scheduling_aggregates", "payroll_case_accounts", "staff_obligations"):
                cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE case_no='ENGINE-DEPOSIT'")
                assert cursor.fetchone()["n"] == 0
            for table in ("client_finance_accounts", "payroll_case_accounts", "staff_obligations"):
                cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE case_no IN ('ENGINE-NO-ROOTS','ENGINE-SCHEDULING')")
                assert cursor.fetchone()["n"] == 0
    finally:
        connection.close()

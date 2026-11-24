"""Real MySQL cancellation/reopen proof without fabricated downstream roots."""
from argparse import Namespace
from contextlib import closing
from datetime import datetime
import json
import os
import re
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymysql
import pytest

from infrastructure.mysql.order_cancellation_repository import MySqlOrderCancellationRepository
from infrastructure.mysql.order_reopen_repository import MySqlOrderReopenRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from scripts.check_runtime_database import ReadOnlyRuntimeConfig
from scripts.migrate_preserved_database_additive_schema import ROOT, local_additive_target_state
from shared_kernel.migration_release import load_migration_release_manifest
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.cancellation_workflow import OrderCancellationApplyRequest, OrderCancellationWorkflow
from subsystems.orders.reopen_workflow import OrderReopenApplyRequest, OrderReopenWorkflow

DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires an explicitly configured disposable lu_test_* MySQL database")


def _assert_established_unserved_schema(arguments):
    release = load_migration_release_manifest(
        ROOT / 'db/migration_releases/labor_union_2026_11_23_order_established_unserved_v1.json', ROOT,
    )
    artifact = '1081_order_established_unserved_status.sql'
    settings = {key: getattr(arguments, key) for key in ('host', 'port', 'user', 'password', 'database')}
    state = local_additive_target_state(
        ReadOnlyRuntimeConfig(settings), arguments.database, artifact,
        release.owned_object_descriptors(ROOT)[artifact],
    )
    assert state['state'] == 'exact', 'The real feature schema must match the strict 1081 descriptor.'


@pytest.mark.parametrize('reopen_reason', ['確認重新受理', ''])
@pytest.mark.parametrize('established', [False, True])
def test_date_only_unassigned_case_cancels_and_reopens_without_downstream_roots(reopen_reason, established):
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    assert host in {"localhost", "127.0.0.1"}
    assert os.getenv("APP_ENV", "development") == "development"
    database = f"{DATABASE}_cancel_absent_{'e' if established else 'd'}_{'empty' if not reopen_reason else 'note'}"
    arguments = Namespace(host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]), user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], database=database, confirm_database=database)
    bootstrap(arguments)  # The canonical helper refuses an already-existing database.
    connection = pymysql.connect(host=host, port=arguments.port, user=arguments.user, password=arguments.password, database=database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    case_no = "CANCEL-ABSENT-1"
    clock = FixedBusinessClock(datetime(2026, 9, 5, 9, tzinfo=TAIPEI_TIME_ZONE))
    try:
        _assert_established_unserved_schema(arguments)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name,identity_status,city,address,service_time,service_type) VALUES (%s,'Synthetic Client','一般市民','新竹市','測試地址','09:00-17:00','連續服務')", (case_no,))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,service_end_time,service_end_day_offset,actual_start_date) VALUES (%s,%s,'洽談中',1,'2026-09-03','2026-09-04',2,8,0,0,'09:00:00','17:00:00',0,'2026-09-03')", (case_no, client_id))
            if established:
                cursor.execute("UPDATE orders SET status='訂單成立' WHERE case_no=%s", (case_no,))
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
        expected_status = "成立後未服務" if established else "訂單取消"
        assert repository.load_for_preview(case_no, ()).lifecycle.current_status.value == expected_status
        assert receipt.lifecycle_status.value == expected_status
        if established:
            with connection.cursor() as cursor:
                cursor.execute("SELECT lifecycle_status FROM order_cancellation_apply_receipts WHERE case_no=%s", (case_no,))
                assert cursor.fetchone()["lifecycle_status"] == expected_status
                cursor.execute("SELECT after_status FROM order_lifecycle_state_events WHERE case_no=%s ORDER BY id DESC LIMIT 1", (case_no,))
                assert cursor.fetchone()["after_status"] == expected_status
                for table in ("client_obligations", "staff_obligations"):
                    cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE case_no=%s", (case_no,))
                    assert cursor.fetchone()["total"] == 0
            return
        reopen = OrderReopenWorkflow(MySqlOrderReopenRepository(connection), lambda: MySqlUnitOfWork(connection), clock)
        reopen_preview = reopen.preview(case_no)
        reopened = reopen.apply(OrderReopenApplyRequest(case_no, ExpectedVersion(2), None, None, reopen_preview.fingerprint, IdempotencyKey("reopen-absent-engine"), ActorContext("engine-test"), reopen_reason, CorrelationId("reopen-absent-engine")))
        assert reopened.lifecycle_status.value == "洽談中"
        assert reopened.requires_fresh_scheduling_preview
        with connection.cursor() as cursor:
            cursor.execute('SELECT reason FROM order_reopen_events WHERE case_no=%s', (case_no,))
            assert cursor.fetchone()['reason'] == reopen_reason
            cursor.execute("SELECT reason FROM order_lifecycle_control_events WHERE case_no=%s AND action='clear'", (case_no,))
            assert cursor.fetchone()['reason'] == (reopen_reason or '系統記錄受控重開訂單')
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
    arguments = Namespace(host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]), user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], database=database, confirm_database=database)
    bootstrap(arguments)
    _assert_established_unserved_schema(arguments)
    monkeypatch.setitem(mysql_adapter.DB_CONFIG, "database", database)
    app = FastAPI()
    for router in (cancellation_router, reopen_router, bootstrap_router):
        app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(id=1, username="admin_tester", display_name="Synthetic test", role="system_admin")
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


def _seed_prior_cancellation(cursor, case_no, refund_identity, cash_entry_id, staff_id):
    prior_key = "synthetic-prior-cancellation"
    fingerprint = "a" * 64
    confirmed_days = json.dumps([{"service_date": "2026-09-03", "staff_id": staff_id, "reason": None}])
    cursor.execute(
        "INSERT INTO order_cancellation_events "
        "(case_no,cancellation_date,actual_end_date,official_service_day_count,official_service_hours,"
        "confirmed_service_days,expected_order_version,resulting_order_version,preview_fingerprint,"
        "idempotency_key,actor,reason,correlation_id) "
        "VALUES (%s,'2026-09-04','2026-09-03',1,8,%s,0,1,%s,%s,'engine-test','Imported cancellation',%s)",
        (case_no, confirmed_days, fingerprint, prior_key, prior_key),
    )
    cancellation_event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO order_lifecycle_control_events "
        "(case_no,control_type,control_key,scope,action,actor,reason,expected_version,"
        "idempotency_key,payload_hash,payload_snapshot) "
        "VALUES (%s,'cancellation','order_cancelled','order','activate','engine-test',"
        "'Imported cancellation',0,%s,SHA2('{}',256),JSON_OBJECT())",
        (case_no, prior_key),
    )
    control_event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO order_lifecycle_control_state "
        "(case_no,control_type,control_key,scope,state,current_event_id,reason,changed_by) "
        "VALUES (%s,'cancellation','order_cancelled','order','active',%s,'Imported cancellation','engine-test')",
        (case_no, control_event_id),
    )
    cursor.execute(
        "INSERT INTO order_lifecycle_state_events "
        "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,"
        "idempotency_key,facts_snapshot) VALUES (%s,'order_cancellation_applied','歷史訂單－服務完成',"
        "'訂單取消','engine-test','2026-09-04',0,%s,JSON_OBJECT('official_service_day_count',1))",
        (case_no, prior_key),
    )
    prior_receipt = {
        "case_no": case_no,
        "order_version": 1,
        "scheduling_version": None,
        "scheduling_generation": None,
        "client_finance_version": 1,
        "payroll_version": None,
        "lifecycle_status": "訂單取消",
        "actual_end_date": "2026-09-03",
        "official_service_day_count": 1,
        "official_service_hours": 8,
        "cancelled_assignment_ids": [],
        "created_assignment_keys": [],
        "preview_fingerprint": fingerprint,
    }
    cursor.execute(
        "INSERT INTO order_cancellation_apply_receipts "
        "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,cancellation_event_id,"
        "cancellation_control_event_id,lifecycle_event_id,order_version,client_finance_version,"
        "lifecycle_status,actual_end_date,official_service_day_count,official_service_hours,correlation_id,result_snapshot) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,1,1,'訂單取消','2026-09-03',1,8,%s,%s)",
        (
            prior_key, fingerprint, fingerprint, case_no, cancellation_event_id, control_event_id,
            cursor.lastrowid, prior_key, json.dumps(prior_receipt),
        ),
    )
    settlement = {
        "cancellation_event_id": cancellation_event_id,
        "cash_entry_id": cash_entry_id,
        "obligation_identity": refund_identity,
        "service_due_ntd": 5000,
        "fee_ntd": 1500,
        "fee_reason": "原取消違約金",
        "net_received_ntd": 16000,
        "refund_due_ntd": 9500,
        "additional_charge_due_ntd": 0,
        "fee_received_ntd": 1500,
        "processed_on": "2026-09-04",
    }
    cursor.execute(
        "INSERT INTO client_finance_apply_receipts "
        "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,resulting_account_version,result_snapshot) "
        "VALUES ('synthetic-prior-finance',%s,%s,%s,1,%s)",
        (fingerprint, fingerprint, case_no, json.dumps({"cancellation_settlement": settlement})),
    )
    return cancellation_event_id, cursor.lastrowid


def _seed_partial_refund_case(cursor, case_no, refund_identity):
    cursor.execute(
        "INSERT INTO clients (case_no,name,identity_status,service_type) "
        "VALUES (%s,'Synthetic Client','一般市民','連續服務')",
        (case_no,),
    )
    cursor.execute(
        "INSERT INTO orders (case_no,client_id,status,lifecycle_version,start_date,end_date,"
        "service_days,service_hours_per_day,floor_fee,requires_cooking,service_start_time,service_end_time,"
        "service_end_day_offset,actual_start_date,actual_end_date) VALUES "
        "(%s,%s,'訂單取消',1,'2026-09-03','2026-09-04',2,8,0,0,'09:00:00','17:00:00',0,'2026-09-03','2026-09-03')",
        (case_no, cursor.lastrowid),
    )
    cursor.execute("INSERT INTO staff (name) VALUES ('Synthetic caregiver')")
    staff_id = cursor.lastrowid
    cursor.execute("INSERT INTO client_finance_accounts (case_no,aggregate_version) VALUES (%s,2)", (case_no,))
    cursor.execute(
        "INSERT INTO client_payment_terms_events "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,'synthetic-v1',625,0,'2026-09-01','2026-09-02',0,'prior-terms','prior-terms','engine-test','Imported terms')",
        (case_no,),
    )
    cursor.execute(
        "INSERT INTO client_payment_terms (case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,current_event_id) "
        "VALUES (%s,'synthetic-v1',625,0,'2026-09-01','2026-09-02',%s)",
        (case_no, cursor.lastrowid),
    )
    receivable_identity = f"{case_no}:first"
    cursor.execute(
        "INSERT INTO client_obligation_events "
        "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,"
        "after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) "
        "VALUES (%s,%s,'first','receivable_from_client','established',0,16000,'2026-09-02',"
        "'prior-payment',0,'prior-receivable','engine-test','Imported receivable')",
        (receivable_identity, case_no),
    )
    cursor.execute(
        "INSERT INTO client_obligations (obligation_identity,case_no,obligation_type,direction,amount_due_ntd,"
        "due_date,status,current_event_id,projection_version) "
        "VALUES (%s,%s,'first','receivable_from_client',0,'2026-09-02','settled',%s,1)",
        (receivable_identity, case_no, cursor.lastrowid),
    )
    cursor.execute(
        "INSERT INTO client_ledger_entries "
        "(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) "
        "VALUES (%s,'receipt',16000,'2026-09-02','prior-receipt','prior-receipt','engine-test','Imported receipt')",
        (case_no,),
    )
    cash_entry_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_ledger_obligation_allocations "
        "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,16000,1)",
        (cash_entry_id, receivable_identity),
    )
    prior_event_id, prior_finance_receipt_id = _seed_prior_cancellation(
        cursor, case_no, refund_identity, cash_entry_id, staff_id,
    )
    cursor.execute(
        "INSERT INTO client_obligation_events "
        "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,"
        "after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) "
        "VALUES (%s,%s,'refund','payable_to_client','adjusted',0,9500,'2026-09-02',%s,%s,0,"
        "'prior-refund-obligation','engine-test','Imported cancellation balance')",
        (refund_identity, case_no, f"orders_cancellation:{prior_event_id}:1", receivable_identity),
    )
    cursor.execute(
        "INSERT INTO client_obligations (obligation_identity,case_no,obligation_type,direction,source_obligation_identity,"
        "amount_due_ntd,due_date,status,current_event_id,projection_version) "
        "VALUES (%s,%s,'refund','payable_to_client',%s,5500,'2026-09-02','open',%s,2)",
        (refund_identity, case_no, receivable_identity, cursor.lastrowid),
    )
    cursor.execute(
        "INSERT INTO client_ledger_entries "
        "(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) "
        "VALUES (%s,'refund',4000,'2026-09-05','prior-refund','prior-refund','engine-test','Imported partial refund')",
        (case_no,),
    )
    refund_entry_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_ledger_obligation_allocations "
        "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,4000,1)",
        (refund_entry_id, refund_identity),
    )
    cursor.execute(
        "INSERT INTO finance_case_accounting_markers "
        "(case_no,reason,actor,source_versions,accounting_snapshot,operation_key) "
        "VALUES (%s,'Imported accounting marker','engine-test',"
        "JSON_OBJECT('client_finance_version',2),JSON_OBJECT('status','needs_review'),'prior-marker')",
        (case_no,),
    )
    return prior_event_id, prior_finance_receipt_id, refund_entry_id


def _apply_partial_refund_return(connection, case_no, refund_entry_id):
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType
    from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalApplyRequest,
        ClientRefundReversalSelection,
        ClientRefundReversalWorkflow,
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO finance_import_rows "
            "(dedup_fingerprint,format_id,transaction_date,credit,direction,currency,bank_references,warnings,"
            "raw_payload,classification_type) VALUES "
            "(%s,'legacy','2026-09-06',4000,'incoming','TWD',JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),'client_refund_return')",
            ("b" * 64,),
        )
        bank_row_id = cursor.lastrowid
    connection.commit()

    repository = MySqlClientRefundReversalRepository(connection)
    workflow = ClientRefundReversalWorkflow(repository, lambda: MySqlUnitOfWork(connection))
    selection = ClientRefundReversalSelection(
        case_no, ClientFinanceCorrectionType.REFUND_RETURN,
        bank_fact_identities=(str(bank_row_id),), reversal_target_identities=(str(refund_entry_id),),
    )
    correlation = CorrelationId("synthetic-refund-return")
    preview = workflow.preview(selection, correlation)
    request = ClientRefundReversalApplyRequest(
        selection, ExpectedVersion(preview.account_version), preview.fingerprint,
        IdempotencyKey("synthetic-refund-return"), ActorContext("engine-test"), "Synthetic bank return", correlation,
    )
    repository.bind_apply_request(request)
    try:
        receipt = workflow.apply(request)
    finally:
        repository.clear_apply_request()
    assert receipt.ledger_entry_count == receipt.allocation_count == 1


def _refund_cash_history(connection, case_no, refund_identity):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,entry_type,amount_ntd,reversal_of_entry_id,finance_import_row_id "
            "FROM client_ledger_entries WHERE case_no=%s ORDER BY id",
            (case_no,),
        )
        ledger = cursor.fetchall()
        cursor.execute(
            "SELECT id,ledger_entry_id,amount_ntd,allocation_ordinal FROM client_ledger_obligation_allocations "
            "WHERE obligation_identity=%s ORDER BY id",
            (refund_identity,),
        )
        return ledger, cursor.fetchall()


@pytest.mark.parametrize(
    "refund_returned,expected_cash,prior_remaining,expected_remaining,net_refunded",
    [(False, 12000, 5500, 10500, 4000), (True, 16000, 9500, 14500, 0)],
    ids=["partial-refund", "partial-refund-returned"],
)
def test_manual_zero_service_corrects_only_difference_on_prior_refund(
    refund_returned, expected_cash, prior_remaining, expected_remaining, net_refunded,
):
    from api.dependencies.admin_auth import require_system_admin
    from api.dependencies.order_cancellation import OrderCancellationApplication, get_order_cancellation_application
    from api.routes.order_cancellation import router as cancellation_router
    from domains.orders.historical_unserved_correction import HistoricalUnservedCorrectionIntent
    from infrastructure.mysql.client_payments_query_repository import query_cancellation_accounting

    assert os.environ["APP_ENV"] == "development"
    assert re.fullmatch(r"lu_test_[a-z0-9_]+", DATABASE)
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    assert host in {"localhost", "127.0.0.1"}
    connection_settings = {
        "host": host, "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"], "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
    }
    database = f"{DATABASE}_op_{uuid4().hex[:12]}"
    assert len(database) <= 64
    arguments = Namespace(**connection_settings, database=database, confirm_database=database)
    bootstrap(arguments)
    try:
        _assert_established_unserved_schema(arguments)
        case_no = "MANUAL-ZERO-REFUND"
        refund_identity = f"{case_no}:prior-refund"
        clock = FixedBusinessClock(datetime(2026, 9, 7, 9, tzinfo=TAIPEI_TIME_ZONE))

        def connect():
            return pymysql.connect(
                **connection_settings, database=database, charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor, autocommit=False,
            )

        def query_application():
            with closing(connect()) as connection:
                repository = MySqlOrderCancellationRepository(connection)
                workflow = OrderCancellationWorkflow(repository, lambda: MySqlUnitOfWork(connection), clock)
                yield OrderCancellationApplication(repository, workflow)

        app = FastAPI()
        app.include_router(cancellation_router)
        app.dependency_overrides[require_system_admin] = lambda: None
        app.dependency_overrides[get_order_cancellation_application] = query_application

        with closing(connect()) as connection:
            with connection.cursor() as cursor:
                prior_event_id, prior_finance_receipt_id, refund_entry_id = _seed_partial_refund_case(
                    cursor, case_no, refund_identity,
                )
            connection.commit()
            if refund_returned:
                _apply_partial_refund_return(connection, case_no, refund_entry_id)
            cash_history = _refund_cash_history(connection, case_no, refund_identity)
            ledger, allocations = cash_history
            assert [(entry["entry_type"], entry["amount_ntd"], entry["reversal_of_entry_id"]) for entry in ledger] == (
                [("receipt", 16000, None), ("refund", 4000, None)]
                + ([("refund_reversal", 4000, refund_entry_id)] if refund_returned else [])
            )
            assert ledger[1]["id"] == refund_entry_id
            assert [(row["ledger_entry_id"], row["amount_ntd"]) for row in allocations] == [
                (row["id"], 4000) for row in ledger[1:]
            ]

            repository = MySqlOrderCancellationRepository(connection)
            workflow = OrderCancellationWorkflow(repository, lambda: MySqlUnitOfWork(connection), clock)
            facts = repository.load_for_preview(case_no, ())
            prior = facts.historical_unserved_evidence.prior_settlement
            assert (prior.cancellation_event_id, prior.finance_receipt_id) == (prior_event_id, prior_finance_receipt_id)
            assert prior.official_service_day_count == 1
            assert prior.client_balance.obligation_identity == refund_identity
            assert prior.client_balance.contracted_amount.amount == 9500
            assert prior.client_balance.remaining_amount.amount == prior_remaining
            assert facts.net_cash_received.amount == expected_cash

            intent = HistoricalUnservedCorrectionIntent("人工確認零服務", "測試通話紀錄")
            preview = workflow.preview(case_no, (), historical_correction=intent)
            finance = preview.client_finance_impact
            settlement = finance.cancellation_settlement
            assert (settlement.net_received_ntd, settlement.fee_ntd, settlement.service_due_ntd) == (expected_cash, 1500, 0)
            assert settlement.refund_due_ntd == expected_remaining
            assert [(action.obligation_identity, action.direction.value, action.direction_amount_ntd) for action in finance.actions] == [
                (refund_identity, "refund_due", 5000)
            ]
            request = OrderCancellationApplyRequest(
                case_no, (), ExpectedVersion(preview.order_version), None, ExpectedVersion(preview.client_finance_version),
                None, preview.fingerprint, IdempotencyKey("manual-zero-refund"), ActorContext("engine-test"),
                intent.reason, CorrelationId("manual-zero-refund"), historical_correction=intent,
            )
            receipt = workflow.apply(request)
            assert workflow.apply(request) == receipt
            assert repository.find_receipt(request.idempotency_key, for_update=False).receipt == receipt
            assert receipt.lifecycle_status.value == "成立後未服務"
            assert receipt.official_service_day_count == receipt.official_service_hours == 0
            assert receipt.actual_end_date is None

            assert _refund_cash_history(connection, case_no, refund_identity) == cash_history
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT o.obligation_identity,o.amount_due_ntd,e.before_amount_ntd,e.after_amount_ntd "
                    "FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id "
                    "WHERE o.case_no=%s AND o.direction='payable_to_client'",
                    (case_no,),
                )
                assert tuple(cursor.fetchall()) == ({
                    "obligation_identity": refund_identity, "amount_due_ntd": expected_remaining,
                    "before_amount_ntd": 9500, "after_amount_ntd": 14500,
                },)
                cursor.execute(
                    "SELECT id FROM client_finance_apply_receipts WHERE case_no=%s ORDER BY id",
                    (case_no,),
                )
                finance_receipts = cursor.fetchall()
                assert len(finance_receipts) == 2 and finance_receipts[0]["id"] == prior_finance_receipt_id
                cursor.execute("SELECT id FROM order_cancellation_events WHERE case_no=%s ORDER BY id", (case_no,))
                events = cursor.fetchall()
                assert len(events) == 2 and events[0]["id"] == prior_event_id
            accounting = query_cancellation_accounting(connection, case_no)
            assert accounting.obligation_identity == refund_identity
            assert accounting.bank_refunded_ntd == net_refunded
            assert accounting.refund_due_ntd == expected_remaining

        with TestClient(app) as client:
            response = client.get(f"/api/v1/orders/{case_no}/cancellation")
            assert response.status_code == 200, response.text
            query = response.json()["data"]
            assert query["lifecycle_status"] == "成立後未服務"
            assert query["actual_start_date"] is None and query["confirmed_service_days"] == []
            evidence = query["historical_unserved_correction"]
            assert "historical_unserved_cash_evidence_requires_review" in evidence["review_codes"]
            assert evidence["net_cash_received_ntd"] == expected_cash
    finally:
        assert database == arguments.database == arguments.confirm_database
        assert re.fullmatch(r"lu_test_[a-z0-9_]+", database)
        with closing(pymysql.connect(**connection_settings, autocommit=True)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{database}`")

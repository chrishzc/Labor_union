"""Cooking reconciliation keeps historical obligations and service facts intact."""

import os
from uuid import uuid4

import pymysql
import pytest

from infrastructure.mysql.hcm_beclass_reconciliation_adapter import MySqlHcmBeClassReconciliationAdapter
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from subsystems.orders.terms_workflow import TermsWorkflowError


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires an explicit disposable lu_test_* MySQL database")


@pytest.fixture
def case_connection():
    assert DATABASE.startswith("lu_test_")
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    assert host in {"localhost", "127.0.0.1", "::1"}
    connection = pymysql.connect(
        host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    case_no = f"COOK-{uuid4().hex[:20]}"
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'cooking fixture')", (case_no,))
            client_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,"
                "actual_start_date,actual_end_date,service_days,service_hours_per_day,floor_fee,requires_cooking) "
                "VALUES (%s,%s,'歷史訂單－服務完成',3,'2026-09-01','2026-09-05',"
                "'2026-09-01','2026-09-05',5,8,1234,NULL)", (case_no, client_id),
            )
            cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,6)", (case_no,))
            cursor.execute("INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES (%s,7)", (case_no,))
            cursor.execute(
                "INSERT INTO client_payment_terms_events(case_no,policy_version,client_hourly_rate_ntd,"
                "deposit_service_days,deposit_due_date,first_payment_due_date,expected_account_version,"
                "source_event_identity,idempotency_key,actor,reason) "
                "VALUES (%s,'cooking-test',300,1,'2026-08-01','2026-09-01',0,%s,%s,'fixture','fixture')",
                (case_no, f"{case_no}:payment", f"{case_no}:payment"),
            )
            terms_event = cursor.lastrowid
            cursor.execute(
                "INSERT INTO client_payment_terms(case_no,policy_version,client_hourly_rate_ntd,"
                "deposit_service_days,deposit_due_date,first_payment_due_date,current_event_id) "
                "VALUES (%s,'cooking-test',300,1,'2026-08-01','2026-09-01',%s)", (case_no, terms_event),
            )
            cursor.execute(
                "INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,"
                "event_type,before_amount_ntd,after_amount_ntd,source_event_identity,expected_account_version,"
                "idempotency_key,actor,reason) VALUES (%s,%s,'adjustment','receivable_from_client',"
                "'established',0,200,%s,5,%s,'fixture','fixture')",
                (f"{case_no}:obligation", case_no, f"{case_no}:obligation", f"{case_no}:obligation"),
            )
            event_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,"
                "amount_due_ntd,status,current_event_id,projection_version) "
                "VALUES (%s,%s,'adjustment','receivable_from_client',200,'open',%s,1)",
                (f"{case_no}:obligation", case_no, event_id),
            )
        yield connection, case_no
    finally:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() is None
        connection.rollback()
        connection.close()


def _snapshot(connection, case_no):
    result = {}
    with connection.cursor() as cursor:
        for table in ("orders", "client_finance_accounts", "client_payment_terms", "client_obligations",
                      "client_obligation_events", "payroll_case_accounts", "scheduling_aggregates",
                      "order_terms_change_events", "order_terms_apply_receipts",
                      "order_lifecycle_state_events", "order_service_data_locks"):
            cursor.execute(f"SELECT * FROM {table} WHERE case_no=%s", (case_no,))
            result[table] = tuple(cursor.fetchall())
    return result


@pytest.mark.parametrize("requires_cooking", [True, False])
@pytest.mark.parametrize("locked", [False, True])
def test_historical_cooking_correction_preserves_existing_accounting(case_connection, requires_cooking, locked):
    connection, case_no = case_connection
    if locked:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events(case_no,trigger_event,before_status,after_status,"
                "actor,business_date,expected_version,idempotency_key,facts_snapshot) "
                "VALUES (%s,'auto_complete','服務中','訂單完成','fixture','2026-09-06',2,%s,'{}')",
                (case_no, f"{case_no}:completion"),
            )
            event_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO order_service_data_locks(case_no,lifecycle_event_id,client_settlement_fingerprint,"
                "created_by) VALUES (%s,%s,%s,'fixture')", (case_no, event_id, "a" * 64),
            )
    before = _snapshot(connection, case_no)
    with pytest.raises(ValueError, match="preassignment_client_finance_obligation_conflict"):
        MySqlOrderTermsRepository(connection).load_for_preview(case_no)

    adapter = MySqlHcmBeClassReconciliationAdapter(connection)
    if locked:
        with pytest.raises(TermsWorkflowError) as captured:
            adapter.apply_cooking_terms(case_no, 1, requires_cooking)
        assert captured.value.error.code == "service_data_locked"
        assert _snapshot(connection, case_no) == before
    else:
        adapter.apply_cooking_terms(case_no, 1, requires_cooking)
        after = _snapshot(connection, case_no)
        order = after["orders"][0]
        assert bool(order["requires_cooking"]) is requires_cooking
        assert order["lifecycle_version"] == 4
        for field in ("start_date", "end_date", "actual_start_date", "actual_end_date", "service_days",
                      "service_hours_per_day", "floor_fee", "service_start_time", "service_end_time",
                      "service_end_day_offset", "status"):
            assert order[field] == before["orders"][0][field]
        assert {k: v for k, v in after.items() if k != "orders"} == {k: v for k, v in before.items() if k != "orders"}
        adapter.apply_cooking_terms(case_no, 1, requires_cooking)
        assert _snapshot(connection, case_no) == after

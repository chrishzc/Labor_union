"""G05 isolated MySQL proof for Orders completion versus lifecycle concurrency."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires an explicitly configured disposable lu_test_* MySQL database")


def _arguments():
    return Namespace(host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"], port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]), user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], database=DATABASE, confirm_database=DATABASE)


def test_g05_auto_completion_commits_orders_only_and_stales_prior_leave_version():
    bootstrap(_arguments())
    _seed_case()
    workflow, connection = _workflow()
    request = _request(expected_version=0, key="g05-auto-first")
    try:
        receipt = workflow.apply(request)
        assert workflow.apply(request) == receipt
    finally:
        connection.close()
    assert receipt.order_version == 1
    assert _counts() == {"receipt": 1, "lifecycle": 1, "orders_outbox": 1, "scheduling": 1, "finance": 0, "payroll": 0}
    assert _stale_lifecycle_envelope_rejects_expected_version(0)


def test_g05_prior_leave_lifecycle_change_stales_auto_completion_without_writes():
    bootstrap(_arguments())
    _seed_case()
    _apply_prior_leave_lifecycle_change()
    workflow, connection = _workflow()
    before = _counts()
    from subsystems.orders.auto_completion_workflow import AutoCompletionWorkflowError
    try:
        with pytest.raises(AutoCompletionWorkflowError) as error:
            workflow.apply(_request(expected_version=0, key="g05-leave-first"))
    finally:
        connection.close()
    assert error.value.error.code == "order_version_conflict"
    assert _counts() == before


def _workflow():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_auto_completion_repository import MySqlOrderAutoCompletionRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.auto_completion_workflow import AutoCompleteOrderService
    connection = get_connection()
    return AutoCompleteOrderService(MySqlOrderAutoCompletionRepository(connection), lambda: MySqlUnitOfWork(connection)), connection


def _request(*, expected_version, key):
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.orders.auto_completion_workflow import AutoCompletionApplyRequest
    return AutoCompletionApplyRequest("G05-CASE", ExpectedVersion(expected_version), datetime.fromisoformat("2026-08-04T17:00:00+08:00"), IdempotencyKey(key), ActorContext("g05-e2e"), "service completion clock reached", CorrelationId(key))


def _seed_case():
    from infrastructure.mysql.mysql_adapter import get_connection
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('G05-CASE','G05 Client')")
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff(name,status) VALUES ('G05 Staff','active')")
            cursor.execute("INSERT INTO orders (case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset,actual_start_date,actual_end_date,staff_payment_due_date) VALUES ('G05-CASE',%s,'服務中',0,'2026-08-01',1,8,0,'09:00:00','17:00:00',0,'2026-08-01','2026-08-04','2026-08-15')", (client_id,))
            cursor.execute("INSERT INTO scheduling_generations (case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) VALUES ('G05-CASE',1,1,'effective',1,'g05-e2e','fixture')")
            generation_id = cursor.lastrowid
            cursor.execute("INSERT INTO scheduling_aggregates (case_no,aggregate_version,generation_counter,effective_generation_id) VALUES ('G05-CASE',1,1,%s)", (generation_id,))
            cursor.execute("INSERT INTO case_staff_assignments (case_no,generation_id,candidate_key,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,floor_fee_allocated,status) VALUES ('G05-CASE',%s,'g05:a1',1,1,'2026-08-04','2026-08-04',0,'planned')", (generation_id,))
        connection.commit()
    finally:
        connection.close()


def _apply_prior_leave_lifecycle_change():
    from infrastructure.mysql.mysql_adapter import get_connection
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO order_lifecycle_state_events (case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) VALUES ('G05-CASE','schedule_applied','服務中','服務中','g05-leave','2026-08-04',0,'g05-prior-leave',JSON_OBJECT('source','leave_substitution'))")
            cursor.execute("UPDATE orders SET lifecycle_version=1 WHERE case_no='G05-CASE' AND lifecycle_version=0")
        connection.commit()
    finally:
        connection.close()


def _stale_lifecycle_envelope_rejects_expected_version(version):
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.orders.order_lifecycle_command_envelope import lock_order_lifecycle_command_envelope
    connection = get_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            with pytest.raises(ValueError):
                lock_order_lifecycle_command_envelope(cursor, "G05-CASE", version, "g05-stale-leave-apply")
        connection.rollback()
        return True
    finally:
        connection.close()


def _counts():
    from infrastructure.mysql.mysql_adapter import get_connection
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            return {"receipt": _count(cursor, "order_auto_completion_apply_receipts"), "lifecycle": _count(cursor, "order_lifecycle_state_events"), "orders_outbox": _count(cursor, "orders_domain_outbox"), "scheduling": _count(cursor, "scheduling_generations"), "finance": _count(cursor, "client_obligation_events"), "payroll": _count(cursor, "staff_obligation_events")}
    finally:
        connection.close()


def _count(cursor, table):
    cursor.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE case_no='G05-CASE'")
    return int(cursor.fetchone()["count"])

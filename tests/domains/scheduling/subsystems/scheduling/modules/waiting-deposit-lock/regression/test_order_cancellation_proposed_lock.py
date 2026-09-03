"""Regression for cancelling an active waiting lock on a legacy proposed plan."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_pre_service_cancellation_releases_legacy_proposed_active_lock():
    bootstrap(_arguments())
    _seed_in_service_case()
    _seed_legacy_proposed_active_lock()
    workflow, connection = _workflow()

    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.orders.cancellation_workflow import (
        OrderCancellationApplyRequest,
    )

    preview = workflow.preview("G03-CASE", ())
    request = OrderCancellationApplyRequest(
        "G03-CASE",
        (),
        ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),
        preview.fingerprint,
        IdempotencyKey("pre-service-proposed-lock-cancellation"),
        ActorContext("g03-test"),
        "client cancelled before service",
        CorrelationId("pre-service-proposed-lock-cancellation"),
    )

    try:
        receipt = workflow.apply(request)
    finally:
        connection.close()

    assert receipt.lifecycle_status.value == "訂單取消"
    assert receipt.official_service_day_count == 0
    _assert_legacy_proposed_lock_cancelled()


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _workflow():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_cancellation_repository import (
        MySqlOrderCancellationRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.orders.cancellation_workflow import OrderCancellationWorkflow

    connection = get_connection()
    return OrderCancellationWorkflow(
        MySqlOrderCancellationRepository(connection),
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)),
    ), connection


def _seed_in_service_case() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients(case_no,name,identity_status) "
                "VALUES ('G03-CASE','G03 Client','一般市民')"
            )
            client_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO staff(name,status) VALUES ('G03 Staff 1','active')"
            )
            assert cursor.lastrowid == 1
            cursor.execute(
                "INSERT INTO staff(name,status) VALUES ('G03 Staff 2','active')"
            )
            assert cursor.lastrowid == 2
            cursor.execute(
                "INSERT INTO orders "
                "(case_no,client_id,status,lifecycle_version,start_date,service_days,"
                "service_hours_per_day,floor_fee,service_start_time,service_end_time,"
                "service_end_day_offset,actual_start_date,staff_payment_due_date) "
                "VALUES ('G03-CASE',%s,'服務中',0,'2026-08-01',4,8,400,"
                "'09:00:00','17:00:00',0,'2026-08-01','2026-08-15')",
                (client_id,),
            )
            cursor.execute(
                "INSERT INTO scheduling_generations "
                "(case_no,generation_number,resulting_aggregate_version,status,"
                "effective_marker,created_by,change_reason) "
                "VALUES ('G03-CASE',1,1,'effective',1,'g03-test',"
                "'initial assignment')"
            )
            generation_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO scheduling_aggregates "
                "(case_no,aggregate_version,generation_counter,effective_generation_id) "
                "VALUES ('G03-CASE',1,1,%s)",
                (generation_id,),
            )
            _insert_assignment(
                cursor,
                generation_id,
                1,
                1,
                _date(1),
                _date(3),
                "G03-CASE:g1:a1",
            )
            _insert_assignment(
                cursor,
                generation_id,
                2,
                2,
                _date(2),
                _date(4),
                "G03-CASE:g1:a2",
            )
            _insert_client_finance_root(cursor)
            _insert_payroll_root(cursor)
        connection.commit()
    finally:
        connection.close()


def _insert_assignment(
    cursor,
    generation_id,
    staff_id,
    sequence,
    first_date,
    second_date,
    key,
) -> None:
    cursor.execute(
        "INSERT INTO case_staff_assignments "
        "(case_no,generation_id,candidate_key,staff_id,assignment_sequence,"
        "assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
        "VALUES ('G03-CASE',%s,%s,%s,%s,%s,%s,0,'planned')",
        (generation_id, key, staff_id, sequence, first_date, second_date),
    )
    assignment_id = cursor.lastrowid
    for service_date in (first_date, second_date):
        cursor.execute(
            "INSERT INTO staff_schedule "
            "(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,"
            "is_double_pay,effective_marker) "
            "VALUES ('G03-CASE',%s,%s,%s,%s,1,0,1)",
            (staff_id, assignment_id, generation_id, service_date),
        )


def _insert_client_finance_root(cursor) -> None:
    cursor.execute(
        "INSERT INTO client_finance_accounts(case_no,aggregate_version) "
        "VALUES ('G03-CASE',0)"
    )
    cursor.execute(
        "INSERT INTO client_payment_terms_events "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES ('G03-CASE','g03-policy',100,2,'2026-08-15','2026-08-20',NULL,"
        "0,'g03-terms-root','g03-terms-root','g03-test','fixture')"
    )
    event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_payment_terms "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) "
        "VALUES ('G03-CASE','g03-policy',100,2,'2026-08-15','2026-08-20',NULL,%s)",
        (event_id,),
    )


def _insert_payroll_root(cursor) -> None:
    cursor.execute(
        "INSERT INTO payroll_case_accounts(case_no,aggregate_version) "
        "VALUES ('G03-CASE',0)"
    )
    cursor.execute(
        "INSERT INTO payroll_rate_policies "
        "(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
        "VALUES ('g03-policy','citizen',150,'2026-01-01')"
    )
    for assignment_id in (1, 2):
        cursor.execute(
            "INSERT INTO assignment_payroll_rate_snapshots "
            "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,"
            "source_identity_status) "
            "VALUES (%s,'g03-policy','citizen',150,'fixture')",
            (assignment_id,),
        )


def _date(day: int):
    from datetime import date

    return date(2026, 8, day)


def _seed_legacy_proposed_active_lock() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET status='訂單成立',actual_start_date=NULL "
                "WHERE case_no='G03-CASE'"
            )
            cursor.execute(
                "INSERT INTO caregiver_matching_plans "
                "(case_no,version,status,is_active,start_date,end_date,created_by) "
                "VALUES ('G03-CASE',1,'proposed',1,'2026-08-01','2026-08-04','g03-test')"
            )
            plan_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO caregiver_matching_plan_segments "
                "(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) "
                "VALUES (%s,1,1,'2026-08-01','2026-08-04')",
                (plan_id,),
            )
            segment_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO caregiver_availability_locks "
                "(plan_id,status,is_active,created_by) "
                "VALUES (%s,'active',1,'g03-test')",
                (plan_id,),
            )
            lock_id = cursor.lastrowid
            for day in range(1, 5):
                cursor.execute(
                    "INSERT INTO caregiver_availability_lock_days "
                    "(lock_id,segment_id,staff_id,lock_date,active_marker) "
                    "VALUES (%s,%s,1,%s,1)",
                    (lock_id, segment_id, f"2026-08-{day:02d}"),
                )
        connection.commit()
    finally:
        connection.close()


def _assert_legacy_proposed_lock_cancelled() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT l.status,l.is_active,p.status AS plan_status "
                "FROM caregiver_availability_locks l "
                "JOIN caregiver_matching_plans p ON p.id=l.plan_id "
                "WHERE p.case_no='G03-CASE'"
            )
            assert cursor.fetchone() == {
                "status": "cancelled",
                "is_active": None,
                "plan_status": "proposed",
            }
            cursor.execute(
                "SELECT COUNT(*) AS active_count "
                "FROM caregiver_availability_lock_days d "
                "JOIN caregiver_availability_locks l ON l.id=d.lock_id "
                "JOIN caregiver_matching_plans p ON p.id=l.plan_id "
                "WHERE p.case_no='G03-CASE' AND d.active_marker=1"
            )
            assert cursor.fetchone() == {"active_count": 0}
    finally:
        connection.close()

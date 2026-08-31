"""Regression for cancelling an active waiting lock on a legacy proposed plan."""

from __future__ import annotations

import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from tests.test_order_cancellation_disposable_mysql_e2e import (
    _arguments,
    _seed_in_service_case,
    _workflow,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE"),
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

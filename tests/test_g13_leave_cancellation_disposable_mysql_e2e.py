"""G13 isolated MySQL proof for leave and cancellation occupancy contention."""

from __future__ import annotations

from argparse import Namespace
from datetime import date, datetime
import os
from queue import Queue
from threading import Barrier, Thread

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)

CASE_NO = "G13-CASE"


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def test_g13_leave_and_cancellation_serialize_shared_occupancy_write():
    bootstrap(_arguments())
    staff_ids = _seed_case()
    leave_preview = _leave_preview()
    cancellation_preview = _cancellation_preview(staff_ids[0])
    start = Barrier(2)
    outcomes: Queue = Queue()
    leave_thread = Thread(
        target=_apply_leave_after_start,
        args=(leave_preview, start, outcomes),
    )
    cancellation_thread = Thread(
        target=_apply_cancellation_after_start,
        args=(cancellation_preview, staff_ids[0], start, outcomes),
    )

    leave_thread.start()
    cancellation_thread.start()
    leave_thread.join(timeout=20)
    cancellation_thread.join(timeout=20)

    assert not leave_thread.is_alive()
    assert not cancellation_thread.is_alive()
    result_rows = [outcomes.get_nowait(), outcomes.get_nowait()]
    assert sum(result[0] == "success" for result in result_rows) == 1
    assert sum(result[0] == "typed_error" for result in result_rows) == 1
    _assert_effective_occupancy_is_unique()


def _apply_leave_after_start(preview, start: Barrier, outcomes: Queue) -> None:
    try:
        start.wait(timeout=10)
        _leave_apply(preview)
        outcomes.put(("success", "leave"))
    except Exception as error:
        outcomes.put(_typed_outcome("leave", error))


def _apply_cancellation_after_start(
    preview,
    staff_id: int,
    start: Barrier,
    outcomes: Queue,
) -> None:
    try:
        start.wait(timeout=10)
        _cancellation_apply(preview, staff_id)
        outcomes.put(("success", "cancellation"))
    except Exception as error:
        outcomes.put(_typed_outcome("cancellation", error))


def _typed_outcome(operation: str, error: Exception) -> tuple[str, str, str]:
    typed_error = getattr(error, "error", None)
    if typed_error is None or not isinstance(getattr(typed_error, "code", None), str):
        raise error
    return "typed_error", operation, typed_error.code


def _leave_preview():
    workflow, connection = _leave_workflow()
    try:
        return workflow.preview(_leave_preview_request())
    finally:
        connection.close()


def _leave_apply(preview) -> None:
    workflow, connection = _leave_workflow()
    try:
        workflow.apply(_leave_apply_request(preview))
    finally:
        connection.close()


def _leave_workflow():
    from infrastructure.mysql.leave_substitution_impact_ports import (
        MySqlClientFinanceLeaveImpactPort,
        MySqlOrdersLeaveImpactPort,
        MySqlPayrollLeaveImpactPort,
    )
    from infrastructure.mysql.leave_substitution_repository import (
        MySqlLeaveSubstitutionRepository,
    )
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.scheduling.leave_substitution_workflow import (
        LeaveSubstitutionWorkflow,
    )

    connection = get_connection()
    return (
        LeaveSubstitutionWorkflow(
            MySqlLeaveSubstitutionRepository(connection),
            MySqlClientFinanceLeaveImpactPort(connection),
            MySqlPayrollLeaveImpactPort(connection),
            MySqlOrdersLeaveImpactPort(
                connection,
                FixedBusinessClock(
                    datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)
                ),
            ),
            lambda: MySqlUnitOfWork(connection),
        ),
        connection,
    )


def _leave_preview_request():
    from shared_kernel.identities import CorrelationId
    from subsystems.scheduling.leave_substitution_workflow import (
        LeaveSubstitutionPreviewRequest,
    )

    return LeaveSubstitutionPreviewRequest(
        CASE_NO,
        _leave_intent(),
        CorrelationId("g13-leave-preview"),
    )


def _leave_apply_request(preview):
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.scheduling.leave_substitution_workflow import (
        LeaveSubstitutionApplyRequest,
    )

    return LeaveSubstitutionApplyRequest(
        CASE_NO,
        _leave_intent(),
        ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),
        preview.fingerprint,
        IdempotencyKey("g13-leave"),
        ActorContext("g13-e2e"),
        "defer the final service day",
        CorrelationId("g13-leave"),
    )


def _leave_intent():
    from domains.scheduling.leave_substitution import (
        LeaveResolutionType,
        LeaveSubstitutionBatchIntent,
        LeaveSubstitutionItem,
    )

    assignment_id, schedule_id = _final_day_assignment_identity()
    return LeaveSubstitutionBatchIntent(
        assignment_id,
        (
            LeaveSubstitutionItem(
                schedule_id,
                date(2026, 8, 4),
                LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
            ),
        ),
    )


def _final_day_assignment_identity() -> tuple[int, int]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT assignment_id,id FROM staff_schedule "
                "WHERE case_no=%s AND work_date='2026-08-04'",
                (CASE_NO,),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    assert row is not None
    return int(row["assignment_id"]), int(row["id"])


def _cancellation_preview(staff_id: int):
    from domains.orders.cancellation import ConfirmedServiceDay

    workflow, connection = _cancellation_workflow()
    try:
        return workflow.preview(
            CASE_NO,
            (ConfirmedServiceDay(date(2026, 8, 1), staff_id),),
        )
    finally:
        connection.close()


def _cancellation_apply(preview, staff_id: int) -> None:
    from domains.orders.cancellation import ConfirmedServiceDay
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.orders.cancellation_workflow import OrderCancellationApplyRequest

    workflow, connection = _cancellation_workflow()
    try:
        workflow.apply(
            OrderCancellationApplyRequest(
                CASE_NO,
                (ConfirmedServiceDay(date(2026, 8, 1), staff_id),),
                ExpectedVersion(preview.order_version),
                ExpectedVersion(preview.scheduling_version),
                ExpectedVersion(preview.client_finance_version),
                ExpectedVersion(preview.payroll_version),
                preview.fingerprint,
                IdempotencyKey("g13-cancellation"),
                ActorContext("g13-e2e"),
                "client cancelled remaining service",
                CorrelationId("g13-cancellation"),
            )
        )
    finally:
        connection.close()


def _cancellation_workflow():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_cancellation_repository import (
        MySqlOrderCancellationRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.orders.cancellation_workflow import OrderCancellationWorkflow

    connection = get_connection()
    return (
        OrderCancellationWorkflow(
            MySqlOrderCancellationRepository(connection),
            lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(
                datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)
            ),
        ),
        connection,
    )


def _seed_case() -> tuple[int, int]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients(case_no,name) VALUES (%s,'G13 Client')",
                (CASE_NO,),
            )
            client_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO staff(name,status) VALUES ('G13 Staff 1','active')"
            )
            first_staff_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO staff(name,status) VALUES ('G13 Staff 2','active')"
            )
            second_staff_id = int(cursor.lastrowid)
            _insert_order(cursor, client_id)
            generation_id = _insert_generation(cursor)
            first_assignment_id = _insert_assignment(
                cursor,
                generation_id,
                first_staff_id,
                1,
                date(2026, 8, 1),
                date(2026, 8, 2),
            )
            second_assignment_id = _insert_assignment(
                cursor,
                generation_id,
                second_staff_id,
                2,
                date(2026, 8, 3),
                date(2026, 8, 4),
            )
            _insert_roots(cursor, first_assignment_id, second_assignment_id)
        connection.commit()
        return first_staff_id, second_staff_id
    finally:
        connection.close()


def _insert_order(cursor, client_id: int) -> None:
    cursor.execute(
        "INSERT INTO orders "
        "(case_no,client_id,status,lifecycle_version,start_date,service_days,"
        "service_hours_per_day,floor_fee,service_start_time,service_end_time,"
        "service_end_day_offset,actual_start_date,staff_payment_due_date) "
        "VALUES (%s,%s,'服務中',0,'2026-08-01',4,8,0,'09:00:00','17:00:00',"
        "0,'2026-08-01','2026-08-15')",
        (CASE_NO, client_id),
    )


def _insert_generation(cursor) -> int:
    cursor.execute(
        "INSERT INTO scheduling_generations "
        "(case_no,generation_number,resulting_aggregate_version,status,"
        "effective_marker,created_by,change_reason) "
        "VALUES (%s,1,1,'effective',1,'g13-e2e','fixture')",
        (CASE_NO,),
    )
    generation_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO scheduling_aggregates "
        "(case_no,aggregate_version,generation_counter,effective_generation_id) "
        "VALUES (%s,1,1,%s)",
        (CASE_NO, generation_id),
    )
    return generation_id


def _insert_assignment(
    cursor,
    generation_id: int,
    staff_id: int,
    sequence: int,
    start_date: date,
    end_date: date,
) -> int:
    cursor.execute(
        "INSERT INTO case_staff_assignments "
        "(case_no,generation_id,candidate_key,staff_id,assignment_sequence,"
        "assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,0,'planned')",
        (
            CASE_NO,
            generation_id,
            f"{CASE_NO}:g1:a{sequence}",
            staff_id,
            sequence,
            start_date,
            end_date,
        ),
    )
    assignment_id = int(cursor.lastrowid)
    for work_date in (start_date, end_date):
        cursor.execute(
            "INSERT INTO staff_schedule "
            "(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,"
            "is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,%s,1,0,1)",
            (CASE_NO, staff_id, assignment_id, generation_id, work_date),
        )
        cursor.execute(
            "INSERT INTO scheduling_effective_occupancy "
            "(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) "
            "VALUES (%s,%s,%s,%s,'assignment_interval')",
            (staff_id, work_date, generation_id, assignment_id),
        )
    return assignment_id


def _insert_roots(cursor, first_assignment_id: int, second_assignment_id: int) -> None:
    cursor.execute(
        "INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)",
        (CASE_NO,),
    )
    cursor.execute(
        "INSERT INTO client_payment_terms_events "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,"
        "expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,'g13-policy',100,0,'2026-08-15','2026-08-20',NULL,0,"
        "'g13-terms-root','g13-terms-root','g13-e2e','fixture')",
        (CASE_NO,),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_payment_terms "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,"
        "deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) "
        "VALUES (%s,'g13-policy',100,0,'2026-08-15','2026-08-20',NULL,%s)",
        (CASE_NO, event_id),
    )
    cursor.execute(
        "INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES (%s,0)",
        (CASE_NO,),
    )
    cursor.execute(
        "INSERT INTO payroll_rate_policies "
        "(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
        "VALUES ('g13-policy','citizen',150,'2026-01-01')"
    )
    cursor.executemany(
        "INSERT INTO assignment_payroll_rate_snapshots "
        "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) "
        "VALUES (%s,'g13-policy','citizen',150,'fixture')",
        ((first_assignment_id,), (second_assignment_id,)),
    )


def _assert_effective_occupancy_is_unique() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM scheduling_generations "
                "WHERE case_no=%s AND effective_marker=1",
                (CASE_NO,),
            )
            assert cursor.fetchone() == {"count": 1}
            cursor.execute(
                "SELECT staff_id,occupancy_date,COUNT(*) AS count "
                "FROM scheduling_effective_occupancy GROUP BY staff_id,occupancy_date "
                "HAVING COUNT(*) > 1"
            )
            assert not cursor.fetchall()
    finally:
        connection.close()

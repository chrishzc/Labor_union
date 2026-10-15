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


def test_leave_acceptance_context_handles_mysql8_connection_collation(monkeypatch):
    """A UTF-8 connection's CAST must compare with the binding owner's collation."""
    from infrastructure.mysql import mysql_adapter
    from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from domains.scheduling.staff_leave_intake import StaffLeaveRequestIntent
    from subsystems.scheduling.staff_leave_intake_workflow import (
        ReviewStaffLeaveRequest, StaffLeaveIntakeApplication, SubmitStaffLeaveRequest,
    )

    arguments = _arguments()
    arguments.database = f"{DATABASE}_leave_collation"
    arguments.confirm_database = arguments.database
    bootstrap(arguments)
    monkeypatch.setitem(mysql_adapter.DB_CONFIG, "database", arguments.database)
    _, original_staff_id = _seed_case()
    with mysql_adapter.get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET collation_connection='utf8mb4_0900_ai_ci'")
        repository = MySqlStaffLeaveIntakeRepository(connection)
        application = StaffLeaveIntakeApplication(repository, lambda: MySqlUnitOfWork(connection))
        request = application.submit(SubmitStaffLeaveRequest(
            original_staff_id, "U" + "9" * 32,
            StaffLeaveRequestIntent(date(2026, 8, 4), date(2026, 8, 4), "fixture leave"),
            "g13-collation-submit",
        ))
        accepted = application.review(ReviewStaffLeaveRequest(
            request.request_id, request.version, "accept", "fixture acceptance", False,
            "fixture-admin", "g13-collation-accept",
        ))
        context = repository.coordination_context(accepted.request_id, accepted.version)
        assert context["targets"] == [{"case_no": CASE_NO, "client_line_user_id": None}]
        assert repository.load(accepted.request_id).status.value == "accepted_for_processing"
        from domains.scheduling.leave_substitution import LeaveResolutionType, LeaveSubstitutionBatchIntent, LeaveSubstitutionItem
        from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
        from shared_kernel.fingerprints import PreviewFingerprint
        from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
        from subsystems.scheduling.leave_substitution_linked_request_resolution import LeaveSubstitutionLinkedRequestResolution
        from subsystems.scheduling.leave_substitution_workflow import (
            LeaveSubstitutionApplyRequest, LeaveSubstitutionPreviewRequest,
            LeaveSubstitutionWorkflowError, LinkedLeaveRequestIntent,
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT assignment_id,id FROM staff_schedule WHERE case_no=%s AND work_date='2026-08-03'", (CASE_NO,))
            wrong_day = cursor.fetchone()
        intent = LeaveSubstitutionBatchIntent(wrong_day["assignment_id"], (
            LeaveSubstitutionItem(wrong_day["id"], date(2026, 8, 3), LeaveResolutionType.SUBSTITUTE, 1),
        ))
        workflow, workflow_connection = _leave_workflow()
        try:
            workflow._linked_request_resolver = LeaveSubstitutionLinkedRequestResolution(
                MySqlStaffLeaveIntakeRepository(workflow_connection), None,
                FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)),
            )
            linked = LinkedLeaveRequestIntent(accepted.request_id, accepted.version)
            preview_request = LeaveSubstitutionPreviewRequest(CASE_NO, intent, CorrelationId("wrong-day-preview"), linked)
            apply_request = LeaveSubstitutionApplyRequest(
                CASE_NO, intent, ExpectedVersion(0), ExpectedVersion(1), ExpectedVersion(0), ExpectedVersion(0),
                PreviewFingerprint("a" * 64), IdempotencyKey("wrong-day-apply"), ActorContext("fixture"),
                "wrong linked day must not apply", CorrelationId("wrong-day-apply"), linked,
            )
            for operation, command in ((workflow.preview, preview_request), (workflow.apply, apply_request)):
                with pytest.raises(LeaveSubstitutionWorkflowError) as caught:
                    operation(command)
                assert caught.value.error.code == "leave_request_dates_outside_window"
                assert "請假之服務日" in caught.value.error.message
            with workflow_connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS n FROM scheduling_leave_substitution_batches WHERE case_no=%s", (CASE_NO,))
                assert cursor.fetchone()["n"] == 0
        finally:
            workflow_connection.close()


def test_identical_leave_submissions_race_replay_without_duplicate_root_or_event(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from infrastructure.mysql import mysql_adapter
    from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from domains.scheduling.staff_leave_intake import StaffLeaveRequestIntent
    from subsystems.scheduling.staff_leave_intake_workflow import StaffLeaveIntakeApplication, SubmitStaffLeaveRequest

    arguments = _arguments()
    arguments.database = f"{DATABASE}_intake_race"
    arguments.confirm_database = arguments.database
    bootstrap(arguments)
    monkeypatch.setitem(mysql_adapter.DB_CONFIG, "database", arguments.database)
    _, staff_id = _seed_case()
    original_create = MySqlStaffLeaveIntakeRepository.create
    barrier = Barrier(2)
    def synchronized_create(self, command, fingerprint):
        barrier.wait(timeout=10)
        return original_create(self, command, fingerprint)
    monkeypatch.setattr(MySqlStaffLeaveIntakeRepository, "create", synchronized_create)
    command = SubmitStaffLeaveRequest(staff_id, "U" + "9" * 32,
        StaffLeaveRequestIntent(date(2026, 8, 4), date(2026, 8, 4), "race fixture"), "g13-identical-intake")
    def submit(value):
        with mysql_adapter.get_connection() as connection:
            application = StaffLeaveIntakeApplication(MySqlStaffLeaveIntakeRepository(connection), lambda: MySqlUnitOfWork(connection))
            return application.submit(value)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(submit, (command, command)))
    assert receipts[0] == receipts[1]
    monkeypatch.setattr(MySqlStaffLeaveIntakeRepository, "create", original_create)
    # A fresh UI operation identity for the same intent still resolves the unique root.
    from dataclasses import replace
    assert submit(replace(command, idempotency_key="g13-identical-intake-alias")).request_id == receipts[0].request_id
    with pytest.raises(ValueError, match="leave_request_idempotency_conflict"):
        submit(replace(command, intent=StaffLeaveRequestIntent(date(2026, 8, 3), date(2026, 8, 3), "changed")))
    with mysql_adapter.get_connection() as connection, connection.cursor() as cursor:
        for table, expected in (("scheduling_staff_leave_request_aggregates", 1),
                                ("scheduling_staff_leave_request_events", 1),
                                ("scheduling_staff_leave_request_receipts", 2)):
            cursor.execute(f"SELECT COUNT(*) AS n FROM {table}")
            assert cursor.fetchone()["n"] == expected
    # A second operator's old assignment must be a typed conflict, never a 500.
    from shared_kernel.identities import IdempotencyKey
    from subsystems.scheduling.leave_substitution_workflow import LeaveSubstitutionWorkflowError
    stale_command = _leave_apply_request(_leave_preview())
    workflow, connection = _leave_workflow()
    try:
        workflow.apply(stale_command)
        with pytest.raises(LeaveSubstitutionWorkflowError) as caught:
            workflow.apply(replace(stale_command, idempotency_key=IdempotencyKey("g13-other-operator")))
        assert caught.value.error.code == "stale_assignment"
        assert caught.value.error.category.value == "conflict"
        assert "重新查詢最新資料" in caught.value.error.message
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM scheduling_leave_substitution_batches WHERE case_no=%s", (CASE_NO,))
            assert cursor.fetchone()["n"] == 1
    finally:
        connection.close()


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
    from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
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
            MySqlSchedulingHolidayQuery(connection),
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
                "INSERT INTO clients(case_no,name,service_type) VALUES (%s,'G13 Client','連續服務')",
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
    # Cancellation requires the complete canonical Payroll root, not just an account.
    cursor.execute(
        "INSERT INTO case_architecture_bootstrap_events(case_no,order_version,client_payment_terms_event_id,"
        "client_policy_version,client_hourly_rate_ntd,payroll_policy_version,payroll_policy_kind,"
        "payroll_hourly_rate_ntd,source_identity_status,candidate_fingerprint,idempotency_key,actor,reason,correlation_id) "
        "VALUES (%s,0,%s,'g13-policy',100,'g13-policy','citizen',150,'fixture',%s,'g13-bootstrap','g13-e2e','fixture','g13-bootstrap')",
        (CASE_NO, event_id, "a" * 64),
    )
    bootstrap_event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO case_payroll_rate_policy_snapshots(case_no,policy_version,policy_kind,hourly_rate_ntd,source_identity_status,source_event_id) "
        "VALUES (%s,'g13-policy','citizen',150,'fixture',%s)",
        (CASE_NO, bootstrap_event_id),
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

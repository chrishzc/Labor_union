"""G05 isolated MySQL proof for real leave/apply completion concurrency."""

from __future__ import annotations

from argparse import Namespace
from datetime import date, datetime
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)

_CASE_NO = "G05-CASE"


def _arguments():
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def test_auto_completion_first_rejects_the_real_stale_leave_apply_without_writes():
    bootstrap(_arguments())
    _seed_case()
    leave_preview = _leave_preview()
    before_auto = _snapshot()

    receipt = _auto_apply(expected_version=0, key="g05-auto-first", evaluation_at="2026-08-04T17:00:00+08:00")
    after_auto = _snapshot()

    assert receipt.order_version == 1
    _assert_auto_delta(before_auto, after_auto, status="訂單完成", actual_end="2026-08-04")

    from subsystems.scheduling.leave_substitution_workflow import (
        LeaveSubstitutionWorkflowError,
    )

    with pytest.raises(LeaveSubstitutionWorkflowError) as error:
        _leave_apply(leave_preview, key="g05-stale-leave")
    assert error.value.error.code == "stale_version"
    assert _snapshot() == after_auto


def test_real_leave_apply_stales_old_completion_then_recomputed_completion_succeeds():
    bootstrap(_arguments())
    _seed_case()
    leave_preview = _leave_preview()
    before_leave = _snapshot()

    leave_receipt = _leave_apply(leave_preview, key="g05-leave-first")
    after_leave = _snapshot()

    assert leave_receipt.order_version == 1
    _assert_leave_delta(before_leave, after_leave)

    from subsystems.orders.auto_completion_workflow import AutoCompletionWorkflowError

    with pytest.raises(AutoCompletionWorkflowError) as stale_error:
        _auto_apply(expected_version=0, key="g05-stale-completion", evaluation_at="2026-08-04T17:00:00+08:00")
    assert stale_error.value.error.code == "order_version_conflict"
    assert _snapshot() == after_leave

    with pytest.raises(AutoCompletionWorkflowError) as early_error:
        _auto_apply(expected_version=1, key="g05-recomputed-too-early", evaluation_at="2026-08-04T17:00:00+08:00")
    assert early_error.value.error.code == "auto_completion_time_not_reached"
    assert _snapshot() == after_leave

    receipt = _auto_apply(expected_version=1, key="g05-recomputed-completion", evaluation_at="2026-08-05T17:00:00+08:00")
    after_completion = _snapshot()

    assert receipt.order_version == 2
    _assert_auto_delta(after_leave, after_completion, status="訂單完成", actual_end="2026-08-05")


def _auto_apply(*, expected_version, key, evaluation_at):
    workflow, connection = _auto_workflow()
    try:
        return workflow.apply(_auto_request(expected_version, key, evaluation_at))
    finally:
        connection.close()


def _auto_workflow():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_auto_completion_repository import (
        MySqlOrderAutoCompletionRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.auto_completion_workflow import AutoCompleteOrderService

    connection = get_connection()
    return (
        AutoCompleteOrderService(
            MySqlOrderAutoCompletionRepository(connection),
            lambda: MySqlUnitOfWork(connection),
        ),
        connection,
    )


def _auto_request(expected_version, key, evaluation_at):
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.orders.auto_completion_workflow import AutoCompletionApplyRequest

    return AutoCompletionApplyRequest(
        _CASE_NO,
        ExpectedVersion(expected_version),
        datetime.fromisoformat(evaluation_at),
        IdempotencyKey(key),
        ActorContext("g05-e2e"),
        "service completion clock reached",
        CorrelationId(key),
    )


def _leave_preview():
    workflow, connection = _leave_workflow()
    try:
        return workflow.preview(_leave_preview_request())
    finally:
        connection.close()


def _leave_apply(preview, *, key):
    workflow, connection = _leave_workflow()
    try:
        return workflow.apply(_leave_apply_request(preview, key))
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
    from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery

    connection = get_connection()
    return (
        LeaveSubstitutionWorkflow(
            MySqlLeaveSubstitutionRepository(connection),
            MySqlClientFinanceLeaveImpactPort(connection),
            MySqlPayrollLeaveImpactPort(connection),
            MySqlOrdersLeaveImpactPort(
                connection,
                FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)),
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

    return LeaveSubstitutionPreviewRequest(_CASE_NO, _leave_intent(), CorrelationId("g05-leave-preview"))


def _leave_apply_request(preview, key):
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
        _CASE_NO,
        _leave_intent(),
        ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),
        preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("g05-e2e"),
        "defer one official service day",
        CorrelationId(key),
    )


def _leave_intent():
    from domains.scheduling.leave_substitution import (
        LeaveResolutionType,
        LeaveSubstitutionBatchIntent,
        LeaveSubstitutionItem,
    )

    assignment_id, schedule_id = _official_schedule_identity()
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


def _official_schedule_identity():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT assignment_id,id FROM staff_schedule "
                "WHERE case_no=%s AND is_work_day=1 ORDER BY id LIMIT 1",
                (_CASE_NO,),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    assert row is not None
    return int(row["assignment_id"]), int(row["id"])


def _seed_case():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'G05 Client')", (_CASE_NO,))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff(name,status) VALUES ('G05 Staff','active')")
            staff_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO orders "
                "(case_no,client_id,status,lifecycle_version,start_date,service_days,"
                "service_hours_per_day,floor_fee,service_start_time,service_end_time,"
                "service_end_day_offset,actual_start_date,actual_end_date,staff_payment_due_date) "
                "VALUES (%s,%s,'服務中',0,'2026-08-01',1,8,0,'09:00:00','17:00:00',0,'2026-08-01','2026-08-04','2026-08-15')",
                (_CASE_NO, client_id),
            )
            cursor.execute(
                "INSERT INTO scheduling_generations "
                "(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) "
                "VALUES (%s,1,1,'effective',1,'g05-e2e','fixture')",
                (_CASE_NO,),
            )
            generation_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO scheduling_aggregates "
                "(case_no,aggregate_version,generation_counter,effective_generation_id) "
                "VALUES (%s,1,1,%s)",
                (_CASE_NO, generation_id),
            )
            cursor.execute(
                "INSERT INTO case_staff_assignments "
                "(case_no,generation_id,candidate_key,staff_id,assignment_sequence,"
                "assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
                "VALUES (%s,%s,'G05-CASE:g1:a1',%s,1,'2026-08-04','2026-08-04',0,'planned')",
                (_CASE_NO, generation_id, staff_id),
            )
            assignment_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO staff_schedule "
                "(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,is_double_pay,effective_marker) "
                "VALUES (%s,%s,%s,%s,'2026-08-04',1,0,1)",
                (_CASE_NO, staff_id, assignment_id, generation_id),
            )
            _insert_client_finance_root(cursor)
            _insert_payroll_root(cursor, assignment_id)
        connection.commit()
    finally:
        connection.close()


def _insert_client_finance_root(cursor):
    cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)", (_CASE_NO,))
    cursor.execute(
        "INSERT INTO client_payment_terms_events "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES (%s,'g05-policy',100,0,'2026-08-15','2026-08-20',NULL,0,'g05-terms-root','g05-terms-root','g05-e2e','fixture')",
        (_CASE_NO,),
    )
    event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_payment_terms "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) "
        "VALUES (%s,'g05-policy',100,0,'2026-08-15','2026-08-20',NULL,%s)",
        (_CASE_NO, event_id),
    )


def _insert_payroll_root(cursor, assignment_id):
    cursor.execute("INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES (%s,0)", (_CASE_NO,))
    cursor.execute(
        "INSERT INTO payroll_rate_policies "
        "(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
        "VALUES ('g05-policy','citizen',150,'2026-01-01')"
    )
    cursor.execute(
        "INSERT INTO assignment_payroll_rate_snapshots "
        "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) "
        "VALUES (%s,'g05-policy','citizen',150,'fixture')",
        (assignment_id,),
    )


def _snapshot():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            return {
                "claims": _count(cursor, "application_command_claims", "aggregate_identity=%s", (_CASE_NO,)),
                "auto_receipts": _count(cursor, "order_auto_completion_apply_receipts", "case_no=%s", (_CASE_NO,)),
                "lifecycle_events": _count(cursor, "order_lifecycle_state_events", "case_no=%s", (_CASE_NO,)),
                "orders_outbox": _count(cursor, "orders_domain_outbox", "case_no=%s", (_CASE_NO,)),
                "generations": _count(cursor, "scheduling_generations", "case_no=%s", (_CASE_NO,)),
                "rebuild_events": _count(cursor, "scheduling_rebuild_events", "case_no=%s", (_CASE_NO,)),
                "scheduling_receipts": _count(cursor, "scheduling_command_receipts", "case_no=%s", (_CASE_NO,)),
                "assignments": _count(cursor, "case_staff_assignments", "case_no=%s", (_CASE_NO,)),
                "schedules": _count(cursor, "staff_schedule", "case_no=%s", (_CASE_NO,)),
                "leave_batches": _count(cursor, "scheduling_leave_substitution_batches", "case_no=%s", (_CASE_NO,)),
                "leave_outcomes": _count(
                    cursor,
                    "scheduling_leave_substitution_outcomes",
                    "batch_key LIKE %s",
                    ("g05-%",),
                ),
                "leave_receipts": _count(cursor, "scheduling_leave_substitution_receipts", "case_no=%s", (_CASE_NO,)),
                "leave_occupancy": _count(
                    cursor,
                    "scheduling_leave_occupancy_days",
                    "batch_key LIKE %s",
                    ("g05-%",),
                ),
                "client_events": _count(cursor, "client_obligation_events", "case_no=%s", (_CASE_NO,)),
                "client_obligations": _count(cursor, "client_obligations", "case_no=%s", (_CASE_NO,)),
                "client_outbox": _count(cursor, "client_finance_outbox", "case_no=%s", (_CASE_NO,)),
                "staff_events": _count(cursor, "staff_obligation_events", "case_no=%s", (_CASE_NO,)),
                "staff_obligations": _count(cursor, "staff_obligations", "case_no=%s", (_CASE_NO,)),
                "payroll_outbox": _count(cursor, "payroll_outbox", "case_no=%s", (_CASE_NO,)),
                "client_version": _aggregate_version(cursor, "client_finance_accounts"),
                "payroll_version": _aggregate_version(cursor, "payroll_case_accounts"),
                "order": _order_state(cursor),
            }
    finally:
        connection.close()


def _count(cursor, table, where, values):
    cursor.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}", values)
    return int(cursor.fetchone()["count"])


def _aggregate_version(cursor, table):
    cursor.execute(f"SELECT aggregate_version FROM {table} WHERE case_no=%s", (_CASE_NO,))
    return int(cursor.fetchone()["aggregate_version"])


def _order_state(cursor):
    cursor.execute("SELECT status,lifecycle_version,actual_end_date FROM orders WHERE case_no=%s", (_CASE_NO,))
    row = cursor.fetchone()
    return str(row["status"]), int(row["lifecycle_version"]), row["actual_end_date"].isoformat()


def _assert_auto_delta(before, after, *, status, actual_end):
    expected = dict(before)
    expected["claims"] += 1
    expected["auto_receipts"] += 1
    expected["lifecycle_events"] += 1
    expected["orders_outbox"] += 1
    expected["order"] = (status, before["order"][1] + 1, actual_end)
    assert after == expected


def _assert_leave_delta(before, after):
    expected = dict(before)
    for key in (
        "claims",
        "lifecycle_events",
        "orders_outbox",
        "generations",
        "rebuild_events",
        "scheduling_receipts",
        "assignments",
        "schedules",
        "leave_batches",
        "leave_outcomes",
        "leave_receipts",
        "leave_occupancy",
        "client_events",
        "client_obligations",
        "client_outbox",
        "staff_events",
        "staff_obligations",
        "payroll_outbox",
    ):
        expected[key] += 1
    expected["client_version"] += 1
    expected["payroll_version"] += 1
    expected["order"] = ("服務中", before["order"][1] + 1, "2026-08-05")
    assert after == expected

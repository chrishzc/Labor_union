"""
File: test_leave_substitution_outer_uow_disposable_mysql_e2e.py
Description: 以唯一MySQL測試庫驗證請假代班、請假結案、LINE intent與receipt的單一交易。
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace
from datetime import datetime
import os

import pymysql
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from tests.test_g13_leave_cancellation_disposable_mysql_e2e import (
    CASE_NO,
    _leave_apply_request,
    _leave_intent,
    _seed_case,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_outer_uow_rolls_back_line_failure_then_replays_exact_receipt_once():
    _require_owned_database(DATABASE)
    created = False
    try:
        bootstrap(_arguments())
        created = True
        staff_ids = _seed_case()
        leave_request = _accepted_leave_request(staff_ids[1])
        preview = _preview(leave_request)
        command = replace(
            _leave_apply_request(preview),
            linked_request=leave_request,
        )

        workflow, connection = _workflow(fail_after_enqueue=True)
        try:
            with pytest.raises(Exception, match="rolled back"):
                workflow.apply(command)
        finally:
            connection.close()
        _assert_failure_rolled_back(command.idempotency_key.value, leave_request.request_id)

        workflow, connection = _workflow(fail_after_enqueue=False)
        try:
            receipt = workflow.apply(command)
            replay = workflow.apply(command)
        finally:
            connection.close()

        assert replay == receipt
        assert receipt.linked_request is not None
        assert receipt.linked_request.status == "resolved"
        assert receipt.linked_request.notification_intent == "enqueued"
        _assert_terminal_counts(command.idempotency_key.value, leave_request.request_id)
    finally:
        if created:
            _drop_owned_database(DATABASE)


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _accepted_leave_request(staff_id):
    from domains.scheduling.staff_leave_intake import StaffLeaveRequestIntent
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
    from subsystems.scheduling.leave_substitution_workflow import LinkedLeaveRequestIntent
    from subsystems.scheduling.staff_leave_intake_workflow import (
        ReviewStaffLeaveRequest,
        StaffLeaveIntakeWorkflow,
        SubmitStaffLeaveRequest,
    )

    connection = get_connection()
    try:
        workflow = StaffLeaveIntakeWorkflow(MySqlStaffLeaveIntakeRepository(connection))
        submitted = workflow.submit(
            SubmitStaffLeaveRequest(
                staff_id,
                "U-PHASE3B2",
                StaffLeaveRequestIntent(
                    datetime(2026, 8, 4).date(),
                    datetime(2026, 8, 4).date(),
                    "Phase3B2 fixture",
                ),
                "phase3b2-leave-submit",
            )
        )
        accepted = workflow.review(
            ReviewStaffLeaveRequest(
                submitted.request_id,
                submitted.version,
                "accept",
                "Phase3B2 accepted fixture",
                False,
                "phase3b2-e2e",
                "phase3b2-leave-accept",
            )
        )
        connection.commit()
        return LinkedLeaveRequestIntent(accepted.request_id, accepted.version)
    finally:
        connection.close()


def _preview(linked_request):
    from shared_kernel.identities import CorrelationId
    from subsystems.scheduling.leave_substitution_workflow import LeaveSubstitutionPreviewRequest

    workflow, connection = _workflow(fail_after_enqueue=False)
    try:
        return workflow.preview(
            LeaveSubstitutionPreviewRequest(
                CASE_NO,
                _leave_intent(),
                CorrelationId("phase3b2-preview"),
                linked_request,
            )
        )
    finally:
        connection.close()


def _workflow(*, fail_after_enqueue):
    from infrastructure.mysql.leave_substitution_impact_ports import (
        MySqlClientFinanceLeaveImpactPort,
        MySqlOrdersLeaveImpactPort,
        MySqlPayrollLeaveImpactPort,
    )
    from infrastructure.mysql.leave_substitution_repository import MySqlLeaveSubstitutionRepository
    from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
    from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.scheduling.leave_substitution_linked_request_resolution import LeaveSubstitutionLinkedRequestResolution
    from subsystems.scheduling.leave_substitution_workflow import LeaveSubstitutionWorkflow

    connection = get_connection()
    line_repository = MySqlLineDeliveryTaskRepository(connection)
    if fail_after_enqueue:
        line_repository = _FailAfterEnqueue(line_repository)
    clock = FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE))
    return (
        LeaveSubstitutionWorkflow(
            MySqlLeaveSubstitutionRepository(connection),
            MySqlClientFinanceLeaveImpactPort(connection),
            MySqlPayrollLeaveImpactPort(connection),
            MySqlOrdersLeaveImpactPort(connection, clock),
            MySqlSchedulingHolidayQuery(connection),
            lambda: MySqlUnitOfWork(connection),
            LeaveSubstitutionLinkedRequestResolution(
                MySqlStaffLeaveIntakeRepository(connection),
                line_repository,
                clock,
            ),
        ),
        connection,
    )


class _FailAfterEnqueue:
    def __init__(self, repository):
        self._repository = repository

    def enqueue(self, request):
        self._repository.enqueue(request)
        raise RuntimeError("phase3b2_line_enqueue_failure")


def _assert_failure_rolled_back(batch_key, request_id):
    counts = _counts(batch_key, request_id)
    assert counts == {
        "batches": 0,
        "receipts": 0,
        "links": 0,
        "line_tasks": 0,
        "resolved": 0,
        "generations": 1,
    }


def _assert_terminal_counts(batch_key, request_id):
    counts = _counts(batch_key, request_id)
    assert counts == {
        "batches": 1,
        "receipts": 1,
        "links": 1,
        "line_tasks": 1,
        "resolved": 1,
        "generations": 2,
    }


def _counts(batch_key, request_id):
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            queries = {
                "batches": ("SELECT COUNT(*) AS count FROM scheduling_leave_substitution_batches WHERE batch_key=%s", (batch_key,)),
                "receipts": ("SELECT COUNT(*) AS count FROM scheduling_leave_substitution_receipts WHERE batch_key=%s", (batch_key,)),
                "links": ("SELECT COUNT(*) AS count FROM scheduling_staff_leave_request_resolution_links WHERE request_id=%s", (request_id,)),
                "line_tasks": ("SELECT COUNT(*) AS count FROM line_delivery_tasks WHERE source_aggregate_type='scheduling_staff_leave_request' AND source_aggregate_identity=%s", (str(request_id),)),
                "resolved": ("SELECT COUNT(*) AS count FROM scheduling_staff_leave_request_aggregates WHERE id=%s AND request_status='resolved'", (request_id,)),
                "generations": ("SELECT COUNT(*) AS count FROM scheduling_generations WHERE case_no=%s", (CASE_NO,)),
            }
            result = {}
            for key, (sql, params) in queries.items():
                cursor.execute(sql, params)
                result[key] = int(cursor.fetchone()["count"])
            return result
    finally:
        connection.close()


def _require_owned_database(database):
    if not isinstance(database, str) or not database.startswith("lu_test_phase3b2_"):
        raise RuntimeError("owned disposable database name is required")


def _drop_owned_database(database):
    _require_owned_database(database)
    connection = pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{database}`")
    finally:
        connection.close()

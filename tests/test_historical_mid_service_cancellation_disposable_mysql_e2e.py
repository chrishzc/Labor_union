"""Disposable-MySQL proof for historical status-0 mid-service cancellation remediation."""

from __future__ import annotations

from argparse import Namespace
from datetime import date, datetime
import json
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)
_CASE_NO = "HIST-CANCEL-1"


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def test_historical_mid_service_cancellation_builds_canonical_owner_roots_once():
    bootstrap(_arguments())
    _seed_historical_cancelled_case()

    from domains.orders.cancellation import ConfirmedServiceDay
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_cancellation_repository import (
        MySqlOrderCancellationRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.orders.cancellation_workflow import (
        OrderCancellationApplyRequest,
        OrderCancellationWorkflow,
    )

    connection = get_connection()
    repository = MySqlOrderCancellationRepository(connection)
    workflow = OrderCancellationWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(
            datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)
        ),
    )
    confirmed_days = (
        ConfirmedServiceDay(
            date(2026, 8, 1),
            1,
            "historical daily service confirmed",
        ),
        ConfirmedServiceDay(
            date(2026, 8, 2),
            1,
            "historical daily service confirmed",
        ),
    )

    try:
        assert repository.list_caregiver_options(_CASE_NO) == (
            {"staff_id": 1, "display_name": "Historical Inactive Staff"},
        )
        before = repository.load_for_preview(_CASE_NO, ())
        assert before.order.actual_start_date is None
        assert before.order.service_started is False
        assert before.historical_cancellation_origin is True

        preview = workflow.preview(_CASE_NO, confirmed_days)
        assert preview.candidate.actual_start_date == date(2026, 8, 1)
        assert preview.candidate.actual_end_date == date(2026, 8, 2)
        assert preview.candidate.official_service_day_count == 2
        assert preview.candidate.official_service_hours == 16
        assert len(preview.candidate.scheduling.assignments) == 1
        assert preview.candidate.scheduling.assignments[0].staff_id == 1
        assert preview.candidate.scheduling.assignments[0].source_assignment_id is None
        assert preview.payroll_impact.payroll.total_payable.amount > 0

        request = OrderCancellationApplyRequest(
            _CASE_NO,
            confirmed_days,
            ExpectedVersion(preview.order_version),
            ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),
            ExpectedVersion(preview.payroll_version),
            preview.fingerprint,
            IdempotencyKey("historical-mid-service-cancellation"),
            ActorContext("historical-remediation-test"),
            "confirm actual historical service before cancellation",
            CorrelationId("historical-mid-service-cancellation"),
        )
        receipt = workflow.apply(request)
        assert workflow.apply(request) == receipt
        assert receipt.official_service_day_count == 2
        assert receipt.official_service_hours == 16

        after = repository.load_for_preview(_CASE_NO, ())
        assert after.order.actual_start_date == date(2026, 8, 1)
        assert after.order.service_started is True
        assert after.historical_cancellation_origin is False
    finally:
        connection.close()

    _assert_persisted_owner_roots()
    _assert_no_payment_facts_fabricated()


def _seed_historical_cancelled_case() -> None:
    from domains.bootstrap.case_architecture import (
        CaseArchitectureBootstrapIntent,
        ClientPaymentTermsRootFacts,
    )
    from infrastructure.mysql.case_architecture_bootstrap_repository import (
        MySqlCaseArchitectureBootstrapRepository,
    )
    from infrastructure.mysql.historical_assignment_writer import (
        MySqlHistoricalAssignmentWriter,
    )
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from shared_kernel.money import MoneyNTD
    from subsystems.bootstrap.case_architecture_workflow import (
        CaseArchitectureBootstrapWorkflow,
        EnsureCaseArchitectureBootstrap,
    )
    from subsystems.orders.order_lifecycle_command_envelope import (
        lock_order_lifecycle_command_envelope,
    )
    from subsystems.orders.order_lifecycle_control_commands import (
        CancellationControlCommand,
        apply_order_lifecycle_control_command,
    )

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients(case_no,name,identity_status) "
                "VALUES (%s,'Historical Client','一般市民')",
                (_CASE_NO,),
            )
            client_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO staff(name,status) "
                "VALUES ('Historical Inactive Staff','inactive')"
            )
            assert int(cursor.lastrowid) == 1
            cursor.execute(
                "INSERT INTO orders "
                "(case_no,client_id,status,lifecycle_version,start_date,"
                "service_days,service_hours_per_day,floor_fee,"
                "service_start_time,service_end_time,service_end_day_offset,"
                "actual_start_date,actual_end_date,staff_payment_due_date) "
                "VALUES (%s,%s,'洽談中',0,'2026-08-01',6,8,400,"
                "'09:00:00','17:00:00',0,NULL,NULL,'2026-09-15')",
                (_CASE_NO, client_id),
            )
        connection.commit()

        repository = MySqlCaseArchitectureBootstrapRepository(connection)
        bootstrap_workflow = CaseArchitectureBootstrapWorkflow(
            repository,
            lambda: MySqlUnitOfWork(connection),
        )
        intent = CaseArchitectureBootstrapIntent(
            _CASE_NO,
            ClientPaymentTermsRootFacts(
                "historical-client-policy-v1",
                MoneyNTD(100),
                5,
                date(2026, 7, 20),
                date(2026, 8, 1),
            ),
            "approved-rates-v1",
        )
        preview = bootstrap_workflow.preview(
            intent,
            CorrelationId("historical-bootstrap-preview"),
        )
        bootstrap_workflow.ensure(
            EnsureCaseArchitectureBootstrap(
                intent,
                ExpectedVersion(0),
                preview.fingerprint,
                IdempotencyKey("historical-bootstrap"),
                ActorContext("historical-import"),
                "bootstrap historical owner roots",
                CorrelationId("historical-bootstrap-apply"),
            )
        )

        MySqlHistoricalAssignmentWriter(connection).append_completed_assignments(
            _CASE_NO,
            ((1, date(2026, 8, 1), date(2026, 8, 6)),),
        )

        with connection.cursor() as cursor:
            historical_key = "historical-adoption-control"
            envelope = lock_order_lifecycle_command_envelope(
                cursor,
                _CASE_NO,
                0,
                historical_key,
            )
            apply_order_lifecycle_control_command(
                cursor,
                envelope,
                CancellationControlCommand(
                    "activate",
                    "historical-import",
                    "historical_order_adoption:source status 0",
                    0,
                    historical_key,
                ),
            )
            cursor.execute(
                "UPDATE orders SET status='訂單取消',lifecycle_version=1 "
                "WHERE case_no=%s AND lifecycle_version=0",
                (_CASE_NO,),
            )
            assert cursor.rowcount == 1
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events "
                "(case_no,trigger_event,before_status,after_status,actor,"
                "business_date,expected_version,idempotency_key,facts_snapshot) "
                "VALUES (%s,'historical_order_adoption','洽談中','訂單取消',"
                "'historical-import','2026-08-04',0,%s,%s)",
                (
                    _CASE_NO,
                    historical_key,
                    json.dumps(
                        {"source_status": 0},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _assert_persisted_owner_roots() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status,lifecycle_version,actual_start_date,actual_end_date "
                "FROM orders WHERE case_no=%s",
                (_CASE_NO,),
            )
            assert cursor.fetchone() == {
                "status": "訂單取消",
                "lifecycle_version": 2,
                "actual_start_date": date(2026, 8, 1),
                "actual_end_date": date(2026, 8, 2),
            }

            cursor.execute(
                "SELECT aggregate_version,generation_counter,effective_generation_id "
                "FROM scheduling_aggregates WHERE case_no=%s",
                (_CASE_NO,),
            )
            aggregate = cursor.fetchone()
            assert aggregate["aggregate_version"] == 1
            assert aggregate["generation_counter"] == 1
            assert aggregate["effective_generation_id"] is not None

            cursor.execute(
                "SELECT id,staff_id,generation_id,status FROM case_staff_assignments "
                "WHERE case_no=%s ORDER BY id",
                (_CASE_NO,),
            )
            assignments = cursor.fetchall()
            assert len(assignments) == 2
            assert assignments[0]["staff_id"] == 1
            assert assignments[0]["generation_id"] is None
            assert assignments[0]["status"] == "completed"
            assert assignments[1]["staff_id"] == 1
            assert assignments[1]["generation_id"] == aggregate["effective_generation_id"]

            cursor.execute(
                "SELECT work_date FROM staff_schedule "
                "WHERE generation_id=%s AND is_work_day=1 "
                "AND effective_marker=1 ORDER BY work_date",
                (aggregate["effective_generation_id"],),
            )
            assert tuple(row["work_date"] for row in cursor.fetchall()) == (
                date(2026, 8, 1),
                date(2026, 8, 2),
            )

            cursor.execute(
                "SELECT aggregate_version FROM payroll_case_accounts "
                "WHERE case_no=%s",
                (_CASE_NO,),
            )
            assert cursor.fetchone() == {"aggregate_version": 1}
            cursor.execute(
                "SELECT staff_id,obligation_kind,direction,amount_due_ntd,"
                "due_date,status FROM staff_obligations WHERE case_no=%s",
                (_CASE_NO,),
            )
            obligation = cursor.fetchone()
            assert obligation["staff_id"] == 1
            assert obligation["obligation_kind"] == "service_pay"
            assert obligation["direction"] == "payable_to_staff"
            assert obligation["amount_due_ntd"] > 0
            assert obligation["due_date"] == date(2026, 9, 15)
            assert obligation["status"] == "open"

            cursor.execute(
                "SELECT source_identity_status FROM assignment_payroll_rate_snapshots "
                "WHERE assignment_id=%s",
                (assignments[1]["id"],),
            )
            assert cursor.fetchone() == {"source_identity_status": "case-policy"}

            cursor.execute(
                "SELECT facts_snapshot FROM order_lifecycle_state_events "
                "WHERE case_no=%s AND trigger_event='order_cancellation_applied'",
                (_CASE_NO,),
            )
            lifecycle_facts = cursor.fetchone()["facts_snapshot"]
            if isinstance(lifecycle_facts, str):
                lifecycle_facts = json.loads(lifecycle_facts)
            assert lifecycle_facts["actual_start_date"] == "2026-08-01"
            assert lifecycle_facts["actual_end_date"] == "2026-08-02"

            cursor.execute(
                "SELECT COUNT(*) AS count FROM order_cancellation_events "
                "WHERE case_no=%s",
                (_CASE_NO,),
            )
            assert cursor.fetchone() == {"count": 1}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM order_cancellation_apply_receipts "
                "WHERE case_no=%s",
                (_CASE_NO,),
            )
            assert cursor.fetchone() == {"count": 1}
    finally:
        connection.close()


def _assert_no_payment_facts_fabricated() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM client_ledger_entries "
                "WHERE case_no=%s",
                (_CASE_NO,),
            )
            assert cursor.fetchone() == {"count": 0}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM staff_payout_events "
                "WHERE staff_id=1",
            )
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()

"""
File: test_payroll_rebuild_durable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Payroll Rebuild Bridge replay、crash recovery 與單次 Domain Apply。
"""

from __future__ import annotations

from datetime import date
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from tests.test_assignment_plan_durable_mysql_e2e import (
    _arguments,
    _seed_waiting_lock_case,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _apply_assignment_plan(connection, staff_id):
    from api.dependencies.assignment_plan import build_assignment_plan_application
    from domains.scheduling.assignment_plan import (
        AssignmentPlanIntent,
        AssignmentPlanSegmentIntent,
    )
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.scheduling.assignment_plan_workflow import (
        AssignmentPlanApplyRequest,
        AssignmentPlanPreviewRequest,
    )

    intent = AssignmentPlanIntent((
        AssignmentPlanSegmentIntent(
            staff_id,
            date(2026, 8, 1),
            date(2026, 8, 2),
            (date(2026, 8, 1), date(2026, 8, 2)),
        ),
    ))
    application = build_assignment_plan_application(connection)
    preview = application.preview(
        AssignmentPlanPreviewRequest("AP-DURABLE-1", intent, CorrelationId("assignment-preview"))
    )
    return application.apply(
        AssignmentPlanApplyRequest(
            "AP-DURABLE-1", intent,
            ExpectedVersion(preview.order_version),
            ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),
            ExpectedVersion(preview.payroll_version),
            preview.fingerprint,
            IdempotencyKey("assignment-bootstrap"),
            ActorContext("durable-test"),
            "create canonical payroll facts",
            CorrelationId("assignment-apply"),
        )
    )


def test_payroll_rebuild_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.payroll_rebuild import build_payroll_rebuild_application
    from api.routes.payroll_rebuild import apply_payroll_rebuild
    from api.schemas.payroll_rebuild import PayrollRebuildApplyBody
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.access.authentication_session import AdminPrincipal
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker
    from subsystems.jobs.command_application import DurableJobCommandApplication

    connection = get_connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        _apply_assignment_plan(connection, staff_id)
        preview = build_payroll_rebuild_application(connection).preview("AP-DURABLE-1")
        body = PayrollRebuildApplyBody(
            expected_payroll_version=preview.payroll_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable payroll rebuild e2e",
        )
        repository = BackgroundJobRepository(connection)
        job_application = DurableJobCommandApplication(repository, connection)
        apply_kwargs = {
            "body": body,
            "case_no": "AP-DURABLE-1",
            "idempotency_key": "payroll-rebuild-durable-apply",
            "correlation_id": "payroll-rebuild-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": job_application,
        }
        apply_payroll_rebuild(**apply_kwargs)
        response = apply_payroll_rebuild(**apply_kwargs)
        job_id = response.data.job_id
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM background_jobs")
            assert cursor.fetchone() == {"count": 1}
        connection.begin()
        assert repository.claim_next_canonical_command("crashed-worker", 60) is not None
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE background_jobs SET lease_expires_at="
                "DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) WHERE job_id=%s",
                (job_id,),
            )
        connection.commit()
    finally:
        connection.close()

    worker_connection = get_connection()
    try:
        worker = DurableJobWorker(
            BackgroundJobRepository(worker_connection),
            worker_connection,
            default_job_handlers(),
            "payroll-rebuild-durable-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        assert stored.result_reference == "payroll_rebuild:AP-DURABLE-1"
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM payroll_apply_receipts")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()

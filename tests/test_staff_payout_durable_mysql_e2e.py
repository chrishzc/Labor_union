"""
File: test_staff_payout_durable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Staff Payout 全事件 Bridge replay 與 crash recovery。
"""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import os

import pytest

from subsystems.jobs.command_application import DurableJobCommandApplication

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from tests.test_assignment_plan_durable_mysql_e2e import _seed_waiting_lock_case


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch):
    import infrastructure.mysql.mysql_adapter as mysql_adapter

    monkeypatch.setattr(
        mysql_adapter,
        "DB_CONFIG",
        {
            "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
            "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
            "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
            "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
            "database": DATABASE,
            "charset": "utf8mb4",
        },
    )


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _apply_assignment_plan(connection, staff_id: int) -> None:
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
            staff_id, date(2026, 8, 1), date(2026, 8, 2),
            (date(2026, 8, 1), date(2026, 8, 2)),
        ),
    ))
    application = build_assignment_plan_application(connection)
    preview = application.preview(
        AssignmentPlanPreviewRequest("AP-DURABLE-1", intent, CorrelationId("assignment-preview"))
    )
    application.apply(
        AssignmentPlanApplyRequest(
            "AP-DURABLE-1", intent, ExpectedVersion(preview.order_version),
            ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),
            ExpectedVersion(preview.payroll_version), preview.fingerprint,
            IdempotencyKey("assignment-bootstrap"), ActorContext("durable-test"),
            "create canonical payroll facts", CorrelationId("assignment-apply"),
        )
    )


def _seed_payout_roots(connection, staff_id: int) -> tuple[int, str]:
    case_no = "AP-DURABLE-1"
    obligation_identity = "staff-obligation-durable-payout"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM case_staff_assignments WHERE case_no=%s AND staff_id=%s",
            (case_no, staff_id),
        )
        assignment_id = cursor.fetchone()["id"]
        cursor.execute(
            "SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s",
            (case_no,),
        )
        payroll_version = cursor.fetchone()["aggregate_version"]
        cursor.execute(
            "INSERT INTO staff_obligation_events (obligation_identity,assignment_id,case_no,staff_id,"
            "obligation_kind,direction,event_type,before_amount_ntd,after_amount_ntd,due_date,"
            "payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) "
            "VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,2400,%s,%s,%s,%s,%s,'test','fixture')",
            (obligation_identity, assignment_id, case_no, staff_id, date(2026, 8, 15), "a" * 64,
             payroll_version, payroll_version + 1, f"{obligation_identity}-event"),
        )
        event_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO staff_obligations (obligation_identity,assignment_id,case_no,staff_id,"
            "obligation_kind,direction,amount_due_ntd,due_date,status,current_event_id,payroll_version) "
            "VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',2400,%s,'open',%s,%s)",
            (obligation_identity, assignment_id, case_no, staff_id, date(2026, 8, 15), event_id,
             payroll_version + 1),
        )
        cursor.execute(
            "INSERT INTO staff_bank_accounts (staff_id,bank_code,branch_code,account_no,is_primary) "
            "VALUES (%s,'001','0001','PAYOUT-ACCOUNT',1)",
            (staff_id,),
        )
        cursor.execute(
            "INSERT INTO finance_import_rows (dedup_fingerprint,format_id,transaction_date,debit,credit,"
            "direction,currency,resolved_counterparty_account,bank_references,warnings,raw_payload,"
            "classification_type,reconciliation_status) "
            "VALUES (%s,'legacy',%s,2400,0,'outgoing','TWD','PAYOUT-ACCOUNT',JSON_ARRAY(),JSON_ARRAY(),"
            "JSON_OBJECT(),'staff_payout','pending')",
            ("b" * 64, date(2026, 8, 16)),
        )
        row_id = cursor.lastrowid
    connection.commit()
    return row_id, obligation_identity


def _apply_payout_source(connection, row_id: int, obligation_identity: str) -> int:
    from api.dependencies.staff_payout import build_staff_payout_application
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.staff_payables.payout_reconciliation import (
        StaffPayoutApplyRequest,
        StaffPayoutEventType,
        StaffPayoutSelection,
    )

    selection = StaffPayoutSelection(
        StaffPayoutEventType.PAYOUT, (str(row_id),), (obligation_identity,)
    )
    application = build_staff_payout_application(connection)
    preview = application.preview(selection, CorrelationId("payout-source-preview"))
    application.apply(
        StaffPayoutApplyRequest(
            selection,
            ExpectedVersion(preview.staff_payables_version),
            ExpectedVersion(preview.bank_facts_version),
            preview.fingerprint,
            IdempotencyKey("payout-source-apply"),
            ActorContext("durable-test"),
            "create return source payout",
            CorrelationId("payout-source-apply"),
        )
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM staff_payout_events WHERE event_type='payout'")
        return cursor.fetchone()["id"]


def _seed_return_bank_fact(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO finance_import_rows (dedup_fingerprint,format_id,transaction_date,debit,credit,"
            "direction,currency,resolved_counterparty_account,bank_references,warnings,raw_payload,"
            "classification_type,reconciliation_status) "
            "VALUES (%s,'legacy',%s,0,2400,'incoming','TWD','PAYOUT-ACCOUNT',JSON_ARRAY(),JSON_ARRAY(),"
            "JSON_OBJECT(),'staff_payout_return','pending')",
            ("c" * 64, date(2026, 8, 17)),
        )
        row_id = cursor.lastrowid
    connection.commit()
    return row_id


def test_staff_payout_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.staff_payout import build_staff_payout_application
    from api.routes.staff_payout import apply_payout
    from api.schemas.staff_payout import PayoutApplyBody
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.access.authentication_session import AdminPrincipal
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker
    from subsystems.staff_payables.payout_reconciliation import (
        StaffPayoutEventType,
        StaffPayoutSelection,
    )

    connection = get_connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        _apply_assignment_plan(connection, staff_id)
        row_id, obligation_identity = _seed_payout_roots(connection, staff_id)
        selection = StaffPayoutSelection(
            StaffPayoutEventType.PAYOUT,
            (str(row_id),),
            (obligation_identity,),
        )
        preview = build_staff_payout_application(connection).preview(
            selection, CorrelationId("staff-payout-preview")
        )
        body = PayoutApplyBody(
            finance_import_row_ids=[row_id],
            obligation_identities=[obligation_identity],
            expected_bank_facts_version=preview.bank_facts_version,
            expected_staff_payables_version=preview.staff_payables_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable staff payout e2e",
        )
        repository = BackgroundJobRepository(connection)
        apply_kwargs = {
            "body": body,
            "idempotency_key": "staff-payout-durable-apply",
            "correlation_id": "staff-payout-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_payout(**apply_kwargs)
        response = apply_payout(**apply_kwargs)
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
            "staff-payout-durable-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        assert stored.receipt_payload == {
            "kind": "success",
            "result_reference": f"staff_payout:{staff_id}",
            "schema_version": 1,
        }
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM staff_payout_events")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM staff_payables_apply_receipts")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()


def test_staff_payout_return_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.staff_payout import build_staff_payout_application
    from api.routes.staff_payout import _return_selection, apply_return
    from api.schemas.staff_payout import ReturnApplyBody, ReturnPreviewBody
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.access.authentication_session import AdminPrincipal
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker

    connection = get_connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        _apply_assignment_plan(connection, staff_id)
        payout_row_id, obligation_identity = _seed_payout_roots(connection, staff_id)
        source_payout_event_id = _apply_payout_source(connection, payout_row_id, obligation_identity)
        return_row_id = _seed_return_bank_fact(connection)
        preview_request = ReturnPreviewBody(
            return_finance_import_row_id=return_row_id,
            source_payout_event_id=source_payout_event_id,
            obligation_identities=[obligation_identity],
        )
        preview = build_staff_payout_application(connection).preview(
            _return_selection(preview_request), CorrelationId("staff-return-preview")
        )
        body = ReturnApplyBody(
            **preview_request.model_dump(),
            expected_bank_facts_version=preview.bank_facts_version,
            expected_staff_payables_version=preview.staff_payables_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable staff return e2e",
        )
        repository = BackgroundJobRepository(connection)
        apply_kwargs = {
            "body": body,
            "idempotency_key": "staff-return-durable-apply",
            "correlation_id": "staff-return-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_return(**apply_kwargs)
        response = apply_return(**apply_kwargs)
        job_id = response.data.job_id
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
            "staff-return-durable-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        assert stored.receipt_payload == {
            "kind": "success",
            "result_reference": f"staff_payout:{staff_id}",
            "schema_version": 1,
        }
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM staff_payout_events")
            assert cursor.fetchone() == {"count": 2}
            cursor.execute("SELECT COUNT(*) AS count FROM staff_payables_apply_receipts")
            assert cursor.fetchone() == {"count": 2}
    finally:
        worker_connection.close()


def test_staff_payout_reversal_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.staff_payout import build_staff_payout_application
    from api.routes.staff_payout import _reversal_selection, apply_reversal
    from api.schemas.staff_payout import ReversalApplyBody, ReversalPreviewBody
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.access.authentication_session import AdminPrincipal
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker

    connection = get_connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        _apply_assignment_plan(connection, staff_id)
        payout_row_id, obligation_identity = _seed_payout_roots(connection, staff_id)
        source_payout_event_id = _apply_payout_source(connection, payout_row_id, obligation_identity)
        preview_request = ReversalPreviewBody(
            source_payout_event_id=source_payout_event_id,
            occurred_on=date(2026, 8, 18),
            obligation_identities=[obligation_identity],
        )
        preview = build_staff_payout_application(connection).preview(
            _reversal_selection(preview_request), CorrelationId("staff-reversal-preview")
        )
        body = ReversalApplyBody(
            **preview_request.model_dump(),
            expected_bank_facts_version=preview.bank_facts_version,
            expected_staff_payables_version=preview.staff_payables_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable staff reversal e2e",
        )
        repository = BackgroundJobRepository(connection)
        apply_kwargs = {
            "body": body,
            "idempotency_key": "staff-reversal-durable-apply",
            "correlation_id": "staff-reversal-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_reversal(**apply_kwargs)
        response = apply_reversal(**apply_kwargs)
        job_id = response.data.job_id
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
            "staff-reversal-durable-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        assert stored.receipt_payload == {
            "kind": "success",
            "result_reference": f"staff_payout:{staff_id}",
            "schema_version": 1,
        }
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM staff_payout_events")
            assert cursor.fetchone() == {"count": 2}
            cursor.execute("SELECT COUNT(*) AS count FROM staff_payables_apply_receipts")
            assert cursor.fetchone() == {"count": 2}
    finally:
        worker_connection.close()

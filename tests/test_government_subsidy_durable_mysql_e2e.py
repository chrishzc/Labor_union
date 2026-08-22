"""
File: test_government_subsidy_durable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Government Subsidy 全 action Bridge replay 與 crash recovery。
"""

from __future__ import annotations

from argparse import Namespace
import os

import pytest

from subsystems.jobs.command_application import DurableJobCommandApplication

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from tests.test_finance_import_disposable_mysql_e2e import _insert_finance_row
from tests.test_staff_payout_durable_mysql_e2e import _apply_assignment_plan
from tests.test_assignment_plan_durable_mysql_e2e import _seed_waiting_lock_case


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch):
    from infrastructure.mysql import mysql_adapter

    settings = {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": DATABASE,
        "charset": "utf8mb4",
    }
    monkeypatch.setattr(mysql_adapter, "DB_CONFIG", settings)


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _seed_receiptable_batch() -> tuple[int, int, int]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        _apply_assignment_plan(connection, staff_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM case_staff_assignments WHERE case_no=%s AND staff_id=%s",
                ("AP-DURABLE-1", staff_id),
            )
            assignment_id = cursor.fetchone()["id"]
            cursor.execute(
                "INSERT INTO subsidy_claim_batches "
                "(application_year,quarter,revision,status,requested_amount,approved_amount,paid_amount,submitted_at,approved_at) "
                "VALUES (2026,3,1,'approved',4800,4800,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
            batch_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO subsidy_claim_batch_items "
                "(batch_id,case_no,assignment_id,staff_id,claimed_hours,unit_price,requested_amount,approved_amount) "
                "VALUES (%s,'AP-DURABLE-1',%s,%s,16,300,4800,4800)",
                (batch_id, assignment_id, staff_id),
            )
            item_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO government_subsidy_batch_accounts "
                "(batch_id,aggregate_version,requested_total_ntd,approved_total_ntd,"
                "net_allocated_ntd,outstanding_ntd,status) "
                "VALUES (%s,1,4800,4800,0,4800,'approved')",
                (batch_id,),
            )
            row_id = _insert_finance_row(cursor, "b", "incoming", "2026-08-03", credit=4800)
            cursor.execute(
                "UPDATE finance_import_rows SET classification_type='government_subsidy' WHERE id=%s",
                (row_id,),
            )
        connection.commit()
        return batch_id, item_id, row_id
    finally:
        connection.close()


def test_government_subsidy_receipt_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from api.routes.government_subsidy import apply_government_subsidy_receipt
    from api.routes.government_subsidy import GovernmentSubsidyReceiptApplyBody
    from api.schemas.government_subsidy import (
        GovernmentSubsidyAllocationIntentView,
        GovernmentSubsidyReceiptIntentView,
    )
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers
    from domains.government_subsidy.ledger import AllocationIntent, ReceiptIntent
    from shared_kernel.money import MoneyNTD

    batch_id, item_id, row_id = _seed_receiptable_batch()
    connection = get_connection()
    try:
        intent = ReceiptIntent(row_id, batch_id, (AllocationIntent(item_id, MoneyNTD(4800)),))
        preview = build_government_subsidy_application(connection).preview_receipt(intent)
        body = GovernmentSubsidyReceiptApplyBody(
            intent=GovernmentSubsidyReceiptIntentView(
                finance_import_row_id=row_id,
                batch_id=batch_id,
                allocations=[GovernmentSubsidyAllocationIntentView(target_identity=item_id, amount_ntd=4800)],
            ),
            expected_batch_version=preview.candidate.expected_batch_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable government receipt e2e",
        )
        repository = BackgroundJobRepository(connection)
        kwargs = {
            "body": body,
            "idempotency_key": "government-receipt-durable-apply",
            "correlation_id": "government-receipt-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_government_subsidy_receipt(**kwargs)
        response = apply_government_subsidy_receipt(**kwargs)
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
            "government-receipt-durable-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM government_subsidy_transactions")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()


def test_government_subsidy_claim_plan_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from api.routes.government_subsidy import apply_government_subsidy_claim_plan
    from api.schemas.government_subsidy import (
        GovernmentSubsidyClaimPlanningApplyBody,
        GovernmentSubsidyClaimPlanningIntentView,
    )
    from domains.government_subsidy.claims import ClaimPlanningIntent
    from domains.government_subsidy.ledger import ClaimBatchIdentity
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers

    connection = get_connection()
    try:
        staff_id = _seed_waiting_lock_case(connection)
        _apply_assignment_plan(connection, staff_id)
        preview = build_government_subsidy_application(connection).preview_claim_plan(
            ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1))
        )
        body = GovernmentSubsidyClaimPlanningApplyBody(
            intent=GovernmentSubsidyClaimPlanningIntentView(
                application_year=2026, quarter=3, revision=1
            ),
            expected_batch_version=preview.candidate.expected_batch_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable government claim plan e2e",
        )
        repository = BackgroundJobRepository(connection)
        kwargs = {
            "body": body,
            "idempotency_key": "government-claim-plan-durable-apply",
            "correlation_id": "government-claim-plan-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_government_subsidy_claim_plan(**kwargs)
        response = apply_government_subsidy_claim_plan(**kwargs)
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
            "government-claim-plan-durable-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM subsidy_claim_batches")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM government_subsidy_claim_apply_receipts")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()


def _create_draft_claim_batch(connection) -> int:
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from domains.government_subsidy.claims import ClaimPlanningIntent
    from domains.government_subsidy.ledger import ClaimBatchIdentity
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.government_subsidy.claim_workflow import ClaimPlanningApplyRequest

    staff_id = _seed_waiting_lock_case(connection)
    _apply_assignment_plan(connection, staff_id)
    application = build_government_subsidy_application(connection)
    intent = ClaimPlanningIntent(ClaimBatchIdentity(2026, 3, 1))
    preview = application.preview_claim_plan(intent)
    receipt = application.apply_claim_plan(ClaimPlanningApplyRequest(
        intent, ExpectedVersion(preview.candidate.expected_batch_version), preview.fingerprint,
        IdempotencyKey("claim-plan-source"), ActorContext("durable-test"),
        "create submission source", CorrelationId("claim-plan-source"),
    ))
    return receipt.batch_id


def test_government_subsidy_submission_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from api.routes.government_subsidy import apply_government_subsidy_claim_submission
    from api.schemas.government_subsidy import GovernmentSubsidyClaimSubmissionApplyBody
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.government_subsidy.claim_workflow import ClaimSubmissionIntent
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers

    connection = get_connection()
    try:
        batch_id = _create_draft_claim_batch(connection)
        preview = build_government_subsidy_application(connection).preview_claim_submission(
            ClaimSubmissionIntent(batch_id)
        )
        body = GovernmentSubsidyClaimSubmissionApplyBody(
            expected_batch_version=preview.candidate.expected_batch_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable government submission e2e",
        )
        repository = BackgroundJobRepository(connection)
        kwargs = {
            "body": body, "batch_id": batch_id,
            "idempotency_key": "government-submission-durable-apply",
            "correlation_id": "government-submission-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_government_subsidy_claim_submission(**kwargs)
        response = apply_government_subsidy_claim_submission(**kwargs)
        job_id = response.data.job_id
        connection.begin()
        assert repository.claim_next_canonical_command("crashed-worker", 60) is not None
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE background_jobs SET lease_expires_at=DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) WHERE job_id=%s", (job_id,))
        connection.commit()
    finally:
        connection.close()

    worker_connection = get_connection()
    try:
        worker = DurableJobWorker(BackgroundJobRepository(worker_connection), worker_connection, default_job_handlers(), "government-submission-durable-worker", retry_delay_seconds=0)
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM government_subsidy_claim_submission_events")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()


def _submit_claim_batch(connection) -> tuple[int, int, int]:
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.government_subsidy.claim_workflow import (
        ClaimSubmissionApplyRequest,
        ClaimSubmissionIntent,
    )

    batch_id = _create_draft_claim_batch(connection)
    application = build_government_subsidy_application(connection)
    intent = ClaimSubmissionIntent(batch_id)
    preview = application.preview_claim_submission(intent)
    application.apply_claim_submission(ClaimSubmissionApplyRequest(
        intent, ExpectedVersion(preview.candidate.expected_batch_version), preview.fingerprint,
        IdempotencyKey("claim-submission-source"), ActorContext("durable-test"),
        "create approval source", CorrelationId("claim-submission-source"),
    ))
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,requested_amount FROM subsidy_claim_batch_items WHERE batch_id=%s", (batch_id,))
        item = cursor.fetchone()
    return batch_id, item["id"], int(item["requested_amount"])


def test_government_subsidy_approval_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from api.routes.government_subsidy import apply_government_subsidy_claim_approval
    from api.schemas.government_subsidy import (
        GovernmentSubsidyClaimApprovalApplyBody,
        GovernmentSubsidyApprovalItemView,
    )
    from domains.government_subsidy.claims import ClaimApprovalIntent
    from domains.government_subsidy.ledger import AllocationIntent
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.money import MoneyNTD
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers

    connection = get_connection()
    try:
        batch_id, item_id, requested_amount = _submit_claim_batch(connection)
        intent = ClaimApprovalIntent(batch_id, (AllocationIntent(item_id, MoneyNTD(requested_amount)),))
        preview = build_government_subsidy_application(connection).preview_claim_approval(intent)
        body = GovernmentSubsidyClaimApprovalApplyBody(
            item_approvals=[GovernmentSubsidyApprovalItemView(item_id=item_id, approved_amount_ntd=requested_amount)],
            expected_batch_version=preview.candidate.expected_batch_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable government approval e2e",
        )
        repository = BackgroundJobRepository(connection)
        kwargs = {
            "body": body, "batch_id": batch_id,
            "idempotency_key": "government-approval-durable-apply",
            "correlation_id": "government-approval-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_government_subsidy_claim_approval(**kwargs)
        response = apply_government_subsidy_claim_approval(**kwargs)
        job_id = response.data.job_id
        connection.begin()
        assert repository.claim_next_canonical_command("crashed-worker", 60) is not None
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE background_jobs SET lease_expires_at=DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) WHERE job_id=%s", (job_id,))
        connection.commit()
    finally:
        connection.close()

    worker_connection = get_connection()
    try:
        worker = DurableJobWorker(BackgroundJobRepository(worker_connection), worker_connection, default_job_handlers(), "government-approval-durable-worker", retry_delay_seconds=0)
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM government_subsidy_claim_approval_events")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()


def test_government_subsidy_reversal_durable_crash_recovery_and_duplicate_apply():
    bootstrap(_arguments())
    from api.dependencies.government_subsidy import build_government_subsidy_application
    from api.routes.government_subsidy import (
        GovernmentSubsidyReversalApplyBody,
        apply_government_subsidy_reversal,
    )
    from api.schemas.government_subsidy import GovernmentSubsidyReversalIntentView
    from domains.government_subsidy.ledger import AllocationIntent, ReceiptIntent, ReversalIntent
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from shared_kernel.money import MoneyNTD
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.government_subsidy.ledger_workflow import GovernmentSubsidyReceiptApplyRequest
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers

    batch_id, item_id, receipt_row_id = _seed_receiptable_batch()
    connection = get_connection()
    try:
        application = build_government_subsidy_application(connection)
        receipt_intent = ReceiptIntent(receipt_row_id, batch_id, (AllocationIntent(item_id, MoneyNTD(4800)),))
        receipt_preview = application.preview_receipt(receipt_intent)
        source_receipt = application.apply_receipt(GovernmentSubsidyReceiptApplyRequest(
            receipt_intent, ExpectedVersion(receipt_preview.candidate.expected_batch_version),
            receipt_preview.fingerprint, IdempotencyKey("reversal-source-receipt"),
            ActorContext("durable-test"), "create reversal source", CorrelationId("reversal-source-receipt"),
        ))
        with connection.cursor() as cursor:
            reversal_row_id = _insert_finance_row(cursor, "c", "outgoing", "2026-08-04", debit=4800)
            cursor.execute("UPDATE finance_import_rows SET classification_type='government_subsidy' WHERE id=%s", (reversal_row_id,))
        connection.commit()
        reversal_intent = ReversalIntent(reversal_row_id, source_receipt.transaction_id)
        preview = application.preview_reversal(reversal_intent)
        body = GovernmentSubsidyReversalApplyBody(
            intent=GovernmentSubsidyReversalIntentView(
                finance_import_row_id=reversal_row_id,
                source_receipt_id=source_receipt.transaction_id,
            ),
            expected_batch_version=preview.candidate.expected_batch_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="durable government reversal e2e",
        )
        repository = BackgroundJobRepository(connection)
        kwargs = {
            "body": body,
            "idempotency_key": "government-reversal-durable-apply",
            "correlation_id": "government-reversal-durable-apply",
            "principal": AdminPrincipal(1, "durable-test", "Durable Test", "system_admin"),
            "job_application": DurableJobCommandApplication(repository, connection),
        }
        apply_government_subsidy_reversal(**kwargs)
        response = apply_government_subsidy_reversal(**kwargs)
        job_id = response.data.job_id
        connection.begin()
        assert repository.claim_next_canonical_command("crashed-worker", 60) is not None
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE background_jobs SET lease_expires_at=DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) WHERE job_id=%s", (job_id,))
        connection.commit()
    finally:
        connection.close()

    worker_connection = get_connection()
    try:
        worker = DurableJobWorker(BackgroundJobRepository(worker_connection), worker_connection, default_job_handlers(), "government-reversal-durable-worker", retry_delay_seconds=0)
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.attempt_count == 2
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM government_subsidy_transactions")
            assert cursor.fetchone() == {"count": 2}
    finally:
        worker_connection.close()

"""Real workbook proof that a durable worker owns Finance Import batch Apply."""

from __future__ import annotations

from argparse import Namespace
import os
import uuid

import pandas as pd
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
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


def test_g16_durable_worker_crash_recovery_and_duplicate_delivery_apply_once(tmp_path):
    bootstrap(_arguments())
    workbook = tmp_path / "durable-finance-import.xlsx"
    pd.DataFrame(
        [
            ["說明"],
            ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"],
            ["0001", "2026/08/04", "09:08:07", "2026/08/04", "轉帳", "300", "", "9000", "客戶退款 0012345678901234"],
        ]
    ).to_excel(workbook, sheet_name="交易明細", index=False, header=False)

    from api.dependencies.finance_import import build_finance_import_application
    from api.routes.finance_import import _batch_apply_job_command
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from scripts.imports.finance_statement_normalizer import normalize_workbook
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker

    ingestion = ingest_finance_workbook(
        str(workbook),
        IdempotencyKey("durable-finance-ingest"),
        ActorContext("durable-test"),
        connection_factory=get_connection,
        normalizer=normalize_workbook,
    )
    connection = get_connection()
    try:
        application = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        )
        preview = application.preview_batch(
            ingestion.batch_identity,
            CorrelationId("durable-finance-preview"),
        )
        request = FinanceImportApplyRequest(
            ingestion.batch_identity,
            ExpectedVersion(preview.batch_version),
            preview.fingerprint,
            IdempotencyKey("durable-finance-apply"),
            ActorContext("durable-test"),
            "durable worker e2e",
            CorrelationId("durable-finance-apply"),
        )
        job_id = "durable-finance-job-" + uuid.uuid4().hex
        repository = BackgroundJobRepository(connection)
        connection.begin()
        repository.enqueue_canonical_command(_batch_apply_job_command(job_id, request))
        connection.commit()
        connection.begin()
        crashed_lease = repository.claim_next_canonical_command("crashed-worker", 60)
        connection.commit()
        assert crashed_lease is not None
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE background_jobs SET lease_expires_at = "
                "DATE_SUB(CURRENT_TIMESTAMP(6), INTERVAL 1 SECOND) "
                "WHERE job_id = %s",
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
            "durable-test-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.receipt_payload["batch_identity"] == ingestion.batch_identity
        assert stored.attempt_count == 2
        assert worker.recover_and_run_once() is False
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM finance_import_apply_receipts")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()


def test_g07_timeout_retry_enqueues_and_applies_one_cross_domain_command(tmp_path):
    """A lost HTTP response reuses one persisted Finance Import command."""
    bootstrap(_arguments())
    workbook = tmp_path / "timeout-retry-finance-import.xlsx"
    pd.DataFrame(
        [
            ["說明"],
            ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"],
            ["0001", "2026/08/04", "09:08:07", "2026/08/04", "轉帳", "300", "", "9000", "客戶退款 0012345678901234"],
        ]
    ).to_excel(workbook, sheet_name="交易明細", index=False, header=False)

    from api.dependencies.finance_import import build_finance_import_application
    from api.routes.finance_import import apply_finance_import_batch
    from api.schemas.finance_import import FinanceImportBatchApplyBody
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.access.authentication_session import AdminPrincipal
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from scripts.imports.finance_statement_normalizer import normalize_workbook
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker

    ingestion = ingest_finance_workbook(
        str(workbook),
        IdempotencyKey("timeout-retry-finance-ingest"),
        ActorContext("timeout-retry-test"),
        connection_factory=get_connection,
        normalizer=normalize_workbook,
    )
    connection = get_connection()
    try:
        preview = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        ).preview_batch(
            ingestion.batch_identity,
            CorrelationId("timeout-retry-preview"),
        )
        body = FinanceImportBatchApplyBody(
            batch_identity=ingestion.batch_identity,
            expected_batch_version=preview.batch_version,
            preview_fingerprint=preview.fingerprint.value,
            reason="timeout retry global e2e",
        )
        repository = BackgroundJobRepository(connection)
        principal = AdminPrincipal(1, "timeout-retry-test", "Timeout Retry", "system_admin")
        apply_kwargs = {
            "body": body,
            "idempotency_key": "timeout-retry-apply",
            "correlation_id": "timeout-retry-apply",
            "principal": principal,
            "job_repository": repository,
        }
        apply_finance_import_batch(**apply_kwargs)  # The client loses this response.
        retry_response = apply_finance_import_batch(**apply_kwargs)
        job_id = retry_response.data.job_id
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM background_jobs")
            assert cursor.fetchone() == {"count": 1}
    finally:
        connection.close()

    worker_connection = get_connection()
    try:
        worker = DurableJobWorker(
            BackgroundJobRepository(worker_connection),
            default_job_handlers(),
            "timeout-retry-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded"
        assert stored.receipt_payload["batch_identity"] == ingestion.batch_identity
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM finance_import_apply_receipts")
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()

"""
File: test_controlled_file_disposable_mysql_e2e.py
Description: 在明確 allowlisted lu_test DB 驗證 controlled-file staging、Apply、receipt 與下載 readback。
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid

import pytest

from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.controlled_files.reconciliation import (
    ControlledFileReconciler,
    ControlledFileReconciliationOutcome,
)
from subsystems.controlled_files.cleanup import (
    CleanupControlledFileStaging,
    ControlledFileCleanupOutcome,
    ControlledFileCleanupWorkflow,
)
from subsystems.controlled_files.contracts import ControlledFileStagingCleanupReason
from shared_kernel.identities import ExpectedVersion
from subsystems.controlled_files.workflow import (
    ApplyControlledFile,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileWorkflow,
    StageControlledFile,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CONTROLLED_FILE_MYSQL_E2E") != "1",
    reason="set RUN_CONTROLLED_FILE_MYSQL_E2E=1 for disposable MySQL acceptance",
)


def test_disposable_mysql_staging_apply_receipt_and_download(tmp_path) -> None:
    database = os.getenv("DB_DATABASE", "")
    app_env = os.getenv("APP_ENV", "development").lower()
    assert app_env == "development"
    assert database.startswith("lu_test_")
    connection = get_connection()
    suffix = uuid.uuid4().hex
    stage_key = IdempotencyKey(f"controlled-file.stage:{suffix}")
    apply_key = IdempotencyKey(f"controlled-file.apply:{suffix}")
    now = datetime.now(timezone.utc)
    repository = MySqlControlledFileWorkflowRepository(connection)
    storage = FileSystemControlledFileStorage(tmp_path, clock=lambda: now.timestamp())
    workflow = ControlledFileWorkflow(
        repository,
        storage,
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(now),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders ORDER BY case_no LIMIT 1")
            row = cursor.fetchone()
        assert row is not None
        case_no = str(row["case_no"])
        content = b"controlled-file-disposable-e2e"
        staged = workflow.stage(
            StageControlledFile(
                owner=ControlledFileOwner.ORDERS,
                purpose=ControlledFilePurpose.ORDER_NOTICE,
                subject_reference=case_no,
                object_key=f"e2e-{suffix}",
                logical_folder=f"orders/{case_no}/e2e",
                filename="receipt.pdf",
                mime_type="application/pdf",
                content=content,
                idempotency_key=stage_key,
                actor=ActorContext("codex-e2e"),
                correlation_id=CorrelationId(f"corr-stage-{suffix}"),
            )
        )
        intent = ControlledFileIntent(
            staging_id=staged.staging_id,
            owner=ControlledFileOwner.ORDERS,
            purpose=ControlledFilePurpose.ORDER_NOTICE,
            subject_reference=case_no,
            object_key=f"e2e-{suffix}",
            logical_folder=f"orders/{case_no}/e2e",
        )
        preview = workflow.preview(intent)
        receipt = workflow.apply(
            ApplyControlledFile(
                intent=intent,
                expected_staging_version=preview.expected_staging_version,
                preview_fingerprint=preview.preview_fingerprint,
                idempotency_key=apply_key,
                actor=ActorContext("codex-e2e"),
                correlation_id=CorrelationId(f"corr-apply-{suffix}"),
            )
        )
        file_id = receipt.readback.file_id
        receipt_id = receipt.receipt_id

        assert workflow.readback(file_id) == receipt.readback
        assert workflow.read_receipt(receipt_id).readback == receipt.readback
        assert workflow.download(file_id).content == content
        assert any(item.file_id == file_id for item in workflow.list_readbacks())
        reconciler = ControlledFileReconciler(
            repository,
            storage,
            lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(now),
        )
        event = reconciler.reconcile_registered(
            file_id,
            actor=ActorContext("codex-e2e"),
            correlation_id=CorrelationId(f"corr-reconcile-{suffix}"),
        )
        assert event.outcome is ControlledFileReconciliationOutcome.EXACT
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT outcome,controlled_object_id,observation_snapshot "
                "FROM controlled_file_reconciliation_events WHERE event_id=%s",
                (event.event_id,),
            )
            reconciliation_row = cursor.fetchone()
        assert reconciliation_row is not None
        assert reconciliation_row["outcome"] == "exact"
        assert reconciliation_row["controlled_object_id"] is not None
        assert "storage_locator" not in str(reconciliation_row["observation_snapshot"])

        cleanup_stage_key = IdempotencyKey(
            f"controlled-file.cleanup-stage:{suffix}"
        )
        cleanup_staging = workflow.stage(
            StageControlledFile(
                owner=ControlledFileOwner.ORDERS,
                purpose=ControlledFilePurpose.ORDER_NOTICE,
                subject_reference=case_no,
                object_key=f"cleanup-e2e-{suffix}",
                logical_folder=f"orders/{case_no}/cleanup-e2e",
                filename="abandoned.pdf",
                mime_type="application/pdf",
                content=b"abandoned-controlled-file",
                idempotency_key=cleanup_stage_key,
                actor=ActorContext("codex-e2e"),
                correlation_id=CorrelationId(f"corr-cleanup-stage-{suffix}"),
            )
        )
        cleanup_workflow = ControlledFileCleanupWorkflow(
            repository,
            storage,
            lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(now),
        )
        cleanup_command = CleanupControlledFileStaging(
            staging_id=cleanup_staging.staging_id,
            reason=ControlledFileStagingCleanupReason.ABANDONED,
            expected_staging_version=ExpectedVersion(1),
            expected_sha256=cleanup_staging.sha256_digest,
            idempotency_key=IdempotencyKey(
                f"controlled-file.cleanup:{suffix}"
            ),
            actor=ActorContext("codex-e2e"),
            correlation_id=CorrelationId(f"corr-cleanup-{suffix}"),
        )
        cleanup_receipt = cleanup_workflow.cleanup(cleanup_command)
        cleanup_replay = cleanup_workflow.cleanup(cleanup_command)
        assert cleanup_receipt.outcome is ControlledFileCleanupOutcome.CLEANED
        assert cleanup_replay.outcome is ControlledFileCleanupOutcome.REPLAYED
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT staging_state,cleaned_at_utc FROM controlled_file_staging_objects "
                "WHERE staging_id=%s",
                (cleanup_staging.staging_id,),
            )
            cleanup_row = cursor.fetchone()
            cursor.execute(
                "SELECT event_sequence,event_type FROM controlled_file_cleanup_events "
                "WHERE cleanup_id=%s ORDER BY event_sequence",
                (cleanup_receipt.cleanup_id,),
            )
            cleanup_events = cursor.fetchall()
        assert cleanup_row["staging_state"] == "cleaned"
        assert cleanup_row["cleaned_at_utc"] is not None
        assert [
            (row["event_sequence"], row["event_type"])
            for row in cleanup_events
        ] == [(1, "intent"), (2, "completed")]
    finally:
        # 四組 records 都由 immutable trigger 保護；本測試只允許在可整庫丟棄的 lu_test target
        # 執行，並以唯一 scenario identity 保留 terminal receipt，最後由 task cleanup 丟棄整個 DB。
        connection.close()

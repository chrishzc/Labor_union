"""Disposable lu_test_* acceptance for the bounded controlled-file finalizer."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid

import pytest

from infrastructure.db.controlled_file_repository import MySqlControlledFileWorkflowRepository
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.mysql.controlled_file_finalize_worker import MySqlControlledFileFinalizeRunner
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
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


def test_finalize_runner_pending_to_available_on_disposable_mysql(tmp_path) -> None:
    assert os.getenv("APP_ENV", "development").lower() == "development"
    assert os.getenv("DB_DATABASE", "").startswith("lu_test_")

    connection = get_connection()
    suffix = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    storage = FileSystemControlledFileStorage(tmp_path, clock=lambda: now.timestamp())
    workflow = ControlledFileWorkflow(
        MySqlControlledFileWorkflowRepository(connection),
        storage,
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(now),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders ORDER BY case_no LIMIT 1")
            order = cursor.fetchone()
        assert order is not None
        case_no = str(order["case_no"])
        content = b"controlled-file-finalize-runner-e2e"
        staged = workflow.stage(
            StageControlledFile(
                owner=ControlledFileOwner.ORDERS,
                purpose=ControlledFilePurpose.ORDER_NOTICE,
                subject_reference=case_no,
                object_key=f"finalize-runner-{suffix}",
                logical_folder=f"orders/{case_no}/finalize-runner",
                filename="finalize-runner.pdf",
                mime_type="application/pdf",
                content=content,
                idempotency_key=IdempotencyKey(f"finalize-runner.stage:{suffix}"),
                actor=ActorContext("codex-finalize-e2e"),
                correlation_id=CorrelationId(f"finalize-runner-stage:{suffix}"),
            )
        )
        intent = ControlledFileIntent(
            staging_id=staged.staging_id,
            owner=ControlledFileOwner.ORDERS,
            purpose=ControlledFilePurpose.ORDER_NOTICE,
            subject_reference=case_no,
            object_key=f"finalize-runner-{suffix}",
            logical_folder=f"orders/{case_no}/finalize-runner",
        )
        preview = workflow.preview(intent)
        receipt = workflow.apply(
            ApplyControlledFile(
                intent=intent,
                expected_staging_version=preview.expected_staging_version,
                preview_fingerprint=preview.preview_fingerprint,
                idempotency_key=IdempotencyKey(f"finalize-runner.apply:{suffix}"),
                actor=ActorContext("codex-finalize-e2e"),
                correlation_id=CorrelationId(f"finalize-runner-apply:{suffix}"),
            )
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT staging.id AS staging_object_id, object.id AS controlled_file_object_id "
                "FROM controlled_file_staging_objects staging "
                "JOIN controlled_file_objects object ON object.source_staging_id=staging.id "
                "WHERE object.opaque_object_id=%s",
                (receipt.readback.file_id,),
            )
            object_row = cursor.fetchone()
            assert object_row is not None
            finalize_id = f"cff_{uuid.uuid4().hex}"
            cursor.execute(
                "INSERT INTO controlled_file_finalize_intents "
                "(finalize_id,staging_object_id,controlled_file_object_id,expected_sha256,created_at_utc) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    finalize_id,
                    object_row["staging_object_id"],
                    object_row["controlled_file_object_id"],
                    receipt.readback.sha256_digest,
                    now,
                ),
            )
        connection.commit()

        runner = MySqlControlledFileFinalizeRunner(
            get_connection,
            storage,
            "controlled-file-finalize-e2e",
            lambda: now,
        )
        assert runner.run_once() == 1
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT finalize_state,observed_sha256,observed_size_bytes "
                "FROM controlled_file_finalize_intents WHERE finalize_id=%s",
                (finalize_id,),
            )
            final = cursor.fetchone()
        assert final["finalize_state"] == "available"
        assert final["observed_sha256"] == receipt.readback.sha256_digest
        assert final["observed_size_bytes"] == len(content)
    finally:
        connection.close()

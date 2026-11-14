"""
File: registration_applications.py
Description: 管理後台需求審核依賴組裝，自動確認 Redis 暫存命名空間初始化狀態。
"""
from functools import lru_cache
from uuid import uuid4

from api.dependencies.controlled_files import get_controlled_file_workflow
from api.dependencies.line_identity import get_line_identity_application
from api.error_contracts import typed_http_error
from infrastructure.file.controlled_file_storage import FileSystemControlledFileStorage
from infrastructure.file.storage_layout import CLIENT_PASSBOOK_DIRECTORY, configured_storage_root
from infrastructure.mysql.controlled_file_finalize_worker import MySqlControlledFileFinalizeRunner
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.redis.registration_connection import RegistrationRedisConfigurationError, registration_redis_client
from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository
from infrastructure.runtime.file_transfer_settings import file_read_capacity
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
from subsystems.case_import.registration_staging import RegistrationReviewApplication
from subsystems.controlled_files.workflow import (
    ApplyControlledFile,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileWorkflowError,
    StageControlledFile,
)


def _verify_client_passbook_finalized(root, client_id: int) -> None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT obj.storage_locator, intent.finalize_state
                FROM controlled_file_objects obj
                LEFT JOIN controlled_file_finalize_intents intent
                  ON intent.controlled_file_object_id = obj.id
                WHERE obj.owner_type = 'clients'
                  AND obj.purpose = 'client_passbook_cover'
                  AND obj.subject_reference = %s
                ORDER BY obj.id DESC
                LIMIT 1
                """,
                (str(client_id),),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if not row or row.get("finalize_state") != "available":
        raise ProvisionalRegistrationStorageError("controlled_file_finalize_incomplete")
    locator = str(row.get("storage_locator") or "").strip()
    if not locator or not (root / locator).is_file():
        raise ProvisionalRegistrationStorageError("controlled_file_storage_missing")


def _archive_client_passbook_cover(
    *,
    client_id: int,
    registration_id: int,
    filename: str,
    mime_type: str,
    content: bytes,
    actor: str,
    correlation_id: CorrelationId,
) -> None:
    root = configured_storage_root()
    if root is None or not root.is_dir():
        raise ProvisionalRegistrationStorageError("controlled_file_storage_unavailable")
    actor_ctx = ActorContext(actor_id=actor)
    object_key = f"clients/{client_id}/passbook_cover"
    gen = get_controlled_file_workflow()
    workflow = next(gen)
    try:
        staged = workflow.stage(
            StageControlledFile(
                owner=ControlledFileOwner.CLIENTS,
                purpose=ControlledFilePurpose.CLIENT_PASSBOOK_COVER,
                subject_reference=str(client_id),
                object_key=object_key,
                logical_folder=CLIENT_PASSBOOK_DIRECTORY,
                filename=filename,
                mime_type=mime_type,
                content=content,
                idempotency_key=IdempotencyKey(f"passbook:{registration_id}:{client_id}"),
                actor=actor_ctx,
                correlation_id=correlation_id,
            )
        )
        intent = ControlledFileIntent(
            staging_id=staged.staging_id,
            owner=ControlledFileOwner.CLIENTS,
            purpose=ControlledFilePurpose.CLIENT_PASSBOOK_COVER,
            subject_reference=str(client_id),
            object_key=object_key,
            logical_folder=CLIENT_PASSBOOK_DIRECTORY,
        )
        try:
            preview = workflow.preview(intent)
            workflow.apply(
                ApplyControlledFile(
                    intent=intent,
                    expected_staging_version=preview.expected_staging_version,
                    preview_fingerprint=preview.preview_fingerprint,
                    idempotency_key=IdempotencyKey(f"passbook-apply:{registration_id}:{client_id}"),
                    actor=actor_ctx,
                    correlation_id=correlation_id,
                )
            )
        except ControlledFileWorkflowError as error:
            if error.code != "controlled_file_already_registered":
                raise
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
    capacity = file_read_capacity()
    storage = FileSystemControlledFileStorage(root, max_staging_bytes=capacity, max_read_bytes=capacity)
    MySqlControlledFileFinalizeRunner(
        get_connection,
        storage,
        "registration-approval",
        SystemBusinessClock().now,
        layout_only=True,
    ).run_once()
    _verify_client_passbook_finalized(root, client_id)


@lru_cache(maxsize=1)
def get_registration_staging_repository():
    return RedisRegistrationStagingRepository(registration_redis_client(role="admin"))


@lru_cache(maxsize=1)
def get_registration_review_application():
    try:
        staging = get_registration_staging_repository()
    except RegistrationRedisConfigurationError:
        raise typed_http_error(503, "unavailable", "registration_storage_not_configured",
                               "申請暫存服務尚未完成設定。", uuid4().hex) from None
    formal = get_line_identity_application()
    try:
        staging.ensure_initialized()
    except Exception:
        try:
            staging.initialize(formal.registration_id_high_water(), shared_instance=True)
        except Exception:
            pass
    return RegistrationReviewApplication(staging, formal, passbook_archiver=_archive_client_passbook_cover)

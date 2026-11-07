"""Declared Data Center maintenance routes; governed identities, never NAS paths."""
from typing import Annotated
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from pymysql import MySQLError

from api.dependencies.admin_auth import require_persisted_admin, admin_actor_context
from api.dependencies.controlled_files import get_controlled_file_maintenance
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from shared_kernel.identities import ExpectedVersion, IdempotencyKey, CorrelationId
from subsystems.controlled_files.cleanup import CleanupControlledFileStaging, ControlledFileCleanupError
from subsystems.controlled_files.contracts import ControlledFileStagingCleanupReason, ControlledFileStorageError
from subsystems.controlled_files.gc import ControlledFileGcError

router = APIRouter(prefix="/api/v1/data-center", tags=["Controlled File Maintenance"])


def require_maintenance_admin(principal=Depends(require_persisted_admin)):
    if principal.id is None or not principal.is_root:
        raise typed_http_error(403, "forbidden", "controlled_file_maintenance_forbidden",
                               "僅 root 管理員可執行檔案維護。", "controlled-file-maintenance")
    return principal


class CleanupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staging_id: str = Field(pattern=r"^cfs_[0-9a-f]{32}$")
    expected_staging_version: StrictInt = Field(gt=0)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    category: ControlledFileStagingCleanupReason = ControlledFileStagingCleanupReason.EXPIRED


class ReconciliationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(pattern=r"^cf_[0-9a-f]{32}$")


def _call(operation):
    try:
        return BaseResponse(data=operation())
    except (ControlledFileCleanupError, ControlledFileGcError, ControlledFileStorageError) as error:
        code = error.code
        unavailable = isinstance(error, ControlledFileStorageError) and error.retryable
        raise typed_http_error(503 if unavailable else 409, "unavailable" if unavailable else "conflict",
            code, "檔案目前無法完成維護，請重新查核。", "controlled-file-maintenance", retryable=unavailable) from None
    except MySQLError:
        raise typed_http_error(503, "unavailable", "controlled_file_maintenance_unavailable",
            "檔案維護資料暫時無法讀取。", "controlled-file-maintenance", retryable=True) from None


@router.post("/staging/preview")
def preview_staging(limit: int = Query(default=100, ge=1, le=100),
                    principal=Depends(require_maintenance_admin), application=Depends(get_controlled_file_maintenance)):
    return _call(lambda: application.preview_cleanup(actor=admin_actor_context(principal),
        correlation_id=CorrelationId("controlled-file-maintenance"), limit=limit))


@router.post("/staging/cleanup")
def cleanup_staging(body: CleanupBody,
                    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[a-z0-9][a-z0-9._:-]{0,190}$")],
                    principal=Depends(require_maintenance_admin), application=Depends(get_controlled_file_maintenance)):
    return _call(lambda: application.cleanup(CleanupControlledFileStaging(
        body.staging_id, body.category, ExpectedVersion(body.expected_staging_version), body.expected_sha256,
        IdempotencyKey(idempotency_key), admin_actor_context(principal), CorrelationId("controlled-file-maintenance"),
    )))


@router.get("/reconciliation")
def list_reconciliation(limit: int = Query(default=100, ge=1, le=100),
                        principal=Depends(require_maintenance_admin), application=Depends(get_controlled_file_maintenance)):
    return _call(lambda: application.list_reconciliation(limit=limit))


@router.post("/reconciliation/preview")
def preview_reconciliation(body: ReconciliationBody, principal=Depends(require_maintenance_admin),
                           application=Depends(get_controlled_file_maintenance)):
    return _call(lambda: application.reconcile(body.file_id, actor=admin_actor_context(principal),
        correlation_id=CorrelationId("controlled-file-maintenance")))


@router.post("/reconciliation/apply")
def apply_reconciliation(body: ReconciliationBody, principal=Depends(require_maintenance_admin),
                         application=Depends(get_controlled_file_maintenance)):
    return _call(lambda: application.reconcile(body.file_id, actor=admin_actor_context(principal),
        correlation_id=CorrelationId("controlled-file-maintenance"), apply=True))

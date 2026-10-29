"""Thin root-only deletion endpoints composed into the existing registry routers."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Path
from pymysql.err import IntegrityError, OperationalError, ProgrammingError

from api.dependencies.admin_auth import admin_actor_context
from api.dependencies.registry_deletion import get_registry_deletion_application, require_registry_deletion_root
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.registry_deletion import RegistryDeletionApplyRequest, RegistryDeletionPreviewView, RegistryDeletionReceiptView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.registry_deletion import RegistryDeletionApplication, RegistryDeletionConflict, RegistryDeletionNotFound, RegistryKind

case_router = APIRouter()


def _raise_error(error: Exception, correlation: str) -> None:
    if isinstance(error, RegistryDeletionNotFound):
        raise typed_http_error(404, "not_found", "registry_deletion_not_found", "資料已不存在，請重新整理名冊。", correlation) from error
    if isinstance(error, RegistryDeletionConflict):
        message = {
            "registry_deletion_signed": "已有月嫂或客戶簽回，禁止永久刪除。" + "；".join(error.blockers),
            "registry_deletion_stale_version": "資料已變更，請重新檢查刪除資格。",
            "registry_deletion_idempotency_mismatch": "此操作識別已用於不同內容，請重新檢查刪除資格。",
        }.get(error.code, "案件綁定不完整，無法永久刪除。")
        category = "idempotency_mismatch" if "idempotency" in error.code else "conflict"
        raise typed_http_error(409, category, error.code, message, correlation) from error
    if isinstance(error, IntegrityError) and error.args[0] in (1451, 1452):
        raise typed_http_error(409, "conflict", "registry_deletion_integrity_conflict", "資料關聯已變更，請重新檢查刪除資格。", correlation) from error
    if isinstance(error, OperationalError) and error.args[0] == 1644 and str(error.args[1]) == "registry_deletion_signed":
        raise typed_http_error(409, "conflict", "registry_deletion_signed", "已有月嫂或客戶簽回，禁止永久刪除。", correlation) from error
    if isinstance(error, OperationalError) and error.args[0] == 1644 and str(error.args[1]) == "registry_deletion_stale_version":
        raise typed_http_error(409, "conflict", "registry_deletion_stale_version", "資料已變更，請重新檢查刪除資格。", correlation) from error
    if isinstance(error, OperationalError) and error.args[0] == 1644:
        raise typed_http_error(409, "conflict", "registry_deletion_guard_rejected", "資料庫保護規則拒絕刪除，這次操作已取消，原資料已保留。請重新檢查刪除資格。", correlation) from error
    if isinstance(error, OperationalError) and error.args[0] in (1205, 1213):
        raise typed_http_error(409, "conflict", "registry_deletion_concurrent_conflict", "資料正在變更，請重新檢查刪除資格。", correlation) from error
    if isinstance(error, (OperationalError, ProgrammingError)):
        raise typed_http_error(503, "unavailable", "registry_deletion_storage_unavailable", "目前無法確認刪除結果，請使用相同操作重新確認。", correlation) from error
    raise error


def _preview(kind: RegistryKind, identity: str, application: RegistryDeletionApplication):
    try:
        return BaseResponse(data=RegistryDeletionPreviewView.model_validate(application.preview(kind, identity)))
    except Exception as error:
        _raise_error(error, uuid4().hex)


def _apply(kind: RegistryKind, identity: str, body: RegistryDeletionApplyRequest, key: str, correlation: str, principal: AdminPrincipal, application: RegistryDeletionApplication):
    if body.expected_client_version is None:
        raise typed_http_error(422, "validation", "registry_deletion_invalid_versions", "刪除版本資料不完整，請重新檢查。", correlation)
    try:
        receipt = application.apply(kind, identity, expected_version=body.expected_version, expected_client_version=body.expected_client_version, key=key, actor=admin_actor_context(principal), correlation=correlation)
        return BaseResponse(data=RegistryDeletionReceiptView.model_validate(receipt), message="資料已永久刪除。")
    except Exception as error:
        _raise_error(error, correlation)


@case_router.get("/{case_no}/deletion", response_model=BaseResponse[RegistryDeletionPreviewView])
def preview_case_deletion(case_no: str = Path(min_length=1, max_length=50), application: RegistryDeletionApplication = Depends(get_registry_deletion_application)):
    return _preview("case", case_no, application)


@case_router.post("/{case_no}/deletion/apply", response_model=BaseResponse[RegistryDeletionReceiptView])
def apply_case_deletion(
    body: RegistryDeletionApplyRequest,
    case_no: str = Path(min_length=1, max_length=50),
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_registry_deletion_root),
    application: RegistryDeletionApplication = Depends(get_registry_deletion_application),
):
    return _apply("case", case_no, body, key, correlation, principal, application)

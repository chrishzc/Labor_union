"""
File: client_beclass_import.py
Description: 提供 authenticated Client BeClass temporary workbook Preview／Apply 與暫存清理。
"""

import logging
from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_admin
from api.dependencies.client_beclass_import import get_client_beclass_workbook_import_service
from api.schemas.base import BaseResponse
from api.schemas.client_beclass_import import ClientBeClassWorkbookPreviewView, ClientBeClassWorkbookReceiptView
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.case_import.client_beclass_workbook_import import ClientBeClassWorkbookConflict, ClientBeClassWorkbookUnavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/case-import/client-beclass/workbooks", tags=["Case Import"])
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]


@router.post("/preview", response_model=BaseResponse[ClientBeClassWorkbookPreviewView])
async def preview_client_beclass_workbook(
    workbook: UploadFile = File(...),
    correlation_id: _CorrelationHeader = "client-beclass-workbook-preview",
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_client_beclass_workbook_import_service),
):
    del principal
    return await _with_workbook(
        workbook,
        lambda path: service.preview(str(path)),
        "Client BeClass Preview 已完成",
        correlation_id,
    )


@router.post("/apply", response_model=BaseResponse[ClientBeClassWorkbookReceiptView])
async def apply_client_beclass_workbook(
    workbook: UploadFile = File(...),
    preview_fingerprint: str = Form(..., min_length=64, max_length=64),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_client_beclass_workbook_import_service),
):
    return await _with_workbook(
        workbook,
        lambda path: service.apply(
            str(path),
            idempotency_key,
            preview_fingerprint,
            str(principal.username or "admin"),
            correlation_id,
        ),
        "Client BeClass Apply 已完成",
        correlation_id,
    )


async def _with_workbook(workbook: UploadFile, operation, message: str, correlation_id: str):
    path = None
    correlation = CorrelationId(correlation_id)
    try:
        path = await _persist_workbook(workbook)
        result = await run_in_threadpool(operation, path)
        return BaseResponse(data=result.as_dict(), message=message)
    except ValueError as error:
        logger.exception("Client BeClass 工作簿處理失敗: %s", error)
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            TypedError(
                ErrorCategory.VALIDATION,
                _error_code(error, "client_beclass_workbook_invalid"),
                "Client BeClass 工作簿資料未通過驗證。",
                correlation,
            ),
        ) from error
    except ClientBeClassWorkbookConflict as error:
        logger.warning("Client BeClass 工作簿衝突: %s", error)
        raise _http_error(
            status.HTTP_409_CONFLICT,
            TypedError(
                ErrorCategory.CONFLICT,
                _error_code(error, "client_beclass_workbook_conflict"),
                "Client BeClass 工作簿套用與目前資料衝突，請重新預覽後再試。",
                correlation,
            ),
        ) from error
    except ClientBeClassWorkbookUnavailable as error:
        logger.warning("Client BeClass 工作簿服務不可用: %s", error)
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            TypedError(
                ErrorCategory.UNAVAILABLE,
                _error_code(error, "client_beclass_workbook_unavailable"),
                "Client BeClass 工作簿服務暫時無法使用。",
                correlation,
                retryable=True,
            ),
        ) from error
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def _error_code(error: Exception, fallback: str) -> str:
    code = str(error)
    return code if code and code == code.strip() and len(code) <= 191 else fallback


def _http_error(status_code: int, error: TypedError) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": _error_payload(error)})


def _error_payload(error: TypedError) -> dict[str, object]:
    return {
        "category": error.category.value,
        "code": error.code,
        "message": error.message,
        "field_errors": [
            {"field": item.field, "code": item.code, "message": item.message}
            for item in error.field_errors
        ],
        "domain_blockers": list(error.domain_blockers),
        "retryable": error.retryable,
        "correlation_id": error.correlation_id.value,
        "current_version": None if error.current_version is None else error.current_version.value,
    }


async def _persist_workbook(workbook: UploadFile) -> Path:
    if Path(str(workbook.filename or "")).suffix.lower() != ".xlsx":
        raise ValueError("client_beclass_workbook_must_be_xlsx")
    content = await workbook.read(_MAXIMUM_WORKBOOK_BYTES + 1)
    if not content:
        raise ValueError("client_beclass_workbook_empty")
    if len(content) > _MAXIMUM_WORKBOOK_BYTES:
        raise ValueError("client_beclass_workbook_exceeds_20_mib")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as target:
        target.write(content)
        return Path(target.name)

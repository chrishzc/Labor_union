"""
File: historical_order_adoption.py
Description: 提供 authenticated Orders historical workbook Preview／Apply 與暫存檔清理邊界。
"""

from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pymysql.err import OperationalError
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_admin
from api.dependencies.historical_order_adoption import get_historical_order_workbook_import_service
from api.schemas.base import BaseResponse
from api.schemas.historical_order_adoption import HistoricalOrderWorkbookPreviewView, HistoricalOrderWorkbookReceiptView
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.actual_start_workflow import ActualStartWorkflowError
from subsystems.orders.historical_order_workbook_import import HistoricalOrderWorkbookConflict, HistoricalOrderWorkbookUnavailable


router = APIRouter(prefix="/api/v1/orders/historical-adoption/workbooks", tags=["Orders Historical Adoption"])
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]


@router.post("/preview", response_model=BaseResponse[HistoricalOrderWorkbookPreviewView])
async def preview_historical_order_workbook(
    workbook: UploadFile = File(...),
    correlation_id: _CorrelationHeader = "historical-order-workbook-preview",
    service=Depends(get_historical_order_workbook_import_service),
    principal: AdminPrincipal = Depends(require_admin),
):
    del principal
    return await _with_workbook(
        workbook,
        lambda path: service.preview(str(path)),
        "訂單歷史資料 Preview 已完成",
        correlation_id,
    )


@router.post("/apply", response_model=BaseResponse[HistoricalOrderWorkbookReceiptView])
async def apply_historical_order_workbook(
    workbook: UploadFile = File(...),
    preview_fingerprint: str = Form(..., min_length=64, max_length=64),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_historical_order_workbook_import_service),
):
    actor = str(principal.username or "admin")
    return await _with_workbook(
        workbook,
        lambda path: service.apply(str(path), idempotency_key, preview_fingerprint, actor, correlation_id),
        "訂單歷史資料 Apply 已完成",
        correlation_id,
    )


async def _with_workbook(
    workbook: UploadFile,
    operation,
    message: str,
    correlation_id: str,
):
    upload_path = None
    correlation = CorrelationId(correlation_id)
    try:
        upload_path = await _persist_uploaded_workbook(workbook)
        result = await run_in_threadpool(operation, upload_path)
        return BaseResponse(data=result.as_dict(), message=message)
    except ValueError as error:
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            TypedError(
                ErrorCategory.VALIDATION,
                _error_code(error, "historical_order_workbook_invalid"),
                "歷史訂單工作簿資料未通過驗證。",
                correlation,
            ),
        ) from error
    except HistoricalOrderWorkbookConflict as error:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            TypedError(
                ErrorCategory.CONFLICT,
                _error_code(error, "historical_order_workbook_conflict"),
                "歷史訂單工作簿套用與目前資料衝突，請重新預覽後再試。",
                correlation,
            ),
        ) from error
    except HistoricalOrderWorkbookUnavailable as error:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            TypedError(
                ErrorCategory.UNAVAILABLE,
                _error_code(error, "historical_order_workbook_unavailable"),
                "歷史訂單工作簿服務暫時無法使用。",
                correlation,
                retryable=True,
            ),
        ) from error
    except ActualStartWorkflowError as error:
        raise _http_error(
            _actual_start_error_status(error.error.category),
            _with_correlation(error.error, correlation),
        ) from error
    except OperationalError as error:
        code = int(error.args[0]) if error.args else 0
        message = str(error.args[1]) if len(error.args) > 1 else ""
        if (
            code == 3819
            and "chk_order_lifecycle_state_event_before_status" in message
        ):
            detail_code = "historical_order_database_upgrade_required"
        else:
            detail_code = "historical_order_import_database_unavailable"
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            TypedError(
                ErrorCategory.UNAVAILABLE,
                detail_code,
                "歷史訂單工作簿服務暫時無法使用。",
                correlation,
                retryable=True,
            ),
        ) from error
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


def _actual_start_error_status(category: ErrorCategory) -> int:
    return {
        ErrorCategory.VALIDATION: status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorCategory.FORBIDDEN: status.HTTP_403_FORBIDDEN,
        ErrorCategory.NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ErrorCategory.DOMAIN_BLOCKED: status.HTTP_409_CONFLICT,
        ErrorCategory.CONFLICT: status.HTTP_409_CONFLICT,
        ErrorCategory.IDEMPOTENCY_MISMATCH: status.HTTP_409_CONFLICT,
        ErrorCategory.UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCategory.INTERNAL: status.HTTP_500_INTERNAL_SERVER_ERROR,
    }[category]


def _with_correlation(error: TypedError, correlation: CorrelationId) -> TypedError:
    return TypedError(
        error.category,
        error.code,
        error.message,
        correlation,
        field_errors=error.field_errors,
        domain_blockers=error.domain_blockers,
        retryable=error.retryable,
        current_version=error.current_version,
    )


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


async def _persist_uploaded_workbook(workbook: UploadFile) -> Path:
    if Path(str(workbook.filename or "")).suffix.lower() != ".xlsx":
        raise ValueError("historical_order_workbook_must_be_xlsx")
    content = await workbook.read(_MAXIMUM_WORKBOOK_BYTES + 1)
    if not content:
        raise ValueError("historical_order_workbook_empty")
    if len(content) > _MAXIMUM_WORKBOOK_BYTES:
        raise ValueError("historical_order_workbook_exceeds_20_mib")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as target:
        target.write(content)
        return Path(target.name)

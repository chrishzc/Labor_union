"""
File: historical_order_adoption.py
Description: 提供歷史訂單 workbook Preview／Apply 路由、排程衝突列號明細投影與暫存檔清理。
"""

import logging
from pathlib import Path
import tempfile
from traceback import extract_tb
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pymysql import MySQLError
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_admin
from api.dependencies.historical_order_adoption import get_historical_order_workbook_import_service
from api.exception_handlers.historical_order_database import historical_database_http_error
from api.schemas.base import BaseResponse
from api.schemas.historical_order_adoption import HistoricalOrderWorkbookPreviewView, HistoricalOrderWorkbookReceiptView
from shared_kernel.errors import ErrorCategory, FieldError, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.actual_start_workflow import ActualStartWorkflowError
from subsystems.orders.historical_order_workbook_import import (
    HistoricalOrderSourceScheduleConflictError,
    HistoricalOrderWorkbookConflict,
    HistoricalOrderWorkbookUnavailable,
)


router = APIRouter(prefix="/api/v1/orders/historical-adoption/workbooks", tags=["Orders Historical Adoption"])
logger = logging.getLogger(__name__)
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_INVALID_WORKBOOK_CODE = "historical_order_workbook_invalid"
_VALIDATION_MESSAGES = {
    _INVALID_WORKBOOK_CODE: "歷史訂單工作簿處理時遇到未分類的驗證錯誤，請提供追蹤編號供管理員查核。",
    "historical_order_workbook_must_be_xlsx": "歷史訂單匯入只接受 .xlsx 檔案。",
    "historical_order_workbook_empty": "上傳的歷史訂單檔案是空檔。",
    "historical_order_workbook_exceeds_20_mib": "上傳的歷史訂單檔案超過 20 MiB。",
    "historical_order_sheet_not_found": "找不到指定的歷史訂單工作表。",
    "historical_order_sheet_contract_mismatch": "指定工作表的欄位格式不符合歷史訂單匯入格式。",
    "historical_order_sheet_contract_not_found": "沒有工作表符合歷史訂單匯入格式，請核對表頭是否包含客戶姓名、案件編號與訂單狀態。",
    "historical_order_sheet_contract_not_unique": "有多張工作表符合歷史訂單匯入格式，請保留一張待匯入的工作表。",
    "xlsx_archive_too_large": "Excel 檔案超過 20 MiB。",
    "xlsx_too_many_members": "Excel 檔案的內部元件數量超過匯入上限。",
    "xlsx_unsafe_member": "Excel 檔案含有加密、重複或不支援的內部元件。",
    "xlsx_expansion_limit_exceeded": "Excel 檔案解壓後的大小或壓縮比超過匯入上限。",
    "xlsx_missing_workbook_parts": "Excel 檔案缺少必要的活頁簿或工作表結構。",
    "xlsx_too_many_sheets": "Excel 檔案有超過 16 張工作表。",
    "xlsx_cell_limit_exceeded": "整份 Excel 的儲存格範圍超過 50 萬格。",
    "xlsx_sheet_limit_exceeded": "單張工作表的使用範圍超過 5 萬列、256 欄或 50 萬格的其中一項限制。",
    "xlsx_invalid_cell_reference": "Excel 檔案內含無效的列號或儲存格位置。",
    "xlsx_xml_element_limit_exceeded": "Excel 檔案的樣式或共用文字數量超過匯入上限。",
    "xlsx_invalid_archive": "無法讀取 Excel 檔案的內部結構，請確認檔案可正常開啟並重新另存為 .xlsx。",
    "historical_order_source_schedule_conflict": "歷史訂單工作簿存在跨案件月嫂排程重疊衝突。",
    "historical_client_payment_terms_missing": "歷史案件缺少客戶付款條款，無法建立帳務。",
    "historical_payroll_rate_policy_missing": "歷史案件缺少月嫂薪資費率，無法建立帳務。",
    "historical_order_import_counts_not_conserved": "系統核對匯入結果時，來源列數與結果筆數不一致，請提供追蹤編號。",
    "historical_order_not_imported_rows_not_conserved": "系統核對匯入結果時，未匯入列的明細與筆數不一致，請提供追蹤編號。",
}


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
    except HistoricalOrderSourceScheduleConflictError as error:
        logger.warning(
            "歷史訂單工作簿跨案件排程衝突: conflict_count=%s correlation_id=%s",
            len(error.conflicts),
            correlation.value,
        )
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            TypedError(
                ErrorCategory.VALIDATION,
                "historical_order_source_schedule_conflict",
                "歷史訂單工作簿存在跨案件月嫂排程重疊衝突。",
                correlation,
                field_errors=_schedule_conflict_field_errors(error),
            ),
        ) from error
    except ValueError as error:
        code = str(error)
        if code not in _VALIDATION_MESSAGES:
            code = _INVALID_WORKBOOK_CODE
            origin = extract_tb(error.__traceback__, limit=-1)[0]
            logger.warning(
                "歷史訂單工作簿處理驗證失敗 code=%s file=%s function=%s line=%s correlation_id=%s",
                code, Path(origin.filename).name, origin.name, origin.lineno, correlation.value,
            )
        else:
            logger.warning("歷史訂單工作簿處理驗證失敗 code=%s correlation_id=%s", code, correlation.value)
        raise _http_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            TypedError(
                ErrorCategory.VALIDATION,
                code,
                _VALIDATION_MESSAGES[code],
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
    except MySQLError as error:
        raise historical_database_http_error(error, correlation.value) from error
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


def _schedule_conflict_field_errors(
    error: HistoricalOrderSourceScheduleConflictError,
) -> tuple[FieldError, ...]:
    items: list[FieldError] = []
    for conflict in error.conflicts[:100]:
        left = conflict.left
        right = conflict.right
        left_start = _format_conflict_date(left.start_date)
        left_end = _format_conflict_date(left.end_date)
        right_start = _format_conflict_date(right.start_date)
        right_end = _format_conflict_date(right.end_date)
        left_case = _safe_case_no(left.case_no)
        right_case = _safe_case_no(right.case_no)
        message = (
            f"Excel 第 {left.source_row} 列（案件 {left_case}，{left_start}～{left_end}）"
            f"與第 {right.source_row} 列（案件 {right_case}，{right_start}～{right_end}）"
            f"的月嫂（ID {left.staff_id}）服務期間重疊。"
        )[:500]
        items.append(
            FieldError(
                f"rows[{left.source_row},{right.source_row}]",
                "historical_order_source_schedule_conflict",
                message,
            )
        )
    return tuple(items)


def _format_conflict_date(value: object) -> str:
    text = value.isoformat() if hasattr(value, "isoformat") else str(value or "未知")
    return " ".join(text.split())[:32] or "未知"


def _safe_case_no(value: str | None) -> str:
    cleaned = " ".join(str(value or "").split())[:64]
    return cleaned or "未提供"


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

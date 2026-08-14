"""
File: historical_order_adoption.py
Description: 提供 authenticated Orders historical workbook Preview／Apply 與暫存檔清理邊界。
"""

from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_admin
from api.dependencies.historical_order_adoption import get_historical_order_workbook_import_service
from api.schemas.base import BaseResponse
from api.schemas.historical_order_adoption import HistoricalOrderWorkbookPreviewView, HistoricalOrderWorkbookReceiptView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_order_workbook_import import HistoricalOrderWorkbookConflict, HistoricalOrderWorkbookUnavailable


router = APIRouter(prefix="/api/v1/orders/historical-adoption/workbooks", tags=["Orders Historical Adoption"])
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]


@router.post("/preview", response_model=BaseResponse[HistoricalOrderWorkbookPreviewView])
async def preview_historical_order_workbook(
    workbook: UploadFile = File(...),
    service=Depends(get_historical_order_workbook_import_service),
    principal: AdminPrincipal = Depends(require_admin),
):
    del principal
    return await _with_workbook(workbook, lambda path: service.preview(str(path)), "訂單歷史資料 Preview 已完成")


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
    )


async def _with_workbook(workbook: UploadFile, operation, message: str):
    upload_path = None
    try:
        upload_path = await _persist_uploaded_workbook(workbook)
        result = await run_in_threadpool(operation, upload_path)
        return BaseResponse(data=result.as_dict(), message=message)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(error)}) from error
    except HistoricalOrderWorkbookConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": str(error)}) from error
    except HistoricalOrderWorkbookUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": str(error)}) from error
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


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

"""
File: staff_historical_workbook.py
Description: 提供 authenticated Staff 歷史 workbook Preview 與 explicit Apply。
"""

from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_historical_workbook import get_staff_historical_workbook_service
from api.schemas.base import BaseResponse
from api.schemas.staff_historical_workbook import StaffHistoricalWorkbookPreviewView, StaffHistoricalWorkbookReceiptView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.case_import.staff_historical_workbook_adoption import (
    StaffHistoricalWorkbookConflict,
    StaffHistoricalWorkbookUnavailable,
)


router = APIRouter(prefix="/api/v1/case-import/staff-historical", tags=["Case Import"])
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_PreviewFingerprintHeader = Annotated[str, Header(alias="X-Preview-Fingerprint", pattern=r"^[0-9a-f]{64}$")]


@router.post("/workbooks/preview", response_model=BaseResponse[StaffHistoricalWorkbookPreviewView])
async def preview_staff_historical_workbook(workbook: UploadFile = File(...), source_revision: str | None = Form(default=None), principal: AdminPrincipal = Depends(require_admin), service=Depends(get_staff_historical_workbook_service)):
    del principal
    return await _call(service.preview, workbook, source_revision)


@router.post("/workbooks/apply", response_model=BaseResponse[StaffHistoricalWorkbookReceiptView])
async def apply_staff_historical_workbook(workbook: UploadFile = File(...), source_revision: str | None = Form(default=None), idempotency_key: _IdempotencyHeader = ..., correlation_id: _CorrelationHeader = ..., preview_fingerprint: _PreviewFingerprintHeader = ..., principal: AdminPrincipal = Depends(require_admin), service=Depends(get_staff_historical_workbook_service)):
    return await _call(service.apply, workbook, source_revision, preview_fingerprint, idempotency_key, str(principal.username or "admin"), correlation_id)


async def _call(operation, workbook: UploadFile, *arguments):
    upload_path = None
    try:
        upload_path = await _persist(workbook)
        result = await run_in_threadpool(operation, str(upload_path), *arguments)
        return BaseResponse(data=result.as_dict(), message="Staff 歷史 workbook 已完成處理")
    except StaffHistoricalWorkbookConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": str(error)}) from error
    except StaffHistoricalWorkbookUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": str(error)}) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(error)}) from error
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


async def _persist(workbook: UploadFile) -> Path:
    if Path(str(workbook.filename or "")).suffix.lower() != ".xlsx":
        raise ValueError("staff_historical_workbook_must_be_xlsx")
    content = await workbook.read(_MAXIMUM_WORKBOOK_BYTES + 1)
    if not content:
        raise ValueError("staff_historical_workbook_empty")
    if len(content) > _MAXIMUM_WORKBOOK_BYTES:
        raise ValueError("staff_historical_workbook_exceeds_20_mib")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as target:
        target.write(content)
        return Path(target.name)

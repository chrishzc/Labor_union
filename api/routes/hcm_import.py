"""
File: hcm_import.py
Description: 提供 authenticated HCM workbook Preview／Apply 與暫存檔清理邊界。
"""

from dataclasses import asdict
from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_admin
from api.dependencies.hcm_import import get_hcm_resubmission_workbook_service, get_hcm_workbook_import_service
from api.schemas.base import BaseResponse
from api.schemas.hcm_import import (
    HcmResubmissionPreviewView,
    HcmResubmissionReceiptView,
    HcmWorkbookPreviewView,
    HcmWorkbookResultPageView,
    HcmWorkbookReceiptView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.case_import.hcm_workbook_import import HcmWorkbookConflict, HcmWorkbookUnavailable
from subsystems.case_import.hcm_resubmission_workbook import HcmResubmissionApplyRequest


router = APIRouter(prefix="/api/v1/case-import/hcm", tags=["Case Import"])
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]
_CorrelationHeader = Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)]
_PreviewFingerprintHeader = Annotated[str, Header(alias="X-Preview-Fingerprint", pattern=r"^[0-9a-f]{64}$")]


@router.post("/workbooks/preview", response_model=BaseResponse[HcmWorkbookPreviewView])
async def preview_hcm_workbook(
    workbook: UploadFile = File(...),
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_hcm_workbook_import_service),
):
    del principal
    return await _run_workbook_command(workbook, service, "preview")


@router.get("/workbooks/results", response_model=BaseResponse[HcmWorkbookResultPageView])
def query_hcm_workbook_results(
    limit: int = Query(20, ge=1, le=50),
    before_receipt_id: int | None = Query(None, gt=0),
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_hcm_workbook_import_service),
):
    del principal
    result = service.query_recent_results(
        limit=limit,
        before_receipt_id=before_receipt_id,
    )
    return BaseResponse(data=result.as_dict(), message="成功取得 HCM 匯入結果")


@router.post("/workbooks/apply", response_model=BaseResponse[HcmWorkbookReceiptView])
async def apply_hcm_workbook(
    workbook: UploadFile = File(...),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    preview_fingerprint: _PreviewFingerprintHeader = ...,
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_hcm_workbook_import_service),
):
    arguments = (preview_fingerprint, idempotency_key, str(principal.username or "admin"), correlation_id)
    return await _run_workbook_command(workbook, service, "apply", arguments)


@router.post("/resubmissions/preview", response_model=BaseResponse[HcmResubmissionPreviewView])
async def preview_hcm_resubmission(
    workbook: UploadFile = File(...),
    review_identity: str = Form(min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_hcm_resubmission_workbook_service),
):
    del principal
    return await _run_hcm_resubmission_preview(workbook, review_identity, service)


@router.post("/resubmissions/apply", response_model=BaseResponse[HcmResubmissionReceiptView])
async def apply_hcm_resubmission(
    workbook: UploadFile = File(...),
    review_identity: str = Form(min_length=1, max_length=191),
    expected_review_version: int = Form(ge=0),
    expected_root_fingerprint: str = Form(pattern=r"^[0-9a-f]{64}$"),
    reason: str = Form(min_length=1, max_length=500),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    preview_fingerprint: _PreviewFingerprintHeader = ...,
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_hcm_resubmission_workbook_service),
):
    request = HcmResubmissionApplyRequest(
        review_identity,
        expected_review_version,
        expected_root_fingerprint,
        preview_fingerprint,
        idempotency_key,
        str(principal.username or "admin"),
        reason,
        correlation_id,
    )
    return await _run_hcm_resubmission_apply(workbook, request, service)


@router.post("/historical-workbooks/preview", response_model=BaseResponse[HcmWorkbookPreviewView])
async def preview_hcm_historical_workbook(
    workbook: UploadFile = File(...),
    principal: AdminPrincipal = Depends(require_admin),
):
    del workbook, principal
    _raise_historical_whole_row_overwrite_retired()


@router.post("/historical-workbooks/apply", response_model=BaseResponse[HcmWorkbookReceiptView])
async def apply_hcm_historical_workbook(
    workbook: UploadFile = File(...),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    preview_fingerprint: _PreviewFingerprintHeader = ...,
    principal: AdminPrincipal = Depends(require_admin),
):
    del workbook, idempotency_key, correlation_id, preview_fingerprint, principal
    _raise_historical_whole_row_overwrite_retired()


@router.post("/workbooks/ingest", response_model=BaseResponse[HcmWorkbookReceiptView])
async def ingest_hcm_workbook(
    workbook: UploadFile = File(...),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_admin),
    service=Depends(get_hcm_workbook_import_service),
):
    upload_path = None
    try:
        upload_path = await _persist_uploaded_workbook(workbook)
        frame = service.load_frame(str(upload_path))
        if frame is None:
            raise ValueError("hcm_workbook_sheet_contract_not_unique")
        receipt = await run_in_threadpool(
            service.ingest, frame, str(upload_path), idempotency_key,
            str(principal.username or "admin"), correlation_id,
        )
        return BaseResponse(data=receipt.as_dict(), message="HCM workbook 已完成逐列處理")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(error)}) from error
    except HcmWorkbookConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": str(error)}) from error
    except HcmWorkbookUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": str(error)}) from error
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


async def _run_workbook_command(workbook, service, operation: str, arguments=()):
    upload_path = None
    try:
        upload_path = await _persist_uploaded_workbook(workbook)
        frame = service.load_frame(str(upload_path))
        if frame is None:
            raise ValueError("hcm_workbook_sheet_contract_not_unique")
        result = await run_in_threadpool(getattr(service, operation), frame, str(upload_path), *arguments)
        message = "HCM workbook Preview 已完成" if operation == "preview" else "HCM workbook Apply 已完成"
        return BaseResponse(data=result.as_dict(), message=message)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(error)}) from error
    except HcmWorkbookConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": str(error)}) from error
    except HcmWorkbookUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": str(error)}) from error
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


async def _run_hcm_resubmission_preview(workbook, review_identity: str, service):
    upload_path = None
    try:
        upload_path = await _persist_uploaded_workbook(workbook)
        result = await run_in_threadpool(service.preview, str(upload_path), review_identity)
        return BaseResponse(data=asdict(result), message="HCM 修正版 Preview 已完成")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(error)}) from error
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


async def _run_hcm_resubmission_apply(workbook, request: HcmResubmissionApplyRequest, service):
    upload_path = None
    try:
        upload_path = await _persist_uploaded_workbook(workbook)
        result = await run_in_threadpool(service.apply, str(upload_path), request)
        return BaseResponse(data=asdict(result), message="HCM 修正版 Apply 已完成")
    except ValueError as error:
        http_status = status.HTTP_409_CONFLICT if "stale" in str(error) or "conflict" in str(error) else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=http_status, detail={"code": str(error)}) from error
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


async def _persist_uploaded_workbook(workbook: UploadFile) -> Path:
    if Path(str(workbook.filename or "")).suffix.lower() != ".xlsx":
        raise ValueError("hcm_workbook_must_be_xlsx")
    content = await workbook.read(_MAXIMUM_WORKBOOK_BYTES + 1)
    if not content:
        raise ValueError("hcm_workbook_empty")
    if len(content) > _MAXIMUM_WORKBOOK_BYTES:
        raise ValueError("hcm_workbook_exceeds_20_mib")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as target:
        target.write(content)
        return Path(target.name)


def _raise_historical_whole_row_overwrite_retired() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "hcm_historical_whole_row_overwrite_retired"},
    )

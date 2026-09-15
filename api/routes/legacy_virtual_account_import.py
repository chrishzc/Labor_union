"""Authenticated legacy virtual-account workbook Preview and Apply endpoints."""

from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_registry_writer
from api.dependencies.legacy_virtual_account_import import get_legacy_virtual_account_workbook_service
from api.schemas.base import BaseResponse
from api.schemas.legacy_virtual_account_import import LegacyVirtualAccountPreviewView, LegacyVirtualAccountReceiptView
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.legacy_virtual_account_workbook import LegacyVirtualAccountWorkbookConflict, LegacyVirtualAccountWorkbookUnavailable


router = APIRouter(prefix="/api/v1/admin/client-finance/legacy-virtual-account-workbooks", tags=["Client Finance"])
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]


@router.post("/preview", response_model=BaseResponse[LegacyVirtualAccountPreviewView])
async def preview_legacy_virtual_accounts(
    workbook: UploadFile = File(...),
    principal: AdminPrincipal = Depends(require_registry_writer),
    service=Depends(get_legacy_virtual_account_workbook_service),
):
    del principal
    return await _with_workbook(workbook, lambda path: service.preview(str(path)), "虛擬帳號匯入預覽已完成")


@router.post("/apply", response_model=BaseResponse[LegacyVirtualAccountReceiptView])
async def apply_legacy_virtual_accounts(
    workbook: UploadFile = File(...),
    preview_fingerprint: str = Form(..., min_length=64, max_length=64),
    idempotency_key: _IdempotencyHeader = ...,
    principal: AdminPrincipal = Depends(require_registry_writer),
    service=Depends(get_legacy_virtual_account_workbook_service),
):
    return await _with_workbook(
        workbook,
        lambda path: service.apply(str(path), idempotency_key, preview_fingerprint, str(principal.username or "admin")),
        "虛擬帳號匯入已完成",
    )


async def _with_workbook(workbook: UploadFile, operation, message: str):
    path = None
    try:
        path = await _persist_workbook(workbook)
        result = await run_in_threadpool(operation, path)
        return BaseResponse(data=result.as_dict(), message=message)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": str(error)}) from error
    except LegacyVirtualAccountWorkbookConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": str(error)}) from error
    except LegacyVirtualAccountWorkbookUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": str(error)}) from error
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


async def _persist_workbook(workbook: UploadFile) -> Path:
    if Path(str(workbook.filename or "")).suffix.lower() != ".xlsx":
        raise ValueError("legacy_virtual_account_workbook_must_be_xlsx")
    content = await workbook.read(_MAXIMUM_WORKBOOK_BYTES + 1)
    if not content:
        raise ValueError("legacy_virtual_account_workbook_empty")
    if len(content) > _MAXIMUM_WORKBOOK_BYTES:
        raise ValueError("legacy_virtual_account_workbook_exceeds_20_mib")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as target:
        target.write(content)
        return Path(target.name)


__all__ = ["router"]

"""
File: controlled_files.py
Description: 提供受控檔案 Preview、Apply、detail 與 receipt 管理 API。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, File, Form, Header, Path, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import admin_actor_context, require_persisted_admin
from api.dependencies.controlled_files import get_controlled_file_workflow
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.controlled_files.contracts import ControlledFileContent, ControlledFileStagingResult, ControlledFileStorageError
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.controlled_files.workflow import (
    ApplyControlledFile,
    ControlledFileApplyReceipt,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePreview,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileWorkflowError,
    StageControlledFile,
)


router = APIRouter(prefix="/api/v1/storage", tags=["Controlled Files"])

_FILE_ID_PATTERN = r"^cf_[0-9a-f]{32}$"
_RECEIPT_ID_PATTERN = r"^cfr_[0-9a-f]{32}$"
_STAGING_ID_PATTERN = r"^cfs_[0-9a-f]{32}$"
_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
_IDEMPOTENCY_KEY_PATTERN = r"^[a-z0-9][a-z0-9._:-]{0,190}$"
_CORRELATION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$"


class ControlledFileRouteWorkflow(Protocol):
    def stage(self, command: StageControlledFile) -> ControlledFileStagingResult: ...

    def preview(self, intent: ControlledFileIntent) -> ControlledFilePreview: ...

    def apply(self, command: ApplyControlledFile) -> ControlledFileApplyReceipt: ...

    def readback(self, file_id: str) -> ControlledFileReadback: ...

    def list_readbacks(self) -> tuple[ControlledFileReadback, ...]: ...

    def download(self, file_id: str) -> ControlledFileContent: ...

    def read_receipt(self, receipt_id: str) -> ControlledFileApplyReceipt: ...


def get_controlled_file_route_workflow() -> ControlledFileRouteWorkflow:
    yield from get_controlled_file_workflow()


class ControlledFileIntentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staging_id: str = Field(pattern=_STAGING_ID_PATTERN)
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str = Field(min_length=1, max_length=191)
    object_key: str = Field(min_length=1, max_length=191)
    logical_folder: str = Field(min_length=1, max_length=500)

    def to_intent(self) -> ControlledFileIntent:
        return ControlledFileIntent(
            staging_id=self.staging_id,
            owner=self.owner,
            purpose=self.purpose,
            subject_reference=self.subject_reference,
            object_key=self.object_key,
            logical_folder=self.logical_folder,
        )


class ControlledFileApplyBody(ControlledFileIntentBody):
    expected_staging_version: int = Field(ge=1)
    preview_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN)


class ControlledFileCandidateView(BaseModel):
    staging_id: str
    staging_version: int
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    object_key: str
    logical_folder: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256_digest: str
    expires_at: datetime


class ControlledFilePreviewView(BaseModel):
    candidate: ControlledFileCandidateView
    preview_fingerprint: str
    expected_staging_version: int
    blockers: tuple[str, ...]


class ControlledFileDetailView(BaseModel):
    file_id: str
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    filename: str
    logical_folder: str
    version: int
    mime_type: str
    size_bytes: int
    status: str
    applied_at: datetime


class ControlledFileReceiptView(ControlledFileDetailView):
    receipt_id: str
    outcome: str
    receipt_type: str
    schema_version: str
    sha256_digest: str


class ControlledFileStagingView(BaseModel):
    staging_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256_digest: str
    expires_at: datetime


class ControlledFileListView(BaseModel):
    items: tuple[ControlledFileDetailView, ...]


@router.post("/staging", response_model=BaseResponse[ControlledFileStagingView])
def stage_controlled_file(
    document: UploadFile = File(),
    owner: ControlledFileOwner = Form(),
    purpose: ControlledFilePurpose = Form(),
    subject_reference: str = Form(min_length=1, max_length=191),
    object_key: str = Form(min_length=1, max_length=191),
    logical_folder: str = Form(min_length=1, max_length=500),
    idempotency_key: str = Header(alias="Idempotency-Key", pattern=_IDEMPOTENCY_KEY_PATTERN),
    correlation_id: str = Header(alias="X-Correlation-ID", pattern=_CORRELATION_ID_PATTERN),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    workflow: ControlledFileRouteWorkflow = Depends(get_controlled_file_route_workflow),
):
    return _call_workflow(
        lambda: BaseResponse(
            data=_staging_view(
                workflow.stage(
                    StageControlledFile(
                        owner=owner,
                        purpose=purpose,
                        subject_reference=subject_reference,
                        object_key=object_key,
                        logical_folder=logical_folder,
                        filename=document.filename or "upload.bin",
                        mime_type=document.content_type or "application/octet-stream",
                        content=document.file.read(),
                        idempotency_key=IdempotencyKey(idempotency_key),
                        actor=admin_actor_context(principal),
                        correlation_id=CorrelationId(correlation_id),
                    )
                )
            ),
            message="檔案已進入受控 staging",
        ),
        correlation_id,
    )


@router.post(
    "/files/preview",
    response_model=BaseResponse[ControlledFilePreviewView],
)
def preview_controlled_file(
    body: ControlledFileIntentBody,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", pattern=_CORRELATION_ID_PATTERN),
    ] = "controlled-files-preview",
    principal: AdminPrincipal = Depends(require_persisted_admin),
    workflow: ControlledFileRouteWorkflow = Depends(get_controlled_file_route_workflow),
):
    del principal
    return _call_workflow(
        lambda: BaseResponse(
            data=_preview_view(workflow.preview(body.to_intent())),
            message="成功產生受控檔案 Preview",
        ),
        correlation_id,
    )


@router.post(
    "/files/apply",
    response_model=BaseResponse[ControlledFileReceiptView],
)
def apply_controlled_file(
    body: ControlledFileApplyBody,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", pattern=_IDEMPOTENCY_KEY_PATTERN),
    ],
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", pattern=_CORRELATION_ID_PATTERN),
    ],
    principal: AdminPrincipal = Depends(require_persisted_admin),
    workflow: ControlledFileRouteWorkflow = Depends(get_controlled_file_route_workflow),
):
    return _call_workflow(
        lambda: BaseResponse(
            data=_receipt_view(
                workflow.apply(
                    ApplyControlledFile(
                        intent=body.to_intent(),
                        expected_staging_version=ExpectedVersion(
                            body.expected_staging_version
                        ),
                        preview_fingerprint=PreviewFingerprint(
                            body.preview_fingerprint
                        ),
                        idempotency_key=IdempotencyKey(idempotency_key),
                        actor=admin_actor_context(principal),
                        correlation_id=CorrelationId(correlation_id),
                    )
                )
            ),
            message="受控檔案已 Apply",
        ),
        correlation_id,
    )


@router.get(
    "/files",
    response_model=BaseResponse[ControlledFileListView],
)
def list_controlled_files(
    principal: AdminPrincipal = Depends(require_persisted_admin),
    workflow: ControlledFileRouteWorkflow = Depends(get_controlled_file_route_workflow),
):
    del principal
    return _call_workflow(
        lambda: BaseResponse(
            data=ControlledFileListView(items=tuple(_detail_view(item) for item in workflow.list_readbacks())),
            message="成功取得受控檔案清單",
        ),
        "controlled-files-list",
    )


@router.get(
    "/files/{file_id}",
    response_model=BaseResponse[ControlledFileDetailView],
)
def get_controlled_file(
    file_id: str = Path(pattern=_FILE_ID_PATTERN),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    workflow: ControlledFileRouteWorkflow = Depends(get_controlled_file_route_workflow),
):
    del principal
    return _call_workflow(
        lambda: BaseResponse(
            data=_detail_view(workflow.readback(file_id)),
            message="成功取得受控檔案",
        ),
        f"controlled-files-detail:{file_id}",
    )


@router.get("/files/{file_id}/download")
def download_controlled_file(
    file_id: str = Path(pattern=_FILE_ID_PATTERN),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    workflow: ControlledFileRouteWorkflow = Depends(get_controlled_file_route_workflow),
):
    del principal
    content = _call_workflow(
        lambda: workflow.download(file_id),
        f"controlled-files-download:{file_id}",
    )
    safe_filename = content.filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=content.content,
        media_type=content.content_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@router.get(
    "/receipts/{receipt_id}",
    response_model=BaseResponse[ControlledFileReceiptView],
)
def get_controlled_file_receipt(
    receipt_id: str = Path(pattern=_RECEIPT_ID_PATTERN),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    workflow: ControlledFileRouteWorkflow = Depends(get_controlled_file_route_workflow),
):
    del principal
    return _call_workflow(
        lambda: BaseResponse(
            data=_receipt_view(workflow.read_receipt(receipt_id)),
            message="成功取得受控檔案 receipt",
        ),
        f"controlled-files-receipt:{receipt_id}",
    )


def _preview_view(preview: ControlledFilePreview) -> ControlledFilePreviewView:
    candidate = preview.candidate
    return ControlledFilePreviewView(
        candidate=ControlledFileCandidateView(
            staging_id=candidate.staging_id,
            staging_version=candidate.staging_version,
            owner=candidate.owner,
            purpose=candidate.purpose,
            subject_reference=candidate.subject_reference,
            object_key=candidate.object_key,
            logical_folder=candidate.logical_folder,
            filename=candidate.filename,
            mime_type=candidate.mime_type,
            size_bytes=candidate.size_bytes,
            sha256_digest=candidate.sha256_digest,
            expires_at=candidate.expires_at,
        ),
        preview_fingerprint=preview.preview_fingerprint.value,
        expected_staging_version=preview.expected_staging_version.value,
        blockers=preview.blockers,
    )


def _detail_view(readback: ControlledFileReadback) -> ControlledFileDetailView:
    return ControlledFileDetailView(
        file_id=readback.file_id,
        owner=readback.owner,
        purpose=readback.purpose,
        subject_reference=readback.subject_reference,
        filename=readback.filename,
        logical_folder=readback.logical_folder,
        version=readback.version,
        mime_type=readback.mime_type,
        size_bytes=readback.size_bytes,
        status=readback.status,
        applied_at=readback.applied_at,
    )


def _staging_view(result: ControlledFileStagingResult) -> ControlledFileStagingView:
    return ControlledFileStagingView(
        staging_id=result.staging_id,
        filename=result.filename,
        mime_type=result.mime_type,
        size_bytes=result.size_bytes,
        sha256_digest=result.sha256_digest,
        expires_at=result.expires_at,
    )


def _receipt_view(receipt: ControlledFileApplyReceipt) -> ControlledFileReceiptView:
    readback = receipt.readback
    return ControlledFileReceiptView(
        receipt_id=receipt.receipt_id,
        outcome=receipt.outcome.value,
        receipt_type=receipt.receipt_type,
        schema_version=receipt.schema_version,
        sha256_digest=readback.sha256_digest,
        **_detail_view(readback).model_dump(),
    )


def _call_workflow(command, correlation_id: str):
    try:
        return command()
    except ControlledFileWorkflowError as error:
        raise _workflow_http_error(error, correlation_id) from error
    except ControlledFileStorageError as error:
        raise typed_http_error(
            503 if error.retryable else 409,
            "unavailable" if error.retryable else "conflict",
            error.code,
            str(error),
            correlation_id,
            retryable=error.retryable,
        ) from error
    except (TypeError, ValueError) as error:
        raise typed_http_error(
            422,
            "validation",
            "controlled_file_request_invalid",
            "受控檔案請求未通過驗證。",
            correlation_id,
        ) from error


def _workflow_http_error(
    error: ControlledFileWorkflowError,
    correlation_id: str,
):
    code = error.code
    if code.endswith("_not_found"):
        return typed_http_error(
            404, "not_found", code, "找不到指定的受控檔案資源。", correlation_id
        )
    if code.endswith("_invalid"):
        return typed_http_error(
            422, "validation", code, "受控檔案請求未通過驗證。", correlation_id
        )
    if code in {
        "controlled_file_reconciliation_required",
        "controlled_file_staging_drift",
        "idempotency_evidence_incomplete",
    }:
        return typed_http_error(
            503,
            "unavailable",
            code,
            "受控檔案需要對帳後才能繼續。",
            correlation_id,
            retryable=error.retryable,
        )
    category = "idempotency_mismatch" if code == "idempotency_mismatch" else "conflict"
    return typed_http_error(
        409,
        category,
        code,
        "受控檔案狀態或 Preview 已變更，請重新查詢。",
        correlation_id,
        retryable=error.retryable,
    )


__all__ = [
    "ControlledFileRouteWorkflow",
    "get_controlled_file_route_workflow",
    "router",
]

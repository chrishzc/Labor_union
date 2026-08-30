"""
File: contract_signing.py
Description: 提供契約簽署與不可變文件下載的 typed API，下載須授權、驗證封存內容並記錄稽核。
"""

from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Path, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import (
    get_access_control_connection_factory,
    require_system_admin,
)
from api.dependencies.contract_signing import (
    _archive_root,
    get_client_contract_signing_application,
    get_contract_signing_document_query_application,
    get_staff_contract_signing_application,
)
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.contract_signing import (
    ContractSigningManualAttestationPreviewView,
    ContractSigningQueryView,
    ContractSigningReceiptView,
)
from infrastructure.archive.contract_documents import read_archived_contract_document, validate_contract_document_content
from subsystems.access.authentication_session import ConnectionFactory, record_admin_audit
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.contract_signing.client_contract_application import (
    ClientContractSigningApplication,
    ManualClientContractAttestationCommand,
    RecordClientSignedReturnCommand,
    SendClientContractCommand,
)
from subsystems.contract_signing.staff_contract_application import (
    ManualStaffContractAttestationCommand,
    RecordStaffSignedReturnCommand,
    SendStaffContractCommand,
    StaffContractSigningApplication,
)
from subsystems.contract_signing.document_query import (
    ContractSigningDocumentQueryApplication,
    ContractSigningStatus,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Contract Signing"])
_MAXIMUM_DOCUMENT_SIZE = 20 * 1024 * 1024


class SendContractBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    download_url: str = Field(min_length=9, max_length=500)


class ManualContractAttestationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_method: Literal["phone", "paper", "in_person", "verified_other"]
    reason: str = Field(min_length=1, max_length=500)


@router.get("/{case_no}/contract-signing", response_model=BaseResponse[ContractSigningQueryView])
def query_contract_signing(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ContractSigningDocumentQueryApplication = Depends(
        get_contract_signing_document_query_application
    ),
):
    del principal
    try:
        status = application.query_status(case_no)
        if status is None:
            raise ValueError("order_not_found")
        return BaseResponse[ContractSigningQueryView](
            data=_contract_signing_status_view(status), message="成功取得契約簽署狀態"
        )
    except ValueError as error:
        raise typed_http_error(404, "not_found", str(error), "找不到案件的契約簽署資料。", f"contract-signing-query:{case_no}") from error
    except Exception as error:
        raise typed_http_error(500, "internal", "contract_signing_query_failed", "契約簽署狀態查詢失敗。", f"contract-signing-query:{case_no}") from error


@router.post("/{case_no}/contract-signing/staff-segments/{segment_id}/send", response_model=BaseResponse[ContractSigningReceiptView])
def send_staff_contract(
    body: SendContractBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    segment_id: int = Path(..., gt=0),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffContractSigningApplication = Depends(get_staff_contract_signing_application),
):
    command = SendStaffContractCommand(case_no, segment_id, _actor_id(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id), body.download_url)
    return _response(lambda: application.send(command), "已建立月嫂契約 LINE 寄送任務", correlation_id)


@router.post("/{case_no}/contract-signing/staff-segments/{segment_id}/signed-return", response_model=BaseResponse[ContractSigningReceiptView])
def record_staff_signed_return(
    document: UploadFile = File(...),
    expected_document_version_id: int = Form(..., gt=0),
    case_no: str = Path(..., min_length=1, max_length=50),
    segment_id: int = Path(..., gt=0),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffContractSigningApplication = Depends(get_staff_contract_signing_application),
):
    content = _document_content(document)
    command = RecordStaffSignedReturnCommand(case_no, segment_id, content, _filename(document), _mime_type(document), _actor_id(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id), expected_document_version_id)
    return _response(lambda: application.record_signed_return(command), "已記錄月嫂簽回契約", correlation_id)


@router.post("/{case_no}/contract-signing/staff-segments/{segment_id}/manual-attestation/preview", response_model=BaseResponse[ContractSigningManualAttestationPreviewView])
def preview_manual_staff_contract_attestation(
    body: ManualContractAttestationBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    segment_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffContractSigningApplication = Depends(get_staff_contract_signing_application),
):
    del principal
    try:
        preview = application.preview_manual_attestation(
            case_no=case_no,
            matching_segment_id=segment_id,
            confirmation_method=body.confirmation_method,
            reason=body.reason,
        )
        return BaseResponse[ContractSigningManualAttestationPreviewView](
            data=ContractSigningManualAttestationPreviewView.model_validate(preview),
            message="人工月嫂簽約證據 Preview 已完成",
        )
    except ValueError as error:
        code = str(error) or "manual_contract_preview_failed"
        raise typed_http_error(409, "domain_blocked", code, "人工月嫂簽約證據目前無法套用。", f"manual-staff-preview:{case_no}:{segment_id}") from error


@router.post("/{case_no}/contract-signing/staff-segments/{segment_id}/manual-attestation", response_model=BaseResponse[ContractSigningReceiptView])
def record_manual_staff_contract_attestation(
    document: UploadFile = File(...),
    confirmation_method: Literal["phone", "paper", "in_person", "verified_other"] = Form(...),
    reason: str = Form(..., min_length=1, max_length=500),
    preview_fingerprint: str = Form(..., min_length=64, max_length=64),
    case_no: str = Path(..., min_length=1, max_length=50),
    segment_id: int = Path(..., gt=0),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: StaffContractSigningApplication = Depends(get_staff_contract_signing_application),
):
    content = _document_content(document)
    command = ManualStaffContractAttestationCommand(
        case_no, segment_id, content, _filename(document), _mime_type(document), confirmation_method,
        reason, preview_fingerprint, _actor_id(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id),
    )
    return _response(lambda: application.record_manual_attestation(command), "已記錄人工月嫂簽約證據", correlation_id)


@router.post("/{case_no}/contract-signing/client/send", response_model=BaseResponse[ContractSigningReceiptView])
def send_client_contract(
    body: SendContractBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientContractSigningApplication = Depends(get_client_contract_signing_application),
):
    command = SendClientContractCommand(case_no, _actor_id(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id), body.download_url)
    return _response(lambda: application.send(command), "已建立客戶契約 LINE 寄送任務", correlation_id)


@router.post("/{case_no}/contract-signing/client/signed-return", response_model=BaseResponse[ContractSigningReceiptView])
def record_client_signed_return(
    document: UploadFile = File(...),
    expected_document_version_id: int = Form(..., gt=0),
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientContractSigningApplication = Depends(get_client_contract_signing_application),
):
    content = _document_content(document)
    command = RecordClientSignedReturnCommand(case_no, content, _filename(document), _mime_type(document), _actor_id(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id), expected_document_version_id)
    return _response(lambda: application.record_signed_return(command), "已記錄客戶簽回契約", correlation_id)


@router.post("/{case_no}/contract-signing/client/manual-attestation/preview", response_model=BaseResponse[ContractSigningManualAttestationPreviewView])
def preview_manual_client_contract_attestation(
    body: ManualContractAttestationBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientContractSigningApplication = Depends(get_client_contract_signing_application),
):
    del principal
    try:
        preview = application.preview_manual_attestation(
            case_no=case_no,
            confirmation_method=body.confirmation_method,
            reason=body.reason,
        )
        return BaseResponse[ContractSigningManualAttestationPreviewView](
            data=ContractSigningManualAttestationPreviewView.model_validate(preview),
            message="人工客戶簽約證據 Preview 已完成",
        )
    except ValueError as error:
        code = str(error) or "manual_contract_preview_failed"
        raise typed_http_error(409, "domain_blocked", code, "人工客戶簽約證據目前無法套用。", f"manual-client-preview:{case_no}") from error


@router.post("/{case_no}/contract-signing/client/manual-attestation", response_model=BaseResponse[ContractSigningReceiptView])
def record_manual_client_contract_attestation(
    document: UploadFile = File(...),
    confirmation_method: Literal["phone", "paper", "in_person", "verified_other"] = Form(...),
    reason: str = Form(..., min_length=1, max_length=500),
    preview_fingerprint: str = Form(..., min_length=64, max_length=64),
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ClientContractSigningApplication = Depends(get_client_contract_signing_application),
):
    content = _document_content(document)
    command = ManualClientContractAttestationCommand(
        case_no, content, _filename(document), _mime_type(document), confirmation_method,
        reason, preview_fingerprint, _actor_id(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id),
    )
    return _response(lambda: application.record_manual_attestation(command), "已記錄人工客戶簽約證據", correlation_id)


@router.get("/{case_no}/contract-signing/documents/{document_version_id}/download")
def download_contract_document(
    request: Request,
    case_no: str = Path(..., min_length=1, max_length=50),
    document_version_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: ContractSigningDocumentQueryApplication = Depends(
        get_contract_signing_document_query_application
    ),
    connection_factory: ConnectionFactory = Depends(get_access_control_connection_factory),
):
    try:
        document = application.find_document_for_download(case_no, document_version_id)
        if document is None:
            raise ValueError("contract_document_not_found")
        content = read_archived_contract_document(
            storage_root=_archive_root(), storage_key=document.storage_key,
            expected_sha256=document.sha256,
        )
        record_admin_audit(
            connection_factory=connection_factory,
            principal=principal, action="contract_document_downloaded",
            request_path=request.url.path, http_method="GET", result_status=200,
            resource_type="contract_document_version", resource_id=str(document_version_id),
            details={"case_no": case_no, "sha256": document.sha256},
        )
        filename = document.original_filename.replace('"', "")
        suffix = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        safe_filename = f"contract_document_{document_version_id}.{suffix}"
        return Response(content=content, media_type=document.mime_type, headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_filename}"; '
                f"filename*=UTF-8''{quote(filename, safe='')}"
            ),
        })
    except (ValueError, OSError) as error:
        raise typed_http_error(
            404,
            "not_found",
            "contract_document_not_found",
            "找不到或無法驗證契約文件。",
            f"contract-document:{document_version_id}",
        ) from error


def _response(operation, message: str, correlation_id: str) -> BaseResponse[ContractSigningReceiptView]:
    try:
        receipt = operation()
        return BaseResponse[ContractSigningReceiptView](
            data=ContractSigningReceiptView(
                document_version_id=receipt.document_version_id,
                signing_event_id=receipt.signing_event_id,
                line_delivery_task_id=receipt.line_delivery_task_id,
                commitment_id=getattr(receipt, "commitment_id", None),
                contract_identity=getattr(receipt, "contract_identity", None),
            ),
            message=message,
        )
    except ValueError as error:
        code = str(error) or "contract_signing_validation_error"
        status_code = 409 if code in _DOMAIN_BLOCKER_CODES else 422
        category = "domain_blocked" if status_code == 409 else "validation"
        raise typed_http_error(status_code, category, code, "契約簽署流程目前無法執行。", correlation_id) from error
    except HTTPException:
        raise
    except Exception as error:
        raise typed_http_error(500, "internal", "contract_signing_internal_error", "契約簽署處理失敗。", correlation_id) from error


def _document_content(document: UploadFile) -> bytes:
    content = document.file.read(_MAXIMUM_DOCUMENT_SIZE + 1)
    validate_contract_document_content(content, _mime_type(document))
    return content


def _filename(document: UploadFile) -> str:
    return document.filename or "signed-contract.bin"


def _mime_type(document: UploadFile) -> str:
    return document.content_type or "application/octet-stream"


def _actor_id(principal: AdminPrincipal) -> str:
    return str(principal.username or "").strip()


def _contract_signing_status_view(status: ContractSigningStatus) -> ContractSigningQueryView:
    return ContractSigningQueryView(
        case_no=status.case_no,
        staff_segments=[
            {
                "segment_id": segment.segment_id,
                "staff_id": segment.staff_id,
                "sent": segment.sent,
                "signed_received": segment.signed_received,
            }
            for segment in status.staff_segments
        ],
        commitment_id=status.commitment_id,
        client_document_sent=status.client_document_sent,
        client_signed_received=status.client_signed_received,
        contract_identity=status.contract_identity,
        documents=[
            {
                "document_version_id": document.document_version_id,
                "scope": document.scope,
                "role": document.role,
                "target_key": document.target_key,
                "version_number": document.version_number,
                "template_key": document.template_key,
                "template_sha256": document.template_sha256,
                "mapping_sha256": document.mapping_sha256,
                "archive_sha256": document.archive_sha256,
                "mime_type": document.mime_type,
                "file_size": document.file_size,
            }
            for document in status.documents
        ],
    )


_DOMAIN_BLOCKER_CODES = frozenset({
    "contract_line_recipient_unbound",
    "contract_line_recipient_subject_mismatch",
    "contract_signing_segment_not_found",
    "staff_contract_not_sent",
    "staff_commitment_required_before_client_contract",
    "client_contract_not_sent",
    "contract_identity_already_recorded",
    "contract_document_version_stale",
    "contract_signature_idempotency_conflict",
    "manual_contract_already_signed",
    "manual_contract_confirmation_method_invalid",
    "manual_contract_plan_not_current",
    "manual_contract_customer_acceptance_required",
    "manual_contract_preview_stale",
    "manual_contract_reason_missing",
})

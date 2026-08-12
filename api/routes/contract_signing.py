"""Typed API endpoints for the staff-first, client-second contract flow."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Path, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.contract_signing import (
    _archive_root,
    get_client_contract_signing_application,
    get_staff_contract_signing_application,
)
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.archive.contract_documents import read_archived_contract_document, validate_contract_document_content
from subsystems.access.authentication_session import record_admin_audit
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.contract_signing.client_contract_application import (
    ClientContractSigningApplication,
    RecordClientSignedReturnCommand,
    SendClientContractCommand,
)
from subsystems.contract_signing.staff_contract_application import (
    RecordStaffSignedReturnCommand,
    SendStaffContractCommand,
    StaffContractSigningApplication,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Contract Signing"])
_MAXIMUM_DOCUMENT_SIZE = 20 * 1024 * 1024


class SendContractBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    download_url: str = Field(min_length=9, max_length=500)


@router.get("/{case_no}/contract-signing", response_model=BaseResponse[dict])
def query_contract_signing(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    connection = get_connection()
    try:
        return BaseResponse(data=_signing_status(connection, case_no), message="成功取得契約簽署狀態")
    except ValueError as error:
        raise typed_http_error(404, "not_found", str(error), "找不到案件的契約簽署資料。", f"contract-signing-query:{case_no}") from error
    except Exception as error:
        raise typed_http_error(500, "internal", "contract_signing_query_failed", "契約簽署狀態查詢失敗。", f"contract-signing-query:{case_no}") from error
    finally:
        connection.close()


@router.post("/{case_no}/contract-signing/staff-segments/{segment_id}/send", response_model=BaseResponse[dict])
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


@router.post("/{case_no}/contract-signing/staff-segments/{segment_id}/signed-return", response_model=BaseResponse[dict])
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


@router.post("/{case_no}/contract-signing/client/send", response_model=BaseResponse[dict])
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


@router.post("/{case_no}/contract-signing/client/signed-return", response_model=BaseResponse[dict])
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


@router.get("/{case_no}/contract-signing/documents/{document_version_id}/download")
def download_contract_document(
    request: Request,
    case_no: str = Path(..., min_length=1, max_length=50),
    document_version_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT asset.storage_key,asset.sha256,asset.mime_type,asset.original_filename "
                "FROM contract_document_versions document JOIN media_assets asset ON asset.id=document.media_asset_id "
                "WHERE document.case_no=%s AND document.id=%s",
                (case_no, document_version_id),
            )
            document = cursor.fetchone()
        if document is None:
            raise ValueError("contract_document_not_found")
        content = read_archived_contract_document(
            storage_root=_archive_root(), storage_key=str(document["storage_key"]),
            expected_sha256=str(document["sha256"]),
        )
        record_admin_audit(
            principal=principal, action="contract_document_downloaded",
            request_path=request.url.path, http_method="GET", result_status=200,
            resource_type="contract_document_version", resource_id=str(document_version_id),
            details={"case_no": case_no, "sha256": str(document["sha256"])},
        )
        filename = str(document["original_filename"]).replace('"', "")
        return Response(content=content, media_type=str(document["mime_type"]), headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        })
    except ValueError as error:
        raise typed_http_error(404, "not_found", str(error), "找不到或無法驗證契約文件。", f"contract-document:{document_version_id}") from error
    finally:
        connection.close()


def _response(operation, message: str, correlation_id: str) -> BaseResponse[dict]:
    try:
        receipt = operation()
        return BaseResponse(data={
            "document_version_id": receipt.document_version_id,
            "signing_event_id": receipt.signing_event_id,
            "line_delivery_task_id": receipt.line_delivery_task_id,
            "commitment_id": getattr(receipt, "commitment_id", None),
            "contract_identity": getattr(receipt, "contract_identity", None),
        }, message=message)
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


def _signing_status(connection, case_no: str) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT contract_identity FROM orders WHERE case_no=%s", (case_no,))
        order = cursor.fetchone()
        if order is None:
            raise ValueError("order_not_found")
        cursor.execute(
            "SELECT segment.id AS segment_id,segment.staff_id, "
            "EXISTS(SELECT 1 FROM contract_signing_events event JOIN contract_document_versions document ON document.id=event.document_version_id WHERE event.matching_segment_id=segment.id AND event.event_type='sent' AND document.document_scope='staff_segment') AS sent, "
            "EXISTS(SELECT 1 FROM contract_signing_events event JOIN contract_document_versions document ON document.id=event.document_version_id WHERE event.matching_segment_id=segment.id AND event.event_type='signed_received' AND document.document_scope='staff_segment') AS signed_received "
            "FROM caregiver_matching_plan_segments segment JOIN caregiver_matching_plans plan ON plan.id=segment.plan_id "
            "WHERE plan.case_no=%s ORDER BY segment.segment_order,segment.id",
            (case_no,),
        )
        staff_segments = [
            {"segment_id": int(row["segment_id"]), "staff_id": int(row["staff_id"]), "sent": bool(row["sent"]), "signed_received": bool(row["signed_received"])}
            for row in cursor.fetchall()
        ]
        cursor.execute("SELECT id FROM precontract_service_commitments WHERE case_no=%s", (case_no,))
        commitment = cursor.fetchone()
        cursor.execute(
            "SELECT event.event_type FROM contract_signing_events event JOIN contract_document_versions document ON document.id=event.document_version_id "
            "WHERE event.case_no=%s AND document.document_scope='client_contract' ORDER BY event.id",
            (case_no,),
        )
        client_events = [str(row["event_type"]) for row in cursor.fetchall()]
        cursor.execute(
            "SELECT document.id,document.document_scope,document.document_role,document.document_target_key,"
            "document.version_number,document.template_key,document.template_sha256,document.mapping_sha256,"
            "asset.sha256 AS archive_sha256,asset.mime_type,asset.file_size "
            "FROM contract_document_versions document "
            "JOIN media_assets asset ON asset.id=document.media_asset_id "
            "WHERE document.case_no=%s ORDER BY document.id",
            (case_no,),
        )
        documents = [
            {
                "document_version_id": int(row["id"]),
                "scope": str(row["document_scope"]),
                "role": str(row["document_role"]),
                "target_key": str(row["document_target_key"]),
                "version_number": int(row["version_number"]),
                "template_key": row["template_key"],
                "template_sha256": row["template_sha256"],
                "mapping_sha256": row["mapping_sha256"],
                "archive_sha256": str(row["archive_sha256"]),
                "mime_type": str(row["mime_type"]),
                "file_size": int(row["file_size"]),
            }
            for row in cursor.fetchall()
        ]
    return {
        "case_no": case_no,
        "staff_segments": staff_segments,
        "commitment_id": None if commitment is None else int(commitment["id"]),
        "client_document_sent": "sent" in client_events,
        "client_signed_received": "signed_received" in client_events,
        "contract_identity": order["contract_identity"],
        "documents": documents,
    }


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
})

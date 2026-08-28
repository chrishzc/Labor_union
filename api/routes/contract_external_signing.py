"""
File: contract_external_signing.py
Description: 提供外部簽約查詢、人工回報、PDF staging、Apply、receipt 與 readback API。
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal, Mapping

from fastapi import APIRouter, Depends, File, Header, HTTPException, Path as ApiPath, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.dependencies.admin_auth import admin_actor_context, require_persisted_admin
from api.dependencies.contract_external_signing import (
    ContractExternalSigningApplication,
    get_contract_external_signing_application,
)
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from domains.contract_signing.external_signing import ExternalSigningRuleError
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.contract_signing.external_signing_contracts import (
    ExternalSigningTypedError,
    ManualAttestationEvidence,
    ManualAttestationMethod,
    RecordManualExternalClientSigningReport,
    RecordManualExternalStaffSigningReport,
)
from subsystems.contract_signing.final_document_workflow import (
    ApplyFinalSignedContractUpload,
    FinalDocumentWorkflowError,
    PreviewFinalSignedContractUpload,
)
from subsystems.contract_signing.unsigned_contract_pdf import UnsignedContractPdfError
from subsystems.controlled_files.contracts import ControlledFileStorageError
from subsystems.controlled_files.workflow import (
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileWorkflowError,
    StageControlledFile,
)
from subsystems.orders.contract_completion_workflow import ContractCompletionWorkflowError


router = APIRouter(prefix="/api/v1/orders", tags=["Contract External Signing"])

_CASE = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,49}$"
_SESSION = r"^ces_[0-9a-f]{32}$"
_STAGING = r"^cfs_[0-9a-f]{32}$"
_RECEIPT = r"^cesr_[0-9a-f]{32}$"
_PREVIEW_TOKEN = r"^cp_[A-Za-z0-9_-]{43}$"
_IDEMPOTENCY = r"^[a-z0-9][a-z0-9._:-]{0,190}$"
_CORRELATION = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$"
_MAX_PDF_BYTES = 20 * 1024 * 1024


class CompletionReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status_version: int = Field(ge=0)
    expected_document_version_id: int = Field(ge=1)
    confirmation_method: ManualAttestationMethod
    reason: str = Field(min_length=1, max_length=1000)


class ClientCompletionReportBody(CompletionReportBody):
    expected_commitment_id: int = Field(ge=1)


class FinalPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staging_id: str = Field(pattern=_STAGING)
    expected_status_version: int = Field(ge=0)


class FinalApplyBody(FinalPreviewBody):
    expected_staging_version: int = Field(ge=1)
    preview_token: str = Field(pattern=_PREVIEW_TOKEN)


class UnsignedDocumentView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_version_id: int = Field(ge=1)
    filename: str = Field(min_length=1, max_length=255)
    mime_type: Literal["application/pdf"]
    size_bytes: int = Field(ge=1)


class StaffTargetView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    matching_segment_id: int = Field(ge=1)
    staff_subject_reference: str = Field(min_length=1, max_length=191)
    document_version_id: int = Field(ge=1)
    reported: bool


class ClientTargetView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    client_subject_reference: str = Field(min_length=1, max_length=191)
    document_version_id: int = Field(ge=1)
    reported: bool


class ExternalSigningQueryView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_no: str = Field(pattern=_CASE)
    session_id: str = Field(pattern=_SESSION)
    state: Literal[
        "staff_reporting",
        "staff_reports_complete",
        "client_reported_final_pdf_pending",
        "completed",
        "superseded",
    ]
    status_version: int = Field(ge=0)
    matching_plan_id: int = Field(ge=1)
    commitment_id: int | None = Field(default=None, ge=1)
    unsigned_document: UnsignedDocumentView | None
    staff_targets: list[StaffTargetView]
    client_target: ClientTargetView


class ExternalSigningReceiptView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receipt_id: str = Field(pattern=_RECEIPT)
    command_type: Literal[
        "record_staff_report",
        "record_client_report",
        "apply_final_signed_contract",
    ]
    schema_version: Literal["contract-external-signing-receipt.v1"]
    session_id: str = Field(pattern=_SESSION)
    outcome_state: Literal["recorded", "completed"]
    resulting_status_version: int = Field(ge=1)
    resulting_state: Literal[
        "staff_reporting",
        "staff_reports_complete",
        "client_reported_final_pdf_pending",
        "completed",
        "superseded",
    ]
    matching_segment_id: int | None = Field(default=None, ge=1)
    final_document_id: str | None = Field(default=None, pattern=r"^cfd_[0-9a-f]{32}$")
    replayed: bool
    applied_at: datetime

    @model_validator(mode="after")
    def require_closed_command_result_union(self):
        valid = {
            "record_staff_report": (
                self.outcome_state == "recorded"
                and self.resulting_state in {"staff_reporting", "staff_reports_complete"}
                and self.matching_segment_id is not None
                and self.final_document_id is None
            ),
            "record_client_report": (
                self.outcome_state == "recorded"
                and self.resulting_state == "client_reported_final_pdf_pending"
                and self.matching_segment_id is None
                and self.final_document_id is None
            ),
            "apply_final_signed_contract": (
                self.outcome_state == "completed"
                and self.resulting_state == "completed"
                and self.matching_segment_id is None
                and self.final_document_id is not None
            ),
        }
        if not valid[self.command_type]:
            raise ValueError("external signing receipt command result is invalid")
        return self


def _application():
    yield from get_contract_external_signing_application()


@router.get("/{case_no}/contract-external-signing")
def query_external_signing(
    case_no: str = ApiPath(pattern=_CASE),
    _: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    return _call(
        lambda: BaseResponse(data=_public_query(application.query_case(case_no))),
        "query",
    )


@router.get("/{case_no}/contract-external-signing/unsigned-pdf")
def download_unsigned_pdf(
    case_no: str = ApiPath(pattern=_CASE),
    expected_document_version: int = Header(
        alias="X-Expected-Document-Version", ge=1
    ),
    correlation_id: str = Header(alias="X-Correlation-ID", pattern=_CORRELATION),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    def action():
        result = application.download_unsigned(
            case_no,
            expected_document_version,
            admin_actor_context(principal),
            CorrelationId(correlation_id),
        )
        filename = Path(result.filename).name.replace('"', "")
        return Response(
            content=result.content,
            media_type="application/pdf",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Contract-Document-Version": str(result.document_version_id),
                "X-Correlation-ID": correlation_id,
            },
        )

    return _call(action, correlation_id)


@router.post("/{case_no}/contract-external-signing/staff-segments/{segment_id}/completion-reports")
def record_staff_report(
    body: CompletionReportBody,
    case_no: str = ApiPath(pattern=_CASE),
    segment_id: int = ApiPath(ge=1),
    idempotency_key: str = Header(alias="Idempotency-Key", pattern=_IDEMPOTENCY),
    receipt_id: str = Header(alias="X-Receipt-ID", pattern=_RECEIPT),
    correlation_id: str = Header(alias="X-Correlation-ID", pattern=_CORRELATION),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    _require_receipt_identity(idempotency_key, receipt_id, correlation_id)

    def action():
        facts = _require_facts(application, case_no)
        target = facts.staff_target(segment_id)
        if target is None:
            raise ExternalSigningTypedError(
                category="domain_blocked",
                code="external_staff_report_target_not_found",
                message="找不到指定簽署對象。",
            )
        receipt = application.reports.apply_manual_staff_report(
            RecordManualExternalStaffSigningReport(
                session_id=facts.session_id,
                case_no=case_no,
                matching_plan_id=facts.matching_plan_id,
                matching_segment_id=segment_id,
                expected_document_version_id=body.expected_document_version_id,
                attested_subject_reference=target.staff_subject_reference,
                attestation=_attestation(body, receipt_id),
                source_event_identity=receipt_id,
                source_payload_sha256=_payload_hash(body, case_no, segment_id),
                occurred_at=datetime.now(timezone.utc),
                expected_status_version=ExpectedVersion(body.expected_status_version),
                actor=admin_actor_context(principal),
                idempotency_key=IdempotencyKey(idempotency_key),
                correlation_id=CorrelationId(correlation_id),
            )
        )
        view = application.read_receipt(case_no, receipt_id)
        if view is None:
            raise RuntimeError("external signing receipt missing after commit")
        view["replayed"] = receipt.replayed
        return BaseResponse(data=_public_receipt(view))

    return _call(action, correlation_id)


@router.post("/{case_no}/contract-external-signing/client/completion-reports")
def record_client_report(
    body: ClientCompletionReportBody,
    case_no: str = ApiPath(pattern=_CASE),
    idempotency_key: str = Header(alias="Idempotency-Key", pattern=_IDEMPOTENCY),
    receipt_id: str = Header(alias="X-Receipt-ID", pattern=_RECEIPT),
    correlation_id: str = Header(alias="X-Correlation-ID", pattern=_CORRELATION),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    _require_receipt_identity(idempotency_key, receipt_id, correlation_id)

    def action():
        facts = _require_facts(application, case_no)
        receipt = application.reports.apply_manual_client_report(
            RecordManualExternalClientSigningReport(
                session_id=facts.session_id,
                case_no=case_no,
                matching_plan_id=facts.matching_plan_id,
                expected_document_version_id=body.expected_document_version_id,
                expected_commitment_id=body.expected_commitment_id,
                attested_subject_reference=facts.client_subject_reference,
                attestation=_attestation(body, receipt_id),
                source_event_identity=receipt_id,
                source_payload_sha256=_payload_hash(body, case_no, None),
                occurred_at=datetime.now(timezone.utc),
                expected_status_version=ExpectedVersion(body.expected_status_version),
                actor=admin_actor_context(principal),
                idempotency_key=IdempotencyKey(idempotency_key),
                correlation_id=CorrelationId(correlation_id),
            )
        )
        view = application.read_receipt(case_no, receipt_id)
        if view is None:
            raise RuntimeError("external signing receipt missing after commit")
        view["replayed"] = receipt.replayed
        return BaseResponse(data=_public_receipt(view))

    return _call(action, correlation_id)


@router.post("/{case_no}/contract-external-signing/final-document/staging")
def stage_final_document(
    case_no: str = ApiPath(pattern=_CASE),
    document: UploadFile = File(),
    idempotency_key: str = Header(alias="Idempotency-Key", pattern=_IDEMPOTENCY),
    correlation_id: str = Header(alias="X-Correlation-ID", pattern=_CORRELATION),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    def action():
        content = document.file.read(_MAX_PDF_BYTES + 1)
        filename = Path(document.filename or "").name
        if (
            not filename.lower().endswith(".pdf")
            or document.content_type != "application/pdf"
            or not content.startswith(b"%PDF-")
            or not content.rstrip().endswith(b"%%EOF")
            or len(content) > _MAX_PDF_BYTES
        ):
            raise ValueError("final signed contract must be a valid PDF")
        result = application.controlled_files.stage(
            StageControlledFile(
                owner=ControlledFileOwner.CONTRACT_SIGNING,
                purpose=ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
                subject_reference=case_no,
                object_key="final-signed-contract",
                logical_folder=f"contract-signing/{case_no}",
                filename=filename,
                mime_type="application/pdf",
                content=content,
                idempotency_key=IdempotencyKey(idempotency_key),
                actor=admin_actor_context(principal),
                correlation_id=CorrelationId(correlation_id),
            )
        )
        return BaseResponse(data={
            "staging_id": result.staging_id,
            "filename": result.filename,
            "mime_type": result.mime_type,
            "size_bytes": result.size_bytes,
            "expires_at": result.expires_at,
        })

    return _call(action, correlation_id)


@router.post("/{case_no}/contract-external-signing/final-document/preview")
def preview_final_document(
    body: FinalPreviewBody,
    case_no: str = ApiPath(pattern=_CASE),
    _: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    def action():
        facts = _require_facts(application, case_no)
        result = application.final_documents.preview(
            PreviewFinalSignedContractUpload(
                facts.session_id,
                case_no,
                ExpectedVersion(body.expected_status_version),
                _final_intent(case_no, body.staging_id),
            )
        )
        return BaseResponse(data={
            "preview_token": result.preview_token,
            "staging_id": body.staging_id,
            "expected_staging_version": result.expected_staging_version,
            "filename": result.filename,
            "mime_type": result.mime_type,
            "size_bytes": result.size_bytes,
            "blockers": list(result.blockers),
            "can_apply": not result.blockers,
        })

    return _call(action, "preview")


@router.post("/{case_no}/contract-external-signing/final-document/apply")
def apply_final_document(
    body: FinalApplyBody,
    case_no: str = ApiPath(pattern=_CASE),
    idempotency_key: str = Header(alias="Idempotency-Key", pattern=_IDEMPOTENCY),
    receipt_id: str = Header(alias="X-Receipt-ID", pattern=_RECEIPT),
    correlation_id: str = Header(alias="X-Correlation-ID", pattern=_CORRELATION),
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    _require_receipt_identity(idempotency_key, receipt_id, correlation_id)

    def action():
        facts = _require_facts(application, case_no)
        preview = PreviewFinalSignedContractUpload(
            facts.session_id,
            case_no,
            ExpectedVersion(body.expected_status_version),
            _final_intent(case_no, body.staging_id),
        )
        receipt = application.final_documents.apply(
            ApplyFinalSignedContractUpload(
                preview,
                ExpectedVersion(body.expected_staging_version),
                body.preview_token,
                IdempotencyKey(idempotency_key),
                admin_actor_context(principal),
                "已驗證並套用最終簽署契約 PDF。",
                CorrelationId(correlation_id),
            )
        )
        view = application.read_receipt(case_no, receipt_id)
        if view is None:
            raise RuntimeError("external signing receipt missing after commit")
        view["replayed"] = receipt.replayed
        return BaseResponse(data=_public_receipt(view))

    return _call(action, correlation_id)


@router.get("/{case_no}/contract-external-signing/receipts/{receipt_id}")
def read_receipt(
    case_no: str = ApiPath(pattern=_CASE),
    receipt_id: str = ApiPath(pattern=_RECEIPT),
    _: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    result = application.read_receipt(case_no, receipt_id)
    if result is None:
        raise typed_http_error(404, "not_found", "external_signing_receipt_not_found", "找不到命令收據。", "receipt")
    return BaseResponse(data=_public_receipt(result))


@router.get("/{case_no}/contract-external-signing/final-document/readback")
def readback_final_document(
    case_no: str = ApiPath(pattern=_CASE),
    _: AdminPrincipal = Depends(require_persisted_admin),
    application: ContractExternalSigningApplication = Depends(_application),
):
    def action():
        facts = _require_facts(application, case_no)
        result = application.final_documents.readback(case_no)
        return BaseResponse(data={
            "case_no": result.case_no,
            "session_id": facts.session_id,
            "final_document_id": result.final_document_id,
            "controlled_file_id": result.file_id,
            "version_number": result.version,
            "filename": result.filename,
            "mime_type": result.mime_type,
            "size_bytes": result.size_bytes,
            "status": result.status,
            "integrity_verified": True,
            "applied_at": result.applied_at,
        })

    return _call(action, "readback")


def _require_facts(application, case_no):
    facts = application.load_facts(case_no)
    if facts is None:
        application.reports.query_case(case_no)
        raise AssertionError("query_case must return or raise")
    return facts


def _public_query(value: Mapping[str, Any]) -> dict[str, Any]:
    return ExternalSigningQueryView.model_validate(value).model_dump(mode="json")


def _public_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    return ExternalSigningReceiptView.model_validate(value).model_dump(mode="json")


def _attestation(body: CompletionReportBody, receipt_id: str) -> ManualAttestationEvidence:
    evidence = f"manual-evidence:{receipt_id}"
    return ManualAttestationEvidence(
        body.confirmation_method,
        body.reason.strip(),
        evidence,
        hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
    )


def _payload_hash(body: BaseModel, case_no: str, segment_id: int | None) -> str:
    payload = {"case_no": case_no, "segment_id": segment_id, **body.model_dump(mode="json")}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _final_intent(case_no: str, staging_id: str) -> ControlledFileIntent:
    return ControlledFileIntent(
        staging_id,
        ControlledFileOwner.CONTRACT_SIGNING,
        ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        case_no,
        "final-signed-contract",
        f"contract-signing/{case_no}",
    )


def _require_receipt_identity(idempotency_key: str, receipt_id: str, correlation_id: str) -> None:
    suffix = idempotency_key.rsplit(":", 1)[-1]
    expected = f"cesr_{suffix}" if re.fullmatch(r"[0-9a-f]{32}", suffix) else None
    if expected != receipt_id:
        raise typed_http_error(422, "validation", "external_signing_receipt_identity_mismatch", "Receipt identity 與命令識別不一致。", correlation_id)


def _call(action, correlation_id: str):
    try:
        return action()
    except HTTPException:
        raise
    except ContractCompletionWorkflowError as error:
        typed = error.error
        raise typed_http_error(409, str(typed.category), typed.code, typed.message, correlation_id, retryable=typed.retryable) from error
    except (ExternalSigningTypedError, ExternalSigningRuleError, FinalDocumentWorkflowError) as error:
        category = getattr(error, "category", "conflict")
        status = 404 if category == "not_found" else 409
        raise typed_http_error(status, category, str(getattr(error, "code", "external_signing_conflict")), str(error), correlation_id, retryable=getattr(error, "retryable", False)) from error
    except UnsignedContractPdfError as error:
        status = 404 if error.category == "not_found" else 503 if error.retryable else 409
        raise typed_http_error(status, error.category, error.code, str(error), correlation_id, retryable=error.retryable) from error
    except (ControlledFileWorkflowError, ControlledFileStorageError) as error:
        raise typed_http_error(503 if getattr(error, "retryable", False) else 409, "unavailable" if getattr(error, "retryable", False) else "conflict", getattr(error, "code", "controlled_file_error"), str(error), correlation_id, retryable=getattr(error, "retryable", False)) from error
    except (TypeError, ValueError) as error:
        raise typed_http_error(422, "validation", "contract_external_signing_input_invalid", str(error), correlation_id) from error


__all__ = ["router"]

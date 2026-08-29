"""Closed HTTP output views for contract signing endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _ContractSigningView(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContractSigningStaffSegmentView(_ContractSigningView):
    segment_id: int
    staff_id: int
    sent: bool
    signed_received: bool


class ContractSigningDocumentView(_ContractSigningView):
    document_version_id: int
    scope: Literal["staff_segment", "client_contract"]
    role: Literal["template_generated", "signed_return"]
    target_key: str
    version_number: int
    template_key: str | None
    template_sha256: str | None
    mapping_sha256: str | None
    archive_sha256: str
    mime_type: str
    file_size: int


class ContractSigningQueryView(_ContractSigningView):
    case_no: str
    staff_segments: list[ContractSigningStaffSegmentView]
    commitment_id: int | None
    client_document_sent: bool
    client_signed_received: bool
    contract_identity: str | None
    documents: list[ContractSigningDocumentView]


class ContractSigningReceiptView(_ContractSigningView):
    document_version_id: int
    signing_event_id: int
    line_delivery_task_id: int | None
    commitment_id: int | None
    contract_identity: str | None


class ContractSigningManualAttestationPreviewView(_ContractSigningView):
    case_no: str
    scope: Literal["staff_segment", "client_contract"]
    matching_segment_id: int | None
    confirmation_method: Literal["phone", "paper", "in_person", "verified_other"]
    preview_fingerprint: str
    can_apply: bool
    line_delivery_task_id: int | None


__all__ = [
    "ContractSigningDocumentView",
    "ContractSigningManualAttestationPreviewView",
    "ContractSigningQueryView",
    "ContractSigningReceiptView",
    "ContractSigningStaffSegmentView",
]

"""Build contract-delivery requests only for verified LINE bindings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey


class ContractLineRecipientError(StrEnum):
    UNBOUND = "contract_line_recipient_unbound"
    SUBJECT_MISMATCH = "contract_line_recipient_subject_mismatch"


@dataclass(frozen=True, slots=True)
class ContractLineBinding:
    line_user_id: str | None
    binding_status: str | None
    subject_type: str | None
    subject_reference: str | None


def require_contract_line_recipient(
    binding: ContractLineBinding,
    *,
    subject_type: str,
    subject_reference: str,
) -> LineRecipient:
    if binding.binding_status != "bound" or not binding.line_user_id:
        raise ValueError(ContractLineRecipientError.UNBOUND.value)
    if (binding.subject_type, binding.subject_reference) != (
        subject_type,
        subject_reference,
    ):
        raise ValueError(ContractLineRecipientError.SUBJECT_MISMATCH.value)
    return LineRecipient(LineRecipientType.USER, LineUserId(binding.line_user_id))


def build_contract_delivery_request(
    recipient: LineRecipient,
    *,
    case_no: str,
    document_version_id: int,
    download_url: str,
    audience_label: str,
    scheduled_at: datetime,
    idempotency_key: IdempotencyKey,
    correlation_id: CorrelationId,
) -> LineDeliveryRequest:
    _require_https_url(download_url)
    payload = canonical_line_payload_json(
        {"text": _delivery_text(case_no, audience_label, download_url)}
    )
    return LineDeliveryRequest(
        recipient,
        LineMessageKind.TEXT,
        payload,
        scheduled_at,
        idempotency_key,
        correlation_id,
        "contract_document_version",
        f"{case_no}:{document_version_id}",
    )


def _require_https_url(value: str) -> None:
    if not isinstance(value, str) or not value.startswith("https://"):
        raise ValueError("contract document download URL must use HTTPS")


def _delivery_text(case_no: str, audience_label: str, download_url: str) -> str:
    return f"案件 {case_no} 的{audience_label}已備妥，請由此安全連結查看：{download_url}"


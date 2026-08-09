"""Typed commands and results for durable contract webhook processing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.contract_integration.contract_event import VerifiedContractEvent
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


class ContractIntakeOutcome(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ReceiveContractWebhookCommand:
    provider: str
    raw_body: bytes
    signature: str | None
    received_at: datetime
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ContractWebhookIntakeResult:
    outcome: ContractIntakeOutcome
    receipt_id: int
    inbox_id: int | None = None


@dataclass(frozen=True, slots=True)
class MapContractEvidenceCommand:
    provider: str
    provider_contract_id: str
    internal_contract_identity: str
    expected_version: int
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ContractEvidenceView:
    inbox_id: int
    event: VerifiedContractEvent
    internal_contract_identity: str | None
    processing_status: str
    processing_attempts: int
    last_error_code: str | None = None
    mapping_version: int = 0


__all__ = [
    "ContractEvidenceView",
    "ContractIntakeOutcome",
    "ContractWebhookIntakeResult",
    "MapContractEvidenceCommand",
    "ReceiveContractWebhookCommand",
]

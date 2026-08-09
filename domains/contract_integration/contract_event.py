"""Pure rules for verified external contract events and projection state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from shared_kernel.validation import require_canonical_text


class ContractInboxStatus(StrEnum):
    RECEIVED = "received"
    VERIFIED = "verified"
    NORMALIZED = "normalized"
    APPLIED = "applied"
    REJECTED = "rejected"
    RETRY_PENDING = "retry_pending"
    FAILED = "failed"


class ContractProjectionStatus(StrEnum):
    PENDING_SIGNATURE = "pending_signature"
    SIGNED = "signed"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    PROVIDER_FAILED = "provider_failed"


@dataclass(frozen=True, slots=True)
class VerifiedContractEvent:
    provider: str
    provider_contract_id: str
    provider_event_id: str
    event_type: str
    contract_status: ContractProjectionStatus
    occurred_at: datetime
    canonical_payload_hash: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.provider, "provider"),
            (self.provider_contract_id, "provider_contract_id"),
            (self.provider_event_id, "provider_event_id"),
            (self.event_type, "event_type"),
        ):
            require_canonical_text(value, name, 191)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("provider_occurred_at must be timezone-aware")
        if len(self.canonical_payload_hash) != 64:
            raise ValueError("canonical_payload_hash must be sha256")


class UnknownProviderStatus(ValueError):
    """An unmapped provider status must never be treated as signed."""


class ContractStatusRegression(ValueError):
    """A terminal provider projection cannot regress or change terminal state."""


def map_provider_status(raw_status: str, exact_mapping: dict[str, str]) -> ContractProjectionStatus:
    normalized = str(raw_status or "").strip()
    mapped = exact_mapping.get(normalized)
    if mapped is None:
        raise UnknownProviderStatus("external_contract_status_unknown")
    return ContractProjectionStatus(mapped)


def canonical_payload_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_projection_transition(
    current: ContractProjectionStatus | None,
    target: ContractProjectionStatus,
) -> None:
    if current is None or current is ContractProjectionStatus.PENDING_SIGNATURE:
        return
    if current is target:
        return
    raise ContractStatusRegression("external_contract_status_regression")


__all__ = [
    "ContractInboxStatus",
    "ContractProjectionStatus",
    "ContractStatusRegression",
    "UnknownProviderStatus",
    "VerifiedContractEvent",
    "canonical_payload_hash",
    "map_provider_status",
    "validate_projection_transition",
]

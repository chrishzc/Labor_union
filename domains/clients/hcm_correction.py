"""Client-owned typed command used by the HCM resubmission boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from shared_kernel.validation import require_canonical_text


_CLIENT_FIELDS = frozenset(
    {
        "created_at",
        "ip_address",
        "name",
        "gender",
        "phone",
        "city",
        "due_month",
        "residence_type",
        "delivery_type",
        "baby_info",
        "service_type",
    }
)


@dataclass(frozen=True, slots=True)
class ClientHcmCorrectionCommand:
    """A bounded, version-checked mutation of one Client root."""

    client_id: int
    case_no: str
    expected_client_version: int
    review_identity: str
    source_event_identity: str
    field_path: str
    values: Mapping[str, object]
    idempotency_key: str
    actor: str
    reason: str
    correlation_id: str
    source_fingerprint: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.client_id, bool) or self.client_id <= 0:
            raise ValueError("client correction client id must be positive")
        if isinstance(self.expected_client_version, bool) or self.expected_client_version < 0:
            raise ValueError("client correction version must be nonnegative")
        require_canonical_text(self.case_no, "client correction case number", 50)
        for value, name, maximum in (
            (self.review_identity, "review identity", 191),
            (self.source_event_identity, "source event identity", 191),
            (self.field_path, "field path", 191),
            (self.idempotency_key, "idempotency key", 191),
            (self.actor, "actor", 100),
            (self.reason, "reason", 500),
            (self.correlation_id, "correlation id", 191),
        ):
            require_canonical_text(value, name, maximum)
        if self.source_fingerprint and (
            len(self.source_fingerprint) != 64
            or any(char not in "0123456789abcdef" for char in self.source_fingerprint)
        ):
            raise ValueError("client correction source fingerprint must be lowercase SHA-256 hex")
        if not isinstance(self.values, Mapping) or not self.values:
            raise ValueError("client correction values are required")
        keys = {str(key) for key in self.values}
        if keys - _CLIENT_FIELDS:
            raise ValueError("client correction target is not Client-owned")
        if any(value is None for value in self.values.values()):
            raise ValueError("client correction values cannot be null")


@dataclass(frozen=True, slots=True)
class ClientHcmCorrectionReceipt:
    event_identity: str
    client_id: int
    case_no: str
    resulting_client_version: int
    field_path: str
    values: Mapping[str, object]
    replayed: bool = False


class ClientHcmCorrectionPort(Protocol):
    def apply_in_current_uow(
        self, command: ClientHcmCorrectionCommand
    ) -> ClientHcmCorrectionReceipt: ...

    def readback(self, client_id: int) -> Mapping[str, object]: ...


__all__ = [
    "ClientHcmCorrectionCommand",
    "ClientHcmCorrectionPort",
    "ClientHcmCorrectionReceipt",
]

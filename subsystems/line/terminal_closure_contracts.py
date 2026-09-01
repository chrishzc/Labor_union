"""Typed handoff contracts for Orders terminal closure -> LINE Identity."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.identities import LineUserId
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


class TerminalClosureDecision(StrEnum):
    RESTORED = "restored"
    BLOCKED_ACTIVE_CLIENT_CASE = "blocked_active_client_case"
    BLOCKED_REVOKED_STAFF = "blocked_revoked_staff"
    NOOP_REPLAY = "noop_replay"


@dataclass(frozen=True, slots=True)
class TerminalClosureSourceEvent:
    """Immutable Orders-owned handoff; LINE only consumes this value."""

    source_event_identity: str
    case_no: str
    terminal_kind: str
    orders_version: int
    source_subject: str | None
    producer_reference: str
    occurred_at: str
    correlation_id: str
    idempotency_identity: str
    binding_version: int | None = None
    menu_revision: int | None = None
    capability: str = "staff_default_restore"

    def __post_init__(self) -> None:
        require_canonical_text(self.source_event_identity, "source event identity", 191)
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.terminal_kind, "terminal kind", 100)
        require_nonnegative_integer(self.orders_version, "Orders version")
        if self.source_subject is not None:
            require_canonical_text(self.source_subject, "source subject", 191)
        require_canonical_text(self.producer_reference, "producer reference", 191)
        require_canonical_text(self.occurred_at, "occurred at", 64)
        require_canonical_text(self.correlation_id, "correlation id", 191)
        require_canonical_text(self.idempotency_identity, "idempotency identity", 191)
        if self.binding_version is not None:
            require_nonnegative_integer(self.binding_version, "binding version")
        if self.menu_revision is not None:
            require_nonnegative_integer(self.menu_revision, "menu revision")
        require_canonical_text(self.capability, "capability", 100)

    @property
    def idempotency_key(self) -> IdempotencyKey:
        return IdempotencyKey(self.idempotency_identity)

    @property
    def payload_fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "source_event_identity": self.source_event_identity,
                "case_no": self.case_no,
                "terminal_kind": self.terminal_kind,
                "orders_version": self.orders_version,
                "source_subject": self.source_subject,
                "producer_reference": self.producer_reference,
                "occurred_at": self.occurred_at,
                "correlation_id": self.correlation_id,
                "idempotency_identity": self.idempotency_identity,
                "binding_version": self.binding_version,
                "menu_revision": self.menu_revision,
                "capability": self.capability,
            }
        )


@dataclass(frozen=True, slots=True)
class TerminalClosureReadback:
    source_event_identity: str
    case_no: str
    orders_version: int
    binding_version: int | None
    decision: TerminalClosureDecision
    menu_intent_identity: str | None = None
    receipt_identity: str | None = None
    typed_failure: str | None = None
    replay_of: TerminalClosureDecision | None = None


__all__ = [
    "TerminalClosureDecision",
    "TerminalClosureReadback",
    "TerminalClosureSourceEvent",
]

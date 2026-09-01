"""Typed contract for LINE's short-lived, one-time safe review links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


class SafeReviewLinkState(StrEnum):
    ISSUED = "issued"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SafeReviewLinkError(RuntimeError):
    """Closed typed failure; callers must not retry blindly."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _text(value: str, name: str, maximum: int = 191) -> str:
    return require_canonical_text(value, name, maximum)


@dataclass(frozen=True, slots=True)
class IssueSafeReviewLink:
    link_id: str
    raw_token: str
    canonical_internal_target: str
    target_version: int
    source_alert_identity: str
    allowed_actor_ref: str
    required_capability: str
    ttl_seconds: int
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        for value, name in (
            (self.link_id, "safe review link id"),
            (self.raw_token, "safe review token"),
            (self.canonical_internal_target, "canonical internal target"),
            (self.source_alert_identity, "source alert identity"),
            (self.allowed_actor_ref, "allowed actor reference"),
            (self.required_capability, "required capability"),
        ):
            _text(value, name)
        require_nonnegative_integer(self.target_version, "safe review target version")
        if not 1 <= self.ttl_seconds <= 900:
            raise ValueError("safe review link TTL must be between 1 and 900 seconds")
        if "?" in self.canonical_internal_target or "#" in self.canonical_internal_target:
            raise ValueError("safe review target cannot contain query or fragment")
        if not self.canonical_internal_target.startswith("/") or self.canonical_internal_target.startswith("//"):
            raise ValueError("safe review target must be an internal path")


@dataclass(frozen=True, slots=True)
class RedeemSafeReviewLink:
    link_id: str
    raw_token: str
    actor: ActorContext
    capability: str
    current_target: str
    current_target_version: int
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _text(self.link_id, "safe review link id")
        _text(self.raw_token, "safe review token")
        _text(self.capability, "redeem capability", 100)
        _text(self.current_target, "current internal target")
        require_nonnegative_integer(self.current_target_version, "current target version")


@dataclass(frozen=True, slots=True)
class RevokeSafeReviewLink:
    link_id: str
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        _text(self.link_id, "safe review link id")
        _text(self.reason, "safe review revoke reason", 500)


@dataclass(frozen=True, slots=True)
class QuerySafeReviewLink:
    link_id: str

    def __post_init__(self) -> None:
        _text(self.link_id, "safe review link id")


@dataclass(frozen=True, slots=True)
class SafeReviewLinkView:
    link_id: str
    status: SafeReviewLinkState
    canonical_internal_target: str
    target_version: int
    source_alert_identity: str
    expires_at_utc: datetime
    redeemed_at_utc: datetime | None
    revoked_at_utc: datetime | None
    root_version: int


@dataclass(frozen=True, slots=True)
class SafeReviewLinkReceipt:
    link_id: str
    outcome: SafeReviewLinkState
    replayed: bool
    receipt_id: str
    root_version: int
    view: SafeReviewLinkView


def command_fingerprint(command: object) -> PreviewFingerprint:
    values = {
        key: getattr(command, key)
        for key in (
            "link_id", "canonical_internal_target", "target_version",
            "source_alert_identity", "allowed_actor_ref", "required_capability",
            "ttl_seconds", "current_target", "current_target_version", "capability",
            "reason",
        )
        if hasattr(command, key)
    }
    if hasattr(command, "raw_token"):
        import hashlib
        values["token_digest"] = hashlib.sha256(str(command.raw_token).encode()).hexdigest()
    return fingerprint_payload(values)


__all__ = [
    "IssueSafeReviewLink", "RedeemSafeReviewLink", "RevokeSafeReviewLink",
    "QuerySafeReviewLink", "SafeReviewLinkError", "SafeReviewLinkState",
    "SafeReviewLinkView", "SafeReviewLinkReceipt", "command_fingerprint",
]

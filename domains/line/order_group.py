"""Pure order-group binding and transient invitation relay rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from domains.line.identities import LineGroupId, LineUserId
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion
from shared_kernel.validation import require_canonical_text

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_INVITATION_URL_MAXIMUM_LENGTH = 2_048
_ALLOWED_INVITATION_HOSTS = {"line.me"}


class LineOrderGroupBindingStatus(StrEnum):
    UNBOUND = "unbound"
    BOUND = "bound"
    REPLACED = "replaced"
    RELEASED = "released"


class LineOrderGroupBindingConflict(ValueError):
    """Raised when an order-group binding candidate is stale or unchanged."""


@dataclass(frozen=True, slots=True)
class LineOrderGroupBindingSnapshot:
    case_no: str
    group_id: LineGroupId | None
    status: LineOrderGroupBindingStatus
    version: ExpectedVersion

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if not isinstance(self.status, LineOrderGroupBindingStatus):
            raise TypeError("LINE order-group binding status is invalid")


@dataclass(frozen=True, slots=True)
class LineOrderGroupBindingCandidate:
    case_no: str
    before_group_id: LineGroupId | None
    resulting_group_id: LineGroupId
    expected_version: ExpectedVersion
    resulting_version: ExpectedVersion
    actor: ActorContext
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class LineGroupInvitationRelay:
    case_no: str
    group_id: LineGroupId
    invitation_url: str = field(repr=False)
    recipients: tuple[LineUserId, ...]
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        _validate_invitation_url(self.invitation_url)
        _validate_recipients(self.recipients)

    @property
    def invitation_fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "case_no": self.case_no,
                "group_id": self.group_id.value,
                "invitation_url": self.invitation_url,
                "recipient_user_ids": [item.value for item in self.recipients],
            }
        )

    def persistent_audit_payload(self) -> dict[str, object]:
        return {
            "case_no": self.case_no,
            "group_id": self.group_id.value,
            "recipient_user_ids": [recipient.value for recipient in self.recipients],
            "invitation_fingerprint": self.invitation_fingerprint.value,
            "actor_id": self.actor.actor_id,
            "correlation_id": self.correlation_id.value,
        }


def build_order_group_binding_candidate(
    snapshot: LineOrderGroupBindingSnapshot,
    *,
    group_id: LineGroupId,
    expected_version: ExpectedVersion,
    actor: ActorContext,
) -> LineOrderGroupBindingCandidate:
    _validate_binding_candidate(snapshot, group_id, expected_version)
    return LineOrderGroupBindingCandidate(
        snapshot.case_no,
        snapshot.group_id,
        group_id,
        expected_version,
        ExpectedVersion(expected_version.value + 1),
        actor,
        _binding_fingerprint(snapshot, group_id, expected_version, actor),
    )


def _binding_fingerprint(
    snapshot: LineOrderGroupBindingSnapshot,
    group_id: LineGroupId,
    expected_version: ExpectedVersion,
    actor: ActorContext,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "case_no": snapshot.case_no,
            "before_group_id": _optional_group_value(snapshot.group_id),
            "resulting_group_id": group_id.value,
            "expected_version": expected_version.value,
            "actor_id": actor.actor_id,
        }
    )


def _validate_binding_candidate(
    snapshot: LineOrderGroupBindingSnapshot,
    group_id: LineGroupId,
    expected_version: ExpectedVersion,
) -> None:
    if snapshot.version != expected_version:
        raise LineOrderGroupBindingConflict("LINE order-group binding is stale")
    if snapshot.group_id == group_id:
        raise LineOrderGroupBindingConflict("LINE group is already bound to this order")


def _validate_invitation_url(invitation_url: str) -> None:
    require_canonical_text(
        invitation_url,
        "LINE group invitation URL",
        _INVITATION_URL_MAXIMUM_LENGTH,
    )
    parsed = urlparse(invitation_url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_INVITATION_HOSTS:
        raise ValueError("LINE group invitation URL must use the approved LINE host")
    if not parsed.path:
        raise ValueError("LINE group invitation URL must include a path")


def _validate_recipients(recipients: tuple[LineUserId, ...]) -> None:
    if not isinstance(recipients, tuple) or not recipients:
        raise ValueError("LINE invitation relay requires recipients")
    if any(not isinstance(recipient, LineUserId) for recipient in recipients):
        raise TypeError("LINE invitation relay recipients are invalid")
    values = tuple(recipient.value for recipient in recipients)
    if values != tuple(sorted(set(values))):
        raise ValueError("LINE invitation recipients must be sorted and unique")


def _optional_group_value(group_id: LineGroupId | None) -> str | None:
    return None if group_id is None else group_id.value


__all__ = [
    "LineGroupInvitationRelay",
    "LineOrderGroupBindingCandidate",
    "LineOrderGroupBindingConflict",
    "LineOrderGroupBindingSnapshot",
    "LineOrderGroupBindingStatus",
    "build_order_group_binding_candidate",
]

"""Pure LINE identity claim and binding transition rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domains.line.identities import LineUserId
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ExpectedVersion
from shared_kernel.validation import require_canonical_text

_SUBJECT_REFERENCE_MAXIMUM_LENGTH = 191


class LineBindingSubjectType(StrEnum):
    CUSTOMER = "customer"
    STAFF = "staff"
    ADMIN = "admin"


class LineIdentityBindingStatus(StrEnum):
    UNBOUND = "unbound"
    PENDING_REVIEW = "pending_review"
    BOUND = "bound"
    REVOCATION_PENDING = "revocation_pending"
    REVOKED = "revoked"


_ALLOWED_BINDING_TRANSITIONS = {
    LineIdentityBindingStatus.UNBOUND: {
        LineIdentityBindingStatus.PENDING_REVIEW,
        LineIdentityBindingStatus.BOUND,
    },
    LineIdentityBindingStatus.PENDING_REVIEW: {
        LineIdentityBindingStatus.BOUND,
        LineIdentityBindingStatus.REVOKED,
    },
    LineIdentityBindingStatus.BOUND: {
        LineIdentityBindingStatus.REVOCATION_PENDING,
        LineIdentityBindingStatus.REVOKED,
    },
    LineIdentityBindingStatus.REVOCATION_PENDING: {
        LineIdentityBindingStatus.REVOKED,
    },
    LineIdentityBindingStatus.REVOKED: {
        LineIdentityBindingStatus.PENDING_REVIEW,
    },
}


class LineIdentityBindingConflict(ValueError):
    """Raised when a LINE identity cannot move to the requested state."""


@dataclass(frozen=True, slots=True)
class LineIdentityClaim:
    line_user_id: LineUserId
    subject_type: LineBindingSubjectType
    subject_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.subject_type, LineBindingSubjectType):
            raise TypeError("LINE binding subject type is invalid")
        require_canonical_text(
            self.subject_reference,
            "LINE binding subject reference",
            _SUBJECT_REFERENCE_MAXIMUM_LENGTH,
        )

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "line_user_id": self.line_user_id.value,
                "subject_type": self.subject_type.value,
                "subject_reference": self.subject_reference,
            }
        )


@dataclass(frozen=True, slots=True)
class LineIdentityBindingSnapshot:
    line_user_id: LineUserId
    status: LineIdentityBindingStatus
    version: ExpectedVersion
    subject_type: LineBindingSubjectType | None = None
    subject_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, LineIdentityBindingStatus):
            raise TypeError("LINE identity binding status is invalid")
        _validate_bound_subject(self.subject_type, self.subject_reference)


def transition_binding_status(
    current: LineIdentityBindingStatus,
    target: LineIdentityBindingStatus,
) -> LineIdentityBindingStatus:
    if not isinstance(current, LineIdentityBindingStatus):
        raise TypeError("current LINE identity binding status is invalid")
    if target not in _ALLOWED_BINDING_TRANSITIONS.get(current, set()):
        raise LineIdentityBindingConflict(
            f"cannot transition LINE binding from {current.value} to {target.value}"
        )
    return target


def _validate_bound_subject(
    subject_type: LineBindingSubjectType | None,
    subject_reference: str | None,
) -> None:
    if (subject_type is None) != (subject_reference is None):
        raise ValueError("LINE binding subject type and reference must appear together")
    if subject_type is None or subject_reference is None:
        return
    if not isinstance(subject_type, LineBindingSubjectType):
        raise TypeError("LINE binding subject type is invalid")
    require_canonical_text(
        subject_reference,
        "LINE binding subject reference",
        _SUBJECT_REFERENCE_MAXIMUM_LENGTH,
    )


__all__ = [
    "LineBindingSubjectType",
    "LineIdentityBindingConflict",
    "LineIdentityBindingStatus",
    "LineIdentityBindingSnapshot",
    "LineIdentityClaim",
    "transition_binding_status",
]

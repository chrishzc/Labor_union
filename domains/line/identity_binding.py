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


@dataclass(frozen=True, slots=True)
class LineIdentityBindingFailureStreak:
    line_user_id: LineUserId
    identity_flow_id: str
    candidate_subject_type: LineBindingSubjectType
    candidate_scope: str
    scope_fingerprint: str
    generation: int
    failure_count: int
    last_failure_fingerprint: str | None
    escalation_id: int | None
    version: ExpectedVersion

    def __post_init__(self) -> None:
        if self.candidate_subject_type not in {
            LineBindingSubjectType.CUSTOMER,
            LineBindingSubjectType.STAFF,
        }:
            raise ValueError("binding failure streak only supports customer or staff")
        require_canonical_text(self.identity_flow_id, "LINE identity flow ID", 191)
        require_canonical_text(self.candidate_scope, "LINE candidate scope", 191)
        if self.failure_count not in {0, 1, 2}:
            raise ValueError("LINE binding failure streak count is invalid")
        if self.generation < 0:
            raise ValueError("LINE binding failure streak generation is invalid")


def advance_binding_failure_streak(
    current: LineIdentityBindingFailureStreak | None,
    *,
    line_user_id: LineUserId,
    identity_flow_id: str,
    candidate_subject_type: LineBindingSubjectType,
    candidate_scope: str,
    failure_identity: str,
) -> tuple[LineIdentityBindingFailureStreak, bool]:
    scope = fingerprint_payload(
        {
            "line_user_id": line_user_id.value,
            "identity_flow_id": identity_flow_id,
            "candidate_subject_type": candidate_subject_type.value,
            "candidate_scope": candidate_scope,
        }
    ).value
    failure = fingerprint_payload({"failure_identity": failure_identity}).value
    if current is not None and current.scope_fingerprint == scope:
        if current.last_failure_fingerprint == failure or current.failure_count == 2:
            return current, False
        count = current.failure_count + 1
        return (
            LineIdentityBindingFailureStreak(
                line_user_id,
                identity_flow_id,
                candidate_subject_type,
                candidate_scope,
                scope,
                current.generation,
                count,
                failure,
                None,
                ExpectedVersion(current.version.value + 1),
            ),
            count == 2,
        )
    generation = 0 if current is None else current.generation + 1
    version = 1 if current is None else current.version.value + 1
    return (
        LineIdentityBindingFailureStreak(
            line_user_id,
            identity_flow_id,
            candidate_subject_type,
            candidate_scope,
            scope,
            generation,
            1,
            failure,
            None,
            ExpectedVersion(version),
        ),
        False,
    )


def reset_binding_failure_streak(
    current: LineIdentityBindingFailureStreak | None,
    identity_flow_id: str,
) -> LineIdentityBindingFailureStreak | None:
    if (
        current is None
        or current.identity_flow_id != identity_flow_id
        or current.failure_count == 0
    ):
        return None
    return LineIdentityBindingFailureStreak(
        current.line_user_id,
        current.identity_flow_id,
        current.candidate_subject_type,
        current.candidate_scope,
        current.scope_fingerprint,
        current.generation + 1,
        0,
        None,
        None,
        ExpectedVersion(current.version.value + 1),
    )


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
    "LineIdentityBindingFailureStreak",
    "LineIdentityClaim",
    "advance_binding_failure_streak",
    "reset_binding_failure_streak",
    "transition_binding_status",
]

"""Framework-neutral typed error envelope."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.identities import CorrelationId, ExpectedVersion
from shared_kernel.validation import require_canonical_text

_ERROR_IDENTITY_MAXIMUM_LENGTH = 191
_ERROR_MESSAGE_MAXIMUM_LENGTH = 500


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    DOMAIN_BLOCKED = "domain_blocked"
    CONFLICT = "conflict"
    IDEMPOTENCY_MISMATCH = "idempotency_mismatch"
    UNAVAILABLE = "unavailable"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    code: str
    message: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.field,
            "field error field",
            _ERROR_IDENTITY_MAXIMUM_LENGTH,
        )
        require_canonical_text(
            self.code,
            "field error code",
            _ERROR_IDENTITY_MAXIMUM_LENGTH,
        )
        require_canonical_text(
            self.message,
            "field error message",
            _ERROR_MESSAGE_MAXIMUM_LENGTH,
        )


@dataclass(frozen=True, slots=True)
class TypedError:
    category: ErrorCategory
    code: str
    message: str
    correlation_id: CorrelationId
    field_errors: tuple[FieldError, ...] = ()
    domain_blockers: tuple[str, ...] = ()
    retryable: bool = False
    current_version: ExpectedVersion | None = None

    def __post_init__(self) -> None:
        require_canonical_text(
            self.code,
            "typed error code",
            _ERROR_IDENTITY_MAXIMUM_LENGTH,
        )
        require_canonical_text(
            self.message,
            "typed error message",
            _ERROR_MESSAGE_MAXIMUM_LENGTH,
        )
        _validate_blockers(self.domain_blockers)
        if self.retryable and self.category is not ErrorCategory.UNAVAILABLE:
            raise ValueError("only unavailable errors may be retryable")


def _validate_blockers(domain_blockers: tuple[str, ...]) -> None:
    if not isinstance(domain_blockers, tuple):
        raise TypeError("domain_blockers must be a tuple")
    for blocker in domain_blockers:
        require_canonical_text(
            blocker,
            "domain blocker",
            _ERROR_IDENTITY_MAXIMUM_LENGTH,
        )
    if domain_blockers != tuple(sorted(set(domain_blockers))):
        raise ValueError("domain_blockers must be sorted and unique")

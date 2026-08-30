"""Pure contracts for reference-aware controlled-file finalization.

This package is deliberately independent from storage, MySQL, Scheduling, and
the existing 1004 staging workflow.  It describes only the immutable facts
and state transitions introduced by the 1015 additive successor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from shared_kernel.validation import require_canonical_text, require_positive_integer, require_sha256_hex


_FINALIZE_ID = re.compile(r"^cff_[0-9a-f]{32}$")
_REFERENCE_ID = re.compile(r"^cfrf_[0-9a-f]{32}$")
_LEASE_ID = re.compile(r"^cfl_[0-9a-f]{32}$")
_STAGING_ID = re.compile(r"^cfs_[0-9a-f]{32}$")
_FILE_ID = re.compile(r"^cf_[0-9a-f]{32}$")
_SAFE_KEY_COMPONENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ControlledFileFinalizeState(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    AVAILABLE = "available"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class ControlledFileLeaseState(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class ControlledFileReferenceKind(StrEnum):
    SCHEDULING_SERVICE_DAY_LOG_ATTACHMENT = "scheduling_service_day_log_attachment"


class ControlledFileReferenceError(ValueError):
    """Raised when a 1015 identity, key, or state fact is invalid."""


@dataclass(frozen=True, slots=True)
class ControlledFileFinalizeIntent:
    finalize_id: str
    staging_id: str
    controlled_file_object_id: str
    expected_sha256: str
    state: ControlledFileFinalizeState = ControlledFileFinalizeState.PENDING
    created_at: datetime | None = None
    claim_token: str | None = None
    observed_sha256: str | None = None
    observed_size_bytes: int | None = None

    def __post_init__(self) -> None:
        if _FINALIZE_ID.fullmatch(self.finalize_id) is None:
            raise ControlledFileReferenceError("controlled file finalize identity is invalid")
        if _STAGING_ID.fullmatch(self.staging_id) is None:
            raise ControlledFileReferenceError("controlled file staging identity is invalid")
        if _FILE_ID.fullmatch(self.controlled_file_object_id) is None:
            raise ControlledFileReferenceError("controlled file object identity is invalid")
        try:
            require_sha256_hex(self.expected_sha256, "controlled file finalize digest")
        except ValueError as exc:
            raise ControlledFileReferenceError(str(exc)) from exc
        if not isinstance(self.state, ControlledFileFinalizeState):
            raise ControlledFileReferenceError("controlled file finalize state is invalid")
        if self.claim_token is not None:
            try:
                require_canonical_text(self.claim_token, "controlled file finalize claim token", 191)
            except ValueError as exc:
                raise ControlledFileReferenceError(str(exc)) from exc
        if self.observed_sha256 is not None:
            try:
                require_sha256_hex(self.observed_sha256, "controlled file finalize observed digest")
            except ValueError as exc:
                raise ControlledFileReferenceError(str(exc)) from exc
        if self.observed_size_bytes is not None:
            try:
                require_positive_integer(self.observed_size_bytes, "controlled file finalize observed size")
            except ValueError as exc:
                raise ControlledFileReferenceError(str(exc)) from exc
        if self.state is ControlledFileFinalizeState.AVAILABLE and (
            self.observed_sha256 is None or self.observed_size_bytes is None
        ):
            raise ControlledFileReferenceError(
                "available finalize intent requires integrity observation"
            )
        if self.created_at is not None:
            _aware(self.created_at, "controlled file finalize created_at")


@dataclass(frozen=True, slots=True)
class SchedulingControlledFileReference:
    reference_id: str
    controlled_file_object_id: str
    service_day_log_attachment_id: int
    created_at: datetime
    kind: ControlledFileReferenceKind = ControlledFileReferenceKind.SCHEDULING_SERVICE_DAY_LOG_ATTACHMENT

    def __post_init__(self) -> None:
        if _REFERENCE_ID.fullmatch(self.reference_id) is None:
            raise ControlledFileReferenceError("controlled file reference identity is invalid")
        if _FILE_ID.fullmatch(self.controlled_file_object_id) is None:
            raise ControlledFileReferenceError("controlled file object identity is invalid")
        try:
            require_positive_integer(
                self.service_day_log_attachment_id,
                "service-day-log attachment identity",
            )
        except ValueError as exc:
            raise ControlledFileReferenceError(str(exc)) from exc
        if not isinstance(self.kind, ControlledFileReferenceKind):
            raise ControlledFileReferenceError("controlled file reference kind is invalid")
        _aware(self.created_at, "controlled file reference created_at")


@dataclass(frozen=True, slots=True)
class ControlledFileLease:
    lease_id: str
    staging_id: str
    holder: str
    acquired_at: datetime
    expires_at: datetime
    state: ControlledFileLeaseState = ControlledFileLeaseState.ACTIVE

    def __post_init__(self) -> None:
        if _LEASE_ID.fullmatch(self.lease_id) is None:
            raise ControlledFileReferenceError("controlled file lease identity is invalid")
        if _STAGING_ID.fullmatch(self.staging_id) is None:
            raise ControlledFileReferenceError("controlled file staging identity is invalid")
        try:
            require_canonical_text(self.holder, "controlled file lease holder", 191)
        except ValueError as exc:
            raise ControlledFileReferenceError(str(exc)) from exc
        _aware(self.acquired_at, "controlled file lease acquired_at")
        _aware(self.expires_at, "controlled file lease expires_at")
        if self.expires_at <= self.acquired_at:
            raise ControlledFileReferenceError("controlled file lease expiry must be after acquisition")
        if not isinstance(self.state, ControlledFileLeaseState):
            raise ControlledFileReferenceError("controlled file lease state is invalid")


@dataclass(frozen=True, slots=True)
class ReferenceAwareStagingCandidate:
    """Repository-confirmed facts consumed by bounded GC."""

    staging_id: str
    staging_version: int
    expected_sha256: str
    expires_at: datetime
    registered: bool
    reference_count: int
    active_lease: bool

    def __post_init__(self) -> None:
        if _STAGING_ID.fullmatch(self.staging_id) is None:
            raise ControlledFileReferenceError("controlled file staging identity is invalid")
        try:
            require_positive_integer(self.staging_version, "controlled file staging version")
            require_sha256_hex(self.expected_sha256, "controlled file staging digest")
        except ValueError as exc:
            raise ControlledFileReferenceError(str(exc)) from exc
        _aware(self.expires_at, "controlled file staging expires_at")
        if not isinstance(self.registered, bool):
            raise ControlledFileReferenceError("controlled file registration state is invalid")
        if isinstance(self.reference_count, bool) or self.reference_count < 0:
            raise ControlledFileReferenceError("controlled file reference count is invalid")
        if not isinstance(self.active_lease, bool):
            raise ControlledFileReferenceError("controlled file lease state is invalid")


def canonical_scheduling_object_key(
    *,
    assignment_id: int,
    service_date: date,
    attachment_kind: str,
    sequence: int,
    sha256_digest: str,
) -> str:
    """Build the Scheduling-owned, non-PII object key fixed by NAS §9.6."""

    try:
        require_positive_integer(assignment_id, "assignment identity")
        require_positive_integer(sequence, "attachment sequence")
        require_sha256_hex(sha256_digest, "controlled file object digest")
        require_canonical_text(attachment_kind, "attachment kind", 64)
    except ValueError as exc:
        raise ControlledFileReferenceError(str(exc)) from exc
    if not isinstance(service_date, date) or isinstance(service_date, datetime):
        raise ControlledFileReferenceError("service date must be a date")
    if _SAFE_KEY_COMPONENT.fullmatch(attachment_kind) is None:
        raise ControlledFileReferenceError("attachment kind is not canonical")
    return (
        f"scheduling/service-day/v1/{assignment_id}/{service_date.isoformat()}"
        f"/{attachment_kind}/{sequence}/{sha256_digest}"
    )


def lease_is_active(lease: ControlledFileLease, now: datetime) -> bool:
    _aware(now, "controlled file lease observation time")
    return lease.state is ControlledFileLeaseState.ACTIVE and now < lease.expires_at


def gc_disposition(candidate: ReferenceAwareStagingCandidate, *, now: datetime, grace_period_seconds: int) -> str:
    """Return a conservative disposition; no storage operation occurs here."""

    _aware(now, "controlled file GC observation time")
    if isinstance(grace_period_seconds, bool) or grace_period_seconds < 0:
        raise ControlledFileReferenceError("controlled file GC grace period is invalid")
    if candidate.registered:
        return "skipped_registered"
    if candidate.reference_count > 0:
        return "skipped_referenced"
    if candidate.active_lease:
        return "skipped_leased"
    from datetime import timedelta

    if candidate.expires_at > now - timedelta(seconds=grace_period_seconds):
        return "skipped_grace_period"
    return "eligible"


def _aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ControlledFileReferenceError(f"{field_name} must be timezone-aware")


__all__ = [
    "ControlledFileFinalizeIntent",
    "ControlledFileFinalizeState",
    "ControlledFileLease",
    "ControlledFileLeaseState",
    "ControlledFileReferenceError",
    "ControlledFileReferenceKind",
    "ReferenceAwareStagingCandidate",
    "SchedulingControlledFileReference",
    "canonical_scheduling_object_key",
    "gc_disposition",
    "lease_is_active",
]

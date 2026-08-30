"""Bounded, reference-aware observation and cleanup of staging objects.

This module intentionally keeps the candidate query and lease/reference facts in
the application-owned repository.  It never infers a reference from a path and
never deletes bytes before the cleanup intent transaction has committed.
"""

from __future__ import annotations

import hashlib
import re
from threading import RLock
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Protocol

from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.controlled_files.cleanup import (
    CleanupControlledFileStaging,
    ControlledFileCleanupError,
    ControlledFileCleanupOutcome,
    ControlledFileCleanupWorkflow,
)
from subsystems.controlled_files.contracts import (
    ControlledFileStagingCleanupReason,
    ControlledFileStagingRegistrationStatus,
)


_STAGING_ID = re.compile(r"^cfs_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")
_MAX_BATCH = 100


class ControlledFileGcOutcome(str, Enum):
    DRY_RUN = "dry_run"
    CLEANED = "cleaned"
    REPLAYED = "replayed"
    BLOCKED = "blocked"


class ControlledFileGcDisposition(str, Enum):
    ELIGIBLE = "eligible"
    SKIPPED_REFERENCED = "skipped_referenced"
    SKIPPED_LEASED = "skipped_leased"
    SKIPPED_GRACE_PERIOD = "skipped_grace_period"
    SKIPPED_REGISTERED = "skipped_registered"
    SKIPPED_ALREADY_CLEANED = "skipped_already_cleaned"
    CLEANED = "cleaned"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ControlledFileGcCandidate:
    """Repository-provided facts needed before a staging object may be deleted."""

    staging_id: str
    staging_version: int
    expected_sha256: str
    expires_at: datetime
    registration_status: ControlledFileStagingRegistrationStatus
    reference_count: int
    active_lease: bool

    def __post_init__(self) -> None:
        if _STAGING_ID.fullmatch(self.staging_id) is None:
            raise ValueError("controlled file staging identity is invalid")
        if self.staging_version <= 0:
            raise ValueError("controlled file staging version must be positive")
        if _DIGEST.fullmatch(self.expected_sha256) is None:
            raise ValueError("controlled file staging digest is invalid")
        if self.expires_at.tzinfo is None:
            raise ValueError("controlled file staging expiry must include timezone")
        if self.reference_count < 0:
            raise ValueError("controlled file staging reference count must not be negative")
        if not isinstance(self.active_lease, bool):
            raise ValueError("controlled file staging lease state must be boolean")


@dataclass(frozen=True, slots=True)
class ControlledFileGcItem:
    staging_id: str
    disposition: ControlledFileGcDisposition
    reason: str


@dataclass(frozen=True, slots=True)
class GarbageCollectControlledFileStaging:
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId
    limit: int = _MAX_BATCH
    grace_period: timedelta = timedelta(hours=24)
    dry_run: bool = True

    def __post_init__(self) -> None:
        if _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key.value) is None:
            raise ValueError("controlled file GC idempotency key is invalid")
        if isinstance(self.limit, bool) or not 1 <= self.limit <= _MAX_BATCH:
            raise ValueError("controlled file GC limit must be between 1 and 100")
        if self.grace_period < timedelta(0):
            raise ValueError("controlled file GC grace period must not be negative")


@dataclass(frozen=True, slots=True)
class ControlledFileGcReceipt:
    receipt_id: str
    outcome: ControlledFileGcOutcome
    scanned: int
    eligible: int
    cleaned: int
    blocked: int
    items: tuple[ControlledFileGcItem, ...]
    observed_at: datetime
    command_fingerprint: PreviewFingerprint
    receipt_type: str = "controlled_file_staging_gc"
    schema_version: str = "controlled-file-staging-gc-receipt.v1"


class ControlledFileGcRepository(Protocol):
    def list_staging_gc_candidates(
        self, *, limit: int, observed_at: datetime
    ) -> tuple[ControlledFileGcCandidate, ...]: ...


class ControlledFileStagingGarbageCollector:
    """Run a bounded GC pass using repository-confirmed references and leases."""

    def __init__(
        self,
        repository: ControlledFileGcRepository,
        cleanup_workflow: ControlledFileCleanupWorkflow,
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._cleanup = cleanup_workflow
        self._clock = clock
        self._runs: dict[str, tuple[PreviewFingerprint, ControlledFileGcReceipt]] = {}
        # A worker process can receive duplicate jobs before its durable
        # cleanup terminal fact is visible.  Serialize the small bounded pass
        # and remember successful local cleanups so two keys cannot issue two
        # byte-delete attempts for the same candidate.  The repository remains
        # the cross-process authority.
        self._lock = RLock()
        self._cleaned_staging: set[str] = set()

    def run(self, command: GarbageCollectControlledFileStaging) -> ControlledFileGcReceipt:
        with self._lock:
            return self._run(command)

    def _run(self, command: GarbageCollectControlledFileStaging) -> ControlledFileGcReceipt:
        observed_at = _utc(self._clock.now())
        fingerprint = fingerprint_payload(
            {
                "schema": "controlled-file-staging-gc-command.v1",
                "dry_run": command.dry_run,
                "grace_period_seconds": int(command.grace_period.total_seconds()),
                "limit": command.limit,
            }
        )
        previous = self._runs.get(command.idempotency_key.value)
        if previous is not None:
            if previous[0] != fingerprint:
                raise ControlledFileGcError("idempotency_mismatch", "相同 GC 重播識別對應不同命令")
            return replace(previous[1], outcome=ControlledFileGcOutcome.REPLAYED)

        candidates = self._repository.list_staging_gc_candidates(
            limit=command.limit,
            observed_at=observed_at,
        )
        items: list[ControlledFileGcItem] = []
        eligible = cleaned = blocked = 0
        cutoff = observed_at - command.grace_period
        for candidate in candidates[: command.limit]:
            if candidate.staging_id in self._cleaned_staging:
                items.append(
                    ControlledFileGcItem(
                        candidate.staging_id,
                        ControlledFileGcDisposition.SKIPPED_ALREADY_CLEANED,
                        "already_cleaned_in_process",
                    )
                )
                continue
            disposition, reason = _eligibility(candidate, cutoff)
            if disposition is ControlledFileGcDisposition.SKIPPED_REGISTERED:
                items.append(ControlledFileGcItem(candidate.staging_id, disposition, reason))
                continue
            if disposition is not ControlledFileGcDisposition.ELIGIBLE:
                items.append(ControlledFileGcItem(candidate.staging_id, disposition, reason))
                continue
            eligible += 1
            if command.dry_run:
                items.append(ControlledFileGcItem(candidate.staging_id, disposition, "dry_run"))
                continue
            try:
                cleanup = self._cleanup.cleanup(
                    CleanupControlledFileStaging(
                        staging_id=candidate.staging_id,
                        reason=ControlledFileStagingCleanupReason.EXPIRED,
                        expected_staging_version=ExpectedVersion(candidate.staging_version),
                        expected_sha256=candidate.expected_sha256,
                        idempotency_key=IdempotencyKey(
                            f"{command.idempotency_key.value}:{candidate.staging_id}"
                        ),
                        actor=command.actor,
                        correlation_id=command.correlation_id,
                    )
                )
            except ControlledFileCleanupError as error:
                blocked += 1
                items.append(ControlledFileGcItem(candidate.staging_id, ControlledFileGcDisposition.BLOCKED, error.code))
            else:
                if cleanup.outcome is ControlledFileCleanupOutcome.CLEANED:
                    cleaned += 1
                    self._cleaned_staging.add(candidate.staging_id)
                items.append(ControlledFileGcItem(candidate.staging_id, ControlledFileGcDisposition.CLEANED, cleanup.outcome.value))

        outcome = (
            ControlledFileGcOutcome.DRY_RUN
            if command.dry_run
            else ControlledFileGcOutcome.BLOCKED
            if blocked
            else ControlledFileGcOutcome.CLEANED
        )
        receipt = ControlledFileGcReceipt(
            receipt_id=_receipt_id(command.idempotency_key),
            outcome=outcome,
            scanned=len(candidates[: command.limit]),
            eligible=eligible,
            cleaned=cleaned,
            blocked=blocked,
            items=tuple(items),
            observed_at=observed_at,
            command_fingerprint=fingerprint,
        )
        self._runs[command.idempotency_key.value] = (fingerprint, receipt)
        return receipt


class ControlledFileGcError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _eligibility(
    candidate: ControlledFileGcCandidate,
    cutoff: datetime,
) -> tuple[ControlledFileGcDisposition, str]:
    if candidate.registration_status is not ControlledFileStagingRegistrationStatus.UNREGISTERED:
        return ControlledFileGcDisposition.SKIPPED_REGISTERED, "staging_not_unregistered"
    if candidate.reference_count:
        return ControlledFileGcDisposition.SKIPPED_REFERENCED, "active_reference"
    if candidate.active_lease:
        return ControlledFileGcDisposition.SKIPPED_LEASED, "active_lease"
    if candidate.expires_at > cutoff:
        return ControlledFileGcDisposition.SKIPPED_GRACE_PERIOD, "grace_period"
    return ControlledFileGcDisposition.ELIGIBLE, "eligible"


def _receipt_id(key: IdempotencyKey) -> str:
    return f"cfg_{hashlib.sha256(key.value.encode('utf-8')).hexdigest()[:32]}"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ControlledFileGcError("business_time_invalid", "GC 時間必須包含時區")
    return value.astimezone(timezone.utc)


__all__ = [
    "ControlledFileGcCandidate",
    "ControlledFileGcDisposition",
    "ControlledFileGcError",
    "ControlledFileGcItem",
    "ControlledFileGcOutcome",
    "ControlledFileGcReceipt",
    "ControlledFileGcRepository",
    "ControlledFileStagingGarbageCollector",
    "GarbageCollectControlledFileStaging",
]

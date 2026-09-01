"""Reference-aware controlled-file finalize, lease, and bounded GC runtime.

The storage provider is always called outside a database transaction.  The
repository port therefore exposes short claim/CAS operations while callers
remain responsible for the surrounding Unit of Work where one is required.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable, Protocol

from domains.controlled_files.reference_finalize import (
    ControlledFileFinalizeIntent,
    ControlledFileFinalizeState,
    ControlledFileLease,
    ReferenceAwareStagingCandidate,
    SchedulingControlledFileReference,
    gc_disposition,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.controlled_files.contracts import (
    ControlledFileStorageError,
    ControlledFileStoragePort,
)


class ControlledFileFinalizeError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class FinalizeOutcome(StrEnum):
    AVAILABLE = "available"
    REPLAYED = "replayed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True, slots=True)
class ControlledFileFinalizeReceipt:
    finalize_id: str
    staging_id: str
    controlled_file_object_id: str
    outcome: FinalizeOutcome
    observed_sha256: str | None
    observed_size_bytes: int | None
    observed_at: datetime
    error_code: str | None = None
    receipt_type: str = "controlled_file_finalize"
    schema_version: str = "controlled-file-finalize-receipt.v1"


class ControlledFileFinalizeRepository(Protocol):
    def claim_finalize_intent(
        self, finalize_id: str, *, worker_id: str, observed_at: datetime
    ) -> ControlledFileFinalizeIntent | None: ...

    def mark_finalize_available(
        self,
        finalize_id: str,
        *,
        worker_id: str,
        claim_token: str,
        observed_at: datetime,
        observed_sha256: str,
        observed_size_bytes: int,
    ) -> None: ...

    def mark_finalize_reconciliation_required(
        self,
        finalize_id: str,
        *,
        worker_id: str,
        claim_token: str,
        observed_at: datetime,
        error_code: str,
    ) -> None: ...

    def acquire_finalize_lease(
        self,
        intent: ControlledFileFinalizeIntent,
        *,
        worker_id: str,
        acquired_at: datetime,
    ) -> ControlledFileLease: ...

    def release_finalize_lease(
        self, lease: ControlledFileLease, *, released_at: datetime, worker_id: str
    ) -> None: ...


class ControlledFileFinalizeWorker:
    """Claim one intent, verify bytes, then perform a CAS terminal update."""

    def __init__(
        self,
        repository: ControlledFileFinalizeRepository,
        storage: ControlledFileStoragePort,
        *,
        checkpoint: Callable[[], None] | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._checkpoint = checkpoint or (lambda: None)

    def run(
        self,
        finalize_id: str,
        *,
        worker_id: str,
        observed_at: datetime,
    ) -> ControlledFileFinalizeReceipt:
        observed_at = _utc(observed_at)
        intent = self._repository.claim_finalize_intent(
            finalize_id, worker_id=worker_id, observed_at=observed_at
        )
        if intent is None:
            raise ControlledFileFinalizeError(
                "controlled_file_finalize_not_found",
                "finalize intent is missing or already claimed",
            )
        if intent.state is ControlledFileFinalizeState.AVAILABLE:
            return ControlledFileFinalizeReceipt(
                intent.finalize_id,
                intent.staging_id,
                intent.controlled_file_object_id,
                FinalizeOutcome.REPLAYED,
                intent.observed_sha256 or intent.expected_sha256,
                intent.observed_size_bytes,
                observed_at,
            )
        self._checkpoint()
        claim_token = intent.claim_token
        if not claim_token:
            raise ControlledFileFinalizeError(
                "controlled_file_finalize_claim_incomplete",
                "finalize claim did not return a CAS token",
            )
        lease = self._repository.acquire_finalize_lease(
            intent, worker_id=worker_id, acquired_at=observed_at
        )
        self._checkpoint()
        try:
            # This call is intentionally outside the repository/CAS operation.
            verified = self._storage.finalize_staged(
                intent.staging_id, expected_sha256=intent.expected_sha256
            )
            if (
                verified.staging_id != intent.staging_id
                or verified.sha256_digest != intent.expected_sha256
            ):
                raise ControlledFileStorageError(
                    "controlled_file_staging_digest_mismatch",
                    "finalized bytes do not match immutable digest",
                    retryable=False,
                    observed_sha256=verified.sha256_digest,
                    observed_size_bytes=len(verified.content),
                )
        except ControlledFileStorageError as error:
            self._repository.release_finalize_lease(
                lease, released_at=observed_at, worker_id=worker_id
            )
            self._checkpoint()
            self._repository.mark_finalize_reconciliation_required(
                intent.finalize_id,
                worker_id=worker_id,
                claim_token=claim_token,
                observed_at=observed_at,
                error_code=error.code,
            )
            self._checkpoint()
            return ControlledFileFinalizeReceipt(
                intent.finalize_id,
                intent.staging_id,
                intent.controlled_file_object_id,
                FinalizeOutcome.RECONCILIATION_REQUIRED,
                error.observed_sha256,
                error.observed_size_bytes,
                observed_at,
                error.code,
            )

        try:
            self._repository.mark_finalize_available(
                intent.finalize_id,
                worker_id=worker_id,
                claim_token=claim_token,
                observed_at=observed_at,
                observed_sha256=verified.sha256_digest,
                observed_size_bytes=len(verified.content),
            )
            self._checkpoint()
        finally:
            self._repository.release_finalize_lease(
                lease, released_at=observed_at, worker_id=worker_id
            )
            self._checkpoint()
        return ControlledFileFinalizeReceipt(
            intent.finalize_id,
            intent.staging_id,
            intent.controlled_file_object_id,
            FinalizeOutcome.AVAILABLE,
            verified.sha256_digest,
            len(verified.content),
            observed_at,
        )


class ControlledFileReferenceRepository(Protocol):
    def assert_controlled_file_exists(self, controlled_file_object_id: str) -> None: ...

    def create_scheduling_reference(
        self, reference: SchedulingControlledFileReference
    ) -> SchedulingControlledFileReference: ...

    def acquire_lease(self, lease: ControlledFileLease) -> ControlledFileLease: ...

    def release_lease(
        self, lease_id: str, *, released_at: datetime, worker_id: str
    ) -> None: ...


class ControlledFileReferenceService:
    """Create only the closed Scheduling service-day-log reference."""

    def __init__(self, repository: ControlledFileReferenceRepository) -> None:
        self._repository = repository

    def attach_scheduling_service_day_log(
        self, reference: SchedulingControlledFileReference
    ) -> SchedulingControlledFileReference:
        # Scheduling Apply records the relation and pending finalize intent in
        # one outer UoW; integrity availability is established post-commit.
        self._repository.assert_controlled_file_exists(reference.controlled_file_object_id)
        return self._repository.create_scheduling_reference(reference)


@dataclass(frozen=True, slots=True)
class ReferenceAwareGcItem:
    staging_id: str
    disposition: str


class ReferenceAwareGcOutcome(StrEnum):
    DRY_RUN = "dry_run"
    CLEANED = "cleaned"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ReferenceAwareGcReceipt:
    receipt_id: str
    outcome: ReferenceAwareGcOutcome
    scanned: int
    eligible: int
    cleaned: int
    blocked: int
    items: tuple[ReferenceAwareGcItem, ...]
    observed_at: datetime
    command_fingerprint: PreviewFingerprint
    receipt_type: str = "controlled_file_reference_aware_gc"
    schema_version: str = "controlled-file-reference-aware-gc-receipt.v1"


class ReferenceAwareGcRepository(Protocol):
    def list_reference_aware_gc_candidates(
        self, *, limit: int, observed_at: datetime
    ) -> tuple[ReferenceAwareStagingCandidate, ...]: ...


class ReferenceAwareControlledFileGc:
    """Bounded, idempotent, dry-run-first GC over repository facts."""

    def __init__(self, repository: ReferenceAwareGcRepository, cleaner) -> None:
        self._repository = repository
        self._cleaner = cleaner
        self._runs: dict[str, tuple[PreviewFingerprint, ReferenceAwareGcReceipt]] = {}
        self._cleaned: set[str] = set()

    def run(
        self,
        *,
        idempotency_key: str,
        observed_at: datetime,
        limit: int = 100,
        grace_period: timedelta = timedelta(hours=24),
        dry_run: bool = True,
    ) -> ReferenceAwareGcReceipt:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ControlledFileFinalizeError("controlled_file_gc_limit_invalid", "GC limit must be 1..100")
        if grace_period < timedelta(0):
            raise ControlledFileFinalizeError("controlled_file_gc_grace_period_invalid", "GC grace period must not be negative")
        observed_at = _utc(observed_at)
        fingerprint = fingerprint_payload(
            {
                "schema": "controlled-file-reference-aware-gc-command.v1",
                "idempotency_key": idempotency_key,
                "limit": limit,
                "grace_period_seconds": int(grace_period.total_seconds()),
                "dry_run": dry_run,
            }
        )
        previous = self._runs.get(idempotency_key)
        if previous is not None:
            if previous[0] != fingerprint:
                raise ControlledFileFinalizeError(
                    "controlled_file_gc_idempotency_mismatch",
                    "same GC idempotency key was used for a different command",
                )
            return previous[1]
        candidates = self._repository.list_reference_aware_gc_candidates(
            limit=limit, observed_at=observed_at
        )[:limit]
        items: list[ReferenceAwareGcItem] = []
        eligible = cleaned = blocked = 0
        for candidate in candidates:
            if candidate.staging_id in self._cleaned:
                items.append(ReferenceAwareGcItem(candidate.staging_id, "already_cleaned"))
                continue
            disposition = gc_disposition(
                candidate,
                now=observed_at,
                grace_period_seconds=int(grace_period.total_seconds()),
            )
            if disposition != "eligible":
                items.append(ReferenceAwareGcItem(candidate.staging_id, disposition))
                continue
            eligible += 1
            if dry_run:
                items.append(ReferenceAwareGcItem(candidate.staging_id, "eligible"))
                continue
            try:
                self._cleaner(candidate)
            except Exception:
                blocked += 1
                items.append(ReferenceAwareGcItem(candidate.staging_id, "blocked"))
            else:
                cleaned += 1
                self._cleaned.add(candidate.staging_id)
                items.append(ReferenceAwareGcItem(candidate.staging_id, "cleaned"))
        outcome = (
            ReferenceAwareGcOutcome.DRY_RUN
            if dry_run
            else ReferenceAwareGcOutcome.BLOCKED
            if blocked
            else ReferenceAwareGcOutcome.CLEANED
        )
        receipt_id = f"cfg_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]}"
        receipt = ReferenceAwareGcReceipt(
            receipt_id,
            outcome,
            len(candidates),
            eligible,
            cleaned,
            blocked,
            tuple(items),
            observed_at,
            fingerprint,
        )
        self._runs[idempotency_key] = (fingerprint, receipt)
        return receipt


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ControlledFileFinalizeError("business_time_invalid", "time must be timezone-aware")
    return value.astimezone(timezone.utc)


__all__ = [
    "ControlledFileFinalizeError",
    "ControlledFileFinalizeReceipt",
    "ControlledFileFinalizeRepository",
    "ControlledFileFinalizeWorker",
    "ControlledFileReferenceRepository",
    "ControlledFileReferenceService",
    "FinalizeOutcome",
    "ReferenceAwareControlledFileGc",
    "ReferenceAwareGcItem",
    "ReferenceAwareGcOutcome",
    "ReferenceAwareGcReceipt",
    "ReferenceAwareGcRepository",
]

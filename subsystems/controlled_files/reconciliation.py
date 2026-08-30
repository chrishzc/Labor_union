"""
File: reconciliation.py
Description: 對帳 registered 物件與未登錄 staging，追加不可變觀測事件而不自動修復。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Protocol

from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId
from shared_kernel.ports import UnitOfWork
from subsystems.controlled_files.contracts import (
    ControlledFileStorageError,
    ControlledFileStoragePort,
    ControlledFileStagingRegistrationStatus,
)
from subsystems.controlled_files.workflow import (
    ControlledFileDownloadReference,
    ControlledFileStagingFacts,
)


class ControlledFileReconciliationOutcome(str, Enum):
    EXACT = "exact"
    MISSING_OBJECT = "missing_object"
    DIGEST_MISMATCH = "digest_mismatch"
    ORPHAN_OBJECT = "orphan_object"
    STILL_WRITING = "still_writing"


@dataclass(frozen=True, slots=True)
class ControlledFileReconciliationEvent:
    event_id: str
    outcome: ControlledFileReconciliationOutcome
    observation_fingerprint: PreviewFingerprint
    observed_at: datetime
    actor: ActorContext
    correlation_id: CorrelationId
    file_id: str | None = None
    staging_id: str | None = None
    observed_sha256: str | None = None
    observed_size_bytes: int | None = None


class ControlledFileReconciliationRepository(Protocol):
    def get_download_reference(
        self, file_id: str
    ) -> ControlledFileDownloadReference | None: ...

    def load_staging(
        self, staging_id: str, *, for_update: bool
    ) -> ControlledFileStagingFacts | None: ...

    def append_reconciliation_event(
        self, event: ControlledFileReconciliationEvent
    ) -> None: ...


class ControlledFileReconciler:
    def __init__(
        self,
        repository: ControlledFileReconciliationRepository,
        storage: ControlledFileStoragePort,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def reconcile_registered(
        self,
        file_id: str,
        *,
        actor: ActorContext,
        correlation_id: CorrelationId,
    ) -> ControlledFileReconciliationEvent:
        target = self._repository.get_download_reference(file_id)
        if target is None:
            raise ControlledFileStorageError(
                "controlled_file_not_found",
                "指定受控檔案不存在",
                retryable=False,
            )
        try:
            # A post-commit worker must use the storage adapter's finalize
            # operation when available.  It is intentionally idempotent and
            # integrity-only; it never promotes bytes based on a path or
            # mutates the owner Domain.  Older adapters can still be audited
            # through their verified-read operation.
            finalize = getattr(self._storage, "finalize_staged", None)
            if callable(finalize):
                observed = finalize(
                    target.staging_id,
                    expected_sha256=target.readback.sha256_digest,
                )
            else:
                observed = self._storage.read_registered_staged(
                    target.staging_id,
                    expected_sha256=target.readback.sha256_digest,
                )
            outcome = ControlledFileReconciliationOutcome.EXACT
            digest = observed.sha256_digest
            size_bytes = len(observed.content)
        except ControlledFileStorageError as error:
            if error.code == "controlled_file_staging_not_found":
                outcome = ControlledFileReconciliationOutcome.MISSING_OBJECT
                digest = None
                size_bytes = None
            elif (
                error.code == "controlled_file_staging_digest_mismatch"
                and error.observed_sha256 is not None
                and error.observed_size_bytes is not None
            ):
                outcome = ControlledFileReconciliationOutcome.DIGEST_MISMATCH
                digest = error.observed_sha256
                size_bytes = error.observed_size_bytes
            else:
                raise
        event = _event(
            outcome=outcome,
            file_id=file_id,
            staging_id=target.staging_id,
            observed_sha256=digest,
            observed_size_bytes=size_bytes,
            actor=actor,
            correlation_id=correlation_id,
            observed_at=_utc(self._clock.now()),
        )
        self._append(event)
        return event

    def reconcile_unregistered_staging(
        self,
        staging_id: str,
        *,
        actor: ActorContext,
        correlation_id: CorrelationId,
    ) -> ControlledFileReconciliationEvent:
        target = self._repository.load_staging(staging_id, for_update=False)
        if target is None:
            raise ControlledFileStorageError(
                "controlled_file_staging_not_found",
                "指定 staging 不存在",
                retryable=False,
            )
        if (
            target.registration_status
            is not ControlledFileStagingRegistrationStatus.UNREGISTERED
        ):
            raise ControlledFileStorageError(
                "controlled_file_staging_already_registered",
                "staging 已登錄，必須依受控檔案識別對帳",
                retryable=False,
            )
        try:
            observed = self._storage.read_staged(
                staging_id,
                expected_sha256=target.staging.sha256_digest,
            )
            outcome = ControlledFileReconciliationOutcome.ORPHAN_OBJECT
            digest = observed.sha256_digest
            size_bytes = len(observed.content)
        except ControlledFileStorageError as error:
            if error.code in {
                "controlled_file_staging_changed_during_read",
                "controlled_file_still_writing",
            }:
                outcome = ControlledFileReconciliationOutcome.STILL_WRITING
                digest = error.observed_sha256
                size_bytes = error.observed_size_bytes
            elif error.code in {
                "controlled_file_staging_not_found",
                "controlled_file_staging_digest_mismatch",
                "controlled_file_staging_reconciliation_required",
            }:
                outcome = ControlledFileReconciliationOutcome.ORPHAN_OBJECT
                digest = error.observed_sha256
                size_bytes = error.observed_size_bytes
            else:
                raise
        event = _event(
            outcome=outcome,
            file_id=None,
            staging_id=staging_id,
            observed_sha256=digest,
            observed_size_bytes=size_bytes,
            actor=actor,
            correlation_id=correlation_id,
            observed_at=_utc(self._clock.now()),
        )
        self._append(event)
        return event

    def _append(self, event: ControlledFileReconciliationEvent) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.append_reconciliation_event(event)
            unit_of_work.commit()


def _event(
    *,
    outcome: ControlledFileReconciliationOutcome,
    file_id: str | None,
    staging_id: str | None,
    observed_sha256: str | None,
    observed_size_bytes: int | None,
    actor: ActorContext,
    correlation_id: CorrelationId,
    observed_at: datetime,
) -> ControlledFileReconciliationEvent:
    fingerprint = fingerprint_payload(
        {
            "schema": "controlled-file-reconciliation-observation.v1",
            "outcome": outcome.value,
            "file_id": file_id,
            "staging_id": staging_id,
            "observed_sha256": observed_sha256,
            "observed_size_bytes": observed_size_bytes,
            "actor": actor.actor_id,
            "correlation_id": correlation_id.value,
            "observed_at": observed_at.isoformat(),
        }
    )
    event_id = f"cfe_{hashlib.sha256(fingerprint.value.encode('utf-8')).hexdigest()[:32]}"
    return ControlledFileReconciliationEvent(
        event_id=event_id,
        outcome=outcome,
        observation_fingerprint=fingerprint,
        observed_at=observed_at,
        actor=actor,
        correlation_id=correlation_id,
        file_id=file_id,
        staging_id=staging_id,
        observed_sha256=observed_sha256,
        observed_size_bytes=observed_size_bytes,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("reconciliation time must include timezone")
    return value.astimezone(timezone.utc)


__all__ = [
    "ControlledFileReconciler",
    "ControlledFileReconciliationEvent",
    "ControlledFileReconciliationOutcome",
    "ControlledFileReconciliationRepository",
]

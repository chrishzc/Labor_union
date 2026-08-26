"""
File: cleanup.py
Description: 編排未登錄 staging 的 durable cleanup intent、bytes cleanup 與 terminal fact。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Protocol

from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.ports import UnitOfWork
from subsystems.controlled_files.contracts import (
    ControlledFileStorageError,
    ControlledFileStoragePort,
    ControlledFileStagingCleanupReason,
    ControlledFileStagingRegistrationStatus,
)


_STAGING_ID = re.compile(r"^cfs_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")


class ControlledFileCleanupTerminal(str, Enum):
    INTENT = "intent"
    COMPLETED = "completed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class ControlledFileCleanupOutcome(str, Enum):
    CLEANED = "cleaned"
    REPLAYED = "replayed"


class ControlledFileCleanupError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class CleanupControlledFileStaging:
    staging_id: str
    reason: ControlledFileStagingCleanupReason
    expected_staging_version: ExpectedVersion
    expected_sha256: str
    idempotency_key: IdempotencyKey
    actor: ActorContext
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if _STAGING_ID.fullmatch(self.staging_id) is None:
            raise ValueError("controlled file staging identity is invalid")
        if _DIGEST.fullmatch(self.expected_sha256) is None:
            raise ValueError("controlled file staging digest is invalid")
        if _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key.value) is None:
            raise ValueError("controlled file cleanup idempotency key is invalid")


@dataclass(frozen=True, slots=True)
class ControlledFileCleanupReceipt:
    cleanup_id: str
    staging_id: str
    reason: ControlledFileStagingCleanupReason
    outcome: ControlledFileCleanupOutcome
    cleaned_at: datetime
    receipt_type: str = "controlled_file_staging_cleanup"
    schema_version: str = "controlled-file-staging-cleanup-receipt.v1"


@dataclass(frozen=True, slots=True)
class StoredControlledFileCleanup:
    cleanup_id: str
    command_fingerprint: PreviewFingerprint
    terminal: ControlledFileCleanupTerminal
    staging_id: str
    reason: ControlledFileStagingCleanupReason
    expected_staging_version: ExpectedVersion
    expected_sha256: str
    receipt: ControlledFileCleanupReceipt | None = None
    error_code: str | None = None


class ControlledFileCleanupRepository(Protocol):
    def load_cleanup(
        self, key: IdempotencyKey, *, for_update: bool
    ) -> StoredControlledFileCleanup | None: ...

    def begin_cleanup(
        self,
        command: CleanupControlledFileStaging,
        *,
        cleanup_id: str,
        command_fingerprint: PreviewFingerprint,
        occurred_at: datetime,
    ) -> StoredControlledFileCleanup: ...

    def complete_cleanup(
        self,
        stored: StoredControlledFileCleanup,
        receipt: ControlledFileCleanupReceipt,
        *,
        occurred_at: datetime,
    ) -> None: ...

    def fail_cleanup(
        self,
        stored: StoredControlledFileCleanup,
        *,
        error_code: str,
        occurred_at: datetime,
    ) -> None: ...


class ControlledFileCleanupWorkflow:
    def __init__(
        self,
        repository: ControlledFileCleanupRepository,
        storage: ControlledFileStoragePort,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: BusinessClock,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def cleanup(
        self, command: CleanupControlledFileStaging
    ) -> ControlledFileCleanupReceipt:
        fingerprint = fingerprint_payload(
            {
                "schema": "controlled-file-staging-cleanup-command.v1",
                "staging_id": command.staging_id,
                "reason": command.reason.value,
                "expected_staging_version": command.expected_staging_version.value,
                "expected_sha256": command.expected_sha256,
            }
        )
        with self._unit_of_work_factory() as unit_of_work:
            stored = self._repository.load_cleanup(
                command.idempotency_key, for_update=True
            )
            if stored is None:
                stored = self._repository.begin_cleanup(
                    command,
                    cleanup_id=_cleanup_id(command.idempotency_key),
                    command_fingerprint=fingerprint,
                    occurred_at=_utc(self._clock.now()),
                )
            else:
                _require_same_command(stored, fingerprint)
                if stored.terminal is ControlledFileCleanupTerminal.COMPLETED:
                    if stored.receipt is None:
                        raise ControlledFileCleanupError(
                            "controlled_file_cleanup_receipt_incomplete",
                            "cleanup terminal fact 缺少 receipt",
                        )
                    unit_of_work.commit()
                    return replace(
                        stored.receipt, outcome=ControlledFileCleanupOutcome.REPLAYED
                    )
                if (
                    stored.terminal
                    is ControlledFileCleanupTerminal.RECONCILIATION_REQUIRED
                ):
                    raise ControlledFileCleanupError(
                        "controlled_file_cleanup_reconciliation_required",
                        "cleanup 先前失敗，需要人工對帳",
                    )
            unit_of_work.commit()

        try:
            removed = self._storage.cleanup_staged(
                stored.staging_id,
                registration_status=ControlledFileStagingRegistrationStatus.UNREGISTERED,
                reason=stored.reason,
                expected_sha256=stored.expected_sha256,
            )
            if not removed:
                raise ControlledFileStorageError(
                    "controlled_file_staging_not_found",
                    "cleanup target bytes 不存在，無法證明刪除結果",
                    retryable=False,
                )
        except ControlledFileStorageError as error:
            with self._unit_of_work_factory() as unit_of_work:
                self._repository.fail_cleanup(
                    stored,
                    error_code=error.code,
                    occurred_at=_utc(self._clock.now()),
                )
                unit_of_work.commit()
            raise ControlledFileCleanupError(
                "controlled_file_cleanup_reconciliation_required",
                "cleanup bytes 失敗，需要人工對帳",
                retryable=False,
            ) from error

        cleaned_at = _utc(self._clock.now())
        receipt = ControlledFileCleanupReceipt(
            cleanup_id=stored.cleanup_id,
            staging_id=stored.staging_id,
            reason=stored.reason,
            outcome=ControlledFileCleanupOutcome.CLEANED,
            cleaned_at=cleaned_at,
        )
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.complete_cleanup(
                stored, receipt, occurred_at=cleaned_at
            )
            unit_of_work.commit()
        return receipt


def _require_same_command(
    stored: StoredControlledFileCleanup,
    fingerprint: PreviewFingerprint,
) -> None:
    if stored.command_fingerprint != fingerprint:
        raise ControlledFileCleanupError(
            "idempotency_mismatch", "相同 cleanup 重播識別對應不同命令"
        )


def _cleanup_id(key: IdempotencyKey) -> str:
    return f"cfc_{hashlib.sha256(key.value.encode('utf-8')).hexdigest()[:32]}"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ControlledFileCleanupError(
            "business_time_invalid", "cleanup 時間必須包含時區"
        )
    return value.astimezone(timezone.utc)


__all__ = [
    "CleanupControlledFileStaging",
    "ControlledFileCleanupError",
    "ControlledFileCleanupOutcome",
    "ControlledFileCleanupReceipt",
    "ControlledFileCleanupRepository",
    "ControlledFileCleanupTerminal",
    "ControlledFileCleanupWorkflow",
    "StoredControlledFileCleanup",
]

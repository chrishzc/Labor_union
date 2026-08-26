"""
File: test_controlled_file_cleanup_workflow.py
Description: 驗證 staging cleanup 的 durable intent、terminal fact、重播與失敗對帳。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.controlled_files.cleanup import (
    CleanupControlledFileStaging,
    ControlledFileCleanupError,
    ControlledFileCleanupOutcome,
    ControlledFileCleanupTerminal,
    ControlledFileCleanupWorkflow,
    StoredControlledFileCleanup,
)
from subsystems.controlled_files.contracts import (
    ControlledFileStorageError,
    ControlledFileStagingCleanupReason,
)


NOW = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
STAGING_ID = "cfs_1234567890abcdef1234567890abcdef"
DIGEST = "a" * 64


class _Uow:
    def __init__(self) -> None:
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


class _Repository:
    def __init__(self) -> None:
        self.stored = None
        self.begin_calls = 0
        self.complete_calls = 0
        self.fail_calls = 0

    def load_cleanup(self, key, *, for_update):
        return self.stored

    def begin_cleanup(
        self, command, *, cleanup_id, command_fingerprint, occurred_at
    ):
        self.begin_calls += 1
        self.stored = StoredControlledFileCleanup(
            cleanup_id,
            command_fingerprint,
            ControlledFileCleanupTerminal.INTENT,
            command.staging_id,
            command.reason,
            command.expected_staging_version,
            command.expected_sha256,
        )
        return self.stored

    def complete_cleanup(self, stored, receipt, *, occurred_at):
        self.complete_calls += 1
        self.stored = StoredControlledFileCleanup(
            stored.cleanup_id,
            stored.command_fingerprint,
            ControlledFileCleanupTerminal.COMPLETED,
            stored.staging_id,
            stored.reason,
            stored.expected_staging_version,
            stored.expected_sha256,
            receipt=receipt,
        )

    def fail_cleanup(self, stored, *, error_code, occurred_at):
        self.fail_calls += 1
        self.stored = StoredControlledFileCleanup(
            stored.cleanup_id,
            stored.command_fingerprint,
            ControlledFileCleanupTerminal.RECONCILIATION_REQUIRED,
            stored.staging_id,
            stored.reason,
            stored.expected_staging_version,
            stored.expected_sha256,
            error_code=error_code,
        )


class _Storage:
    def __init__(self) -> None:
        self.calls = 0
        self.error = None
        self.removed = True

    def cleanup_staged(self, staging_id, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.removed


def _command(key="controlled-file.cleanup:test-001"):
    return CleanupControlledFileStaging(
        staging_id=STAGING_ID,
        reason=ControlledFileStagingCleanupReason.EXPIRED,
        expected_staging_version=ExpectedVersion(1),
        expected_sha256=DIGEST,
        idempotency_key=IdempotencyKey(key),
        actor=ActorContext("cleanup-worker"),
        correlation_id=CorrelationId("corr-cleanup-001"),
    )


def _workflow():
    repository = _Repository()
    storage = _Storage()
    uows = []

    def factory():
        unit = _Uow()
        uows.append(unit)
        return unit

    return (
        ControlledFileCleanupWorkflow(
            repository, storage, factory, FixedBusinessClock(NOW)
        ),
        repository,
        storage,
        uows,
    )


def test_cleanup_commits_intent_before_bytes_then_terminal_fact():
    workflow, repository, storage, uows = _workflow()

    receipt = workflow.cleanup(_command())

    assert receipt.outcome is ControlledFileCleanupOutcome.CLEANED
    assert repository.begin_calls == repository.complete_calls == 1
    assert storage.calls == 1
    assert [unit.commits for unit in uows] == [1, 1]


def test_completed_cleanup_replays_without_touching_bytes():
    workflow, repository, storage, _ = _workflow()
    created = workflow.cleanup(_command())

    replay = workflow.cleanup(_command())

    assert replay.cleanup_id == created.cleanup_id
    assert replay.outcome is ControlledFileCleanupOutcome.REPLAYED
    assert storage.calls == 1
    assert repository.complete_calls == 1


def test_same_key_different_command_fails_before_bytes():
    workflow, _, storage, _ = _workflow()
    workflow.cleanup(_command())

    with pytest.raises(ControlledFileCleanupError, match="不同命令"):
        changed = _command()
        changed = CleanupControlledFileStaging(
            changed.staging_id,
            ControlledFileStagingCleanupReason.ABANDONED,
            changed.expected_staging_version,
            changed.expected_sha256,
            changed.idempotency_key,
            changed.actor,
            changed.correlation_id,
        )
        workflow.cleanup(changed)

    assert storage.calls == 1


def test_bytes_failure_appends_reconciliation_terminal_and_never_reports_success():
    workflow, repository, storage, uows = _workflow()
    storage.error = ControlledFileStorageError(
        "controlled_file_staging_cleanup_failed",
        "failed",
        retryable=True,
    )

    with pytest.raises(ControlledFileCleanupError) as captured:
        workflow.cleanup(_command())

    assert captured.value.code == "controlled_file_cleanup_reconciliation_required"
    assert repository.fail_calls == 1
    assert repository.complete_calls == 0
    assert [unit.commits for unit in uows] == [1, 1]


def test_missing_bytes_cannot_be_inferred_as_cleanup_success():
    workflow, repository, storage, _ = _workflow()
    storage.removed = False

    with pytest.raises(ControlledFileCleanupError) as captured:
        workflow.cleanup(_command())

    assert captured.value.code == "controlled_file_cleanup_reconciliation_required"
    assert repository.fail_calls == 1
    assert repository.complete_calls == 0

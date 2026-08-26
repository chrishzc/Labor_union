"""
File: test_controlled_file_reconciliation.py
Description: 驗證受控檔案對帳的五種封閉結果、冪等事件與 outer UoW 邊界。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.controlled_files.contracts import (
    ControlledFileStorageError,
    ControlledFileStagingContent,
    ControlledFileStagingRegistrationStatus,
    ControlledFileStagingResult,
)
from subsystems.controlled_files.reconciliation import (
    ControlledFileReconciler,
    ControlledFileReconciliationOutcome,
)
from subsystems.controlled_files.workflow import (
    ControlledFileDownloadReference,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileStagingFacts,
)


NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
FILE_ID = "cf_1234567890abcdef1234567890abcdef"
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
        readback = ControlledFileReadback(
            file_id=FILE_ID,
            owner=ControlledFileOwner.ORDERS,
            purpose=ControlledFilePurpose.ORDER_NOTICE,
            subject_reference="CASE-001",
            filename="notice.pdf",
            logical_folder="orders/CASE-001",
            version=1,
            sha256_digest=DIGEST,
            mime_type="application/pdf",
            size_bytes=3,
            status="registered",
            applied_at=NOW,
        )
        self.download = ControlledFileDownloadReference(readback, STAGING_ID)
        self.staging = ControlledFileStagingFacts(
            ControlledFileStagingResult(
                STAGING_ID,
                "notice.pdf",
                "application/pdf",
                3,
                DIGEST,
                NOW + timedelta(hours=1),
                False,
            ),
            1,
            ControlledFileStagingRegistrationStatus.UNREGISTERED,
        )
        self.events = []

    def get_download_reference(self, file_id):
        return self.download if file_id == FILE_ID else None

    def load_staging(self, staging_id, *, for_update):
        return self.staging if staging_id == STAGING_ID else None

    def append_reconciliation_event(self, event):
        self.events.append(event)


class _Storage:
    def __init__(self) -> None:
        self.registered_error = None
        self.staging_error = None

    def read_registered_staged(self, staging_id, *, expected_sha256):
        if self.registered_error is not None:
            raise self.registered_error
        return ControlledFileStagingContent(staging_id, b"abc", DIGEST, NOW)

    def read_staged(self, staging_id, *, expected_sha256):
        if self.staging_error is not None:
            raise self.staging_error
        return ControlledFileStagingContent(staging_id, b"abc", DIGEST, NOW)


def _service():
    repository = _Repository()
    storage = _Storage()
    uow = _Uow()
    return (
        ControlledFileReconciler(
            repository, storage, lambda: uow, FixedBusinessClock(NOW)
        ),
        repository,
        storage,
        uow,
    )


def _identity():
    return {
        "actor": ActorContext("reconciliation-worker"),
        "correlation_id": CorrelationId("corr-reconcile-001"),
    }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, ControlledFileReconciliationOutcome.EXACT),
        (
            ControlledFileStorageError(
                "controlled_file_staging_not_found", "missing", retryable=False
            ),
            ControlledFileReconciliationOutcome.MISSING_OBJECT,
        ),
        (
            ControlledFileStorageError(
                "controlled_file_staging_digest_mismatch",
                "mismatch",
                retryable=False,
                observed_sha256="b" * 64,
                observed_size_bytes=4,
            ),
            ControlledFileReconciliationOutcome.DIGEST_MISMATCH,
        ),
    ],
)
def test_registered_reconciliation_has_three_closed_outcomes(error, expected):
    service, repository, storage, uow = _service()
    storage.registered_error = error

    event = service.reconcile_registered(FILE_ID, **_identity())

    assert event.outcome is expected
    assert repository.events == [event]
    assert uow.commits == 1
    assert "locator" not in repr(event).casefold()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, ControlledFileReconciliationOutcome.ORPHAN_OBJECT),
        (
            ControlledFileStorageError(
                "controlled_file_staging_changed_during_read",
                "changing",
                retryable=True,
            ),
            ControlledFileReconciliationOutcome.STILL_WRITING,
        ),
    ],
)
def test_unregistered_staging_distinguishes_orphan_from_still_writing(error, expected):
    service, repository, storage, uow = _service()
    storage.staging_error = error

    event = service.reconcile_unregistered_staging(STAGING_ID, **_identity())

    assert event.outcome is expected
    assert event.file_id is None
    assert event.staging_id == STAGING_ID
    assert repository.events == [event]
    assert uow.commits == 1


def test_same_observation_identity_is_deterministic_for_repository_replay():
    service, _, _, _ = _service()

    first = service.reconcile_registered(FILE_ID, **_identity())
    second = service.reconcile_registered(FILE_ID, **_identity())

    assert first.event_id == second.event_id
    assert first.observation_fingerprint == second.observation_fingerprint

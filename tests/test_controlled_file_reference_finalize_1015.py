"""Focused local contract tests for the 1015 media successor package."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from domains.controlled_files.reference_finalize import (
    ControlledFileFinalizeIntent,
    ControlledFileFinalizeState,
    ControlledFileLease,
    ControlledFileReferenceError,
    ReferenceAwareStagingCandidate,
    SchedulingControlledFileReference,
    canonical_scheduling_object_key,
    gc_disposition,
)
from subsystems.controlled_files.contracts import ControlledFileStagingContent, ControlledFileStorageError
from subsystems.controlled_files.reference_finalize import (
    ControlledFileFinalizeError as DomainError,
    ControlledFileFinalizeWorker,
    FinalizeOutcome,
    ReferenceAwareControlledFileGc,
    ReferenceAwareGcOutcome,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
STAGING = "cfs_1234567890abcdef1234567890abcdef"
FILE = "cf_abcdefabcdefabcdefabcdefabcdefab"
DIGEST = "a" * 64
FINALIZE = "cff_1234567890abcdef1234567890abcdef"


def _intent(state=ControlledFileFinalizeState.PENDING):
    return ControlledFileFinalizeIntent(FINALIZE, STAGING, FILE, DIGEST, state, NOW)


def test_identity_prefixes_and_canonical_key_are_closed_and_non_pii():
    key = canonical_scheduling_object_key(
        assignment_id=42,
        service_date=date(2026, 8, 30),
        attachment_kind="meal_photo",
        sequence=2,
        sha256_digest=DIGEST,
    )
    assert key == f"scheduling/service-day/v1/42/2026-08-30/meal_photo/2/{DIGEST}"
    assert "{" not in key
    assert "Alice" not in key


def test_canonical_key_rejects_locator_or_pii_like_components():
    with pytest.raises(ControlledFileReferenceError):
        canonical_scheduling_object_key(
            assignment_id=42,
            service_date=date(2026, 8, 30),
            attachment_kind="../name",
            sequence=1,
            sha256_digest=DIGEST,
        )


def test_lease_requires_positive_interval_and_opaque_identity():
    lease = ControlledFileLease(
        "cfl_1234567890abcdef1234567890abcdef",
        STAGING,
        "worker-1",
        NOW,
        NOW + timedelta(hours=24),
    )
    assert lease.state.value == "active"
    with pytest.raises(ControlledFileReferenceError):
        ControlledFileLease(lease.lease_id, STAGING, "worker-1", NOW, NOW)


class _Storage:
    def __init__(self, *, failure=None):
        self.failure = failure
        self.calls = []

    def finalize_staged(self, staging_id, *, expected_sha256):
        self.calls.append((staging_id, expected_sha256))
        if self.failure:
            raise self.failure
        return ControlledFileStagingContent(staging_id, b"payload", DIGEST, NOW + timedelta(hours=1))


class _FinalizeRepo:
    def __init__(self, intent):
        self.intent = intent
        self.transitions = []

    def claim_finalize_intent(self, finalize_id, *, worker_id, observed_at):
        self.transitions.append(("claim", finalize_id, worker_id))
        return replace(self.intent, claim_token=f"{worker_id}:token")

    def mark_finalize_available(self, finalize_id, *, worker_id, claim_token, observed_at, observed_sha256, observed_size_bytes):
        self.transitions.append(("available", finalize_id, observed_sha256, observed_size_bytes))

    def mark_finalize_reconciliation_required(self, finalize_id, *, worker_id, claim_token, observed_at, error_code):
        self.transitions.append(("blocked", finalize_id, error_code))

    def acquire_finalize_lease(self, intent, *, worker_id, acquired_at):
        self.transitions.append(("lease", intent.staging_id, worker_id))
        return ControlledFileLease(
            "cfl_1234567890abcdef1234567890abcdef",
            intent.staging_id,
            worker_id,
            acquired_at,
            acquired_at + timedelta(hours=24),
        )

    def release_finalize_lease(self, lease, *, released_at, worker_id):
        self.transitions.append(("release", lease.lease_id, worker_id))


def test_worker_calls_storage_between_claim_and_available_cas():
    repo = _FinalizeRepo(_intent())
    storage = _Storage()
    receipt = ControlledFileFinalizeWorker(repo, storage).run(
        FINALIZE, worker_id="worker-1", observed_at=NOW
    )
    assert receipt.outcome is FinalizeOutcome.AVAILABLE
    assert storage.calls == [(STAGING, DIGEST)]
    assert [item[0] for item in repo.transitions] == ["claim", "lease", "available", "release"]


def test_worker_never_reports_success_when_storage_integrity_fails():
    repo = _FinalizeRepo(_intent())
    storage = _Storage(
        failure=ControlledFileStorageError(
            "controlled_file_staging_not_found", "missing", retryable=False
        )
    )
    receipt = ControlledFileFinalizeWorker(repo, storage).run(
        FINALIZE, worker_id="worker-1", observed_at=NOW
    )
    assert receipt.outcome is FinalizeOutcome.RECONCILIATION_REQUIRED
    assert receipt.error_code == "controlled_file_staging_not_found"
    assert repo.transitions[-2:] == [
        ("release", "cfl_1234567890abcdef1234567890abcdef", "worker-1"),
        ("blocked", FINALIZE, "controlled_file_staging_not_found"),
    ]


def test_reference_requires_registered_controlled_file_object():
    reference = SchedulingControlledFileReference(
        "cfrf_1234567890abcdef1234567890abcdef", FILE, 9, NOW
    )
    class Repo:
        def assert_controlled_file_exists(self, object_id):
            raise DomainError("not_available", "not available")
        def create_scheduling_reference(self, ref):
            return ref

    from subsystems.controlled_files.reference_finalize import ControlledFileReferenceService
    with pytest.raises(DomainError):
        ControlledFileReferenceService(Repo()).attach_scheduling_service_day_log(reference)


def test_gc_is_reference_and_lease_aware_and_dry_run():
    candidate = ReferenceAwareStagingCandidate(
        STAGING, 1, DIGEST, NOW - timedelta(days=2), False, 0, False
    )
    class Repo:
        def list_reference_aware_gc_candidates(self, *, limit, observed_at):
            return (candidate,)
    cleaned = []
    receipt = ReferenceAwareControlledFileGc(Repo(), lambda item: cleaned.append(item)).run(
        idempotency_key="gc-1015", observed_at=NOW, dry_run=True
    )
    assert receipt.outcome is ReferenceAwareGcOutcome.DRY_RUN
    assert receipt.eligible == 1
    assert cleaned == []


def test_gc_replays_same_command_and_rejects_same_key_with_different_command():
    candidate = ReferenceAwareStagingCandidate(
        STAGING, 1, DIGEST, NOW - timedelta(days=2), False, 0, False
    )
    class Repo:
        def list_reference_aware_gc_candidates(self, *, limit, observed_at):
            return (candidate,)
    service = ReferenceAwareControlledFileGc(Repo(), lambda item: None)
    first = service.run(idempotency_key="gc-1015-replay", observed_at=NOW)
    replay = service.run(idempotency_key="gc-1015-replay", observed_at=NOW)
    assert replay == first
    with pytest.raises(DomainError):
        service.run(idempotency_key="gc-1015-replay", observed_at=NOW, limit=2)


def test_gc_skips_referenced_and_leased_candidates():
    referenced = ReferenceAwareStagingCandidate(STAGING, 1, DIGEST, NOW - timedelta(days=2), False, 1, False)
    leased = ReferenceAwareStagingCandidate("cfs_abcdefabcdefabcdefabcdefabcdefab", 1, DIGEST, NOW - timedelta(days=2), False, 0, True)
    assert gc_disposition(referenced, now=NOW, grace_period_seconds=0) == "skipped_referenced"
    assert gc_disposition(leased, now=NOW, grace_period_seconds=0) == "skipped_leased"


def test_schema_part_and_descriptor_are_additive_no_backfill():
    sql = (ROOT / "db/schema_parts/1015_controlled_file_reference_finalize_leases.sql").read_text(encoding="utf-8")
    descriptor = json.loads(
        (ROOT / "db/migration_releases/labor_union_2026_08_30_controlled_file_reference_finalize_leases_v1.descriptors.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "db/migration_releases/labor_union_2026_08_30_controlled_file_reference_finalize_leases_v1.json").read_text(encoding="utf-8")
    )
    assert "controlled_file_finalize_intents" in sql
    assert "controlled_file_references" in sql
    assert "controlled_file_leases" in sql
    assert "cff_" in sql and "cfrf_" in sql and "cfl_" in sql
    assert "INSERT INTO" not in sql.upper()
    assert "UPDATE controlled_file" not in sql.upper()
    assert "legacy-readable" in sql
    assert "controlled_file_object_id BIGINT UNSIGNED NULL" in sql
    assert descriptor["release_id"] == manifest["release_id"]
    assert manifest["backfills"] == []
    assert set(descriptor["descriptors"]) == {"1015_controlled_file_reference_finalize_leases.sql"}

"""Verify bounded reference/lease-aware controlled-file staging GC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.controlled_files.cleanup import ControlledFileCleanupOutcome
from subsystems.controlled_files.contracts import ControlledFileStagingRegistrationStatus
from subsystems.controlled_files.gc import (
    ControlledFileGcCandidate,
    ControlledFileGcDisposition,
    ControlledFileGcOutcome,
    ControlledFileStagingGarbageCollector,
    GarbageCollectControlledFileStaging,
)


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
DIGEST = "a" * 64


class _Repository:
    def __init__(self, candidates):
        self.candidates = tuple(candidates)

    def list_staging_gc_candidates(self, *, limit, observed_at):
        return self.candidates[:limit]


class _Cleanup:
    def __init__(self):
        self.commands = []

    def cleanup(self, command):
        self.commands.append(command)
        return type("Receipt", (), {"outcome": ControlledFileCleanupOutcome.CLEANED})()


def _candidate(
    staging_id="cfs_1234567890abcdef1234567890abcdef",
    *,
    expires_at=NOW - timedelta(days=2),
    references=0,
    leased=False,
    status=ControlledFileStagingRegistrationStatus.UNREGISTERED,
):
    return ControlledFileGcCandidate(
        staging_id=staging_id,
        staging_version=1,
        expected_sha256=DIGEST,
        expires_at=expires_at,
        registration_status=status,
        reference_count=references,
        active_lease=leased,
    )


def _command(key="controlled-file.gc:test-001", *, dry_run=True):
    return GarbageCollectControlledFileStaging(
        idempotency_key=IdempotencyKey(key),
        actor=ActorContext("gc-worker"),
        correlation_id=CorrelationId("corr-gc-001"),
        dry_run=dry_run,
    )


def test_dry_run_is_bounded_and_skips_referenced_or_leased_objects():
    candidates = [
        _candidate(),
        _candidate("cfs_abcdefabcdefabcdefabcdefabcdefab", references=1),
        _candidate("cfs_fedcbafedcbafedcbafedcbafedcbafe", leased=True),
    ]
    cleanup = _Cleanup()
    service = ControlledFileStagingGarbageCollector(
        _Repository(candidates), cleanup, FixedBusinessClock(NOW)
    )

    receipt = service.run(_command())

    assert receipt.outcome is ControlledFileGcOutcome.DRY_RUN
    assert receipt.scanned == 3
    assert receipt.eligible == 1
    assert receipt.cleaned == 0
    assert [item.disposition for item in receipt.items] == [
        ControlledFileGcDisposition.ELIGIBLE,
        ControlledFileGcDisposition.SKIPPED_REFERENCED,
        ControlledFileGcDisposition.SKIPPED_LEASED,
    ]
    assert cleanup.commands == []


def test_apply_uses_cleanup_intent_before_delete_and_replays_by_key():
    candidate = _candidate()
    cleanup = _Cleanup()
    service = ControlledFileStagingGarbageCollector(
        _Repository([candidate]), cleanup, FixedBusinessClock(NOW)
    )

    receipt = service.run(_command("controlled-file.gc:test-002", dry_run=False))
    replay = service.run(_command("controlled-file.gc:test-002", dry_run=False))

    assert receipt.outcome is ControlledFileGcOutcome.CLEANED
    assert replay.outcome is ControlledFileGcOutcome.REPLAYED
    assert receipt.cleaned == 1
    assert len(cleanup.commands) == 1


def test_registered_objects_are_never_gc_eligible():
    cleanup = _Cleanup()
    service = ControlledFileStagingGarbageCollector(
        _Repository([_candidate(status=ControlledFileStagingRegistrationStatus.REGISTERED)]),
        cleanup,
        FixedBusinessClock(NOW),
    )

    receipt = service.run(_command("controlled-file.gc:test-003", dry_run=False))

    assert receipt.eligible == 0
    assert receipt.items[0].disposition is ControlledFileGcDisposition.SKIPPED_REGISTERED
    assert cleanup.commands == []


def test_concurrent_gc_passes_do_not_issue_duplicate_cleanup_for_one_staging_object():
    candidate = _candidate()
    cleanup = _Cleanup()
    service = ControlledFileStagingGarbageCollector(
        _Repository([candidate]), cleanup, FixedBusinessClock(NOW)
    )

    def run(key):
        return service.run(_command(key, dry_run=False))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(run, ("controlled-file.gc:concurrent-1", "controlled-file.gc:concurrent-2"))

    assert len(cleanup.commands) == 1
    assert sorted((first.cleaned, second.cleaned)) == [0, 1]
    skipped = second if second.cleaned == 0 else first
    assert skipped.items[0].disposition is ControlledFileGcDisposition.SKIPPED_ALREADY_CLEANED

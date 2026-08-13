from __future__ import annotations

from datetime import date, datetime

import pytest

from domains.scheduling.staff_availability import (
    StaffAvailabilityAction,
    StaffAvailabilityBlockStatus,
    StaffAvailabilityConflict,
    StaffAvailabilityDomainError,
    StaffAvailabilityErrorCode,
    StaffAvailabilityFacts,
    StaffAvailabilityIntent,
    StaffUnavailabilityBlock,
    StaffUnavailabilityKind,
    build_staff_availability_preview,
)
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.scheduling.staff_availability_workflow import (
    StaffAvailabilityApplyRequest,
    StaffAvailabilityPreviewRequest,
    StaffAvailabilityWorkflow,
    StoredStaffAvailabilityReceipt,
)


class FakeRepository:
    def __init__(self, *, version=0, blocks=(), conflicts=()):
        self.version = version
        self.blocks = list(blocks)
        self.conflicts = tuple(conflicts)
        self.receipts = {}
        self.events = []
        self.commits = 0
        self.rollbacks = 0
        self.receipt_reads = 0

    def list_blocks(self, _query):
        return tuple(self.blocks)

    def load_facts(self, intent, *, for_update):
        del for_update
        target = next((item for item in self.blocks if item.block_id == intent.block_id), None)
        return StaffAvailabilityFacts(
            intent.staff_id,
            self.version,
            tuple(self.blocks),
            self.conflicts,
            target,
        )

    def load_receipt(self, key):
        self.receipt_reads += 1
        return self.receipts.get(key.value)

    def create_block(self, intent, candidate, actor, occurred_at):
        del actor, occurred_at
        block = StaffUnavailabilityBlock(
            100 + len(self.blocks) + 1,
            intent.staff_id,
            candidate.kind,
            candidate.start_date,
            candidate.end_date,
            candidate.status,
            intent.reason,
        )
        self.blocks.append(block)
        return block

    def end_pause(self, target, candidate, actor, occurred_at):
        del actor, occurred_at
        block = StaffUnavailabilityBlock(
            target.block_id,
            target.staff_id,
            target.kind,
            candidate.start_date,
            candidate.end_date,
            target.status,
            target.reason,
        )
        self._replace(block)
        return block

    def cancel_block(self, target, actor, occurred_at):
        del actor, occurred_at
        block = StaffUnavailabilityBlock(
            target.block_id,
            target.staff_id,
            target.kind,
            target.start_date,
            target.end_date,
            StaffAvailabilityBlockStatus.CANCELLED,
            target.reason,
        )
        self._replace(block)
        return block

    def increment_version(self, staff_id, expected_version):
        del staff_id
        assert expected_version == self.version
        self.version += 1
        return self.version

    def append_event(self, request, before, after, aggregate_version, occurred_at):
        self.events.append((request, before, after, aggregate_version, occurred_at))

    def save_receipt(self, request, request_fingerprint, receipt, occurred_at):
        del occurred_at
        self.receipts[request.idempotency_key.value] = StoredStaffAvailabilityReceipt(
            request_fingerprint,
            receipt,
        )

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def _replace(self, block):
        self.blocks = [block if item.block_id == block.block_id else item for item in self.blocks]


def test_long_leave_requires_a_finite_date_range():
    with pytest.raises(TypeError, match="long leave end date"):
        StaffAvailabilityIntent(
            StaffAvailabilityAction.CREATE_LONG_LEAVE,
            7,
            "照顧家人",
            start_date=date(2026, 9, 1),
        )


def test_create_long_leave_preview_contains_versioned_candidate():
    intent = _long_leave_intent()
    preview = build_staff_availability_preview(intent, StaffAvailabilityFacts(7, 3, (), ()))

    assert preview.source_version == 3
    assert preview.can_apply is True
    assert preview.candidate.kind is StaffUnavailabilityKind.LONG_LEAVE
    assert preview.candidate.end_date == date(2026, 9, 30)
    assert len(preview.preview_fingerprint.value) == 64


def test_existing_assignment_blocks_new_unavailability():
    conflict = StaffAvailabilityConflict(
        "assignment",
        "88",
        date(2026, 9, 4),
        date(2026, 9, 20),
    )
    preview = build_staff_availability_preview(
        _long_leave_intent(),
        StaffAvailabilityFacts(7, 0, (), (conflict,)),
    )

    assert preview.can_apply is False
    assert preview.blockers[0].startswith("assignment:88:")


def test_create_pause_apply_is_atomic_and_exact_replay_returns_same_receipt():
    repository = FakeRepository()
    workflow = _workflow(repository)
    intent = _pause_intent()
    preview = workflow.preview(StaffAvailabilityPreviewRequest(intent))
    request = _apply_request(intent, preview.preview_fingerprint, 0, "pause-001")

    receipt = workflow.apply(request)
    replay = workflow.apply(request)

    assert receipt == replay
    assert receipt.block.kind is StaffUnavailabilityKind.PAUSED_SERVICE
    assert receipt.block.end_date is None
    assert receipt.aggregate_version == 1
    assert repository.commits == 1
    assert len(repository.events) == 1
    assert repository.receipt_reads == 3


def test_apply_rejects_stale_version_without_commit():
    repository = FakeRepository(version=2)
    workflow = _workflow(repository)
    intent = _long_leave_intent()
    preview = workflow.preview(StaffAvailabilityPreviewRequest(intent))
    request = _apply_request(intent, preview.preview_fingerprint, 1, "leave-stale")

    with pytest.raises(StaffAvailabilityDomainError) as caught:
        workflow.apply(request)

    assert caught.value.code is StaffAvailabilityErrorCode.STALE
    assert repository.commits == 0
    assert repository.rollbacks == 1


def test_same_idempotency_key_with_different_request_is_rejected():
    repository = FakeRepository()
    workflow = _workflow(repository)
    intent = _pause_intent()
    preview = workflow.preview(StaffAvailabilityPreviewRequest(intent))
    workflow.apply(_apply_request(intent, preview.preview_fingerprint, 0, "same-key"))
    changed = StaffAvailabilityIntent(
        StaffAvailabilityAction.CREATE_PAUSE,
        7,
        "不同原因",
        start_date=date(2026, 10, 1),
    )

    with pytest.raises(StaffAvailabilityDomainError) as caught:
        workflow.apply(_apply_request(changed, PreviewFingerprint("0" * 64), 0, "same-key"))

    assert caught.value.code is StaffAvailabilityErrorCode.IDEMPOTENCY_CONFLICT


def test_end_pause_closes_day_before_resume_and_keeps_history():
    existing = _pause_block()
    repository = FakeRepository(version=4, blocks=(existing,))
    workflow = _workflow(repository)
    intent = StaffAvailabilityIntent(
        StaffAvailabilityAction.END_PAUSE,
        7,
        "恢復接案",
        block_id=existing.block_id,
        resume_date=date(2026, 11, 10),
    )
    preview = workflow.preview(StaffAvailabilityPreviewRequest(intent))

    receipt = workflow.apply(_apply_request(intent, preview.preview_fingerprint, 4, "resume-001"))

    assert receipt.block.start_date == date(2026, 10, 1)
    assert receipt.block.end_date == date(2026, 11, 9)
    assert receipt.block.status is StaffAvailabilityBlockStatus.EFFECTIVE
    assert repository.events[0][1] == existing


def test_cancel_preserves_block_as_cancelled_audit_fact():
    existing = _pause_block()
    repository = FakeRepository(version=1, blocks=(existing,))
    workflow = _workflow(repository)
    intent = StaffAvailabilityIntent(
        StaffAvailabilityAction.CANCEL,
        7,
        "原排程取消",
        block_id=existing.block_id,
    )
    preview = workflow.preview(StaffAvailabilityPreviewRequest(intent))

    receipt = workflow.apply(_apply_request(intent, preview.preview_fingerprint, 1, "cancel-001"))

    assert receipt.block.status is StaffAvailabilityBlockStatus.CANCELLED
    assert repository.version == 2


def _workflow(repository):
    clock = FixedBusinessClock(datetime(2026, 8, 13, 9, 0, tzinfo=TAIPEI_TIME_ZONE))
    return StaffAvailabilityWorkflow(repository, clock)


def _apply_request(intent, fingerprint, version, key):
    return StaffAvailabilityApplyRequest(
        intent,
        ExpectedVersion(version),
        fingerprint,
        IdempotencyKey(key),
        ActorContext("admin:7"),
        CorrelationId(f"correlation-{key}"),
    )


def _long_leave_intent():
    return StaffAvailabilityIntent(
        StaffAvailabilityAction.CREATE_LONG_LEAVE,
        7,
        "照顧家人",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
    )


def _pause_intent():
    return StaffAvailabilityIntent(
        StaffAvailabilityAction.CREATE_PAUSE,
        7,
        "暫停接案",
        start_date=date(2026, 10, 1),
    )


def _pause_block():
    return StaffUnavailabilityBlock(
        91,
        7,
        StaffUnavailabilityKind.PAUSED_SERVICE,
        date(2026, 10, 1),
        None,
        StaffAvailabilityBlockStatus.EFFECTIVE,
        "暫停接案",
    )

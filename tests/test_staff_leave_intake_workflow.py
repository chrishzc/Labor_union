"""File: test_staff_leave_intake_workflow.py
Description: 驗證請假待辦 workflow 的重播與樂觀鎖定契約。"""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from domains.scheduling.staff_leave_intake import StaffLeaveRequestIntent, StaffLeaveRequestStatus
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.leave_substitution_linked_request_resolution import (
    LeaveSubstitutionLinkedRequestResolution,
)
from subsystems.scheduling.leave_substitution_workflow import LinkedLeaveRequestIntent
from subsystems.scheduling.staff_leave_intake_workflow import (
    ReviewStaffLeaveRequest,
    StaffLeaveIntakeWorkflow,
    StaffLeaveIntakeWorkflowError,
    StaffLeaveRequestSnapshot,
    ResolveStaffLeaveRequest,
    SubmitStaffLeaveRequest,
)


class FakeRepository:
    def __init__(self):
        self.snapshot = None
        self.by_key = {}

    def replay(self, key, fingerprint):
        found = self.by_key.get(key)
        if found and found.request_fingerprint != fingerprint:
            raise StaffLeaveIntakeWorkflowError("leave_request_idempotency_conflict")
        return found

    def create(self, command, fingerprint):
        self.snapshot = StaffLeaveRequestSnapshot(1, command.staff_id, command.line_user_id, StaffLeaveRequestStatus.PENDING, 1, fingerprint)
        self.by_key[command.idempotency_key] = self.snapshot
        return self.snapshot

    def load_for_update(self, request_id):
        return self.snapshot if self.snapshot and self.snapshot.request_id == request_id else None

    def load(self, request_id):
        return self.snapshot if self.snapshot and self.snapshot.request_id == request_id else None

    def replay_mutation(self, key, fingerprint):
        return self.replay(key, fingerprint)

    def transition(self, snapshot, target, reason, actor_id, key, fingerprint):
        self.snapshot = StaffLeaveRequestSnapshot(snapshot.request_id, snapshot.staff_id, snapshot.line_user_id, target, snapshot.version + 1, snapshot.request_fingerprint)
        self.by_key[key] = StaffLeaveRequestSnapshot(snapshot.request_id, snapshot.staff_id, snapshot.line_user_id, target, snapshot.version + 1, fingerprint)
        return self.snapshot

    def resolve(self, snapshot, receipt_key, key, fingerprint):
        return self.transition(snapshot, StaffLeaveRequestStatus.RESOLVED, receipt_key, "receipt", key, fingerprint)


def test_submit_exact_replay_returns_original_receipt_snapshot():
    workflow = StaffLeaveIntakeWorkflow(FakeRepository())
    command = SubmitStaffLeaveRequest(7, "U-7", StaffLeaveRequestIntent(date(2026, 8, 20), date(2026, 8, 21), "家務"), "leave-1")
    assert workflow.submit(command) == workflow.submit(command)


def test_preview_is_zero_write_and_apply_requires_the_same_opaque_fingerprint():
    repository = FakeRepository()
    workflow = StaffLeaveIntakeWorkflow(repository)
    command = SubmitStaffLeaveRequest(
        7,
        "U-7",
        StaffLeaveRequestIntent(date(2026, 8, 20), date(2026, 8, 21), "家務"),
        "leave-apply-1",
    )

    preview = workflow.preview(command)

    assert preview.can_apply is True
    assert repository.snapshot is None
    applied = workflow.apply(command, preview.preview_fingerprint)
    assert applied.status is StaffLeaveRequestStatus.PENDING

    changed = SubmitStaffLeaveRequest(
        7,
        "U-7",
        StaffLeaveRequestIntent(date(2026, 8, 22), date(2026, 8, 23), "家務"),
        "leave-apply-2",
    )
    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_request_preview_stale"):
        workflow.apply(changed, preview.preview_fingerprint)


def test_preview_rejects_invalid_date_range_without_repository_write():
    repository = FakeRepository()
    workflow = StaffLeaveIntakeWorkflow(repository)
    intent = SimpleNamespace(
        leave_start_date=date(2026, 8, 22),
        leave_end_date=date(2026, 8, 20),
        reason="",
    )
    command = SubmitStaffLeaveRequest(7, "U-7", intent, "leave-invalid")
    with pytest.raises(ValueError, match="leave_request_invalid"):
        workflow.preview(command)
    assert repository.snapshot is None


def test_review_requires_fresh_expected_version():
    workflow = StaffLeaveIntakeWorkflow(FakeRepository())
    submitted = workflow.submit(SubmitStaffLeaveRequest(7, "U-7", StaffLeaveRequestIntent(date(2026, 8, 20), date(2026, 8, 20)), "leave-1"))
    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_request_stale"):
        workflow.review(ReviewStaffLeaveRequest(submitted.request_id, 2, "accept", "受理", False, "admin", "review-stale"))
    assert workflow.review(ReviewStaffLeaveRequest(submitted.request_id, 1, "accept", "受理", False, "admin", "review-1")).status is StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING


def test_resolve_requires_accepted_request_and_replays_receipt_linkage():
    repository = FakeRepository()
    workflow = StaffLeaveIntakeWorkflow(repository)
    submitted = workflow.submit(SubmitStaffLeaveRequest(7, "U-7", StaffLeaveRequestIntent(date(2026, 8, 20), date(2026, 8, 20)), "leave-1"))
    accepted = workflow.review(ReviewStaffLeaveRequest(submitted.request_id, 1, "accept", "受理", False, "admin", "review-1"))
    command = ResolveStaffLeaveRequest(accepted.request_id, accepted.version, "batch-1", "resolve-1")
    assert workflow.resolve(command).status is StaffLeaveRequestStatus.RESOLVED
    assert workflow.resolve(command).status is StaffLeaveRequestStatus.RESOLVED


def test_staff_cannot_cancel_another_staff_request():
    workflow = StaffLeaveIntakeWorkflow(FakeRepository())
    submitted = workflow.submit(SubmitStaffLeaveRequest(7, "U-7", StaffLeaveRequestIntent(date(2026, 8, 20), date(2026, 8, 20)), "leave-1"))
    with pytest.raises(StaffLeaveIntakeWorkflowError, match="leave_request_not_found"):
        workflow.review(ReviewStaffLeaveRequest(submitted.request_id, 1, "cancel", "取消", True, "line:U-8", "cancel-1", 8))


class FakeLineDeliveryRepository:
    def __init__(self, failure=None):
        self.failure = failure
        self.requests = []

    def enqueue(self, request):
        if self.failure is not None:
            raise self.failure
        self.requests.append(request)


def test_linked_leave_resolution_uses_locked_snapshot_and_stable_notification():
    repository = FakeRepository()
    workflow = StaffLeaveIntakeWorkflow(repository)
    submitted = workflow.submit(SubmitStaffLeaveRequest(7, "U-7", StaffLeaveRequestIntent(date(2026, 8, 20), date(2026, 8, 20)), "leave-1"))
    accepted = workflow.review(ReviewStaffLeaveRequest(submitted.request_id, 1, "accept", "受理", False, "admin", "review-1"))
    line = FakeLineDeliveryRepository()
    resolver = LeaveSubstitutionLinkedRequestResolution(
        repository,
        line,
        FixedBusinessClock(datetime(2026, 8, 21, 9, tzinfo=TAIPEI_TIME_ZONE)),
    )

    locked = resolver.lock_for_apply(
        LinkedLeaveRequestIntent(accepted.request_id, accepted.version)
    )
    result = resolver.resolve_and_enqueue(
        locked,
        receipt_key="leave-batch-1",
        idempotency_key=IdempotencyKey("leave-batch-1"),
        correlation_id=CorrelationId("phase3b2-linked"),
    )

    assert result.status == StaffLeaveRequestStatus.RESOLVED.value
    assert result.receipt_key == "leave-batch-1"
    assert result.notification_intent == "enqueued"
    assert len(line.requests) == 1
    assert line.requests[0].scheduled_at == datetime(
        2026, 8, 21, 9, tzinfo=TAIPEI_TIME_ZONE
    )


def test_linked_leave_resolution_propagates_line_enqueue_failure():
    repository = FakeRepository()
    workflow = StaffLeaveIntakeWorkflow(repository)
    submitted = workflow.submit(SubmitStaffLeaveRequest(7, "U-7", StaffLeaveRequestIntent(date(2026, 8, 20), date(2026, 8, 20)), "leave-1"))
    accepted = workflow.review(ReviewStaffLeaveRequest(submitted.request_id, 1, "accept", "受理", False, "admin", "review-1"))
    resolver = LeaveSubstitutionLinkedRequestResolution(
        repository,
        FakeLineDeliveryRepository(RuntimeError("enqueue_failed")),
        FixedBusinessClock(datetime(2026, 8, 21, 9, tzinfo=TAIPEI_TIME_ZONE)),
    )

    with pytest.raises(RuntimeError, match="enqueue_failed"):
        resolver.resolve_and_enqueue(
            resolver.lock_for_apply(
                LinkedLeaveRequestIntent(accepted.request_id, accepted.version)
            ),
            receipt_key="leave-batch-1",
            idempotency_key=IdempotencyKey("leave-batch-1"),
            correlation_id=CorrelationId("phase3b2-linked"),
        )

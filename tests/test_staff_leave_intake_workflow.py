"""File: test_staff_leave_intake_workflow.py
Description: 驗證請假待辦 workflow 的重播與樂觀鎖定契約。"""

from datetime import date

import pytest

from domains.scheduling.staff_leave_intake import StaffLeaveRequestIntent, StaffLeaveRequestStatus
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

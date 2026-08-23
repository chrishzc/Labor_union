"""File: staff_leave_intake_workflow.py
Description: 編排月嫂請假待辦的冪等提交與版本化管理操作。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.scheduling.staff_leave_intake import (
    StaffLeaveRequestIntent,
    StaffLeaveRequestStatus,
    transition_request,
)
from shared_kernel.fingerprints import fingerprint_payload


@dataclass(frozen=True, slots=True)
class StaffLeaveRequestSnapshot:
    request_id: int
    staff_id: int
    line_user_id: str
    status: StaffLeaveRequestStatus
    version: int
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class SubmitStaffLeaveRequest:
    staff_id: int
    line_user_id: str
    intent: StaffLeaveRequestIntent
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ReviewStaffLeaveRequest:
    request_id: int
    expected_version: int
    action: str
    reason: str
    actor_is_staff: bool
    actor_id: str
    idempotency_key: str
    actor_staff_id: int | None = None


@dataclass(frozen=True, slots=True)
class ResolveStaffLeaveRequest:
    request_id: int
    expected_version: int
    leave_substitution_receipt_key: str
    idempotency_key: str


class StaffLeaveIntakeRepository(Protocol):
    def replay(self, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot | None: ...
    def create(self, command: SubmitStaffLeaveRequest, fingerprint: str) -> StaffLeaveRequestSnapshot: ...
    def load_for_update(self, request_id: int) -> StaffLeaveRequestSnapshot | None: ...
    def load(self, request_id: int) -> StaffLeaveRequestSnapshot | None: ...
    def replay_mutation(self, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot | None: ...
    def transition(self, snapshot: StaffLeaveRequestSnapshot, target: StaffLeaveRequestStatus, reason: str, actor_id: str, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot: ...
    def resolve(self, snapshot: StaffLeaveRequestSnapshot, receipt_key: str, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot: ...


class StaffLeaveIntakeWorkflowError(ValueError):
    pass


class StaffLeaveIntakeWorkflow:
    def __init__(self, repository: StaffLeaveIntakeRepository) -> None:
        self._repository = repository

    def submit(self, command: SubmitStaffLeaveRequest) -> StaffLeaveRequestSnapshot:
        fingerprint = _submit_fingerprint(command)
        replay = self._repository.replay(command.idempotency_key, fingerprint)
        if replay is not None:
            return replay
        return self._repository.create(command, fingerprint)

    def review(self, command: ReviewStaffLeaveRequest) -> StaffLeaveRequestSnapshot:
        fingerprint = _review_fingerprint(command)
        replay = self._repository.replay_mutation(command.idempotency_key, fingerprint)
        if replay is not None:
            return replay
        snapshot = self._repository.load_for_update(command.request_id)
        if snapshot is None:
            raise StaffLeaveIntakeWorkflowError("leave_request_not_found")
        if snapshot.version != command.expected_version:
            raise StaffLeaveIntakeWorkflowError("leave_request_stale")
        if command.actor_is_staff and command.actor_staff_id != snapshot.staff_id:
            raise StaffLeaveIntakeWorkflowError("leave_request_not_found")
        try:
            target = transition_request(
                snapshot.status,
                action=command.action,
                actor_is_staff=command.actor_is_staff,
                reason=command.reason,
            )
        except ValueError as error:
            raise StaffLeaveIntakeWorkflowError(str(error)) from error
        return self._repository.transition(
            snapshot, target, command.reason.strip(), command.actor_id,
            command.idempotency_key, fingerprint,
        )

    def resolve(self, command: ResolveStaffLeaveRequest) -> StaffLeaveRequestSnapshot:
        fingerprint = _resolve_fingerprint(command)
        replay = self._repository.replay_mutation(command.idempotency_key, fingerprint)
        if replay is not None:
            return replay
        snapshot = self._repository.load_for_update(command.request_id)
        if snapshot is None:
            raise StaffLeaveIntakeWorkflowError("leave_request_not_found")
        if snapshot.version != command.expected_version:
            raise StaffLeaveIntakeWorkflowError("leave_request_stale")
        try:
            transition_request(snapshot.status, action="resolve", actor_is_staff=False)
        except ValueError as error:
            raise StaffLeaveIntakeWorkflowError("leave_request_not_resolvable") from error
        try:
            return self._repository.resolve(
                snapshot, command.leave_substitution_receipt_key,
                command.idempotency_key, fingerprint,
            )
        except ValueError as error:
            code = str(error)
            if code in {"leave_request_receipt_conflict", "leave_request_stale"}:
                raise StaffLeaveIntakeWorkflowError(code) from error
            raise


def _submit_fingerprint(command: SubmitStaffLeaveRequest) -> str:
    intent = command.intent
    return fingerprint_payload(
        {
            "family": "scheduling-staff-leave-intake",
            "staff_id": command.staff_id,
            "line_user_id": command.line_user_id,
            "leave_start_date": intent.leave_start_date.isoformat(),
            "leave_end_date": intent.leave_end_date.isoformat(),
            "reason": intent.reason.strip(),
        }
    ).value


def _review_fingerprint(command: ReviewStaffLeaveRequest) -> str:
    return fingerprint_payload({
        "family": "scheduling-staff-leave-review",
        "request_id": command.request_id,
        "expected_version": command.expected_version,
        "action": command.action,
        "reason": command.reason.strip(),
        "actor_id": command.actor_id,
        "actor_staff_id": command.actor_staff_id,
    }).value


def _resolve_fingerprint(command: ResolveStaffLeaveRequest) -> str:
    return fingerprint_payload({
        "family": "scheduling-staff-leave-resolve",
        "request_id": command.request_id,
        "expected_version": command.expected_version,
        "leave_substitution_receipt_key": command.leave_substitution_receipt_key,
    }).value

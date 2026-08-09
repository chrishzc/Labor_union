"""Canonical human-authorized LINE identity review decision workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identity_binding import LineIdentityBindingStatus, LineIdentityClaim
from domains.line.review import (
    LineReviewDecision,
    LineReviewSnapshot,
    LineReviewStatus,
    LineReviewType,
    build_review_decision_candidate,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ExpectedVersion, IdempotencyKey, IdempotencyReceipt
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort
from subsystems.line.review_contracts import (
    ApplyLineReviewDecisionResult,
    DecideLineReviewCommand,
    LineReviewCommandOutcome,
    LineReviewListQuery,
    LineReviewQueueSummary,
)


class LineReviewNotFoundError(LookupError):
    pass


class LineReviewDataConflictError(RuntimeError):
    pass


class LineIdentityReviewApplication:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        now: Callable[[], datetime],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def get(self, request_id):
        with self._unit_of_work_factory() as unit_of_work:
            snapshot = unit_of_work.reviews.get(request_id)
        if snapshot is None:
            raise LineReviewNotFoundError("找不到 LINE 身分審核申請")
        return snapshot

    def list(self, query: LineReviewListQuery):
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.reviews.list(query)

    def summary(self, stale_hours: int) -> LineReviewQueueSummary:
        if stale_hours < 1 or stale_hours > 720:
            raise ValueError("LINE review stale hours must be between 1 and 720")
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.reviews.summary(stale_hours)

    # Kept cohesive to show every side effect inside the caller-owned review transaction.
    def decide(self, command: DecideLineReviewCommand) -> ApplyLineReviewDecisionResult:
        require_line_capability(command.actor, LineCapability.IDENTITY_REVIEW)
        with self._unit_of_work_factory() as unit_of_work:
            existing = _existing_decision_result(unit_of_work, command)
            if existing is not None:
                unit_of_work.commit()
                return existing
            snapshot = unit_of_work.reviews.get(command.request_id)
            if snapshot is None:
                raise LineReviewNotFoundError("找不到 LINE 身分審核申請")
            candidate = build_review_decision_candidate(
                snapshot,
                command.decision,
                expected_version=command.expected_version,
                actor=command.actor,
                reason=command.reason,
            )
            if command.decision is LineReviewDecision.APPROVE:
                _apply_approval(unit_of_work, snapshot, command)
            else:
                _apply_rejection(unit_of_work, snapshot, command)
            unit_of_work.reviews.decide(command, candidate)
            reviewed_at = self._now()
            resulting = _resulting_snapshot(snapshot, candidate, reviewed_at)
            _append_decision_facts(unit_of_work, command, candidate, resulting)
            _enqueue_decision_message(unit_of_work, resulting, command, reviewed_at)
            unit_of_work.commit()
        return ApplyLineReviewDecisionResult(LineReviewCommandOutcome.CREATED, resulting)


def _existing_decision_result(unit_of_work, command):
    receipt = unit_of_work.receipts.get(command.idempotency_key)
    if receipt is None:
        return None
    snapshot = unit_of_work.reviews.get(command.request_id)
    if snapshot is None:
        raise LineReviewNotFoundError("找不到 LINE 身分審核申請")
    expected = _command_fingerprint(command, snapshot.review_type)
    if receipt.payload_fingerprint != expected:
        raise LineReviewDataConflictError("LINE 審核 idempotency key 已用於其他操作")
    return ApplyLineReviewDecisionResult(LineReviewCommandOutcome.EXISTING, snapshot)


# Kept cohesive so old revoke, owner update, and new bind preserve their lock order.
def _apply_approval(unit_of_work, snapshot, command):
    _require_review_identity(snapshot)
    old_binding = unit_of_work.identities.get_by_subject(
        snapshot.subject_type,
        snapshot.subject_reference,
    )
    old_line_user_id = (
        old_binding.line_user_id
        if old_binding and old_binding.status is LineIdentityBindingStatus.BOUND
        else None
    )
    if old_line_user_id is not None and old_line_user_id != snapshot.line_user_id:
        unit_of_work.identities.revoke(
            old_line_user_id,
            old_binding.version,
            command.actor.actor_id,
            _derived_key(command, "revoke-old"),
            command.correlation_id.value,
        )
    _bind_owner_projection(unit_of_work, snapshot, old_line_user_id)
    _bind_review_claim(unit_of_work, snapshot, command)


def _bind_owner_projection(unit_of_work, snapshot, old_line_user_id):
    if snapshot.review_type is LineReviewType.CLIENT_REBIND:
        unit_of_work.customers.bind_customer(
            snapshot.subject_reference,
            snapshot.line_user_id,
            old_line_user_id,
        )
        return
    if snapshot.review_type is LineReviewType.STAFF_VERIFICATION:
        unit_of_work.staff.bind_staff(
            snapshot.subject_reference,
            snapshot.line_user_id,
            old_line_user_id,
        )
        return
    unit_of_work.admins.bind_admin(
        snapshot.subject_reference,
        snapshot.line_user_id,
        old_line_user_id,
    )


# Kept cohesive because the optimistic-version branch is one binding invariant.
def _bind_review_claim(unit_of_work, snapshot, command):
    claim = LineIdentityClaim(
        snapshot.line_user_id,
        snapshot.subject_type,
        snapshot.subject_reference,
    )
    current = unit_of_work.identities.get(snapshot.line_user_id)
    if current and current.status is LineIdentityBindingStatus.BOUND:
        if current.subject_type is claim.subject_type and current.subject_reference == claim.subject_reference:
            return current
        raise LineReviewDataConflictError("新的 LINE 身分已被其他主體占用")
    if current and current.status is LineIdentityBindingStatus.REVOKED:
        current = unit_of_work.identities.save_claim(claim, current.version)
    expected_version = current.version if current else ExpectedVersion(0)
    return unit_of_work.identities.bind(
        claim,
        expected_version,
        command.actor.actor_id,
        _derived_key(command, "bind-new"),
        command.correlation_id.value,
    )


def _apply_rejection(unit_of_work, snapshot, command):
    _require_review_identity(snapshot)
    current = unit_of_work.identities.get(snapshot.line_user_id)
    if not current or current.status is not LineIdentityBindingStatus.PENDING_REVIEW:
        return
    if current.subject_type is not snapshot.subject_type:
        return
    if current.subject_reference != snapshot.subject_reference:
        return
    unit_of_work.identities.revoke(
        current.line_user_id,
        current.version,
        command.actor.actor_id,
        _derived_key(command, "reject-claim"),
        command.correlation_id.value,
    )


def _append_decision_facts(unit_of_work, command, candidate, snapshot):
    unit_of_work.receipts.append(
        IdempotencyReceipt(
            command.idempotency_key,
            candidate.fingerprint,
            f"line-review:{command.request_id.value}:{snapshot.status.value}",
        )
    )
    unit_of_work.audit.append(
        LineAuditIntent(
            f"line.identity.review.{snapshot.status.value}",
            command.actor.actor_id,
            "line_review_request",
            str(command.request_id.value),
        )
    )


def _enqueue_decision_message(unit_of_work, snapshot, command, scheduled_at):
    approved = snapshot.status is LineReviewStatus.APPROVED
    text = "您的 LINE 身分申請已審核通過。" if approved else "您的 LINE 身分申請未通過，請聯絡工會人員。"
    request = LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, snapshot.line_user_id),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": text}),
        scheduled_at,
        _derived_key(command, "notification"),
        command.correlation_id,
        "line_review_request",
        str(command.request_id.value),
    )
    unit_of_work.delivery_tasks.enqueue(request)


def _resulting_snapshot(snapshot, candidate, reviewed_at):
    return LineReviewSnapshot(
        snapshot.request_id,
        snapshot.review_type,
        candidate.after_status,
        candidate.resulting_version,
        snapshot.line_user_id,
        snapshot.subject_type,
        snapshot.subject_reference,
        snapshot.request_fingerprint,
        snapshot.evidence_json,
        snapshot.assigned_admin_id,
        snapshot.assigned_at,
        snapshot.due_at,
        snapshot.reassignment_count,
        candidate.actor.actor_id,
        candidate.reason,
        reviewed_at,
        snapshot.created_at,
    )


def _require_review_identity(snapshot):
    if snapshot.line_user_id is None:
        raise LineReviewDataConflictError("LINE 審核缺少使用者身分")
    if snapshot.subject_type is None or snapshot.subject_reference is None:
        raise LineReviewDataConflictError("LINE 審核缺少綁定主體")


def _command_fingerprint(command, review_type):
    return fingerprint_payload(
        {
            "request_id": command.request_id.value,
            "review_type": review_type.value,
            "decision": command.decision.value,
            "expected_version": command.expected_version.value,
            "actor_id": command.actor.actor_id,
            "reason": command.reason,
        }
    )


def _derived_key(command, suffix):
    digest = fingerprint_payload(
        {"command_key": command.idempotency_key.value, "suffix": suffix}
    )
    return IdempotencyKey(f"line-review:{digest.value}")


__all__ = [
    "LineIdentityReviewApplication",
    "LineReviewDataConflictError",
    "LineReviewNotFoundError",
]

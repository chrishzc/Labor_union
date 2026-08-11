"""Canonical LIFF identity preview and apply workflows for all LINE actors."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineIdentityFlowId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingStatus,
    LineIdentityClaim,
)
from domains.line.identity_flow import (
    LineIdentityFlowPurpose,
    validate_identity_flow,
)
from domains.line.review import LineReviewType
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.identity_contracts import (
    AdminCredentialProof,
    CustomerIdentityProof,
    LineIdentityApplyResult,
    LineIdentityApplyStatus,
    LineIdentityCandidate,
    LineIdentityPreview,
    LineIdentityPreviewStatus,
    OpenLineIdentityFlowCommand,
    StaffIdentityProof,
)
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort
from subsystems.line.review_contracts import CreateLineReviewCommand
from subsystems.line.rich_menu_binding import schedule_rich_menu_binding


class LineIdentityNotFoundError(LookupError):
    pass


class LineIdentityConflictError(RuntimeError):
    pass


class LineIdentityAuthenticationError(PermissionError):
    pass


class LineIdentityApplication:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        now: Callable[[], datetime],
        *,
        flow_lifetime: timedelta = timedelta(minutes=15),
        maximum_admin_attempts: int = 5,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now
        self._flow_lifetime = flow_lifetime
        self._maximum_admin_attempts = maximum_admin_attempts

    def open_flow(self, purpose, line_user_id, idempotency_key, correlation_id):
        command = OpenLineIdentityFlowCommand(
            purpose,
            line_user_id,
            self._now() + self._flow_lifetime,
            idempotency_key,
            correlation_id,
        )
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.identity_flows.open(command)
            unit_of_work.commit()
        return result

    def preview_customer(self, flow_id, line_user_id, proof):
        with self._unit_of_work_factory() as unit_of_work:
            _require_flow(
                unit_of_work,
                flow_id,
                LineIdentityFlowPurpose.CUSTOMER_BINDING,
                line_user_id,
                self._now(),
            )
            candidate = unit_of_work.customers.resolve_customer(proof)
            return _customer_preview(unit_of_work, line_user_id, candidate)

    # Kept cohesive so flow consumption and customer binding/review stay one transaction.
    def apply_customer(self, flow_id, line_user_id, proof, correlation_id):
        with self._unit_of_work_factory() as unit_of_work:
            _require_flow(
                unit_of_work,
                flow_id,
                LineIdentityFlowPurpose.CUSTOMER_BINDING,
                line_user_id,
                self._now(),
            )
            candidate = unit_of_work.customers.resolve_customer(proof)
            if candidate is None:
                raise LineIdentityNotFoundError("找不到相符的客戶資料")
            preview = _customer_preview(unit_of_work, line_user_id, candidate)
            unit_of_work.identity_flows.consume(
                flow_id,
                LineIdentityFlowPurpose.CUSTOMER_BINDING,
                line_user_id,
                self._now(),
            )
            result = self._apply_customer_candidate(
                unit_of_work,
                flow_id,
                preview,
                proof,
                correlation_id,
            )
            unit_of_work.commit()
        return result

    def preview_staff(self, flow_id, line_user_id, proof):
        with self._unit_of_work_factory() as unit_of_work:
            _require_flow(
                unit_of_work,
                flow_id,
                LineIdentityFlowPurpose.STAFF_VERIFICATION,
                line_user_id,
                self._now(),
            )
            candidate = unit_of_work.staff.resolve_staff(proof)
            return _staff_preview(unit_of_work, line_user_id, candidate)

    # Kept cohesive so the one-use flow and manual-review claim cannot diverge.
    def apply_staff(self, flow_id, line_user_id, proof, correlation_id):
        with self._unit_of_work_factory() as unit_of_work:
            _require_flow(
                unit_of_work,
                flow_id,
                LineIdentityFlowPurpose.STAFF_VERIFICATION,
                line_user_id,
                self._now(),
            )
            candidate = unit_of_work.staff.resolve_staff(proof)
            if candidate is None:
                raise LineIdentityNotFoundError("找不到相符的月嫂資料")
            preview = _staff_preview(unit_of_work, line_user_id, candidate)
            unit_of_work.identity_flows.consume(
                flow_id,
                LineIdentityFlowPurpose.STAFF_VERIFICATION,
                line_user_id,
                self._now(),
            )
            result = _apply_staff_candidate(
                unit_of_work,
                flow_id,
                preview,
                proof,
                correlation_id,
            )
            _enqueue_result_message(unit_of_work, result, correlation_id, self._now())
            unit_of_work.commit()
        return result

    # Kept cohesive so authenticated admin binding and its notification commit together.
    def apply_admin(self, flow_id, line_user_id, proof, correlation_id):
        candidate = self._authenticated_admin_candidate(flow_id, line_user_id, proof)
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.identity_flows.consume(
                flow_id,
                LineIdentityFlowPurpose.ADMIN_BINDING,
                line_user_id,
                self._now(),
            )
            if candidate.currently_bound_line_user_id not in {None, line_user_id}:
                result = _create_review(
                    unit_of_work,
                    flow_id,
                    line_user_id,
                    candidate,
                    LineReviewType.ADMIN_BINDING,
                    fingerprint_payload({"admin_id": candidate.subject_reference}).value,
                    correlation_id,
                )
            else:
                unit_of_work.admins.bind_admin(
                    candidate.subject_reference,
                    line_user_id,
                    candidate.currently_bound_line_user_id,
                )
                result = _bind_result(
                    unit_of_work,
                    line_user_id,
                    candidate,
                    correlation_id,
                )
            _enqueue_result_message(unit_of_work, result, correlation_id, self._now())
            unit_of_work.commit()
        return result

    def _authenticated_admin_candidate(self, flow_id, line_user_id, proof):
        with self._unit_of_work_factory() as unit_of_work:
            _require_flow(
                unit_of_work,
                flow_id,
                LineIdentityFlowPurpose.ADMIN_BINDING,
                line_user_id,
                self._now(),
            )
            candidate = unit_of_work.admins.authenticate_admin(proof)
            if candidate is None:
                unit_of_work.identity_flows.record_failed_attempt(
                    flow_id,
                    self._maximum_admin_attempts,
                )
            unit_of_work.commit()
        if candidate is None:
            raise LineIdentityAuthenticationError("工會人員帳號或密碼錯誤")
        return candidate

    # Kept cohesive so direct bind and review creation share one explicit decision boundary.
    def _apply_customer_candidate(
        self,
        unit_of_work,
        flow_id,
        preview,
        proof,
        correlation_id,
    ):
        candidate = preview.candidate
        if candidate is None:
            raise LineIdentityNotFoundError("找不到相符的客戶資料")
        if preview.status is LineIdentityPreviewStatus.REQUIRES_REVIEW:
            result = _create_review(
                unit_of_work,
                flow_id,
                preview.line_user_id,
                candidate,
                LineReviewType.CLIENT_REBIND,
                _customer_proof_fingerprint(proof).value,
                correlation_id,
            )
        else:
            unit_of_work.customers.bind_customer(
                candidate.subject_reference,
                preview.line_user_id,
                candidate.currently_bound_line_user_id,
            )
            result = _bind_result(
                unit_of_work,
                preview.line_user_id,
                candidate,
                correlation_id,
            )
        _enqueue_result_message(unit_of_work, result, correlation_id, self._now())
        return result


def _customer_preview(unit_of_work, line_user_id, candidate):
    binding = unit_of_work.identities.get(line_user_id)
    version = binding.version if binding else ExpectedVersion(0)
    if candidate is None:
        return LineIdentityPreview(LineIdentityPreviewStatus.NOT_FOUND, line_user_id, None, version)
    if candidate.currently_bound_line_user_id == line_user_id:
        status = LineIdentityPreviewStatus.ALREADY_BOUND
    elif candidate.currently_bound_line_user_id is not None:
        status = LineIdentityPreviewStatus.REQUIRES_REVIEW
    elif binding and binding.status is LineIdentityBindingStatus.BOUND:
        status = LineIdentityPreviewStatus.REQUIRES_REVIEW
    else:
        status = LineIdentityPreviewStatus.MATCHED
    return LineIdentityPreview(status, line_user_id, candidate, version)


def _staff_preview(unit_of_work, line_user_id, candidate):
    binding = unit_of_work.identities.get(line_user_id)
    version = binding.version if binding else ExpectedVersion(0)
    if candidate is None:
        status = LineIdentityPreviewStatus.NOT_FOUND
    elif candidate.currently_bound_line_user_id == line_user_id:
        status = LineIdentityPreviewStatus.ALREADY_BOUND
    else:
        status = LineIdentityPreviewStatus.REQUIRES_REVIEW
    return LineIdentityPreview(status, line_user_id, candidate, version)


def _apply_staff_candidate(unit_of_work, flow_id, preview, proof, correlation_id):
    candidate = preview.candidate
    if candidate is None:
        raise LineIdentityNotFoundError("找不到相符的月嫂資料")
    if preview.status is LineIdentityPreviewStatus.ALREADY_BOUND:
        return _bind_result(unit_of_work, preview.line_user_id, candidate, correlation_id)
    result = _create_review(
        unit_of_work,
        flow_id,
        preview.line_user_id,
        candidate,
        LineReviewType.STAFF_VERIFICATION,
        _staff_proof_fingerprint(proof).value,
        correlation_id,
    )
    _save_pending_claim_if_available(unit_of_work, preview.line_user_id, candidate)
    return result


def _require_flow(unit_of_work, flow_id, purpose, line_user_id, now):
    snapshot = unit_of_work.identity_flows.get(flow_id)
    if snapshot is None:
        raise LineIdentityNotFoundError("找不到 LINE 身分驗證流程")
    validate_identity_flow(snapshot, purpose=purpose, line_user_id=line_user_id, now=now)
    return snapshot


# Kept cohesive so the canonical binding, audit fact, and typed result cannot drift.
def _bind_result(unit_of_work, line_user_id, candidate, correlation_id):
    claim = LineIdentityClaim(line_user_id, candidate.subject_type, candidate.subject_reference)
    snapshot = _bind_claim(unit_of_work, claim, correlation_id)
    unit_of_work.audit.append(
        LineAuditIntent(
            "line.identity.bound",
            f"line-user:{line_user_id.value}"[:100],
            "line_identity_binding",
            line_user_id.value,
        )
    )
    schedule_rich_menu_binding(unit_of_work, snapshot)
    status = (
        LineIdentityApplyStatus.EXISTING
        if snapshot.status is LineIdentityBindingStatus.BOUND
        and candidate.currently_bound_line_user_id == line_user_id
        else LineIdentityApplyStatus.BOUND
    )
    return LineIdentityApplyResult(
        status,
        line_user_id,
        candidate.subject_type,
        candidate.subject_reference,
    )


def _bind_claim(unit_of_work, claim, correlation_id):
    current = unit_of_work.identities.get(claim.line_user_id)
    if current and current.status is LineIdentityBindingStatus.BOUND:
        if current.subject_type is claim.subject_type and current.subject_reference == claim.subject_reference:
            return current
        raise LineIdentityConflictError("LINE 帳號已綁定其他身分")
    if current and current.status is LineIdentityBindingStatus.REVOKED:
        current = unit_of_work.identities.save_claim(claim, current.version)
    expected = current.version if current else ExpectedVersion(0)
    return unit_of_work.identities.bind(
        claim,
        expected,
        f"line-user:{claim.line_user_id.value}"[:100],
        IdempotencyKey(f"identity-bind:{claim.fingerprint.value}"),
        correlation_id.value,
    )


def _save_pending_claim_if_available(unit_of_work, line_user_id, candidate):
    if unit_of_work.identities.get_by_subject(candidate.subject_type, candidate.subject_reference):
        return
    current = unit_of_work.identities.get(line_user_id)
    if current and current.status not in {
        LineIdentityBindingStatus.UNBOUND,
        LineIdentityBindingStatus.REVOKED,
    }:
        return
    claim = LineIdentityClaim(line_user_id, candidate.subject_type, candidate.subject_reference)
    unit_of_work.identities.save_claim(
        claim,
        current.version if current else ExpectedVersion(0),
    )


# Kept cohesive so review identity, evidence fingerprint, and idempotency remain aligned.
def _create_review(
    unit_of_work,
    flow_id,
    line_user_id,
    candidate,
    review_type,
    proof_fingerprint,
    correlation_id,
):
    request_fingerprint = fingerprint_payload(
        {
            "flow_id": flow_id.value,
            "line_user_id": line_user_id.value,
            "review_type": review_type.value,
            "subject_type": candidate.subject_type.value,
            "subject_reference": candidate.subject_reference,
            "proof_fingerprint": proof_fingerprint,
        }
    )
    evidence_json = canonical_line_payload_json(
        {
            "proof_fingerprint": proof_fingerprint,
            "subject_reference": candidate.subject_reference,
            "subject_type": candidate.subject_type.value,
        }
    )
    created = unit_of_work.reviews.create(
        CreateLineReviewCommand(
            review_type,
            line_user_id,
            candidate.subject_type,
            candidate.subject_reference,
            request_fingerprint,
            evidence_json,
            flow_id,
            IdempotencyKey(f"review-create:{flow_id.value}"),
            correlation_id,
        )
    )
    return LineIdentityApplyResult(
        LineIdentityApplyStatus.PENDING_REVIEW,
        line_user_id,
        candidate.subject_type,
        candidate.subject_reference,
        created.snapshot.request_id,
    )


# Kept cohesive so the stable delivery key covers every semantic result field.
def _enqueue_result_message(unit_of_work, result, correlation_id, scheduled_at):
    pending = result.status is LineIdentityApplyStatus.PENDING_REVIEW
    text = (
        "您的身分申請已送出，請等待工會人員確認。"
        if pending
        else "您的 LINE 身分已完成綁定。"
    )
    key_fingerprint = fingerprint_payload(
        {
            "line_user_id": result.line_user_id.value,
            "subject_type": result.subject_type.value,
            "subject_reference": result.subject_reference,
            "status": result.status.value,
            "review_request_id": (
                result.review_request_id.value if result.review_request_id else None
            ),
        }
    )
    request = LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, result.line_user_id),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": text}),
        scheduled_at,
        IdempotencyKey(f"identity-result:{key_fingerprint.value}"),
        correlation_id,
        "line_identity",
        f"{result.subject_type.value}:{result.subject_reference}",
    )
    unit_of_work.delivery_tasks.enqueue(request)


def _customer_proof_fingerprint(proof):
    return fingerprint_payload(
        {
            "name": proof.name.strip(),
            "phone": proof.phone.replace(" ", "").replace("-", ""),
        }
    )


def _staff_proof_fingerprint(proof):
    return fingerprint_payload(
        {
            "name": proof.name.strip(),
            "identity_card": proof.identity_card.strip().upper(),
            "birthday": proof.birthday.isoformat(),
        }
    )


__all__ = [
    "LineIdentityApplication",
    "LineIdentityAuthenticationError",
    "LineIdentityConflictError",
    "LineIdentityNotFoundError",
]

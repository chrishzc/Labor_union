"""
File: identity_application.py
Description: 編排 verified LINE platform root、身分流程、原子登記、owner projection 與 durable intent。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable

from domains.line.canonical_payload import canonical_line_payload_json
from domains.case_import.provisional_registration import (
    ProvisionalRegistrationIntent,
    build_provisional_registration_candidate,
)
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
    advance_binding_failure_streak,
)
from domains.customer_service.escalation import MaskedContext, TriggerCode
from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.identity_flow import (
    LineIdentityFlowPurpose,
    validate_identity_flow,
)
from domains.line.review import LineReviewType
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.customer_service.escalation_application import HumanEscalationApplication
from subsystems.customer_service.escalation_contracts import CreateHumanEscalation
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
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
from subsystems.line.rich_menu_binding import schedule_resolved_identity_menu
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflict,
    ProvisionalRegistrationConflictError,
    ProvisionalRegistrationPreview,
    ProvisionalRegistrationReceipt,
)


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
            unit_of_work.platform_users.ensure_verified_user(line_user_id)
            result = unit_of_work.identity_flows.open(command)
            unit_of_work.commit()
        return result

    def validate_flow(self, flow_id, purpose, line_user_id):
        with self._unit_of_work_factory() as unit_of_work:
            return _require_flow(
                unit_of_work,
                flow_id,
                purpose,
                line_user_id,
                self._now(),
            )

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
            preview = _customer_preview(unit_of_work, line_user_id, candidate)
            return _with_identity_preview_fingerprint(
                "customer",
                flow_id,
                _customer_proof_fingerprint(proof),
                preview,
            )

    # Kept cohesive so flow consumption and customer binding/review stay one transaction.
    def apply_customer(
        self,
        flow_id,
        line_user_id,
        proof,
        expected_version,
        preview_fingerprint,
        correlation_id,
    ):
        try:
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
                preview = _with_identity_preview_fingerprint(
                    "customer",
                    flow_id,
                    _customer_proof_fingerprint(proof),
                    _customer_preview(unit_of_work, line_user_id, candidate),
                )
                _require_identity_preview(preview, expected_version, preview_fingerprint)
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
                if result.status is not LineIdentityApplyStatus.PENDING_REVIEW:
                    unit_of_work.identities.reset_failure_streak(
                        line_user_id,
                        flow_id,
                    )
                unit_of_work.commit()
        except LineIdentityNotFoundError:
            self._record_binding_failure(
                flow_id,
                line_user_id,
                LineBindingSubjectType.CUSTOMER,
                _customer_proof_fingerprint(proof).value,
                correlation_id,
            )
            raise
        return result

    def preview_registration(
        self,
        intent: ProvisionalRegistrationIntent,
        line_user_id: LineUserId,
        flow_id: LineIdentityFlowId | None,
    ) -> ProvisionalRegistrationPreview:
        if intent.line_user_id.strip() != line_user_id.value:
            raise LineIdentityConflictError("registration_line_identity_mismatch")
        candidate = build_provisional_registration_candidate(intent)
        with self._unit_of_work_factory() as unit_of_work:
            if flow_id is not None:
                _require_flow(
                    unit_of_work,
                    flow_id,
                    LineIdentityFlowPurpose.CUSTOMER_BINDING,
                    line_user_id,
                    self._now(),
                )
            binding = unit_of_work.identities.get(
                line_user_id,
                LineBindingSubjectType.CUSTOMER,
            )
        expected_version = binding.version if binding else ExpectedVersion(0)
        return ProvisionalRegistrationPreview(
            "ready",
            expected_version,
            candidate.payload_fingerprint,
            _registration_preview_fingerprint(
                candidate.payload_fingerprint,
                line_user_id,
                flow_id,
                expected_version,
            ),
        )

    # Kept cohesive so provisional roots, verified binding, owner projection, and
    # durable intents share exactly one outer UoW and one commit owner.
    def apply_registration(
        self,
        intent: ProvisionalRegistrationIntent,
        line_user_id: LineUserId,
        flow_id: LineIdentityFlowId | None,
        expected_binding_version: ExpectedVersion,
        preview_fingerprint: PreviewFingerprint,
        correlation_id: CorrelationId,
    ) -> tuple[ProvisionalRegistrationReceipt, LineIdentityApplyResult]:
        if intent.line_user_id.strip() != line_user_id.value:
            raise LineIdentityConflictError("registration_line_identity_mismatch")
        candidate = build_provisional_registration_candidate(intent)
        with self._unit_of_work_factory() as unit_of_work:
            if flow_id is not None:
                _require_flow(
                    unit_of_work,
                    flow_id,
                    LineIdentityFlowPurpose.CUSTOMER_BINDING,
                    line_user_id,
                    self._now(),
                )
            binding = unit_of_work.identities.get(
                line_user_id,
                LineBindingSubjectType.CUSTOMER,
            )
            current_binding_version = binding.version if binding else ExpectedVersion(0)
            if current_binding_version != expected_binding_version:
                raise LineIdentityConflictError("registration_preview_stale")
            current_preview_fingerprint = _registration_preview_fingerprint(
                candidate.payload_fingerprint,
                line_user_id,
                flow_id,
                current_binding_version,
            )
            if current_preview_fingerprint != preview_fingerprint:
                raise LineIdentityConflictError("registration_preview_stale")
            outcome = unit_of_work.provisional_registrations.apply(candidate)
            if isinstance(outcome, ProvisionalRegistrationConflict):
                raise ProvisionalRegistrationConflictError("registration_conflict")
            if not isinstance(outcome, ProvisionalRegistrationReceipt):
                raise RuntimeError("registration_receipt_invalid")
            # Case Import is the owner of provisional registration and creates
            # the customer root in this same UoW.  Registration must therefore
            # not perform a proof lookup that assumes a pre-existing customer;
            # the receipt's client ID is the fresh root reference.
            current_binding = unit_of_work.identities.get(
                line_user_id,
                LineBindingSubjectType.CUSTOMER,
            )
            currently_bound = None
            if (
                current_binding
                and current_binding.status is LineIdentityBindingStatus.BOUND
                and current_binding.subject_type is LineBindingSubjectType.CUSTOMER
                and current_binding.subject_reference == str(outcome.client_id)
            ):
                currently_bound = line_user_id
            customer = LineIdentityCandidate(
                LineBindingSubjectType.CUSTOMER,
                str(outcome.client_id),
                currently_bound,
            )
            preview = _customer_preview(unit_of_work, line_user_id, customer)
            if flow_id is not None:
                unit_of_work.identity_flows.consume(
                    flow_id,
                    LineIdentityFlowPurpose.CUSTOMER_BINDING,
                    line_user_id,
                    self._now(),
                )
            result = self._apply_customer_candidate(
                unit_of_work,
                flow_id or LineIdentityFlowId(f"registration:{outcome.registration_id}"),
                preview,
                CustomerIdentityProof(intent.name.strip(), intent.phone.strip()),
                correlation_id,
                owner_projection_line_user_id=(line_user_id if not outcome.replayed else None),
            )
            unit_of_work.commit()
        return outcome, result

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
            preview = _staff_preview(unit_of_work, line_user_id, candidate)
            return _with_identity_preview_fingerprint(
                "staff",
                flow_id,
                _staff_proof_fingerprint(proof),
                preview,
            )

    # Kept cohesive so the one-use flow and manual-review claim cannot diverge.
    def apply_staff(
        self,
        flow_id,
        line_user_id,
        proof,
        expected_version,
        preview_fingerprint,
        correlation_id,
    ):
        try:
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
                preview = _with_identity_preview_fingerprint(
                    "staff",
                    flow_id,
                    _staff_proof_fingerprint(proof),
                    _staff_preview(unit_of_work, line_user_id, candidate),
                )
                _require_identity_preview(preview, expected_version, preview_fingerprint)
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
                if result.status is not LineIdentityApplyStatus.PENDING_REVIEW:
                    unit_of_work.identities.reset_failure_streak(
                        line_user_id,
                        flow_id,
                    )
                unit_of_work.commit()
        except LineIdentityNotFoundError:
            self._record_binding_failure(
                flow_id,
                line_user_id,
                LineBindingSubjectType.STAFF,
                _staff_proof_fingerprint(proof).value,
                correlation_id,
            )
            raise
        return result

    def _record_binding_failure(
        self,
        flow_id,
        line_user_id,
        subject_type,
        candidate_scope,
        correlation_id,
    ) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            current = unit_of_work.identities.get_failure_streak(
                line_user_id,
                lock=True,
            )
            streak, threshold = advance_binding_failure_streak(
                current,
                line_user_id=line_user_id,
                identity_flow_id=flow_id.value,
                candidate_subject_type=subject_type,
                candidate_scope=candidate_scope,
                failure_identity=correlation_id.value,
            )
            if streak is current:
                unit_of_work.commit()
                return
            if threshold:
                source_identity = (
                    f"binding-failure:{streak.scope_fingerprint}:"
                    f"{streak.generation}"
                )
                source_fingerprint = fingerprint_payload(
                    {
                        "scope_fingerprint": streak.scope_fingerprint,
                        "generation": streak.generation,
                        "failure_count": 2,
                    }
                ).value
                escalation_command = CreateHumanEscalation(
                    source_event_identity=source_identity,
                    source_kind="binding_failure",
                    source_fingerprint=source_fingerprint,
                    trigger_code=TriggerCode.BINDING_FAILURE_THRESHOLD_2,
                    trigger_policy_version="identity.v1",
                    ticket_category=CustomerServiceCategory.CONTACT_UNION,
                    masked_context=MaskedContext(
                        (
                            "customer_binding_failure_threshold_2"
                            if subject_type is LineBindingSubjectType.CUSTOMER
                            else "staff_verification_failure_threshold_2"
                        ),
                        "identity.v1",
                        "other",
                        "m1-mask.v1",
                    ),
                    hold_scope=source_identity,
                    idempotency_key=IdempotencyKey(source_identity),
                    correlation_id=correlation_id,
                    actor=ActorContext("system:line-identity"),
                )
                ticket = unit_of_work.customer_service.create_or_append(
                    CreateCustomerServiceMessage(
                        line_user_id.value,
                        CustomerServiceCategory.CONTACT_UNION,
                        "binding_failure_threshold_2",
                        source_identity,
                    )
                )
                receipt = HumanEscalationApplication(
                    self._unit_of_work_factory,
                    self._now,
                ).create_for_ticket(
                    escalation_command,
                    ticket,
                    unit_of_work,
                )
                streak = replace(streak, escalation_id=receipt.escalation_id)
            unit_of_work.identities.save_failure_streak(streak)
            unit_of_work.commit()

    def preview_admin(self, flow_id, line_user_id, proof):
        # Password verification is intentionally deferred to Apply so Preview
        # remains zero-write and cannot bypass the flow's failed-attempt policy.
        with self._unit_of_work_factory() as unit_of_work:
            _require_flow(
                unit_of_work,
                flow_id,
                LineIdentityFlowPurpose.ADMIN_BINDING,
                line_user_id,
                self._now(),
            )
            binding = unit_of_work.identities.get(
                line_user_id,
                LineBindingSubjectType.ADMIN,
            )
        preview = LineIdentityPreview(
            LineIdentityPreviewStatus.AUTHENTICATION_PENDING,
            line_user_id,
            None,
            binding.version if binding else ExpectedVersion(0),
            PreviewFingerprint("0" * 64),
        )
        return _with_identity_preview_fingerprint(
            "admin",
            flow_id,
            _admin_proof_fingerprint(proof),
            preview,
        )

    # Kept cohesive so authenticated admin binding and its notification commit together.
    def apply_admin(
        self,
        flow_id,
        line_user_id,
        proof,
        expected_version,
        preview_fingerprint,
        correlation_id,
    ):
        candidate = self._authenticated_admin_candidate(flow_id, line_user_id, proof)
        with self._unit_of_work_factory() as unit_of_work:
            _require_flow(
                unit_of_work,
                flow_id,
                LineIdentityFlowPurpose.ADMIN_BINDING,
                line_user_id,
                self._now(),
            )
            binding = unit_of_work.identities.get(
                line_user_id,
                LineBindingSubjectType.ADMIN,
            )
            current_preview = _with_identity_preview_fingerprint(
                "admin",
                flow_id,
                _admin_proof_fingerprint(proof),
                LineIdentityPreview(
                    LineIdentityPreviewStatus.AUTHENTICATION_PENDING,
                    line_user_id,
                    None,
                    binding.version if binding else ExpectedVersion(0),
                    PreviewFingerprint("0" * 64),
                ),
            )
            _require_identity_preview(
                current_preview,
                expected_version,
                preview_fingerprint,
            )
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
        owner_projection_line_user_id=None,
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
                owner_projection_line_user_id or candidate.currently_bound_line_user_id,
            )
            result = _bind_result(
                unit_of_work,
                preview.line_user_id,
                candidate,
                correlation_id,
            )
        _enqueue_result_message(unit_of_work, result, correlation_id, self._now())
        return result


def _registration_preview_fingerprint(
    payload_fingerprint: PreviewFingerprint,
    line_user_id: LineUserId,
    flow_id: LineIdentityFlowId | None,
    expected_binding_version: ExpectedVersion,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "payload_fingerprint": payload_fingerprint.value,
            "line_user_id": line_user_id.value,
            "flow_id": flow_id.value if flow_id else None,
            "expected_binding_version": expected_binding_version.value,
        }
    )


def _with_identity_preview_fingerprint(
    family: str,
    flow_id: LineIdentityFlowId,
    proof_fingerprint: PreviewFingerprint,
    preview: LineIdentityPreview,
) -> LineIdentityPreview:
    candidate = preview.candidate
    fingerprint = fingerprint_payload(
        {
            "family": family,
            "flow_id": flow_id.value,
            "line_user_id": preview.line_user_id.value,
            "expected_version": preview.expected_version.value,
            "status": preview.status.value,
            "proof_fingerprint": proof_fingerprint.value,
            "candidate": (
                {
                    "subject_type": candidate.subject_type.value,
                    "subject_reference": candidate.subject_reference,
                    "currently_bound_line_user_id": (
                        candidate.currently_bound_line_user_id.value
                        if candidate.currently_bound_line_user_id
                        else None
                    ),
                }
                if candidate
                else None
            ),
        }
    )
    return LineIdentityPreview(
        preview.status,
        preview.line_user_id,
        candidate,
        preview.expected_version,
        fingerprint,
    )


def _require_identity_preview(
    preview: LineIdentityPreview,
    expected_version: ExpectedVersion,
    preview_fingerprint: PreviewFingerprint,
) -> None:
    if (
        preview.expected_version != expected_version
        or preview.preview_fingerprint != preview_fingerprint
    ):
        raise LineIdentityConflictError("line_identity_preview_stale")


def _customer_preview(unit_of_work, line_user_id, candidate):
    binding = unit_of_work.identities.get(
        line_user_id,
        LineBindingSubjectType.CUSTOMER,
    )
    version = binding.version if binding else ExpectedVersion(0)
    if candidate is None:
        return LineIdentityPreview(
            LineIdentityPreviewStatus.NOT_FOUND,
            line_user_id,
            None,
            version,
            PreviewFingerprint("0" * 64),
        )
    if candidate.currently_bound_line_user_id == line_user_id:
        status = LineIdentityPreviewStatus.ALREADY_BOUND
    elif candidate.currently_bound_line_user_id is not None:
        status = LineIdentityPreviewStatus.REQUIRES_REVIEW
    elif binding and binding.status is LineIdentityBindingStatus.BOUND:
        status = LineIdentityPreviewStatus.REQUIRES_REVIEW
    else:
        status = LineIdentityPreviewStatus.MATCHED
    return LineIdentityPreview(
        status,
        line_user_id,
        candidate,
        version,
        PreviewFingerprint("0" * 64),
    )


def _staff_preview(unit_of_work, line_user_id, candidate):
    binding = unit_of_work.identities.get(
        line_user_id,
        LineBindingSubjectType.STAFF,
    )
    version = binding.version if binding else ExpectedVersion(0)
    if candidate is None:
        status = LineIdentityPreviewStatus.NOT_FOUND
    elif candidate.currently_bound_line_user_id == line_user_id:
        status = LineIdentityPreviewStatus.ALREADY_BOUND
    else:
        status = LineIdentityPreviewStatus.REQUIRES_REVIEW
    return LineIdentityPreview(
        status,
        line_user_id,
        candidate,
        version,
        PreviewFingerprint("0" * 64),
    )


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
    schedule_resolved_identity_menu(unit_of_work, snapshot.line_user_id)
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
        receipt_identity=(
            f"line-binding:{line_user_id.value}:{snapshot.version.value}"
        ),
    )


def _bind_claim(unit_of_work, claim, correlation_id):
    current = unit_of_work.identities.get(
        claim.line_user_id,
        claim.subject_type,
    )
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
    current = unit_of_work.identities.get(
        line_user_id,
        candidate.subject_type,
    )
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
        f"line-review:{created.snapshot.request_id.value}:pending",
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


def _admin_proof_fingerprint(proof):
    return fingerprint_payload(
        {
            "username": proof.username.strip(),
            "password": proof.password,
        }
    )


__all__ = [
    "LineIdentityApplication",
    "LineIdentityAuthenticationError",
    "LineIdentityConflictError",
    "LineIdentityNotFoundError",
]

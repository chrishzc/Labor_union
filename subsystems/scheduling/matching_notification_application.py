"""
File: matching_notification_application.py
Description: 協調媒合通知、人工回覆與 assignment conversion 後的雙向 LINE durable intents。
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Callable

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingCommunicationConflictError,
    MatchingCommunicationStaleError,
    MatchingDecisionNotReadyError,
    MatchingNotificationKind,
    MatchingRecipientMismatchError,
    MatchingResponseSource,
    record_caregiver_willingness,
    record_customer_decision,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.capabilities import (
    LineCapability,
    require_line_capability,
)
from subsystems.line.delivery_contracts import LineDeliveryCommandOutcome
from subsystems.scheduling.matching_line_cards import (
    caregiver_information_card,
    customer_profiles_card,
)
from subsystems.scheduling.matching_notification_contracts import (
    MatchingContactState,
    MatchingNotificationProjectionStatus,
    MatchingNotificationResult,
    MatchingResponseResult,
    AssignmentConversionNotificationResult,
    NotifyAssignmentConversionCommand,
    RecordManualMatchingResponseCommand,
    RequestCaregiverInformationCommand,
    RequestCustomerProfilesCommand,
)
from subsystems.scheduling.segmented_availability_query import (
    search_segmented_caregiver_availability,
)


class MatchingNotificationApplication:
    def __init__(
        self,
        unit_of_work_factory,
        now: Callable[[], datetime],
        *,
        token_factory: Callable[[], str] | None = None,
        interaction_lifetime: timedelta = timedelta(days=7),
        availability_validator: Callable[[MatchingContactState], None] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self._interaction_lifetime = interaction_lifetime
        self._availability_validator = availability_validator or _validate_availability

    def get_contact_state(
        self,
        actor: ActorContext,
        case_no: str,
        plan_id: int,
    ) -> MatchingContactState:
        require_line_capability(actor, LineCapability.MATCHING_READ)
        with self._unit_of_work_factory() as unit_of_work:
            state = unit_of_work.matching_notifications.get_contact_state(case_no, plan_id)
            unit_of_work.commit()
        if state is None:
            raise LookupError("matching plan not found")
        return state

    def request_caregiver_information(
        self,
        command: RequestCaregiverInformationCommand,
    ) -> MatchingNotificationResult:
        require_line_capability(command.actor, LineCapability.MATCHING_SEND)
        with self._unit_of_work_factory() as unit_of_work:
            replay = unit_of_work.matching_notifications.get_intent_result(
                command.idempotency_key,
                command.fingerprint.value,
            )
            if replay is not None:
                unit_of_work.commit()
                return replay
            result = self._create_caregiver_notification(unit_of_work, command)
            unit_of_work.commit()
        return result

    def request_customer_profiles(
        self,
        command: RequestCustomerProfilesCommand,
    ) -> MatchingNotificationResult:
        require_line_capability(command.actor, LineCapability.MATCHING_SEND)
        with self._unit_of_work_factory() as unit_of_work:
            replay = unit_of_work.matching_notifications.get_intent_result(
                command.idempotency_key,
                command.fingerprint.value,
            )
            if replay is not None:
                unit_of_work.commit()
                return replay
            result = self._create_customer_notification(unit_of_work, command)
            unit_of_work.commit()
        return result

    def notify_assignment_conversion(
        self,
        command: NotifyAssignmentConversionCommand,
    ) -> AssignmentConversionNotificationResult:
        require_line_capability(command.actor, LineCapability.MATCHING_SEND)
        with self._unit_of_work_factory() as unit_of_work:
            customer = unit_of_work.delivery_tasks.enqueue(
                _assignment_conversion_delivery(command, "customer")
            )
            caregiver = unit_of_work.delivery_tasks.enqueue(
                _assignment_conversion_delivery(command, "caregiver")
            )
            _require_assignment_conversion_outcomes(customer, caregiver)
            unit_of_work.commit()
        return AssignmentConversionNotificationResult(
            command.receipt.request_id,
            customer.task_id,
            caregiver.task_id,
            replayed=(
                customer.outcome is LineDeliveryCommandOutcome.EXISTING
                and caregiver.outcome is LineDeliveryCommandOutcome.EXISTING
            ),
        )

    def record_line_response(
        self,
        *,
        token: str,
        decision: str,
        line_user_id: LineUserId,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
        occurred_at: datetime,
    ) -> MatchingResponseResult:
        with self._unit_of_work_factory() as unit_of_work:
            result = self.record_line_response_in_unit_of_work(
                unit_of_work,
                token=token,
                decision=decision,
                line_user_id=line_user_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
        return result

    def record_line_response_in_unit_of_work(
        self,
        unit_of_work,
        *,
        token: str,
        decision: str,
        line_user_id: LineUserId,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
        occurred_at: datetime,
    ) -> MatchingResponseResult:
        result = self._record_line_response(
            unit_of_work,
            token,
            decision,
            line_user_id,
            idempotency_key,
            occurred_at,
        )
        unit_of_work.delivery_tasks.enqueue(
            _response_confirmation(result, line_user_id, correlation_id, occurred_at)
        )
        return result

    def record_manual_response(
        self,
        command: RecordManualMatchingResponseCommand,
    ) -> MatchingResponseResult:
        require_line_capability(command.actor, LineCapability.MATCHING_OVERRIDE)
        with self._unit_of_work_factory() as unit_of_work:
            state = _required_state(unit_of_work, command.plan.case_no, command.plan.plan_id, True)
            _require_expected_state(state, command.plan.version)
            result = _append_manual_response(unit_of_work, command, state, self._now())
            unit_of_work.commit()
        return result

    def _create_caregiver_notification(self, unit_of_work, command):
        state = _required_state(unit_of_work, command.plan.case_no, command.plan.plan_id, True)
        _require_sendable_state(state, command.plan.version)
        self._availability_validator(state)
        segment = next((item for item in state.segments if item.segment_id == command.segment_id), None)
        if segment is None:
            raise LookupError("matching segment not found")
        if segment.staff_line_user_id is None:
            raise MatchingDecisionNotReadyError("caregiver has no LINE binding")
        facts = unit_of_work.matching_notifications.caregiver_card_facts(
            command.plan.plan_id,
            command.segment_id,
        )
        token = self._token_factory()
        payload_json = caregiver_information_card(command.notification_kind, facts, token)
        return self._append_notification(
            unit_of_work,
            command,
            segment.staff_line_user_id,
            command.segment_id,
            command.notification_kind,
            facts,
            payload_json,
            token,
            "caregiver_willingness",
        )

    def _create_customer_notification(self, unit_of_work, command):
        state = _required_state(unit_of_work, command.plan.case_no, command.plan.plan_id, True)
        _require_sendable_state(state, command.plan.version)
        self._availability_validator(state)
        if not state.all_willing:
            raise MatchingDecisionNotReadyError("all caregivers must be willing")
        if state.customer_line_user_id is None:
            raise MatchingDecisionNotReadyError("customer has no LINE binding")
        profiles = unit_of_work.matching_notifications.customer_profile_facts(command.plan.plan_id)
        if not 1 <= len(profiles) <= 4:
            raise MatchingDecisionNotReadyError("customer profile count must be between 1 and 4")
        token = self._token_factory()
        payload_json = customer_profiles_card(
            command.plan.case_no,
            profiles,
            token,
            command.note,
        )
        snapshot = {
            "case_no": command.plan.case_no,
            "profile_count": len(profiles),
            "note": command.note,
        }
        return self._append_notification(
            unit_of_work,
            command,
            state.customer_line_user_id,
            None,
            MatchingNotificationKind.CUSTOMER_PROFILES,
            snapshot,
            payload_json,
            token,
            "customer_decision",
        )

    # Intent, one-time action, delivery task, and projection are one transaction.
    def _append_notification(self, unit_of_work, command, recipient, segment_id,
                             kind, snapshot, payload_json, token, action_scope):
        repository = unit_of_work.matching_notifications
        intent_id = repository.append_notification_intent(
            plan=command.plan,
            segment_id=segment_id,
            kind=kind,
            recipient=recipient,
            payload_snapshot=snapshot,
            idempotency_key=command.idempotency_key,
            fingerprint=command.fingerprint.value,
            actor_id=command.actor.actor_id,
        )
        repository.open_interaction(
            token_hash=_token_hash(token),
            plan_id=command.plan.plan_id,
            segment_id=segment_id,
            action_scope=action_scope,
            recipient=recipient,
            expires_at=self._now() + self._interaction_lifetime,
        )
        delivery = unit_of_work.delivery_tasks.enqueue(
            _matching_delivery(command, recipient, payload_json, intent_id, self._now())
        )
        repository.project_intent(intent_id, delivery.task_id, self._now())
        return MatchingNotificationResult(
            intent_id,
            command.plan,
            kind,
            MatchingNotificationProjectionStatus.PROJECTED,
            delivery.task_id,
        )

    def _record_line_response(self, unit_of_work, token, decision, line_user_id,
                              idempotency_key, occurred_at):
        token_hash = _token_hash(token)
        interaction = unit_of_work.matching_notifications.interaction(token_hash)
        if interaction is None:
            raise LookupError("matching interaction not found")
        _require_active_interaction(interaction, line_user_id, occurred_at)
        state = _required_state(
            unit_of_work,
            str(interaction["case_no"]),
            int(interaction["plan_id"]),
            True,
        )
        return _append_line_response(
            unit_of_work,
            interaction,
            state,
            decision,
            line_user_id,
            idempotency_key,
            occurred_at,
            token_hash,
        )


def _required_state(unit_of_work, case_no, plan_id, lock):
    state = unit_of_work.matching_notifications.get_contact_state(case_no, plan_id, lock=lock)
    if state is None:
        raise LookupError("matching plan not found")
    return state


def _require_sendable_state(state, expected_version):
    _require_expected_state(state, expected_version)
    if not state.plan_is_active or state.plan_status != "proposed":
        raise MatchingCommunicationStaleError("matching plan is not active and proposed")
    if state.order_status != "洽談中":
        raise MatchingCommunicationStaleError("order is no longer in negotiation")


def _require_expected_state(state, expected_version):
    if state.plan.version != expected_version:
        raise MatchingCommunicationStaleError("matching communication version is stale")


def _require_active_interaction(interaction, line_user_id, occurred_at):
    if str(interaction["recipient_line_user_id"]) != line_user_id.value:
        raise MatchingRecipientMismatchError("LINE responder does not match the recipient")
    if str(interaction["interaction_status"]) != "active":
        raise MatchingCommunicationStaleError("matching interaction is no longer active")
    if aware_datetime(interaction["expires_at_utc"]) <= occurred_at:
        raise MatchingCommunicationStaleError("matching interaction has expired")


# This stays cohesive so one parsed action maps to one domain rule and immutable fact.
def _append_line_response(unit_of_work, interaction, state, decision, line_user_id,
                          key, occurred_at, token_hash):
    scope = str(interaction["action_scope"])
    segment_id = interaction.get("segment_id")
    if scope == "caregiver_willingness":
        if decision not in {"willing", "unwilling"}:
            raise MatchingCommunicationConflictError("invalid caregiver response action")
        value = CaregiverWillingness(decision)
        segment = next(
            (item for item in state.segments if item.segment_id == int(segment_id)),
            None,
        )
        if segment is None:
            raise LookupError("matching segment not found")
        record_caregiver_willingness(
            segment.willingness, value,
            plan_is_active=state.plan_is_active,
            recipient_matches=segment.staff_line_user_id == line_user_id,
        )
        response_type = scope
    else:
        if decision not in {"accepted", "declined", "contact_requested"}:
            raise MatchingCommunicationConflictError("invalid customer response action")
        value = CustomerMatchingDecision(decision)
        record_customer_decision(
            state.customer_decision, value,
            plan_is_active=state.plan_is_active,
            recipient_matches=state.customer_line_user_id == line_user_id,
            profiles_are_available=state.customer_profiles_status is not None,
        )
        response_type = scope
    return unit_of_work.matching_notifications.append_response(
        plan=state.plan,
        segment_id=int(segment_id) if segment_id is not None else None,
        response_type=response_type,
        response_value=value.value,
        source=MatchingResponseSource.LINE,
        actor_id=f"line:{line_user_id.value}",
        line_user_id=line_user_id,
        reason=None,
        idempotency_key=key,
        fingerprint=_response_fingerprint(
            state.plan.plan_id,
            segment_id,
            value.value,
            "line",
            actor_id=f"line:{line_user_id.value}",
        ),
        occurred_at=occurred_at,
        token_hash=token_hash,
    )


# This stays cohesive so both manual decision types share the same audited write path.
def _append_manual_response(unit_of_work, command, state, occurred_at):
    if command.caregiver_willingness is not None:
        segment = next(
            (item for item in state.segments if item.segment_id == command.segment_id),
            None,
        )
        if segment is None:
            raise LookupError("matching segment not found")
        value = record_caregiver_willingness(
            segment.willingness, command.caregiver_willingness,
            plan_is_active=state.plan_is_active,
            recipient_matches=True,
        )
        response_type = "caregiver_willingness"
    else:
        value = record_customer_decision(
            state.customer_decision, command.customer_decision,
            plan_is_active=state.plan_is_active,
            recipient_matches=True,
            # 人工補登已由內部操作者保存原因與 audit；不得被 LINE recipient／delivery 缺漏阻擋。
            profiles_are_available=True,
        )
        response_type = "customer_decision"
    return unit_of_work.matching_notifications.append_response(
        plan=state.plan,
        segment_id=command.segment_id,
        response_type=response_type,
        response_value=value.value,
        source=MatchingResponseSource.ADMIN,
        actor_id=command.actor.actor_id,
        line_user_id=None,
        reason=command.reason,
        idempotency_key=command.idempotency_key,
        fingerprint=_response_fingerprint(
            state.plan.plan_id,
            command.segment_id,
            value.value,
            "admin",
            actor_id=command.actor.actor_id,
            reason=command.reason,
        ),
        occurred_at=occurred_at,
    )


def _matching_delivery(command, recipient, payload_json, intent_id, scheduled_at):
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, recipient),
        LineMessageKind.FLEX,
        payload_json,
        scheduled_at,
        IdempotencyKey(f"matching-delivery:{command.idempotency_key.value}"),
        command.correlation_id,
        "matching_notification_intent",
        str(intent_id),
    )


def _assignment_conversion_delivery(
    command: NotifyAssignmentConversionCommand,
    role: str,
) -> LineDeliveryRequest:
    if role == "customer":
        recipient = command.customer.line_user_id
        text = "媒合已完成，工會人員將提供後續服務資訊。"
    elif role == "caregiver":
        recipient = command.caregiver.line_user_id
        text = "派案已完成，工會人員將提供後續服務資訊。"
    else:
        raise ValueError("assignment conversion notification role is invalid")
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, recipient),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": text}),
        command.scheduled_at,
        _assignment_conversion_idempotency_key(command, role),
        command.correlation_id,
        "assignment_conversion_receipt",
        command.receipt.request_id,
    )


def _assignment_conversion_idempotency_key(
    command: NotifyAssignmentConversionCommand,
    role: str,
) -> IdempotencyKey:
    digest = fingerprint_payload(
        {
            "parent_key": command.idempotency_key.value,
            "command_fingerprint": command.fingerprint.value,
            "audience": role,
        }
    ).value
    return IdempotencyKey(f"matching-assignment-notification:{role}:{digest}")


def _require_assignment_conversion_outcomes(customer, caregiver) -> None:
    outcome_values = (customer.outcome, caregiver.outcome)
    if not all(
        isinstance(outcome, LineDeliveryCommandOutcome)
        for outcome in outcome_values
    ):
        raise MatchingCommunicationConflictError(
            "assignment conversion notification returned an unknown delivery outcome"
        )
    outcomes = set(outcome_values)
    if outcomes not in (
        {LineDeliveryCommandOutcome.CREATED},
        {LineDeliveryCommandOutcome.EXISTING},
    ):
        raise MatchingCommunicationConflictError(
            "assignment conversion notification delivery outcomes conflict"
        )


def _response_confirmation(result, recipient, correlation_id, scheduled_at):
    if result.caregiver_willingness is not None:
        text = "已收到您的承接意願，工會人員會依流程與您聯繫。"
    else:
        text = "已收到您的配對選擇，工會人員會依流程與您聯繫。"
    from domains.line.canonical_payload import canonical_line_payload_json
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, recipient),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": text}),
        scheduled_at,
        IdempotencyKey(f"matching-response-confirmation:{result.event_id}"),
        correlation_id,
        "matching_response_event",
        str(result.event_id),
    )


def _response_fingerprint(
    plan_id,
    segment_id,
    decision,
    source,
    *,
    actor_id,
    reason=None,
):
    return fingerprint_payload(
        {
            "plan_id": plan_id,
            "segment_id": segment_id,
            "decision": decision,
            "source": source,
            "actor_id": actor_id,
            "reason": reason,
        }
    ).value


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def aware_datetime(value):
    if not isinstance(value, datetime):
        raise TypeError("matching interaction expiry is invalid")
    return value.replace(tzinfo=self_timezone()) if value.tzinfo is None else value


def self_timezone():
    from datetime import timezone
    return timezone.utc


def _validate_availability(state: MatchingContactState) -> None:
    result = search_segmented_caregiver_availability(
        case_no=state.plan.case_no,
        segment_count=len(state.segments),
        segment_drafts=[
            {
                "staff_id": segment.staff_id,
                "start_date": segment.assigned_start_date,
                "end_date": segment.assigned_end_date,
            }
            for segment in state.segments
        ],
        as_of=datetime.now().date().isoformat(),
    )
    if result.get("feasibility") != "complete" or result.get("conflicts"):
        raise MatchingDecisionNotReadyError("matching plan is no longer fully available")


__all__ = ["MatchingNotificationApplication"]

"""
File: test_line_matching_notification_application_stage7.py
Description: 驗證 Stage 7 matching LINE 通知與互動 durable intent。
"""

import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from domains.line.delivery import (
    LineDeliveryStatus,
    LineMessageKind,
    LineRecipientType,
)
from domains.line.identities import LineDeliveryTaskId, LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingCommunicationConflictError,
    MatchingNotificationKind,
    MatchingPlanReference,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.delivery_contracts import LineDeliveryCommandOutcome
from subsystems.scheduling.matching_notification_application import (
    MatchingNotificationApplication,
)
from subsystems.scheduling.matching_notification_contracts import (
    ApplyManualCustomerProfilesCommand,
    ManualCustomerProfilesEvidence,
    ManualMatchingConfirmationMethod,
    MatchingContactState,
    MatchingResponseResult,
    MatchingSegmentContact,
    PreviewManualCustomerProfilesCommand,
    RecordManualMatchingResponseCommand,
    RequestCaregiverInformationCommand,
)

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


class _MatchingRepository:
    def __init__(self, state) -> None:
        self.state = state
        self.intent_arguments = None
        self.interaction_arguments = None
        self.projection_arguments = None
        self.manual_profile_arguments = None

    def get_intent_result(self, key, fingerprint):
        return None

    def get_response_result(self, key, fingerprint):
        return None

    def interaction(self, token_hash):
        return getattr(self, "_interaction_data", None)

    def get_contact_state(self, case_no, plan_id, *, lock=False):
        return self.state

    def get_manual_customer_profiles_result(self, key, fingerprint):
        return None

    def caregiver_card_facts(self, plan_id, segment_id):
        return {
            "case_no": "CASE-1",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "city": "台北市",
            "service_type": "到府服務",
        }

    def customer_profile_facts(self, plan_id):
        return ({"id": 30, "name": "林月嫂"},)

    def append_manual_customer_profiles(self, **arguments):
        self.manual_profile_arguments = arguments
        return ManualCustomerProfilesEvidence(
            (61,),
            arguments["confirmation_method"],
            arguments["reason"],
            arguments["actor_id"],
            arguments["idempotency_key"],
            PreviewFingerprint(arguments["fingerprint"]),
        )

    def append_notification_intent(self, **arguments):
        self.intent_arguments = arguments
        return 31

    def open_interaction(self, **arguments):
        self.interaction_arguments = arguments

    def project_intent(self, *arguments):
        self.projection_arguments = arguments

    def append_response(self, **arguments):
        self.response_arguments = arguments
        return MatchingResponseResult(
            51,
            MatchingPlanReference(
                arguments["plan"].case_no,
                arguments["plan"].plan_id,
                arguments["plan"].version + 1,
            ),
            arguments["source"],
            customer_decision=CustomerMatchingDecision(arguments["response_value"]),
            segment_id=arguments["segment_id"],
            idempotency_key=arguments["idempotency_key"],
        )


class _DeliveryRepository:
    def __init__(
        self,
        outcomes: tuple[LineDeliveryCommandOutcome, ...] = (),
    ) -> None:
        self.requests = []
        self.outcomes = outcomes

    def enqueue(self, request):
        request_index = len(self.requests)
        self.requests.append(request)
        outcome = (
            self.outcomes[request_index]
            if request_index < len(self.outcomes)
            else LineDeliveryCommandOutcome.CREATED
        )
        return SimpleNamespace(
            outcome=outcome,
            task_id=LineDeliveryTaskId(41 + request_index),
        )


class _UnitOfWork:
    def __init__(
        self,
        state,
        delivery_outcomes: tuple[LineDeliveryCommandOutcome, ...] = (),
        active_group_targets=(),
    ) -> None:
        self.matching_notifications = _MatchingRepository(state)
        self.delivery_tasks = _DeliveryRepository(delivery_outcomes)
        self.runtime_monitor = SimpleNamespace(
            find_active_group_targets=lambda **_: active_group_targets
        )
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def commit(self):
        self.committed = True


def _state():
    return MatchingContactState(
        MatchingPlanReference("CASE-1", 10, 0),
        "proposed",
        True,
        "洽談中",
        LineUserId("U-customer"),
        CustomerMatchingDecision.PENDING,
        None,
        (
            MatchingSegmentContact(
                20,
                1,
                30,
                "林月嫂",
                LineUserId("U-caregiver"),
                "2026-09-01",
                "2026-09-10",
                CaregiverWillingness.PENDING,
            ),
        ),
    )


def test_manual_customer_decision_allows_documented_non_line_confirmation() -> None:
    unit_of_work = _UnitOfWork(_state())
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        availability_validator=lambda state: None,
    )
    command = RecordManualMatchingResponseCommand(
        MatchingPlanReference("CASE-1", 10, 0),
        None,
        None,
        CustomerMatchingDecision.ACCEPTED,
        "電話確認客戶接受正式方案",
        ActorContext("admin:1", ("line.matching.override",)),
        ExpectedVersion(0),
        IdempotencyKey("manual-customer:1"),
        CorrelationId("manual-customer-correlation:1"),
    )

    result = application.record_manual_response(command)

    assert result.customer_decision is CustomerMatchingDecision.ACCEPTED
    assert unit_of_work.committed
    assert unit_of_work.matching_notifications.response_arguments["line_user_id"] is None


def test_manual_customer_profiles_requires_preview_and_appends_distinct_evidence() -> None:
    willing_state = replace(
        _state(),
        segments=(replace(_state().segments[0], willingness=CaregiverWillingness.WILLING),),
    )
    unit_of_work = _UnitOfWork(willing_state)
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        availability_validator=lambda state: None,
    )
    actor = ActorContext("admin:1", ("line.matching.override",))
    preview_command = PreviewManualCustomerProfilesCommand(
        willing_state.plan,
        ManualMatchingConfirmationMethod.PHONE,
        "已逐一向客戶說明正式方案內月嫂履歷",
        actor,
        ExpectedVersion(0),
    )

    preview = application.preview_manual_customer_profiles(preview_command)
    receipt = application.apply_manual_customer_profiles(
        ApplyManualCustomerProfilesCommand(
            willing_state.plan,
            preview.confirmation_method,
            preview.reason,
            actor,
            ExpectedVersion(0),
            preview.preview_fingerprint,
            IdempotencyKey("manual-profiles:1"),
            CorrelationId("manual-profiles-correlation:1"),
        )
    )

    assert preview.segment_ids == (20,)
    assert receipt.evidence.confirmation_method is ManualMatchingConfirmationMethod.PHONE
    assert receipt.replayed is False
    assert unit_of_work.matching_notifications.manual_profile_arguments["segment_ids"] == (20,)
    assert unit_of_work.committed is True


def test_caregiver_card_intent_action_and_delivery_share_one_commit() -> None:
    unit_of_work = _UnitOfWork(_state())
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        token_factory=lambda: "safe-token-12345678901234567890",
        availability_validator=lambda state: None,
    )
    command = RequestCaregiverInformationCommand(
        MatchingPlanReference("CASE-1", 10, 0),
        20,
        MatchingNotificationKind.CAREGIVER_INFO_1,
        ActorContext("admin:1", ("line.matching.send",)),
        ExpectedVersion(0),
        IdempotencyKey("matching-info:1"),
        CorrelationId("correlation:1"),
    )

    result = application.request_caregiver_information(command)

    assert result.line_delivery_task_id == LineDeliveryTaskId(41)
    assert unit_of_work.committed
    assert unit_of_work.matching_notifications.intent_arguments["recipient"] == LineUserId(
        "U-caregiver"
    )
    assert "safe-token" not in str(
        unit_of_work.matching_notifications.intent_arguments["payload_snapshot"]
    )
    request = unit_of_work.delivery_tasks.requests[0]
    assert request.message_kind.value == "flex"
    assert "matching:safe-token-12345678901234567890:willing" in request.payload_json
    assert unit_of_work.matching_notifications.projection_arguments[0] == 31


def test_record_line_response_accepted_enqueues_match_success_group_notification() -> None:
    state = _state()
    unit_of_work = _UnitOfWork(
        state,
        active_group_targets=({"group_id": "C-group-target"},),
    )
    unit_of_work.matching_notifications._interaction_data = {
        "case_no": "CASE-1",
        "plan_id": 10,
        "recipient_line_user_id": "U-customer",
        "interaction_status": "active",
        "expires_at_utc": datetime(2026, 8, 10, tzinfo=timezone.utc),
        "action_scope": "customer_decision",
        "segment_id": None,
    }
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        availability_validator=lambda state: None,
    )

    result = application.record_line_response_in_unit_of_work(
        unit_of_work,
        token="token-12345678901234567890",
        decision="accepted",
        line_user_id=LineUserId("U-customer"),
        idempotency_key=IdempotencyKey("matching-postback:event-1"),
        correlation_id=CorrelationId("line-event:event-1"),
        occurred_at=NOW,
    )

    assert result.customer_decision is CustomerMatchingDecision.ACCEPTED
    assert len(unit_of_work.delivery_tasks.requests) == 2
    customer_confirmation, group_notification = unit_of_work.delivery_tasks.requests
    assert customer_confirmation.recipient.identity.value == "U-customer"
    assert customer_confirmation.message_kind == LineMessageKind.TEXT
    assert group_notification.recipient.recipient_type == LineRecipientType.GROUP
    assert group_notification.recipient.identity.value == "C-group-target"
    assert group_notification.message_kind == LineMessageKind.FLEX
    assert "案件媒合成功通知" in group_notification.payload_json

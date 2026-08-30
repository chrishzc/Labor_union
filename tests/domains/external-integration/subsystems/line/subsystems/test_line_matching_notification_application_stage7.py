"""
File: test_line_matching_notification_application_stage7.py
Description: 驗證 Stage 7 matching 通知與 assignment conversion 雙向 LINE durable intent。
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
from domains.scheduling.matching_coordination import (
    SOURCE_KINDS,
    MatchingCrossDomainRequest,
    MatchingRequestKind,
    MatchingSourceVersion,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.delivery_contracts import LineDeliveryCommandOutcome
from subsystems.scheduling.matching_assignment_conversion import (
    AssignmentConversionResultState,
    CanonicalAssignmentConversionReceipt,
)
from subsystems.scheduling.matching_notification_application import (
    MatchingNotificationApplication,
)
from subsystems.scheduling.matching_notification_contracts import (
    ApplyManualCustomerProfilesCommand,
    ManualCustomerProfilesEvidence,
    ManualMatchingConfirmationMethod,
    MatchingNotificationAudience,
    MatchingContactState,
    MatchingSegmentContact,
    NotifyAssignmentConversionCommand,
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
        return SimpleNamespace(
            event_id=51,
            plan=arguments["plan"],
            source=arguments["source"],
            caregiver_willingness=None,
            customer_decision=CustomerMatchingDecision(arguments["response_value"]),
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
    ) -> None:
        self.matching_notifications = _MatchingRepository(state)
        self.delivery_tasks = _DeliveryRepository(delivery_outcomes)
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


def _assignment_conversion_notification() -> NotifyAssignmentConversionCommand:
    source_versions = tuple(
        MatchingSourceVersion(kind, f"{kind}:1", 1, "a" * 64)
        for kind in SOURCE_KINDS
    )
    request = MatchingCrossDomainRequest(
        request_id="assignment-conversion-request-1",
        request_kind=MatchingRequestKind.ASSIGNMENT_CONVERSION_REQUESTED,
        case_no="CASE-1",
        package_id="matching-package-10",
        package_version=2,
        criteria_snapshot_id="matching-criteria-10",
        candidate_id="candidate-30",
        source_versions=source_versions,
        lineage_event_id="matching-decision-10",
        reason="customer accepted willing candidate",
    )
    receipt = CanonicalAssignmentConversionReceipt(
        request_id=request.request_id,
        result_state=AssignmentConversionResultState.CONVERTED,
        package_id=request.package_id,
        package_version=request.package_version,
        criteria_snapshot_id=request.criteria_snapshot_id,
        candidate_id=request.candidate_id,
        source_versions=request.source_versions,
        assignment_reference="assignment:canonical-10",
        receipt_fingerprint=PreviewFingerprint("c" * 64),
    )
    return NotifyAssignmentConversionCommand(
        request=request,
        receipt=receipt,
        customer=MatchingNotificationAudience(
            LineUserId("U-customer"),
            "王小姐",
            request.case_no,
        ),
        caregiver=MatchingNotificationAudience(
            LineUserId("U-caregiver"),
            "林月嫂",
            request.candidate_id,
        ),
        actor=ActorContext("admin:1", ("line.matching.send",)),
        scheduled_at=NOW,
        idempotency_key=IdempotencyKey("matching-assignment-notification:1"),
        correlation_id=CorrelationId("matching-assignment-correlation:1"),
    )


def test_assignment_conversion_command_rejects_mismatched_receipt_and_customer_subject() -> None:
    command = _assignment_conversion_notification()

    with pytest.raises(ValueError, match="receipt does not match request"):
        replace(
            command,
            receipt=replace(
                command.receipt,
                package_version=command.receipt.package_version + 1,
            ),
        )
    with pytest.raises(ValueError, match="customer subject reference"):
        replace(
            command,
            customer=replace(command.customer, subject_reference="CASE-WRONG"),
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


def test_assignment_conversion_enqueues_bilateral_created_user_texts_in_one_commit() -> None:
    unit_of_work = _UnitOfWork(_state())
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        availability_validator=lambda state: None,
    )
    command = _assignment_conversion_notification()

    result = application.notify_assignment_conversion(command)

    assert result.request_id == command.request.request_id
    assert result.customer_task_id == LineDeliveryTaskId(41)
    assert result.caregiver_task_id == LineDeliveryTaskId(42)
    assert result.replayed is False
    assert unit_of_work.committed
    customer, caregiver = unit_of_work.delivery_tasks.requests
    assert [customer.recipient.recipient_type, caregiver.recipient.recipient_type] == [
        LineRecipientType.USER,
        LineRecipientType.USER,
    ]
    assert [customer.recipient.identity, caregiver.recipient.identity] == [
        command.customer.line_user_id,
        command.caregiver.line_user_id,
    ]
    assert [customer.message_kind, caregiver.message_kind] == [
        LineMessageKind.TEXT,
        LineMessageKind.TEXT,
    ]
    assert [customer.source_aggregate_type, caregiver.source_aggregate_type] == [
        "assignment_conversion_receipt",
        "assignment_conversion_receipt",
    ]
    assert [customer.source_aggregate_identity, caregiver.source_aggregate_identity] == [
        command.receipt.request_id,
        command.receipt.request_id,
    ]
    assert customer.idempotency_key.value.startswith(
        "matching-assignment-notification:customer:"
    )
    assert caregiver.idempotency_key.value.startswith(
        "matching-assignment-notification:caregiver:"
    )
    assert customer.idempotency_key != caregiver.idempotency_key
    assert json.loads(customer.payload_json) == {
        "type": "text",
        "text": "媒合已完成，工會人員將提供後續服務資訊。",
    }
    assert json.loads(caregiver.payload_json) == {
        "type": "text",
        "text": "派案已完成，工會人員將提供後續服務資訊。",
    }
    internal_identities = (
        command.request.request_id,
        command.request.package_id,
        command.request.criteria_snapshot_id,
        command.request.candidate_id,
        command.receipt.assignment_reference,
    )
    assert all(
        identity not in delivery.payload_json
        for identity in internal_identities
        for delivery in (customer, caregiver)
    )


def test_assignment_conversion_bilateral_existing_is_a_committed_replay() -> None:
    unit_of_work = _UnitOfWork(
        _state(),
        (
            LineDeliveryCommandOutcome.EXISTING,
            LineDeliveryCommandOutcome.EXISTING,
        ),
    )
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        availability_validator=lambda state: None,
    )

    result = application.notify_assignment_conversion(
        _assignment_conversion_notification()
    )

    assert result.replayed is True
    assert result.customer_task_id == LineDeliveryTaskId(41)
    assert result.caregiver_task_id == LineDeliveryTaskId(42)
    assert unit_of_work.committed


def test_assignment_conversion_mixed_delivery_outcomes_fail_without_commit() -> None:
    unit_of_work = _UnitOfWork(
        _state(),
        (
            LineDeliveryCommandOutcome.CREATED,
            LineDeliveryCommandOutcome.EXISTING,
        ),
    )
    application = MatchingNotificationApplication(
        lambda: unit_of_work,
        lambda: NOW,
        availability_validator=lambda state: None,
    )

    with pytest.raises(MatchingCommunicationConflictError):
        application.notify_assignment_conversion(
            _assignment_conversion_notification()
        )

    assert len(unit_of_work.delivery_tasks.requests) == 2
    assert unit_of_work.committed is False

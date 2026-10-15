"""Formal LINE consent corrections retain recipient checks and replacement evidence."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domains.line.identities import LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingCommunicationConflictError,
    MatchingCommunicationStaleError,
    MatchingPlanReference,
    MatchingRecipientMismatchError,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication
from subsystems.scheduling.matching_notification_contracts import (
    MatchingContactState,
    MatchingResponseResult,
    MatchingSegmentContact,
)

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)
CAREGIVER = LineUserId("U-synthetic-caregiver")


class _Repository:
    def __init__(self, customer_decision, interaction_status):
        self.state = MatchingContactState(
            MatchingPlanReference("CASE-SYNTHETIC", 10, 0), "proposed", True, "洽談中",
            LineUserId("U-synthetic-customer"), customer_decision, None,
            (MatchingSegmentContact(20, 1, 30, "Synthetic caregiver", CAREGIVER,
                                    "2026-11-01", "2026-11-10", CaregiverWillingness.WILLING),),
        )
        self.interaction_data = {
            "case_no": self.state.plan.case_no, "plan_id": 10, "segment_id": 20,
            "recipient_line_user_id": CAREGIVER.value, "interaction_status": interaction_status,
            "expires_at_utc": NOW + timedelta(days=1), "action_scope": "caregiver_willingness",
        }
        self.events = []

    def interaction(self, token_hash):
        return self.interaction_data

    def get_contact_state(self, case_no, plan_id, *, lock=False):
        assert lock
        return self.state

    def append_response(self, **arguments):
        for event, receipt in self.events:
            if event["idempotency_key"] == arguments["idempotency_key"]:
                assert event["fingerprint"] == arguments["fingerprint"]
                return receipt
        willingness = CaregiverWillingness(arguments["response_value"])
        plan = replace(self.state.plan, version=self.state.plan.version + 1)
        self.state = replace(self.state, plan=plan, segments=(replace(self.state.segments[0], willingness=willingness),))
        receipt = MatchingResponseResult(
            len(self.events) + 1, plan, arguments["source"], caregiver_willingness=willingness,
            segment_id=20, idempotency_key=arguments["idempotency_key"],
        )
        self.events.append((arguments, receipt))
        if arguments["token_hash"] is not None:
            self.interaction_data["interaction_status"] = "consumed"
        return receipt


class _UnitOfWork:
    def __init__(self, decision=CustomerMatchingDecision.PENDING, interaction_status="active"):
        self.matching_notifications = _Repository(decision, interaction_status)
        self.requests = []
        self.delivery_tasks = SimpleNamespace(enqueue=self.requests.append)
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def commit(self):
        self.commits += 1


def _reply(unit_of_work, willingness, event="event-1", line_user_id=CAREGIVER):
    application = MatchingNotificationApplication(lambda: unit_of_work, lambda: NOW, availability_validator=lambda state: None)
    return application.record_line_response(
        token="synthetic-formal-line-interaction-token", decision=willingness,
        line_user_id=line_user_id, idempotency_key=IdempotencyKey(event),
        correlation_id=CorrelationId(event), occurred_at=NOW,
    )


@pytest.mark.parametrize("decision", [CustomerMatchingDecision.PENDING, CustomerMatchingDecision.CONTACT_REQUESTED])
@pytest.mark.parametrize("interaction_status", ["active", "consumed"])
def test_same_line_card_allows_repeated_changes_before_customer_confirmation(decision, interaction_status):
    unit_of_work = _UnitOfWork(decision, interaction_status)
    for version, willingness in enumerate(("unwilling", "willing", "unwilling"), start=1):
        result = _reply(unit_of_work, willingness, f"event-{version}")
        assert result.caregiver_willingness.value == willingness
        assert result.plan.version == version
        assert unit_of_work.matching_notifications.state.segments[0].willingness.value == willingness
    assert unit_of_work.commits == 3
    assert len(unit_of_work.matching_notifications.events) == 3
    assert all(event["token_hash"] is None for event, _ in unit_of_work.matching_notifications.events)
    assert unit_of_work.matching_notifications.state.customer_decision is decision


def test_withdrawal_after_customer_acceptance_preserves_decision_and_current_refusal():
    unit_of_work = _UnitOfWork(CustomerMatchingDecision.ACCEPTED, "consumed")
    unit_of_work.matching_notifications.state = replace(unit_of_work.matching_notifications.state, plan_status="accepted")
    result = _reply(unit_of_work, "unwilling")
    state = unit_of_work.matching_notifications.state
    assert result.caregiver_willingness is CaregiverWillingness.UNWILLING
    assert state.customer_decision is CustomerMatchingDecision.ACCEPTED
    assert state.plan_status == "accepted"
    assert not state.all_willing
    assert unit_of_work.commits == 1
    assert len(unit_of_work.requests) == 1  # Only the caregiver acknowledgement, no new matching-success message.


def test_duplicate_webhook_event_does_not_append_another_consent_change():
    unit_of_work = _UnitOfWork()
    original = _reply(unit_of_work, "unwilling")
    replay = _reply(unit_of_work, "unwilling")
    assert replay == original
    assert len(unit_of_work.matching_notifications.events) == 1
    assert unit_of_work.matching_notifications.state.plan.version == 1


@pytest.mark.parametrize("boundary,error", [
    ("interaction_recipient", MatchingRecipientMismatchError),
    ("current_recipient", MatchingRecipientMismatchError),
    ("expired", MatchingCommunicationStaleError),
    ("cancelled_interaction", MatchingCommunicationStaleError),
    ("inactive_plan", MatchingCommunicationStaleError),
    ("declined", MatchingCommunicationConflictError),
    ("restore_after_acceptance", MatchingCommunicationConflictError),
    ("consumed_customer_token", MatchingCommunicationStaleError),
])
def test_consent_correction_keeps_identity_lifetime_and_customer_decision_boundaries(boundary, error):
    unit_of_work = _UnitOfWork()
    repository = unit_of_work.matching_notifications
    target = "unwilling"
    if boundary == "interaction_recipient":
        repository.interaction_data["recipient_line_user_id"] = "U-someone-else"
    elif boundary == "current_recipient":
        repository.state = replace(repository.state, segments=(replace(repository.state.segments[0], staff_line_user_id=LineUserId("U-someone-else")),))
    elif boundary == "expired":
        repository.interaction_data["expires_at_utc"] = NOW
    elif boundary == "cancelled_interaction":
        repository.interaction_data["interaction_status"] = "cancelled"
    elif boundary == "inactive_plan":
        repository.state = replace(repository.state, plan_is_active=False)
    elif boundary == "declined":
        repository.state = replace(repository.state, customer_decision=CustomerMatchingDecision.DECLINED)
    elif boundary == "restore_after_acceptance":
        repository.state = replace(repository.state, customer_decision=CustomerMatchingDecision.ACCEPTED,
                                   segments=(replace(repository.state.segments[0], willingness=CaregiverWillingness.UNWILLING),))
        target = "willing"
    elif boundary == "consumed_customer_token":
        repository.interaction_data.update(action_scope="customer_decision", interaction_status="consumed")
    with pytest.raises(error):
        _reply(unit_of_work, target)
    assert not repository.events
    assert not unit_of_work.requests
    assert unit_of_work.commits == 0

"""Stage 7 pure matching communication rules."""

import pytest

from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingCommunicationConflictError,
    MatchingCommunicationStaleError,
    MatchingDecisionNotReadyError,
    MatchingPlanReference,
    MatchingRecipientMismatchError,
    record_caregiver_willingness,
    record_customer_decision,
    waiting_deposit_lock_is_allowed,
)


def test_caregiver_response_requires_active_plan_and_matching_recipient() -> None:
    with pytest.raises(MatchingCommunicationStaleError):
        record_caregiver_willingness(
            CaregiverWillingness.PENDING,
            CaregiverWillingness.WILLING,
            plan_is_active=False,
            recipient_matches=True,
        )
    with pytest.raises(MatchingRecipientMismatchError):
        record_caregiver_willingness(
            CaregiverWillingness.PENDING,
            CaregiverWillingness.WILLING,
            plan_is_active=True,
            recipient_matches=False,
        )


def test_replayed_response_is_idempotent_but_conflicting_response_is_rejected() -> None:
    replayed = record_caregiver_willingness(
        CaregiverWillingness.WILLING,
        CaregiverWillingness.WILLING,
        plan_is_active=True,
        recipient_matches=True,
    )
    assert replayed is CaregiverWillingness.WILLING

    with pytest.raises(MatchingCommunicationConflictError):
        record_caregiver_willingness(
            CaregiverWillingness.WILLING,
            CaregiverWillingness.UNWILLING,
            plan_is_active=True,
            recipient_matches=True,
        )


def test_customer_decision_requires_delivered_profiles() -> None:
    with pytest.raises(MatchingDecisionNotReadyError):
        record_customer_decision(
            CustomerMatchingDecision.PENDING,
            CustomerMatchingDecision.ACCEPTED,
            plan_is_active=True,
            recipient_matches=True,
            profiles_are_available=False,
        )


def test_only_customer_acceptance_allows_waiting_deposit_lock() -> None:
    assert waiting_deposit_lock_is_allowed(CustomerMatchingDecision.ACCEPTED)
    assert not waiting_deposit_lock_is_allowed(CustomerMatchingDecision.CONTACT_REQUESTED)
    assert not waiting_deposit_lock_is_allowed(CustomerMatchingDecision.DECLINED)


def test_matching_plan_reference_rejects_invalid_identity_or_version() -> None:
    with pytest.raises(ValueError):
        MatchingPlanReference("", 1, 0)
    with pytest.raises(ValueError):
        MatchingPlanReference("CASE-1", 0, 0)
    with pytest.raises(ValueError):
        MatchingPlanReference("CASE-1", 1, -1)

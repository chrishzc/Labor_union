"""
File: test_matching_coordination_contracts.py
Description: 驗證 M3 command 與 typed view／error 邊界。
"""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone

import pytest

from domains.scheduling.matching_coordination import (
    CandidateEligibility,
    MatchingCandidateResult,
    MatchingCriteriaSnapshot,
    MatchingPackage,
    MatchingPackageMode,
    MatchingSegment,
    MatchingSourceVersion,
    SOURCE_KINDS,
    StableRejectionReason,
    build_criteria_snapshot,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyInitialCriteriaSnapshot,
    ApplyCaregiverSelection,
    ApplyCriteriaDiffResend,
    ApplyCustomerMatchingDecision,
    ApplyLeaveImpactOnMatching,
    ApplyRematch,
    ApplyServiceDateChangeRematch,
    ApplyZeroCandidateAlternative,
    ApplyZeroCandidateConfirmation,
    MatchingCommandName,
    MatchingApplyReceipt,
    MatchingNotificationIntentProjection,
    MatchingNotificationRecipientRole,
    PreviewCriteriaDiffResend,
    PreviewInitialCriteriaSnapshot,
    PreviewLeaveImpactOnMatching,
    PreviewMatchingPackage,
    PreviewRematch,
    PreviewServiceDateChangeRematch,
    PreviewZeroCandidateAlternative,
    PreviewZeroCandidateConfirmation,
    QueryMatchingCoordination,
    command_fingerprint,
    candidate_view,
    snapshot_view,
)


def _sources() -> tuple[MatchingSourceVersion, ...]:
    return tuple(MatchingSourceVersion(kind, f"{kind}:1", 1, "b" * 64) for kind in SOURCE_KINDS)


def _common() -> dict[str, object]:
    return {
        "case_no": "CASE-001",
        "actor": ActorContext("admin_user_id:1"),
        "reason": "matching review",
        "correlation_id": CorrelationId("corr-matching-1"),
        "idempotency_key": IdempotencyKey("matching:case-001:1"),
        "expected_source_versions": _sources(),
    }


def test_all_eighteen_commands_have_stable_names_and_common_identity() -> None:
    fp = fingerprint_payload({"preview": "a"})
    values = [
        QueryMatchingCoordination(
            case_no="CASE-001",
            actor=ActorContext("admin_user_id:1"),
            correlation_id=CorrelationId("corr-matching-query-1"),
            expected_source_versions=_sources(),
        ),
        PreviewInitialCriteriaSnapshot(**_common()),
        ApplyInitialCriteriaSnapshot(**_common(), preview_fingerprint=fp),
        PreviewMatchingPackage(**_common(), criteria_snapshot_id="snapshot-1", required_service_dates=(date(2026, 9, 1),)),
        PreviewCriteriaDiffResend(**_common(), before_snapshot_id="before", after_snapshot_id="after"),
        ApplyCriteriaDiffResend(**_common(), before_snapshot_id="before", after_snapshot_id="after", preview_fingerprint=fp, recipient_ids=("candidate-1",)),
        PreviewZeroCandidateAlternative(**_common(), criteria_snapshot_id="snapshot-1", policy_id="policy-v1", policy_version=1),
        ApplyZeroCandidateAlternative(**_common(), criteria_snapshot_id="snapshot-1", alternative_id="alternative-1", policy_id="policy-v1", policy_version=1, relaxed_criteria=("service_days",), preview_fingerprint=fp),
        PreviewZeroCandidateConfirmation(
            **_common(),
            criteria_snapshot_id="snapshot-1",
            package_id="package-open",
            package_version=2,
            evidence=("fresh_pool_query_empty",),
        ),
        ApplyZeroCandidateConfirmation(
            **_common(),
            criteria_snapshot_id="snapshot-1",
            package_id="package-open",
            package_version=2,
            evidence=("fresh_pool_query_empty",),
            preview_fingerprint=fp,
        ),
        ApplyCaregiverSelection(**_common(), criteria_snapshot_id="snapshot-1", package_id="package-1", package_version=1, candidate_id="candidate-1", willingness="willing", reason_code=None, affected_criteria=(), preview_fingerprint=fp),
        ApplyCustomerMatchingDecision(**_common(), criteria_snapshot_id="snapshot-1", package_id="package-1", package_version=1, candidate_id="candidate-1", decision="accepted", preview_fingerprint=fp),
        PreviewRematch(**_common(), criteria_snapshot_id="snapshot-1"),
        ApplyRematch(**_common(), criteria_snapshot_id="snapshot-1", package_id="package-1", preview_fingerprint=fp),
        PreviewLeaveImpactOnMatching(**_common(), package_id="package-1", leave_reference="leave-1"),
        ApplyLeaveImpactOnMatching(
            **_common(),
            package_id="package-1",
            leave_reference="leave-1",
            criteria_snapshot_id="snapshot-1",
            expected_leave_version=1,
            original_staff_id=17,
            preview_fingerprint=fp,
        ),
        PreviewServiceDateChangeRematch(
            **_common(),
            criteria_snapshot_id="snapshot-1",
            assignment_id=31,
            original_staff_id=17,
            original_service_dates=(date(2026, 9, 1),),
            shifted_service_dates=(date(2026, 9, 2),),
        ),
        ApplyServiceDateChangeRematch(
            **_common(),
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
            assignment_id=31,
            original_staff_id=17,
            original_service_dates=(date(2026, 9, 1),),
            shifted_service_dates=(date(2026, 9, 2),),
            preview_fingerprint=fp,
        ),
    ]

    assert [item.command_name.value for item in values] == [item.value for item in MatchingCommandName]
    assert all(command_fingerprint(item).value for item in values)


def test_initial_preview_allows_no_prior_client_source_tuple() -> None:
    command = PreviewInitialCriteriaSnapshot(
        **{**_common(), "expected_source_versions": None}
    )

    assert command.expected_source_versions is None
    with pytest.raises(TypeError, match="source versions are required"):
        ApplyInitialCriteriaSnapshot(
            **{**_common(), "expected_source_versions": None},
            preview_fingerprint=fingerprint_payload({"preview": "initial"}),
        )


def test_snapshot_view_thaws_nested_immutable_criteria_for_transport() -> None:
    snapshot = build_criteria_snapshot(
        snapshot_id="matching:CASE-001:criteria:1:transport",
        case_no="CASE-001",
        criteria_version=1,
        criteria={"nested": {"service": ("day-1", "day-2")}},
        source_versions=_sources(),
        created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    view = snapshot_view(snapshot)

    assert dict(view.criteria)["nested"] == {"service": ("day-1", "day-2")}


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("assignment_id", 0),
        ("original_staff_id", 0),
        ("original_service_dates", ()),
        (
            "shifted_service_dates",
            (date(2026, 9, 3), date(2026, 9, 2)),
        ),
        ("shifted_service_dates", (date(2026, 9, 1),)),
    ),
)
def test_service_date_command_rejects_incomplete_or_noncanonical_identity(
    field: str,
    value: object,
) -> None:
    payload = {
        **_common(),
        "criteria_snapshot_id": "snapshot-1",
        "assignment_id": 31,
        "original_staff_id": 17,
        "original_service_dates": (date(2026, 9, 1),),
        "shifted_service_dates": (date(2026, 9, 2),),
        field: value,
    }

    with pytest.raises((TypeError, ValueError)):
        PreviewServiceDateChangeRematch(**payload)


def test_apply_contract_preserves_explicit_preview_fingerprint() -> None:
    command = ApplyCustomerMatchingDecision(
        **_common(),
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        candidate_id="candidate-1",
        decision="accepted",
        preview_fingerprint=fingerprint_payload({"preview": "a"}),
    )
    assert command.preview_fingerprint.value == fingerprint_payload({"preview": "a"}).value


def test_candidate_view_exposes_stable_rejection_codes_as_strings() -> None:
    candidate = MatchingCandidateResult(
        "candidate-view",
        7,
        CandidateEligibility.INELIGIBLE,
        (),
        rejection_reasons=(StableRejectionReason.BUFFER_CONFLICT,),
    )

    view = candidate_view(candidate)

    assert view.rejection_reasons == ("buffer_conflict",)
    assert all(type(reason) is str for reason in view.rejection_reasons)


def test_accepted_matching_projects_exactly_customer_and_caregiver_notifications() -> None:
    package_fingerprint = fingerprint_payload({"package": "package-1"})
    customer_key = IdempotencyKey("matching:case-001:customer-notification")
    caregiver_key = IdempotencyKey("matching:case-001:caregiver-notification")
    customer = MatchingNotificationIntentProjection(
        intent_id="intent:customer",
        recipient_role=MatchingNotificationRecipientRole.CUSTOMER,
        recipient_subject_reference="customer:CASE-001",
        source_decision_event_id="decision:event-1",
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        package_fingerprint=package_fingerprint,
        candidate_id="candidate-1",
        idempotency_key=customer_key,
    )
    caregiver = MatchingNotificationIntentProjection(
        intent_id="intent:caregiver",
        recipient_role=MatchingNotificationRecipientRole.CAREGIVER,
        recipient_subject_reference="caregiver:candidate-1",
        source_decision_event_id="decision:event-1",
        criteria_snapshot_id="snapshot-1",
        package_id="package-1",
        package_version=1,
        package_fingerprint=package_fingerprint,
        candidate_id="candidate-1",
        idempotency_key=caregiver_key,
    )

    receipt = MatchingApplyReceipt(
        receipt_id="receipt-1",
        command_name=MatchingCommandName.APPLY_CUSTOMER_DECISION,
        command_fingerprint=package_fingerprint,
        preview_fingerprint=package_fingerprint,
        source_versions=_sources(),
        decision_event_id="decision:event-1",
        package_id="package-1",
        outbox_intent_ids=(),
        result_state="accepted",
        notification_intents=(customer, caregiver),
    )

    assert {item.recipient_role for item in receipt.notification_intents} == {
        MatchingNotificationRecipientRole.CUSTOMER,
        MatchingNotificationRecipientRole.CAREGIVER,
    }
    assert all(item.package_fingerprint is package_fingerprint for item in receipt.notification_intents)
    assert customer.idempotency_key is customer_key
    assert caregiver.idempotency_key is caregiver_key
    with pytest.raises(FrozenInstanceError):
        customer.intent_id = "mutated"  # type: ignore[misc]
    with pytest.raises(ValueError):
        MatchingNotificationIntentProjection(
            "intent:invalid",
            "operator",
            "subject:invalid",
            "decision:event-1",
            "snapshot-1",
            "package-1",
            1,
            package_fingerprint,
            "candidate-1",
            IdempotencyKey("matching:case-001:invalid-notification"),
        )

    existing_receipt = MatchingApplyReceipt(
        "receipt-2",
        MatchingCommandName.APPLY_CUSTOMER_DECISION,
        package_fingerprint,
        package_fingerprint,
        _sources(),
        None,
        "package-1",
        (),
        "accepted",
    )
    assert existing_receipt.notification_intents == ()
    PreviewInitialCriteriaSnapshot,

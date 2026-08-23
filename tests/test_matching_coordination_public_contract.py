"""
File: test_matching_coordination_public_contract.py
Description: 驗證 Matching Coordination source-version closed schema。
"""

import pytest
from pydantic import ValidationError

from api.schemas.matching_coordination import (
    ApplyCaregiverSelectionRequest,
    ApplyCriteriaDiffRequest,
    ApplyCustomerDecisionRequest,
    ApplyLeaveImpactRequest,
    ApplyRematchRequest,
    ApplyServiceDateRematchRequest,
    ApplyZeroCandidateRequest,
    MatchingCandidateResultTransportView,
    MatchingCriteriaResultTransportView,
    MatchingCriteriaSnapshotView,
    MatchingCoordinationQueryResponse,
    MatchingApplyReceiptResponse,
    PreviewCriteriaDiffRequest,
    RefusalRoutingTransportView,
    CriteriaDiffTransportView,
    PreviewZeroCandidateRequest,
    ZeroCandidateAlternativeTransportView,
    PreviewMatchingPackageRequest,
    PreviewLeaveImpactRequest,
    LeaveImpactPreviewResponse,
    PreviewServiceDateRematchRequest,
    ServiceDateRematchPreviewResponse,
    ServiceDateShiftAvailabilityConfirmationTransportView,
    ServiceDateShiftReassignmentReferenceTransportView,
    MatchingPackageTransportView,
    RefusalHistoryTransportView,
    DynamicWillingnessLineageTransportView,
    MatchingCriteriaRecontactIntentTransportView,
    MatchingSourceTupleView,
    MatchingSourceVersionView,
)
from domains.scheduling.matching_coordination import (
    SOURCE_KINDS,
    CandidateEligibility,
    CriterionStatus,
    MatchingCriteriaSnapshot,
    MatchingCandidateResult,
    MatchingCriteriaResult,
    MatchingPackage,
    MatchingPackageMode,
    MatchingSegment,
    MatchingPackageState,
    MatchingSourceVersion,
    MatchingCriteriaDiff,
    RefusalRouting,
    RefusalRoutingGroup,
    RefusalHistoryEntry,
    DynamicWillingnessLineage,
    ZeroCandidateAlternative,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.fingerprints import PreviewFingerprint
from domains.scheduling.leave_substitution import LeaveResolutionType
from subsystems.scheduling.matching_leave_integration import MatchingLeaveImpactResult
from subsystems.scheduling.matching_coordination_workflow import (
    ServiceDateShiftAvailabilityConfirmation,
    ServiceDateShiftReassignmentReference,
)
from subsystems.scheduling.matching_coordination_contracts import (
    MatchingApplyReceipt,
    MatchingCommandName,
    candidate_view,
    criteria_diff_view,
    snapshot_view,
)
from subsystems.scheduling.matching_coordination_query import MatchingCoordinationQueryResult


def _source(kind: str, index: int) -> MatchingSourceVersion:
    return MatchingSourceVersion(kind, f"source-{index}", index, "a" * 64)


def test_source_version_from_attributes_and_canonical_tuple() -> None:
    items = tuple(_source(kind, index) for index, kind in enumerate(SOURCE_KINDS))
    result = MatchingSourceTupleView.model_validate({"items": items})
    assert tuple(item.source_kind for item in result.items) == SOURCE_KINDS
    assert result.items[0].source_id == "source-0"


def test_source_tuple_rejects_noncanonical_order_and_extra() -> None:
    items = tuple(_source(kind, index) for index, kind in enumerate(reversed(SOURCE_KINDS)))
    with pytest.raises(ValidationError):
        MatchingSourceTupleView.model_validate({"items": items})
    with pytest.raises(ValidationError):
        MatchingSourceVersionView.model_validate({"source_kind": SOURCE_KINDS[0], "source_id": "x", "version": 1, "fingerprint": "a" * 64, "extra": True})


def test_source_version_rejects_bad_fingerprint_and_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        MatchingSourceVersionView.model_validate({"source_kind": SOURCE_KINDS[0], "source_id": "x", "version": 1, "fingerprint": "bad"})
    with pytest.raises(ValidationError):
        MatchingSourceVersionView.model_validate({"source_kind": "unknown", "source_id": "x", "version": 1, "fingerprint": "a" * 64})


def test_criteria_snapshot_maps_domain_attributes_and_forbids_extra() -> None:
    from datetime import datetime, timezone

    snapshot = MatchingCriteriaSnapshot(
        snapshot_id="snapshot-1",
        case_no="case-1",
        criteria_version=1,
        criteria={"region": "north"},
        source_versions=tuple(_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)),
        fingerprint=fingerprint_payload(
            {
                "case_no": "case-1",
                "criteria": {"region": "north"},
                "criteria_version": 1,
                "source_versions": [
                    item.as_payload()
                    for item in tuple(_source(kind, index) for index, kind in enumerate(SOURCE_KINDS))
                ],
            }
        ),
        created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    result = MatchingCriteriaSnapshotView.model_validate(snapshot)
    assert result.criteria == (("region", "north"),)
    assert result.fingerprint == snapshot.fingerprint.value
    with pytest.raises(ValidationError):
        MatchingCriteriaSnapshotView.model_validate({**result.model_dump(), "extra": True})


def test_candidate_result_maps_domain_and_rejects_unknown_transport_enums() -> None:
    candidate = MatchingCandidateResult(
        candidate_id="candidate-1",
        staff_id=7,
        eligibility=CandidateEligibility.ELIGIBLE,
        criteria_results=(
            MatchingCriteriaResult(
                code="region",
                status=CriterionStatus.MATCHED,
                source_version=_source(SOURCE_KINDS[0], 1),
            ),
        ),
        coverage_evidence=(),
        willingness="willing",
        notification_lineage=(),
    )
    result = MatchingCandidateResultTransportView.model_validate(candidate)
    assert result.criteria_results[0].status == "matched"
    assert result.willingness == "willing"
    with pytest.raises(ValidationError):
        MatchingCandidateResultTransportView.model_validate(
            {**result.model_dump(), "eligibility": "unknown"}
        )
    with pytest.raises(ValidationError):
        MatchingCandidateResultTransportView.model_validate(
            {**result.model_dump(), "willingness": "unknown"}
        )
    with pytest.raises(ValueError, match="supported state"):
        MatchingCandidateResult(
            candidate_id="candidate-invalid",
            staff_id=8,
            eligibility=CandidateEligibility.ELIGIBLE,
            criteria_results=(),
            willingness="unknown",
        )


def test_package_maps_domain_segment_and_rejects_unknown_mode_or_state() -> None:
    from datetime import date

    service_day = date(2026, 8, 22)
    package = MatchingPackage(
        package_id="package-1",
        version=1,
        mode=MatchingPackageMode.SINGLE,
        segments=(MatchingSegment(7, (service_day,), 1),),
        required_service_dates=(service_day,),
        candidate_results=(),
        criteria_snapshot_id="snapshot-1",
        source_versions=tuple(_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)),
        state=MatchingPackageState.PROPOSED,
    )

    result = MatchingPackageTransportView.model_validate(package)
    assert result.segments[0].staff_id == 7
    assert result.segments[0].sequence == 1
    with pytest.raises(ValidationError):
        MatchingPackageTransportView.model_validate({**result.model_dump(), "mode": "unknown"})
    with pytest.raises(ValidationError):
        MatchingPackageTransportView.model_validate({**result.model_dump(), "state": "unknown"})


def test_refusal_and_willingness_lineage_map_and_reject_unknown_state() -> None:
    refusal = RefusalHistoryEntry(
        refusal_id="refusal-1",
        candidate_id="candidate-1",
        snapshot_id="snapshot-1",
        reason_code="region_mismatch",
        affected_criteria=("region",),
        originally_willing=True,
        pain_resolved=False,
    )
    lineage = DynamicWillingnessLineage(
        event_id="event-1",
        candidate_id="candidate-1",
        staff_id=7,
        snapshot_id="snapshot-1",
        source_versions=tuple(_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)),
        previous_state="pending",
        current_state="willing",
        affected_criteria=("region",),
    )

    refusal_result = RefusalHistoryTransportView.model_validate(refusal)
    lineage_result = DynamicWillingnessLineageTransportView.model_validate(lineage)
    assert refusal_result.reason_code == "region_mismatch"
    assert lineage_result.current_state == "willing"
    with pytest.raises(ValidationError):
        DynamicWillingnessLineageTransportView.model_validate(
            {**lineage_result.model_dump(), "current_state": "unknown"}
        )
    stale_lineage = DynamicWillingnessLineage(
        event_id="event-stale",
        candidate_id="candidate-1",
        staff_id=7,
        snapshot_id="snapshot-1",
        source_versions=tuple(_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)),
        previous_state="willing",
        current_state="stale",
        affected_criteria=("region",),
    )
    assert DynamicWillingnessLineageTransportView.model_validate(stale_lineage).current_state == "stale"


def test_query_response_maps_all_nested_domain_views() -> None:
    from datetime import datetime, timezone

    sources = tuple(_source(kind, index) for index, kind in enumerate(SOURCE_KINDS))
    snapshot = MatchingCriteriaSnapshot(
        snapshot_id="snapshot-query-1",
        case_no="case-query-1",
        criteria_version=1,
        criteria={"region": "north"},
        source_versions=sources,
        fingerprint=fingerprint_payload(
            {
                "case_no": "case-query-1",
                "criteria": {"region": "north"},
                "criteria_version": 1,
                "source_versions": [item.as_payload() for item in sources],
            }
        ),
        created_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    candidate = MatchingCandidateResult(
        candidate_id="candidate-query-1",
        staff_id=7,
        eligibility=CandidateEligibility.ELIGIBLE,
        criteria_results=(
            MatchingCriteriaResult(
                code="region",
                status=CriterionStatus.MATCHED,
                source_version=sources[0],
            ),
        ),
        willingness="willing",
    )
    refusal = RefusalHistoryEntry(
        refusal_id="refusal-query-1",
        candidate_id="candidate-query-1",
        snapshot_id=snapshot.snapshot_id,
        reason_code="region_mismatch",
    )
    lineage = DynamicWillingnessLineage(
        event_id="lineage-query-1",
        candidate_id="candidate-query-1",
        staff_id=7,
        snapshot_id=snapshot.snapshot_id,
        source_versions=sources,
        previous_state="pending",
        current_state="willing",
        affected_criteria=("region",),
    )
    query_result = MatchingCoordinationQueryResult(
        case_no=snapshot.case_no,
        snapshot=snapshot_view(snapshot),
        package=None,
        candidates=(candidate_view(candidate),),
        source_versions=sources,
        refusal_history=(refusal,),
        willingness_lineage=(lineage,),
        expected_source_versions_match=True,
    )

    result = MatchingCoordinationQueryResponse.model_validate(query_result)
    assert result.candidates[0].candidate_id == "candidate-query-1"
    assert result.refusal_history[0].reason_code == "region_mismatch"
    assert result.willingness_lineage[0].current_state == "willing"
    assert tuple(item.source_kind for item in result.source_versions.items) == SOURCE_KINDS


def test_criteria_diff_transport_maps_and_request_is_closed() -> None:
    route = RefusalRouting(
        candidate_id="candidate-1",
        refusal_id="refusal-1",
        group=RefusalRoutingGroup.GROUP1_ORIGINAL_WILLING_RECONFIRM,
        action="reconfirm",
        reason_code="region_mismatch",
        source_snapshot_id="before-1",
        diff_fingerprint=PreviewFingerprint("a" * 64),
    )
    diff = MatchingCriteriaDiff(
        before_snapshot_id="before-1",
        after_snapshot_id="after-1",
        added=("region",),
        removed=(),
        changed=("region",),
        unchanged=(),
        affected_candidate_ids=("candidate-1",),
        affected_recipient_ids=("recipient-1",),
        resend_eligible=True,
        fingerprint=PreviewFingerprint("b" * 64),
        refusal_routes=(route,),
    )

    result = CriteriaDiffTransportView.model_validate(criteria_diff_view(diff))
    assert result.refusal_routes[0].group == "group1_original_willing_reconfirm"
    assert result.diff_fingerprint == "b" * 64
    body = PreviewCriteriaDiffRequest.model_validate(
        {
            "reason": "criteria changed",
            "expected_source_versions": {
                "items": [_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)]
            },
            "before_snapshot_id": "before-1",
            "after_snapshot_id": "after-1",
        }
    )
    assert body.before_snapshot_id == "before-1"
    with pytest.raises(ValidationError):
        PreviewCriteriaDiffRequest.model_validate(
            {**body.model_dump(), "extra": True}
        )
    with pytest.raises(ValidationError):
        CriteriaDiffTransportView.model_validate(
            {
                **result.model_dump(),
                "refusal_routes": [
                    {**result.model_dump()["refusal_routes"][0], "group": "unknown"}
                ],
            }
        )


def test_zero_candidate_alternative_maps_and_preview_body_is_closed() -> None:
    candidate = MatchingCandidateResult(
        candidate_id="candidate-zero-1",
        staff_id=9,
        eligibility=CandidateEligibility.ELIGIBLE,
        criteria_results=(),
        willingness="willing",
    )
    alternative = ZeroCandidateAlternative(
        alternative_id="alternative-1",
        policy_id="policy-1",
        policy_version=2,
        relaxed_criteria=("region",),
        unchanged_hard_criteria=("service_date",),
        candidate_result=candidate,
        risk_warnings=("coverage_incomplete",),
        deterministic_rank=1,
        preview_fingerprint=PreviewFingerprint("c" * 64),
    )

    result = ZeroCandidateAlternativeTransportView.model_validate(alternative)
    assert result.candidate_result is not None
    assert result.candidate_result.candidate_id == "candidate-zero-1"
    assert result.preview_fingerprint == "c" * 64
    body = PreviewZeroCandidateRequest.model_validate(
        {
            "reason": "no candidate",
            "expected_source_versions": {
                "items": [_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)]
            },
            "criteria_snapshot_id": "snapshot-1",
            "policy_id": "policy-1",
            "policy_version": 2,
            "relaxed_criteria": ["requires_cooking"],
        }
    )
    assert body.policy_version == 2
    with pytest.raises(ValidationError):
        PreviewZeroCandidateRequest.model_validate({**body.model_dump(), "extra": True})


def test_matching_package_preview_body_enforces_date_canonicality_and_extra() -> None:
    from datetime import date

    source_payload = {
        "items": [_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)]
    }
    body = PreviewMatchingPackageRequest.model_validate(
        {
            "reason": "package preview",
            "expected_source_versions": source_payload,
            "criteria_snapshot_id": "snapshot-1",
            "required_service_dates": [date(2026, 8, 22)],
            "segments": [
                {
                    "staff_id": 7,
                    "service_dates": [date(2026, 8, 22)],
                    "sequence": 1,
                }
            ],
        }
    )
    assert body.required_service_dates == (date(2026, 8, 22),)
    assert body.segments[0].staff_id == 7
    with pytest.raises(ValidationError):
        PreviewMatchingPackageRequest.model_validate({**body.model_dump(), "extra": True})
    with pytest.raises(ValidationError):
        PreviewMatchingPackageRequest.model_validate(
            {
                **body.model_dump(),
                "required_service_dates": [date(2026, 8, 23), date(2026, 8, 22)],
            }
        )


def test_leave_preview_maps_typed_result_and_rejects_unknown_state() -> None:
    from datetime import date

    result = MatchingLeaveImpactResult(
        receipt_key="leave-receipt-1",
        result_state="leave_substituted",
        package_id="package-1",
        criteria_snapshot_id="snapshot-1",
        rematch_required=True,
        resolution_type=LeaveResolutionType.SUBSTITUTE,
        original_work_date=date(2026, 8, 22),
        resulting_work_date=date(2026, 8, 22),
        outcome_event_ids=("event-1",),
        receipt_fingerprint=PreviewFingerprint("d" * 64),
        substitute_staff_id=11,
    )
    response = LeaveImpactPreviewResponse.model_validate(result)
    assert response.resolution_type == "substitute"
    assert response.receipt_fingerprint == "d" * 64
    with pytest.raises(ValidationError):
        LeaveImpactPreviewResponse.model_validate(
            {**response.model_dump(), "result_state": "unknown"}
        )
    with pytest.raises(ValidationError):
        LeaveImpactPreviewResponse.model_validate(
            {**response.model_dump(), "extra": True}
        )

    body = PreviewLeaveImpactRequest.model_validate(
        {
            "reason": "leave impact preview",
            "expected_source_versions": {
                "items": [_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)]
            },
            "package_id": "package-1",
            "criteria_snapshot_id": "snapshot-1",
            "receipt_key": "leave-receipt-1",
            "expected_leave_version": 1,
            "original_staff_id": 7,
        }
    )
    assert body.original_staff_id == 7
    with pytest.raises(ValidationError):
        PreviewLeaveImpactRequest.model_validate({**body.model_dump(), "extra": True})


def test_service_date_preview_body_is_closed_and_supports_optional_package() -> None:
    from datetime import date

    body = PreviewServiceDateRematchRequest.model_validate(
        {
            "reason": "service date changed",
            "expected_source_versions": {
                "items": [_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)]
            },
            "criteria_snapshot_id": "snapshot-1",
            "package_id": "package-1",
            "assignment_id": 17,
            "original_staff_id": 7,
            "original_service_dates": [date(2026, 8, 22)],
            "shifted_service_dates": [date(2026, 8, 23)],
        }
    )
    assert body.package_id == "package-1"
    assert body.assignment_id == 17
    with pytest.raises(ValidationError):
        PreviewServiceDateRematchRequest.model_validate({**body.model_dump(), "extra": True})
    with pytest.raises(ValidationError):
        PreviewServiceDateRematchRequest.model_validate(
            {**body.model_dump(), "shifted_service_dates": body.original_service_dates}
        )


def test_service_date_preview_response_requires_one_typed_outcome() -> None:
    from datetime import date

    confirmation = ServiceDateShiftAvailabilityConfirmation(
        intent_id="matching:case-1:service-date-approval:1:" + "e" * 64,
        case_no="case-1",
        assignment_id=1,
        staff_id=7,
        original_service_dates=(date(2026, 8, 22),),
        shifted_service_dates=(date(2026, 8, 23),),
        source_fingerprint=PreviewFingerprint("e" * 64),
    )
    projected_confirmation = ServiceDateShiftAvailabilityConfirmationTransportView.model_validate(
        confirmation
    )
    response = ServiceDateRematchPreviewResponse(
        outcome_kind="availability_confirmation",
        availability_confirmation=projected_confirmation,
    )
    assert response.availability_confirmation == projected_confirmation
    with pytest.raises(ValidationError):
        ServiceDateRematchPreviewResponse(
            outcome_kind="availability_confirmation",
            reassignment_reference={
                "queue_reference": "queue-1",
                "case_no": "case-1",
                "assignment_id": 1,
                "staff_id": 7,
                "shifted_service_dates": [date(2026, 8, 23)],
                "conflict_source_ids": ["availability:block:1"],
                "source_fingerprint": "f" * 64,
            },
        )

    reassignment = ServiceDateShiftReassignmentReference(
        queue_reference="matching:case-1:service-date-reassignment:1:" + "f" * 64,
        case_no="case-1",
        assignment_id=1,
        staff_id=7,
        shifted_service_dates=(date(2026, 8, 23),),
        conflict_source_ids=("availability:block:1",),
        source_fingerprint=PreviewFingerprint("f" * 64),
    )
    projected = ServiceDateShiftReassignmentReferenceTransportView.model_validate(reassignment)
    assert projected.queue_reference == reassignment.queue_reference


def test_apply_transport_requests_and_receipt_are_closed() -> None:
    from datetime import date

    source_payload = {
        "items": [_source(kind, index) for index, kind in enumerate(SOURCE_KINDS)]
    }
    common = {
        "reason": "approved matching action",
        "expected_source_versions": source_payload,
        "preview_fingerprint": "a" * 64,
    }
    requests = (
        ApplyCriteriaDiffRequest(
            **common,
            before_snapshot_id="before-1",
            after_snapshot_id="after-1",
            recipient_ids=("candidate-1",),
        ),
        ApplyZeroCandidateRequest(
            **common,
            criteria_snapshot_id="snapshot-1",
            alternative_id="alternative-1",
            policy_id="policy-1",
            policy_version=1,
            relaxed_criteria=("requires_cooking",),
            decision="agree",
        ),
        ApplyCaregiverSelectionRequest(
            **common,
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
            package_version=1,
            candidate_id="candidate-1",
            willingness="willing",
        ),
        ApplyCustomerDecisionRequest(
            **common,
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
            package_version=1,
            candidate_id="candidate-1",
            decision="accepted",
        ),
        ApplyRematchRequest(
            **common,
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
        ),
        ApplyLeaveImpactRequest(
            **common,
            package_id="package-1",
            leave_reference="leave-receipt-1",
        ),
        ApplyServiceDateRematchRequest(
            **common,
            criteria_snapshot_id="snapshot-1",
            package_id="package-1",
            assignment_id=17,
            original_staff_id=7,
            original_service_dates=(date(2026, 9, 1),),
            shifted_service_dates=(date(2026, 9, 2),),
        ),
    )
    assert len(requests) == 7
    with pytest.raises(ValidationError):
        ApplyCustomerDecisionRequest.model_validate(
            {**requests[3].model_dump(), "decision": "unknown"}
        )

    receipt = MatchingApplyReceipt(
        receipt_id="receipt-1",
        command_name=MatchingCommandName.APPLY_REMATCH,
        command_fingerprint=PreviewFingerprint("b" * 64),
        preview_fingerprint=PreviewFingerprint("a" * 64),
        source_versions=tuple(
            _source(kind, index) for index, kind in enumerate(SOURCE_KINDS)
        ),
        decision_event_id=None,
        package_id="package-1",
        outbox_intent_ids=(),
        result_state="rematch_required",
    )
    projected_receipt = MatchingApplyReceiptResponse.model_validate(receipt)
    assert projected_receipt.command_name == "ApplyRematch"
    assert projected_receipt.result_state == "rematch_required"


def test_criteria_recontact_intent_transport_is_closed_and_preserves_lineage() -> None:
    payload = {
        "intent_id": "matching:case-001:resend:criteria-resend:candidate-1",
        "recipient_subject_reference": "staff:7",
        "candidate_id": "candidate-1",
        "staff_id": 7,
        "route_group": "group1_original_willing_reconfirm",
        "action": "reconfirm",
        "reason_code": "willingness_unconfirmed",
        "before_snapshot_id": "snapshot-before",
        "after_snapshot_id": "snapshot-after",
        "diff_fingerprint": "d" * 64,
        "source_versions": {
            "items": [
                _source(kind, index) for index, kind in enumerate(SOURCE_KINDS)
            ]
        },
        "idempotency_key": "matching:case-001:resend",
        "package_id": None,
        "package_version": None,
        "package_fingerprint": None,
    }

    intent = MatchingCriteriaRecontactIntentTransportView.model_validate(payload)
    assert intent.action == "reconfirm"
    assert intent.reason_code.value == "willingness_unconfirmed"
    assert intent.before_snapshot_id == "snapshot-before"
    with pytest.raises(ValidationError, match="route group"):
        MatchingCriteriaRecontactIntentTransportView.model_validate(
            {**payload, "action": "reprobe"}
        )
    with pytest.raises(ValidationError, match="package lineage"):
        MatchingCriteriaRecontactIntentTransportView.model_validate(
            {**payload, "package_id": "package-1"}
        )


def test_service_date_availability_confirmation_maps_from_attributes() -> None:
    from datetime import date

    typed = ServiceDateShiftAvailabilityConfirmation(
        intent_id="intent-1",
        case_no="case-1",
        assignment_id=7,
        staff_id=11,
        original_service_dates=(date(2026, 8, 22),),
        shifted_service_dates=(date(2026, 8, 23),),
        source_fingerprint=PreviewFingerprint("e" * 64),
    )
    result = ServiceDateShiftAvailabilityConfirmationTransportView.model_validate(typed)
    assert result.intent_id == "intent-1"
    assert result.source_fingerprint == "e" * 64

"""
File: test_matching_coordination_leave_and_date_rematch.py
Description: 驗證 M3 leave defer 的 canonical receipt 投影與 rematch 標記。
"""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from domains.scheduling.leave_substitution import LeaveResolutionType
from domains.scheduling.matching_coordination import SOURCE_KINDS, MatchingSourceVersion
from domains.scheduling.staff_availability import StaffAvailabilityConflict, StaffAvailabilityFacts
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId
from subsystems.scheduling.matching_leave_integration import (
    CanonicalSchedulingLeaveReference,
    MatchingLeaveImpactRequest,
    MatchingLeaveIntegration,
    MatchingLeaveIntegrationError,
)
from subsystems.scheduling.matching_coordination_workflow import (
    MatchingCoordinationWorkflow,
    ServiceDateShiftAvailabilityConfirmation,
    ServiceDateShiftReassignmentReference,
)


class FakeLeaveReferencePort:
    def __init__(self, reference: CanonicalSchedulingLeaveReference | None) -> None:
        self.reference = reference
        self.calls: list[str] = []

    def get_canonical_receipt(self, receipt_key: str) -> CanonicalSchedulingLeaveReference | None:
        self.calls.append(receipt_key)
        return self.reference


def _availability(*, conflicts: tuple[StaffAvailabilityConflict, ...] = ()) -> StaffAvailabilityFacts:
    return StaffAvailabilityFacts(
        staff_id=17,
        aggregate_version=4,
        blocks=(),
        conflicts=conflicts,
    )


def test_service_date_shift_confirms_original_caregiver_when_owner_facts_are_available() -> None:
    result = MatchingCoordinationWorkflow().evaluate_service_date_shift(
        case_no="case-shift",
        assignment_id=31,
        original_staff_id=17,
        original_service_dates=(date(2026, 8, 22),),
        shifted_service_dates=(date(2026, 8, 23),),
        availability=_availability(),
    )

    assert isinstance(result, ServiceDateShiftAvailabilityConfirmation)
    assert result.intent_id.startswith("matching:case-shift:service-date-approval:31:")
    assert len(result.source_fingerprint.value) == 64


def test_service_date_shift_returns_deterministic_reassignment_reference_on_conflict() -> None:
    conflict = StaffAvailabilityConflict(
        source_kind="incumbent_assignment",
        source_identity="assignment-31",
        start_date=date(2026, 8, 23),
        end_date=date(2026, 8, 23),
    )
    result = MatchingCoordinationWorkflow().evaluate_service_date_shift(
        case_no="case-shift",
        assignment_id=31,
        original_staff_id=17,
        original_service_dates=(date(2026, 8, 22),),
        shifted_service_dates=(date(2026, 8, 23),),
        availability=_availability(conflicts=(conflict,)),
    )

    assert isinstance(result, ServiceDateShiftReassignmentReference)
    assert result.queue_reference.startswith("matching:case-shift:service-date-reassignment:31:")
    assert result.conflict_source_ids == ("incumbent_assignment:assignment-31",)
    assert len(result.source_fingerprint.value) == 64


def test_leave_defer_projects_rematch_and_reads_canonical_receipt_once() -> None:
    receipt_key = "leave-receipt-001"
    original_date = date(2026, 8, 22)
    source_versions = tuple(MatchingSourceVersion.not_consulted(kind) for kind in SOURCE_KINDS)
    reference = CanonicalSchedulingLeaveReference(
        receipt_key=receipt_key,
        case_no="case-001",
        package_id="package-001",
        criteria_snapshot_id="criteria-001",
        leave_version=2,
        original_staff_id=17,
        resolution_type=LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
        original_work_date=original_date,
        resulting_work_date=original_date + timedelta(days=1),
        outcome_event_ids=("leave-outcome-001",),
        source_versions=source_versions,
        receipt_fingerprint=PreviewFingerprint("a" * 64),
    )
    port = FakeLeaveReferencePort(reference)
    request = MatchingLeaveImpactRequest(
        receipt_key=receipt_key,
        case_no="case-001",
        package_id="package-001",
        criteria_snapshot_id="criteria-001",
        expected_leave_version=2,
        original_staff_id=17,
        expected_source_versions=source_versions,
        correlation_id=CorrelationId("correlation-001"),
    )

    result = MatchingLeaveIntegration(port).evaluate(request)

    assert result.result_state == "leave_deferred"
    assert result.rematch_required is True
    assert port.calls == [receipt_key]


def test_leave_substitute_projects_rematch_and_retains_substitute_staff() -> None:
    receipt_key = "leave-receipt-substitute"
    work_date = date(2026, 8, 22)
    source_versions = tuple(MatchingSourceVersion.not_consulted(kind) for kind in SOURCE_KINDS)
    reference = CanonicalSchedulingLeaveReference(
        receipt_key=receipt_key,
        case_no="case-substitute",
        package_id="package-substitute",
        criteria_snapshot_id="criteria-substitute",
        leave_version=3,
        original_staff_id=17,
        resolution_type=LeaveResolutionType.SUBSTITUTE,
        original_work_date=work_date,
        resulting_work_date=work_date,
        outcome_event_ids=("leave-outcome-substitute",),
        source_versions=source_versions,
        receipt_fingerprint=PreviewFingerprint("e" * 64),
        substitute_staff_id=29,
    )
    port = FakeLeaveReferencePort(reference)
    request = MatchingLeaveImpactRequest(
        receipt_key=receipt_key,
        case_no="case-substitute",
        package_id="package-substitute",
        criteria_snapshot_id="criteria-substitute",
        expected_leave_version=3,
        original_staff_id=17,
        expected_source_versions=source_versions,
        correlation_id=CorrelationId("correlation-substitute"),
    )

    result = MatchingLeaveIntegration(port).evaluate(request)

    assert result.result_state == "leave_substituted"
    assert result.rematch_required is True
    assert result.substitute_staff_id == 29
    assert port.calls == [receipt_key]


def test_missing_leave_receipt_fails_closed_after_one_read() -> None:
    receipt_key = "leave-receipt-missing"
    source_versions = tuple(MatchingSourceVersion.not_consulted(kind) for kind in SOURCE_KINDS)
    port = FakeLeaveReferencePort(None)
    request = MatchingLeaveImpactRequest(
        receipt_key=receipt_key,
        case_no="case-missing",
        package_id="package-missing",
        criteria_snapshot_id="criteria-missing",
        expected_leave_version=1,
        original_staff_id=17,
        expected_source_versions=source_versions,
        correlation_id=CorrelationId("correlation-missing"),
    )

    with pytest.raises(MatchingLeaveIntegrationError) as raised:
        MatchingLeaveIntegration(port).evaluate(request)

    assert raised.value.error.code == "matching_leave_resolution_not_applied"
    assert port.calls == [receipt_key]


@pytest.mark.parametrize(
    ("substitute_staff_id", "resulting_date_offset"),
    (
        (None, 0),
        (17, 0),
        (29, 1),
    ),
)
def test_invalid_leave_substitute_fails_closed_after_one_read(
    substitute_staff_id: int | None,
    resulting_date_offset: int,
) -> None:
    receipt_key = f"leave-receipt-invalid-substitute-{substitute_staff_id}-{resulting_date_offset}"
    work_date = date(2026, 8, 22)
    source_versions = tuple(MatchingSourceVersion.not_consulted(kind) for kind in SOURCE_KINDS)
    reference = CanonicalSchedulingLeaveReference(
        receipt_key=receipt_key,
        case_no="case-invalid-substitute",
        package_id="package-invalid-substitute",
        criteria_snapshot_id="criteria-invalid-substitute",
        leave_version=4,
        original_staff_id=17,
        resolution_type=LeaveResolutionType.SUBSTITUTE,
        original_work_date=work_date,
        resulting_work_date=work_date + timedelta(days=resulting_date_offset),
        outcome_event_ids=("leave-outcome-invalid-substitute",),
        source_versions=source_versions,
        receipt_fingerprint=PreviewFingerprint("f" * 64),
        substitute_staff_id=substitute_staff_id,
    )
    port = FakeLeaveReferencePort(reference)
    request = MatchingLeaveImpactRequest(
        receipt_key=receipt_key,
        case_no="case-invalid-substitute",
        package_id="package-invalid-substitute",
        criteria_snapshot_id="criteria-invalid-substitute",
        expected_leave_version=4,
        original_staff_id=17,
        expected_source_versions=source_versions,
        correlation_id=CorrelationId("correlation-invalid-substitute"),
    )

    with pytest.raises(MatchingLeaveIntegrationError) as raised:
        MatchingLeaveIntegration(port).evaluate(request)

    assert raised.value.error.code == "matching_leave_resolution_not_applied"
    assert port.calls == [receipt_key]


@pytest.mark.parametrize(
    ("request_field", "mismatched_value"),
    (
        ("package_id", "package-stale"),
        ("criteria_snapshot_id", "criteria-stale"),
        (
            "expected_source_versions",
            tuple(MatchingSourceVersion(kind, f"{kind}:changed", 2, "d" * 64) for kind in SOURCE_KINDS),
        ),
    ),
)
def test_reference_mismatch_raises_stale_error_once(
    request_field: str,
    mismatched_value: object,
) -> None:
    receipt_key = "leave-receipt-mismatch"
    original_date = date(2026, 8, 22)
    source_versions = tuple(MatchingSourceVersion.not_consulted(kind) for kind in SOURCE_KINDS)
    reference = CanonicalSchedulingLeaveReference(
        receipt_key=receipt_key,
        case_no="case-mismatch",
        package_id="package-mismatch",
        criteria_snapshot_id="criteria-mismatch",
        leave_version=2,
        original_staff_id=17,
        resolution_type=LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
        original_work_date=original_date,
        resulting_work_date=original_date + timedelta(days=1),
        outcome_event_ids=("leave-outcome-mismatch",),
        source_versions=source_versions,
        receipt_fingerprint=PreviewFingerprint("b" * 64),
    )
    port = FakeLeaveReferencePort(reference)
    request = MatchingLeaveImpactRequest(
        receipt_key=receipt_key,
        case_no="case-mismatch",
        package_id="package-mismatch",
        criteria_snapshot_id="criteria-mismatch",
        expected_leave_version=2,
        original_staff_id=17,
        expected_source_versions=source_versions,
        correlation_id=CorrelationId("correlation-mismatch"),
    )
    mismatched_request = replace(request, **{request_field: mismatched_value})

    with pytest.raises(MatchingLeaveIntegrationError) as raised:
        MatchingLeaveIntegration(port).evaluate(mismatched_request)

    assert raised.value.error.code == "matching_leave_reference_stale"
    assert port.calls == [receipt_key]

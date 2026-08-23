"""
File: matching_leave_integration.py
Description: 唯讀驗證 canonical leave receipt，投影 M3 rematch 結果且不寫入根事實。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domains.scheduling.leave_substitution import LeaveResolutionType
from domains.scheduling.matching_coordination import (
    MatchingSourceTuple,
    MatchingSourceVersion,
    canonical_source_tuple,
)
from shared_kernel.errors import TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.scheduling.matching_coordination_contracts import typed_error


@dataclass(frozen=True, slots=True)
class MatchingLeaveImpactRequest:
    receipt_key: str
    case_no: str
    package_id: str
    criteria_snapshot_id: str
    expected_leave_version: int
    original_staff_id: int
    expected_source_versions: MatchingSourceTuple
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.receipt_key, "leave receipt key", 191)
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.package_id, "package ID", 191)
        require_canonical_text(self.criteria_snapshot_id, "criteria snapshot ID", 191)
        require_positive_integer(self.expected_leave_version, "expected leave version")
        require_positive_integer(self.original_staff_id, "original staff ID")
        object.__setattr__(self, "expected_source_versions", canonical_source_tuple(self.expected_source_versions))
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("leave impact correlation_id must be CorrelationId")


@dataclass(frozen=True, slots=True)
class CanonicalSchedulingLeaveReference:
    receipt_key: str
    case_no: str
    leave_version: int
    original_staff_id: int
    resolution_type: LeaveResolutionType | str
    original_work_date: date
    resulting_work_date: date
    outcome_event_ids: tuple[str, ...]
    receipt_fingerprint: PreviewFingerprint
    substitute_staff_id: int | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.receipt_key, "leave receipt key", 191)
        require_canonical_text(self.case_no, "case number", 50)
        require_positive_integer(self.leave_version, "leave version")
        require_positive_integer(self.original_staff_id, "original staff ID")
        try:
            object.__setattr__(self, "resolution_type", LeaveResolutionType(self.resolution_type))
        except (TypeError, ValueError) as exc:
            raise TypeError("leave resolution type must be LeaveResolutionType") from exc
        if type(self.original_work_date) is not date:
            raise TypeError("original work date must be date")
        if type(self.resulting_work_date) is not date:
            raise TypeError("resulting work date must be date")
        if not isinstance(self.outcome_event_ids, tuple):
            raise TypeError("leave outcome event IDs must be a tuple")
        for event_id in self.outcome_event_ids:
            require_canonical_text(event_id, "leave outcome event ID", 191)
        if not isinstance(self.receipt_fingerprint, PreviewFingerprint):
            object.__setattr__(self, "receipt_fingerprint", PreviewFingerprint(self.receipt_fingerprint))
        if self.substitute_staff_id is not None:
            require_positive_integer(self.substitute_staff_id, "substitute staff ID")


@dataclass(frozen=True, slots=True)
class MatchingLeaveImpactResult:
    receipt_key: str
    result_state: str
    package_id: str
    criteria_snapshot_id: str
    rematch_required: bool
    resolution_type: LeaveResolutionType
    original_work_date: date
    resulting_work_date: date
    outcome_event_ids: tuple[str, ...]
    source_versions: MatchingSourceTuple
    receipt_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint
    substitute_staff_id: int | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.receipt_key, "leave receipt key", 191)
        require_canonical_text(self.result_state, "leave impact result state", 80)
        require_canonical_text(self.package_id, "package ID", 191)
        require_canonical_text(self.criteria_snapshot_id, "criteria snapshot ID", 191)
        if not isinstance(self.rematch_required, bool):
            raise TypeError("leave impact rematch marker must be bool")
        if not isinstance(self.resolution_type, LeaveResolutionType):
            raise TypeError("leave impact resolution must be LeaveResolutionType")
        if type(self.original_work_date) is not date:
            raise TypeError("original work date must be date")
        if type(self.resulting_work_date) is not date:
            raise TypeError("resulting work date must be date")
        if not isinstance(self.outcome_event_ids, tuple):
            raise TypeError("leave outcome event IDs must be a tuple")
        object.__setattr__(self, "source_versions", canonical_source_tuple(self.source_versions))
        if not isinstance(self.receipt_fingerprint, PreviewFingerprint):
            object.__setattr__(self, "receipt_fingerprint", PreviewFingerprint(self.receipt_fingerprint))
        if not isinstance(self.preview_fingerprint, PreviewFingerprint):
            object.__setattr__(self, "preview_fingerprint", PreviewFingerprint(self.preview_fingerprint))


class SchedulingLeaveReferencePort(Protocol):
    def get_canonical_receipt(self, receipt_key: str) -> CanonicalSchedulingLeaveReference | None: ...


class MatchingLeaveIntegrationError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.message)
        self.error = error


class MatchingLeaveIntegration:
    def __init__(self, leave_references: SchedulingLeaveReferencePort) -> None:
        self._leave_references = leave_references

    def evaluate(self, request: MatchingLeaveImpactRequest) -> MatchingLeaveImpactResult:
        reference = self._leave_references.get_canonical_receipt(request.receipt_key)
        if reference is None or not reference.outcome_event_ids:
            raise self._error(request, "matching_leave_resolution_not_applied")
        if (
            reference.receipt_key != request.receipt_key
            or reference.case_no != request.case_no
            or reference.leave_version != request.expected_leave_version
            or reference.original_staff_id != request.original_staff_id
        ):
            raise self._error(request, "matching_leave_reference_stale")
        if reference.resolution_type is LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS:
            if reference.resulting_work_date == reference.original_work_date:
                raise self._error(request, "matching_leave_resolution_not_applied")
            state = "leave_deferred"
        elif reference.resolution_type is LeaveResolutionType.SUBSTITUTE:
            if (
                reference.substitute_staff_id is None
                or reference.substitute_staff_id == reference.original_staff_id
                or reference.resulting_work_date != reference.original_work_date
            ):
                raise self._error(request, "matching_leave_resolution_not_applied")
            state = "leave_substituted"
        else:
            raise self._error(request, "matching_leave_resolution_not_applied")
        source_versions = _with_leave_source(request.expected_source_versions, reference)
        preview_fingerprint = fingerprint_payload(
            {
                "case_no": request.case_no,
                "package_id": request.package_id,
                "criteria_snapshot_id": request.criteria_snapshot_id,
                "receipt_key": reference.receipt_key,
                "leave_version": reference.leave_version,
                "original_staff_id": reference.original_staff_id,
                "resolution_type": reference.resolution_type.value,
                "original_work_date": reference.original_work_date.isoformat(),
                "resulting_work_date": reference.resulting_work_date.isoformat(),
                "outcome_event_ids": reference.outcome_event_ids,
                "substitute_staff_id": reference.substitute_staff_id,
                "receipt_fingerprint": reference.receipt_fingerprint.value,
                "source_versions": tuple(item.as_payload() for item in source_versions),
            }
        )
        return MatchingLeaveImpactResult(
            receipt_key=reference.receipt_key,
            result_state=state,
            package_id=request.package_id,
            criteria_snapshot_id=request.criteria_snapshot_id,
            rematch_required=True,
            resolution_type=reference.resolution_type,
            original_work_date=reference.original_work_date,
            resulting_work_date=reference.resulting_work_date,
            outcome_event_ids=reference.outcome_event_ids,
            source_versions=source_versions,
            receipt_fingerprint=reference.receipt_fingerprint,
            preview_fingerprint=preview_fingerprint,
            substitute_staff_id=reference.substitute_staff_id,
        )

    @staticmethod
    def _error(request: MatchingLeaveImpactRequest, code: str) -> MatchingLeaveIntegrationError:
        return MatchingLeaveIntegrationError(typed_error(code, request.correlation_id))


def _with_leave_source(
    sources: MatchingSourceTuple,
    reference: CanonicalSchedulingLeaveReference,
) -> MatchingSourceTuple:
    leave_source = MatchingSourceVersion(
        "leave_request_or_outcome",
        reference.receipt_key,
        reference.leave_version,
        reference.receipt_fingerprint,
    )
    return canonical_source_tuple(
        tuple(
            leave_source if item.source_kind == "leave_request_or_outcome" else item
            for item in sources
        )
    )


__all__ = [
    "CanonicalSchedulingLeaveReference",
    "MatchingLeaveImpactRequest",
    "MatchingLeaveImpactResult",
    "MatchingLeaveIntegration",
    "MatchingLeaveIntegrationError",
    "SchedulingLeaveReferencePort",
]

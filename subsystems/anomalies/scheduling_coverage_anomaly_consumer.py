"""Project assignment-owned service-day coverage into canonical Anomalies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domains.anomalies.registry import CurrentAlertProjection, DesiredAlertState
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest


_ANOMALY_CODE = "SCHEDULE-006"
_CONSUMER_IDENTITY = "scheduling-coverage-anomaly-projector-v1"
_MAXIMUM_SCAN_SIZE = 100
_TEXT_MAXIMUM_LENGTH = 191
_CASE_NUMBER_MAXIMUM_LENGTH = 50


@dataclass(frozen=True, slots=True)
class AssignmentOfficialServiceDays:
    assignment_id: int
    service_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.assignment_id, "assignment id")
        if not isinstance(self.service_dates, tuple):
            raise TypeError("service dates must be a tuple")
        if any(type(value) is not date for value in self.service_dates):
            raise TypeError("service dates must contain dates")
        if self.service_dates != tuple(sorted(set(self.service_dates))):
            raise ValueError("service dates must be sorted and unique")


@dataclass(frozen=True, slots=True)
class SchedulingCoverageRootFact:
    case_no: str
    generation: int
    expected_service_days: int
    assignments: tuple[AssignmentOfficialServiceDays, ...]
    generation_effective: bool
    completed_eligible: bool
    source_version: int
    source_event_identity: str

    def __post_init__(self) -> None:
        _validate_coverage_identity(self)
        _validate_coverage_counts(self)
        _validate_assignments(self.assignments)
        if not isinstance(self.generation_effective, bool):
            raise TypeError("generation effective flag must be bool")
        if not isinstance(self.completed_eligible, bool):
            raise TypeError("completed eligible flag must be bool")

    @property
    def actual_service_days(self) -> int:
        return len(
            {
                service_date
                for assignment in self.assignments
                for service_date in assignment.service_dates
            }
        )


@dataclass(frozen=True, slots=True)
class SchedulingCoverageScanRequest:
    limit: int
    after_source_identity: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("scan limit must be an integer")
        if not 1 <= self.limit <= _MAXIMUM_SCAN_SIZE:
            raise ValueError("scan limit must be between 1 and 100")
        if self.after_source_identity is not None:
            require_canonical_text(
                self.after_source_identity,
                "scan cursor",
                _TEXT_MAXIMUM_LENGTH,
            )


@dataclass(frozen=True, slots=True)
class SchedulingCoverageScanPage:
    facts: tuple[SchedulingCoverageRootFact, ...]
    next_source_identity: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple):
            raise TypeError("scan facts must be a tuple")
        if any(not isinstance(value, SchedulingCoverageRootFact) for value in self.facts):
            raise TypeError("scan facts contain an invalid root fact")
        if self.next_source_identity is not None:
            require_canonical_text(
                self.next_source_identity,
                "next scan cursor",
                _TEXT_MAXIMUM_LENGTH,
            )


@dataclass(frozen=True, slots=True)
class SchedulingCoverageScanResult:
    projections: tuple[CurrentAlertProjection | None, ...]
    next_source_identity: str | None


class SchedulingCoverageRootFactSource(Protocol):
    def load_page(self, request: SchedulingCoverageScanRequest) -> SchedulingCoverageScanPage: ...


class SchedulingCoverageAnomalyConsumer:
    def __init__(
        self,
        source: SchedulingCoverageRootFactSource,
        anomaly_application: AnomalyApplication,
    ) -> None:
        self._source = source
        self._anomaly_application = anomaly_application

    def consume(self, root_fact: SchedulingCoverageRootFact) -> CurrentAlertProjection | None:
        request = build_schedule_coverage_project_request(root_fact)
        return self._anomaly_application.project(request)

    def scan_page(self, request: SchedulingCoverageScanRequest) -> SchedulingCoverageScanResult:
        page = self._source.load_page(request)
        if len(page.facts) > request.limit:
            raise ValueError("root-fact source exceeded the bounded scan limit")
        projections = tuple(self.consume(fact) for fact in page.facts)
        return SchedulingCoverageScanResult(projections, page.next_source_identity)


def build_schedule_coverage_project_request(
    root_fact: SchedulingCoverageRootFact,
) -> ProjectAlertRequest:
    source_identity = f"case:{root_fact.case_no}"
    generation = str(root_fact.generation)
    return ProjectAlertRequest(
        desired=_desired_state(root_fact, source_identity, generation),
        source_event_identity=root_fact.source_event_identity,
        consumer_identity=_CONSUMER_IDENTITY,
        partition_identity=f"{_ANOMALY_CODE}:{source_identity}:generation:{generation}",
        display_snapshot=_display_snapshot(root_fact),
    )


def _desired_state(
    root_fact: SchedulingCoverageRootFact,
    source_identity: str,
    generation: str,
) -> DesiredAlertState:
    return DesiredAlertState(
        definition_code=_ANOMALY_CODE,
        source_identity=source_identity,
        source_version=root_fact.source_version,
        active=_coverage_mismatch_is_active(root_fact),
        fingerprint_values={"case_no": root_fact.case_no, "generation": generation},
    )


def _display_snapshot(root_fact: SchedulingCoverageRootFact) -> dict[str, object]:
    return {
        "case_no": root_fact.case_no,
        "generation": root_fact.generation,
        "expected_days": root_fact.expected_service_days,
        "actual_days": root_fact.actual_service_days,
    }


def _coverage_mismatch_is_active(root_fact: SchedulingCoverageRootFact) -> bool:
    return (
        root_fact.generation_effective
        and root_fact.completed_eligible
        and root_fact.actual_service_days != root_fact.expected_service_days
    )


def _validate_coverage_identity(root_fact: SchedulingCoverageRootFact) -> None:
    require_canonical_text(root_fact.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
    require_positive_integer(root_fact.generation, "generation")
    require_nonnegative_integer(root_fact.source_version, "source version")
    require_canonical_text(
        root_fact.source_event_identity,
        "source event identity",
        _TEXT_MAXIMUM_LENGTH,
    )


def _validate_coverage_counts(root_fact: SchedulingCoverageRootFact) -> None:
    require_nonnegative_integer(root_fact.expected_service_days, "expected service days")


def _validate_assignments(assignments: tuple[AssignmentOfficialServiceDays, ...]) -> None:
    if not isinstance(assignments, tuple):
        raise TypeError("assignments must be a tuple")
    if any(not isinstance(value, AssignmentOfficialServiceDays) for value in assignments):
        raise TypeError("assignments contain an invalid root fact")
    assignment_ids = tuple(value.assignment_id for value in assignments)
    if assignment_ids != tuple(sorted(set(assignment_ids))):
        raise ValueError("assignments must be sorted and unique")


__all__ = [
    "AssignmentOfficialServiceDays",
    "SchedulingCoverageAnomalyConsumer",
    "SchedulingCoverageRootFact",
    "SchedulingCoverageRootFactSource",
    "SchedulingCoverageScanPage",
    "SchedulingCoverageScanRequest",
    "SchedulingCoverageScanResult",
    "build_schedule_coverage_project_request",
]

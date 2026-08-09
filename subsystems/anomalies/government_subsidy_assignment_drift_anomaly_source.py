"""Project GOVSUB-005 from frozen claim items and official assignment facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.anomalies.registry import CurrentAlertProjection, DesiredAlertState
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest

_ANOMALY_CODE = "GOVSUB-005"
_CONSUMER_IDENTITY = "govsub-assignment-drift-v1"
_TEXT_MAXIMUM_LENGTH = 191
_CASE_NUMBER_MAXIMUM_LENGTH = 50
_MAXIMUM_SCAN_SIZE = 100


@dataclass(frozen=True)
class GovernmentSubsidyAssignmentDriftRootFact:
    claim_item_id: int
    batch_id: int
    frozen_assignment_id: int
    frozen_case_no: str
    frozen_staff_id: int
    frozen_claimed_hours: int
    authoritative_assignment_id: int
    authoritative_case_no: str
    authoritative_staff_id: int
    official_service_hours: int
    assignment_effective: bool
    source_version: int
    source_event_identity: str

    def __post_init__(self) -> None:
        _validate_identities(self)
        _validate_case_numbers(self)
        _validate_hours(self)
        if not isinstance(self.assignment_effective, bool):
            raise TypeError("assignment effective flag must be bool")

    @property
    def drift_fields(self) -> tuple[str, ...]:
        fields = []
        if not self.assignment_effective or self.frozen_assignment_id != self.authoritative_assignment_id:
            fields.append("assignment_id")
        if self.frozen_case_no != self.authoritative_case_no:
            fields.append("case_no")
        if self.frozen_staff_id != self.authoritative_staff_id:
            fields.append("staff_id")
        if self.frozen_claimed_hours != self.official_service_hours:
            fields.append("claimed_hours")
        return tuple(fields)


@dataclass(frozen=True)
class GovernmentSubsidyAssignmentDriftScanRequest:
    limit: int
    after_claim_item_id: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("scan limit must be an integer")
        if not 1 <= self.limit <= _MAXIMUM_SCAN_SIZE:
            raise ValueError("scan limit must be between 1 and 100")
        require_nonnegative_integer(self.after_claim_item_id, "claim item scan cursor")


@dataclass(frozen=True)
class GovernmentSubsidyAssignmentDriftScanPage:
    facts: tuple[GovernmentSubsidyAssignmentDriftRootFact, ...]
    next_claim_item_id: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple):
            raise TypeError("scan facts must be a tuple")
        if any(not isinstance(fact, GovernmentSubsidyAssignmentDriftRootFact) for fact in self.facts):
            raise TypeError("scan facts contain an invalid root fact")
        if self.next_claim_item_id is not None:
            require_positive_integer(self.next_claim_item_id, "next claim item cursor")


@dataclass(frozen=True)
class GovernmentSubsidyAssignmentDriftScanResult:
    projections: tuple[CurrentAlertProjection | None, ...]
    next_claim_item_id: int | None


class GovernmentSubsidyAssignmentDriftRootFactSource(Protocol):
    def load_page(self, request: GovernmentSubsidyAssignmentDriftScanRequest) -> GovernmentSubsidyAssignmentDriftScanPage: ...


class GovernmentSubsidyAssignmentDriftAnomalyConsumer:
    def __init__(self, source: GovernmentSubsidyAssignmentDriftRootFactSource, anomaly_application: AnomalyApplication) -> None:
        self._source = source
        self._anomaly_application = anomaly_application

    def scan_page(self, request: GovernmentSubsidyAssignmentDriftScanRequest) -> GovernmentSubsidyAssignmentDriftScanResult:
        page = self._source.load_page(request)
        if len(page.facts) > request.limit:
            raise ValueError("root-fact source exceeded the bounded scan limit")
        return GovernmentSubsidyAssignmentDriftScanResult(
            tuple(self._anomaly_application.project(build_assignment_drift_project_request(fact)) for fact in page.facts),
            page.next_claim_item_id,
        )


def build_assignment_drift_project_request(root_fact: GovernmentSubsidyAssignmentDriftRootFact) -> ProjectAlertRequest:
    source_identity = f"claim-item:{root_fact.claim_item_id}"
    return ProjectAlertRequest(_desired_state(root_fact, source_identity), root_fact.source_event_identity, _CONSUMER_IDENTITY, f"{_ANOMALY_CODE}:{source_identity}", _display_snapshot(root_fact))


def _desired_state(root_fact, source_identity):
    return DesiredAlertState(_ANOMALY_CODE, source_identity, root_fact.source_version, bool(root_fact.drift_fields), {"assignment_id": str(root_fact.frozen_assignment_id), "batch_id": str(root_fact.batch_id), "claim_item_id": str(root_fact.claim_item_id)})


def _display_snapshot(root_fact):
    return {"assignment_id": root_fact.frozen_assignment_id, "batch_id": root_fact.batch_id, "claim_item_id": root_fact.claim_item_id, "drift_fields": root_fact.drift_fields, "frozen_case_no": root_fact.frozen_case_no, "frozen_claimed_hours": root_fact.frozen_claimed_hours, "frozen_staff_id": root_fact.frozen_staff_id, "official_service_hours": root_fact.official_service_hours}


def _validate_identities(root_fact) -> None:
    for value, field in ((root_fact.claim_item_id, "claim item id"), (root_fact.batch_id, "claim batch id"), (root_fact.frozen_assignment_id, "frozen assignment id"), (root_fact.authoritative_assignment_id, "authoritative assignment id"), (root_fact.frozen_staff_id, "frozen staff id"), (root_fact.authoritative_staff_id, "staff id")):
        require_positive_integer(value, field)
    require_nonnegative_integer(root_fact.source_version, "source version")
    require_canonical_text(root_fact.source_event_identity, "source event identity", _TEXT_MAXIMUM_LENGTH)


def _validate_case_numbers(root_fact) -> None:
    require_canonical_text(root_fact.frozen_case_no, "frozen case number", _CASE_NUMBER_MAXIMUM_LENGTH)
    require_canonical_text(root_fact.authoritative_case_no, "authoritative case number", _CASE_NUMBER_MAXIMUM_LENGTH)


def _validate_hours(root_fact) -> None:
    require_nonnegative_integer(root_fact.frozen_claimed_hours, "frozen claimed hours")
    require_nonnegative_integer(root_fact.official_service_hours, "official service hours")


__all__ = ["GovernmentSubsidyAssignmentDriftAnomalyConsumer", "GovernmentSubsidyAssignmentDriftRootFact", "GovernmentSubsidyAssignmentDriftRootFactSource", "GovernmentSubsidyAssignmentDriftScanPage", "GovernmentSubsidyAssignmentDriftScanRequest", "GovernmentSubsidyAssignmentDriftScanResult", "build_assignment_drift_project_request"]

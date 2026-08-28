"""
File: government_subsidy_reversal_anomaly_source.py
Description: 依政府補助 reversal 根事實投影 GOVSUB-004 告警。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domains.anomalies.registry import CurrentAlertProjection, DesiredAlertState
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest


_CONSUMER_IDENTITY = "government-subsidy-reversal-anomaly-source-v1"
_MAXIMUM_SCAN_SIZE = 100
_TEXT_MAXIMUM_LENGTH = 191
_UNIDENTIFIED_SOURCE_RECEIPT = "unidentified"


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalAllocationRootFact:
    allocation_id: int
    allocated_ntd: int
    reversed_ntd: int

    def __post_init__(self) -> None:
        require_positive_integer(self.allocation_id, "receipt allocation id")
        require_positive_integer(self.allocated_ntd, "receipt allocation amount")
        require_nonnegative_integer(self.reversed_ntd, "reversed allocation amount")

    @property
    def remaining_reversible_ntd(self) -> int:
        return self.allocated_ntd - self.reversed_ntd


@dataclass(frozen=True, slots=True)
class GovernmentSubsidySourceReceiptRootFact:
    source_receipt_id: int
    transaction_type: str
    transaction_status: str
    amount_ntd: int
    allocations: tuple[GovernmentSubsidyReversalAllocationRootFact, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.source_receipt_id, "source receipt id")
        require_canonical_text(self.transaction_type, "source transaction type", _TEXT_MAXIMUM_LENGTH)
        require_canonical_text(self.transaction_status, "source transaction status", _TEXT_MAXIMUM_LENGTH)
        require_positive_integer(self.amount_ntd, "source receipt amount")
        _validate_allocations(self.allocations)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalRootFact:
    finance_import_row_id: int
    reversal_bank_fact_identity: str
    amount_ntd: int
    currently_government_subsidy: bool
    classified_source_receipt_id: int | None
    successful_reversal_source_receipt_id: int | None
    source_receipt: GovernmentSubsidySourceReceiptRootFact | None
    previous_source_receipt_coordinates: tuple[str, ...]
    source_version: int
    source_event_identity: str

    def __post_init__(self) -> None:
        require_positive_integer(self.finance_import_row_id, "finance import row id")
        require_canonical_text(self.reversal_bank_fact_identity, "reversal bank fact identity", _TEXT_MAXIMUM_LENGTH)
        require_positive_integer(self.amount_ntd, "reversal bank amount")
        _validate_bool(self.currently_government_subsidy)
        _validate_optional_identity(self.classified_source_receipt_id)
        _validate_optional_identity(self.successful_reversal_source_receipt_id)
        _validate_source_receipt(self.source_receipt)
        _validate_coordinates(self.previous_source_receipt_coordinates)
        require_nonnegative_integer(self.source_version, "source version")
        require_canonical_text(self.source_event_identity, "source event identity", _TEXT_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalScanRequest:
    limit: int
    after_finance_import_row_id: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("scan limit must be an integer")
        if not 1 <= self.limit <= _MAXIMUM_SCAN_SIZE:
            raise ValueError("scan limit must be between 1 and 100")
        require_nonnegative_integer(self.after_finance_import_row_id, "finance import scan cursor")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalScanPage:
    facts: tuple[GovernmentSubsidyReversalRootFact, ...]
    next_finance_import_row_id: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.facts, tuple):
            raise TypeError("scan facts must be a tuple")
        if any(not isinstance(fact, GovernmentSubsidyReversalRootFact) for fact in self.facts):
            raise TypeError("scan facts contain an invalid reversal root fact")
        _validate_optional_identity(self.next_finance_import_row_id)


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReversalScanResult:
    projections: tuple[CurrentAlertProjection | None, ...]
    next_finance_import_row_id: int | None


class GovernmentSubsidyReversalRootFactSource(Protocol):
    def load_page(self, request: GovernmentSubsidyReversalScanRequest) -> GovernmentSubsidyReversalScanPage: ...


class GovernmentSubsidyReversalAnomalyConsumer:
    def __init__(self, source: GovernmentSubsidyReversalRootFactSource, anomaly_application: AnomalyApplication) -> None:
        self._source = source
        self._anomaly_application = anomaly_application

    def scan_page(self, request: GovernmentSubsidyReversalScanRequest) -> GovernmentSubsidyReversalScanResult:
        page = self._source.load_page(request)
        if len(page.facts) > request.limit:
            raise ValueError("root-fact source exceeded the bounded scan limit")
        projections = tuple(
            self._anomaly_application.project(alert_request)
            for fact in page.facts
            for alert_request in build_reversal_alert_requests(fact)
        )
        return GovernmentSubsidyReversalScanResult(projections, page.next_finance_import_row_id)


def build_reversal_alert_requests(root_fact: GovernmentSubsidyReversalRootFact) -> tuple[ProjectAlertRequest, ...]:
    current_coordinate = _current_source_coordinate(root_fact)
    coordinates = set(root_fact.previous_source_receipt_coordinates)
    coordinates.add(current_coordinate)
    return tuple(
        _project_request(root_fact, coordinate, current_coordinate)
        for coordinate in sorted(coordinates)
    )


def _project_request(root_fact, coordinate, current_coordinate):
    active = coordinate == current_coordinate and _reversal_review_required(root_fact)
    snapshot = _display_snapshot(root_fact, coordinate)
    source_identity = _source_identity(root_fact.finance_import_row_id, coordinate)
    desired = DesiredAlertState(
        "GOVSUB-004",
        source_identity,
        root_fact.source_version,
        active,
        {
            "reversal_bank_fact_identity": root_fact.reversal_bank_fact_identity,
            "source_receipt_id": coordinate,
        },
    )
    return ProjectAlertRequest(
        desired,
        _projector_event_identity(root_fact, coordinate, active, snapshot),
        _CONSUMER_IDENTITY,
        f"G4:{root_fact.finance_import_row_id}:{coordinate}",
        snapshot,
    )


def _reversal_review_required(root_fact) -> bool:
    if not root_fact.currently_government_subsidy:
        return False
    receipt = root_fact.source_receipt
    if root_fact.classified_source_receipt_id is None or receipt is None:
        return True
    if receipt.source_receipt_id != root_fact.classified_source_receipt_id:
        return True
    if not _source_receipt_is_valid(receipt):
        return True
    return not _reversal_is_automatic(root_fact.amount_ntd, receipt)


def _source_receipt_is_valid(receipt) -> bool:
    if receipt.transaction_type != "receipt" or receipt.transaction_status != "succeeded":
        return False
    if not receipt.allocations:
        return False
    if any(item.remaining_reversible_ntd < 0 for item in receipt.allocations):
        return False
    return sum(item.allocated_ntd for item in receipt.allocations) == receipt.amount_ntd


def _reversal_is_automatic(amount_ntd, receipt) -> bool:
    remaining = tuple(
        item.remaining_reversible_ntd
        for item in receipt.allocations
        if item.remaining_reversible_ntd > 0
    )
    total_remaining = sum(remaining)
    if amount_ntd > total_remaining:
        return False
    return amount_ntd == total_remaining or len(remaining) == 1


def _display_snapshot(root_fact, coordinate):
    source_receipt_id = _coordinate_identity(coordinate)
    receipt = root_fact.source_receipt
    remaining = None
    if receipt is not None and receipt.source_receipt_id == source_receipt_id:
        remaining = sum(item.remaining_reversible_ntd for item in receipt.allocations)
    return {
        "remaining_reversible_ntd": remaining,
        "reversal_bank_fact_identity": root_fact.reversal_bank_fact_identity,
        "source_receipt_id": source_receipt_id,
    }


def _current_source_coordinate(root_fact) -> str:
    source_id = root_fact.successful_reversal_source_receipt_id or root_fact.classified_source_receipt_id
    return str(source_id) if source_id is not None else _UNIDENTIFIED_SOURCE_RECEIPT


def _source_identity(row_id, coordinate) -> str:
    return f"finance-import-row:{row_id}:source-receipt:{coordinate}"


def _coordinate_identity(coordinate):
    if coordinate.isdigit() and int(coordinate) > 0:
        return int(coordinate)
    return None


def _projector_event_identity(root_fact, coordinate, active, snapshot):
    digest = fingerprint_payload(
        {
            "active": active,
            "coordinate": coordinate,
            "root_event": root_fact.source_event_identity,
            "snapshot": snapshot,
        }
    ).value
    return f"government-subsidy:GOVSUB-004:{digest}"


def _validate_allocations(allocations) -> None:
    if not isinstance(allocations, tuple):
        raise TypeError("source allocations must be a tuple")
    if any(not isinstance(item, GovernmentSubsidyReversalAllocationRootFact) for item in allocations):
        raise TypeError("source allocations contain an invalid root fact")
    identities = tuple(item.allocation_id for item in allocations)
    if identities != tuple(sorted(set(identities))):
        raise ValueError("source allocations must be sorted and unique")


def _validate_coordinates(coordinates) -> None:
    if not isinstance(coordinates, tuple):
        raise TypeError("previous source coordinates must be a tuple")
    if coordinates != tuple(sorted(set(coordinates))):
        raise ValueError("previous source coordinates must be sorted and unique")
    for coordinate in coordinates:
        require_canonical_text(coordinate, "source receipt coordinate", _TEXT_MAXIMUM_LENGTH)


def _validate_optional_identity(value) -> None:
    if value is not None:
        require_positive_integer(value, "optional source identity")


def _validate_source_receipt(value) -> None:
    if value is not None and not isinstance(value, GovernmentSubsidySourceReceiptRootFact):
        raise TypeError("source receipt must be a reversal root fact")


def _validate_bool(value) -> None:
    if not isinstance(value, bool):
        raise TypeError("classification flag must be bool")


__all__ = [
    "GovernmentSubsidyReversalAllocationRootFact",
    "GovernmentSubsidyReversalAnomalyConsumer",
    "GovernmentSubsidyReversalRootFact",
    "GovernmentSubsidyReversalRootFactSource",
    "GovernmentSubsidyReversalScanPage",
    "GovernmentSubsidyReversalScanRequest",
    "GovernmentSubsidyReversalScanResult",
    "GovernmentSubsidySourceReceiptRootFact",
    "build_reversal_alert_requests",
]

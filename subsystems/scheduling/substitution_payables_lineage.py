"""Typed read model for substitution → Payroll → Staff Payables lineage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from shared_kernel.validation import require_canonical_text, require_positive_integer


@dataclass(frozen=True, slots=True)
class StaffPayablesEvidence:
    obligation_identity: str
    assignment_id: int
    staff_id: int
    amount_due_ntd: int
    due_date: date | None
    obligation_status: str
    obligation_payroll_version: int
    obligation_event_id: int
    projection_status: str | None
    projection_amount_ntd: int | None
    projection_net_paid_ntd: int | None
    projection_balance_ntd: int | None
    projection_version: int | None
    projection_event_id: int | None
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_text(self.obligation_identity, "obligation identity", 191)
        require_positive_integer(self.assignment_id, "obligation assignment id")
        require_positive_integer(self.staff_id, "obligation staff id")
        if self.amount_due_ntd <= 0:
            raise ValueError("staff obligation amount must be positive")
        if self.obligation_payroll_version < 0 or self.obligation_event_id <= 0:
            raise ValueError("staff obligation version evidence is invalid")
        if self.projection_version is not None and self.projection_version < 0:
            raise ValueError("staff payable projection version is invalid")


@dataclass(frozen=True, slots=True)
class SubstitutionPayablesLineageItem:
    item_index: int
    outcome_event_id: int
    original_assignment_id: int
    original_schedule_id: int
    original_staff_id: int
    original_work_date: date
    resolution_type: str
    resulting_assignment_id: int
    resulting_staff_id: int
    resulting_service_date: date
    payroll_event_id: int | None
    payroll_event_expected_version: int | None
    payroll_event_resulting_version: int | None
    payroll_fingerprint: str | None
    payables_evidence: StaffPayablesEvidence | None
    lineage_subject: str
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.item_index < 0:
            raise ValueError("substitution item index must be nonnegative")
        for value, label in (
            (self.outcome_event_id, "outcome event id"),
            (self.original_assignment_id, "original assignment id"),
            (self.original_schedule_id, "original schedule id"),
            (self.original_staff_id, "original staff id"),
            (self.resulting_assignment_id, "resulting assignment id"),
            (self.resulting_staff_id, "resulting staff id"),
        ):
            require_positive_integer(value, label)
        require_canonical_text(self.resolution_type, "resolution type", 50)
        require_canonical_text(self.lineage_subject, "lineage subject", 191)


@dataclass(frozen=True, slots=True)
class SubstitutionPayablesLineageReadback:
    case_no: str
    batch_key: str
    scheduling_receipt_id: int
    scheduling_version: int
    scheduling_generation: int
    expected_payroll_version: int
    resulting_payroll_version: int
    items: tuple[SubstitutionPayablesLineageItem, ...]
    authoritative_complete: bool
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        require_canonical_text(self.batch_key, "substitution batch key", 191)
        for value, label in (
            (self.scheduling_receipt_id, "scheduling receipt id"),
            (self.scheduling_version, "scheduling version"),
            (self.scheduling_generation, "scheduling generation"),
            (self.expected_payroll_version, "expected payroll version"),
            (self.resulting_payroll_version, "resulting payroll version"),
        ):
            if value < 0 or (label.endswith("id") and value <= 0):
                raise ValueError(f"{label} is invalid")
        if not isinstance(self.items, tuple):
            raise TypeError("lineage items must be a tuple")
        if self.authoritative_complete != (not self.blockers and all(not item.blockers for item in self.items)):
            raise ValueError("lineage completeness does not match blockers")


class SubstitutionPayablesLineageRepository(Protocol):
    def query(self, case_no: str, batch_key: str) -> SubstitutionPayablesLineageReadback: ...


class SubstitutionPayablesLineageApplication:
    """Read-only cross-owner projection; it has no mutation or commit method."""

    def __init__(self, repository: SubstitutionPayablesLineageRepository) -> None:
        self._repository = repository

    def query(self, case_no: str, batch_key: str) -> SubstitutionPayablesLineageReadback:
        return self._repository.query(case_no, batch_key)


__all__ = [
    "StaffPayablesEvidence",
    "SubstitutionPayablesLineageApplication",
    "SubstitutionPayablesLineageItem",
    "SubstitutionPayablesLineageReadback",
    "SubstitutionPayablesLineageRepository",
]

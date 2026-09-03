"""
File: historical_adoption_workflow.py
Description: 編排逐列 Historical Order Preview／Apply、replay、配對 evidence 與單一 UoW。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Callable, Protocol

from domains.orders.historical_adoption import (
    HistoricalOrderAdoptionCandidate,
    HistoricalOrderCurrentFacts,
    HistoricalOrderOutcome,
    HistoricalOrderResult,
    HistoricalOrderSourceFacts,
    HistoricalOrderSourceStatus,
    build_historical_order_candidate,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.clock import BusinessClock, SystemBusinessClock
from shared_kernel.ports import UnitOfWork
from subsystems.orders.historical_actual_start_rebuild import HistoricalActualStartRebuilder
from subsystems.orders.historical_order_workbook import HistoricalOrderWorkbookRow
from subsystems.scheduling.historical_pending_deposit_matching import (
    HistoricalPendingDepositMatchCommand,
    HistoricalPendingDepositMatchingPort,
)


class HistoricalPairingResolution(StrEnum):
    BLANK = "blank"
    STAFF_MISSING = "staff_missing"
    STAFF_AMBIGUOUS = "staff_ambiguous"
    EVIDENCE_ONLY = "evidence_only"
    ASSIGNMENT_CANDIDATE = "assignment_candidate"
    ASSIGNMENT_REUSED = "assignment_reused"
    ASSIGNMENT_CONFLICT = "assignment_conflict"


@dataclass(frozen=True, slots=True)
class HistoricalPairingCandidate:
    ordinal: int
    name: str
    staff_id: int | None
    start_date: object | None
    end_date: object | None
    resolution: HistoricalPairingResolution
    issue_codes: tuple[str, ...]
    assignment_id: int | None = None


@dataclass(frozen=True, slots=True)
class HistoricalOrderAdoptionPreview:
    source_identity: str
    source_fingerprint: str
    outcome: HistoricalOrderOutcome
    case_no: str | None
    expected_version: int | None
    resulting_version: int | None
    before_status: str | None
    after_status: str | None
    date_patch: tuple[tuple[str, object], ...]
    pairings: tuple[HistoricalPairingCandidate, ...]
    issue_codes: tuple[str, ...]
    fingerprint: PreviewFingerprint

    @property
    def result(self) -> HistoricalOrderResult:
        if self.outcome in {
            HistoricalOrderOutcome.UNMATCHED_CASE,
            HistoricalOrderOutcome.REVIEW_REQUIRED,
        }:
            return HistoricalOrderResult.NOT_ADOPTED
        return {
            OrderLifecycleStatus.DISCUSSION.value: HistoricalOrderResult.MATCHING_PENDING_DEPOSIT,
            OrderLifecycleStatus.HISTORICAL_UNSERVED.value: HistoricalOrderResult.HISTORICAL_UNSERVED,
            OrderLifecycleStatus.HISTORICAL_IN_SERVICE.value: HistoricalOrderResult.HISTORICAL_IN_SERVICE,
            OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value: HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED,
        }.get(self.after_status, HistoricalOrderResult.NOT_ADOPTED)


@dataclass(frozen=True, slots=True)
class HistoricalOrderAdoptionRequest:
    row: HistoricalOrderWorkbookRow
    preview_fingerprint: PreviewFingerprint
    idempotency_key: str
    actor: str
    reason: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class HistoricalOrderAdoptionReceipt:
    outcome: HistoricalOrderOutcome
    case_no: str | None
    resulting_version: int | None
    assignment_count: int
    review_identity: str | None
    replayed: bool
    preview_fingerprint: PreviewFingerprint


class HistoricalOrderAdoptionRepository(Protocol):
    def load_order(self, case_no: str, client_name: str, *, for_update: bool) -> HistoricalOrderCurrentFacts | None: ...
    def resolve_staff(self, name: str, *, for_update: bool) -> tuple[int, ...]: ...
    def active_assignments(self, case_no: str, *, for_update: bool) -> tuple[dict[str, object], ...]: ...
    def find_receipt(self, key: str, source_identity: str) -> dict[str, object] | None: ...
    def persist(
        self,
        request: HistoricalOrderAdoptionRequest,
        preview: HistoricalOrderAdoptionPreview,
        assignment_ids: tuple[int, ...],
    ) -> HistoricalOrderAdoptionReceipt: ...


class SchedulingHistoricalAssignmentPort(Protocol):
    """Append purpose-specific historical assignments in the caller's UoW."""

    def append_completed_assignments(
        self,
        case_no: str,
        assignments: tuple[tuple[int, date, date], ...],
    ) -> tuple[int, ...]: ...


class HistoricalOrderAdoptionWorkflow:
    def __init__(
        self,
        repository: HistoricalOrderAdoptionRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
        scheduling_historical_assignment: SchedulingHistoricalAssignmentPort,
        actual_start_rebuilder: HistoricalActualStartRebuilder | None = None,
        clock: BusinessClock | None = None,
        matching_pending_deposit: HistoricalPendingDepositMatchingPort | None = None,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._scheduling_historical_assignment = scheduling_historical_assignment
        # Compatibility-only dependencies: historical adoption deliberately
        # does not invoke Actual Start calculation, scheduling generation, or
        # finance/payroll projection.  The workbook carries interval evidence,
        # not a reconstructed daily roster.
        del actual_start_rebuilder
        self._scheduling_historical_assignment = scheduling_historical_assignment
        self._clock = clock or SystemBusinessClock()
        self._matching_pending_deposit = matching_pending_deposit

    def preview(self, row: HistoricalOrderWorkbookRow) -> HistoricalOrderAdoptionPreview:
        return self._build_preview(row, for_update=False)

    def apply(self, request: HistoricalOrderAdoptionRequest) -> HistoricalOrderAdoptionReceipt:
        with self._unit_of_work_factory() as unit_of_work:
            receipt = self.apply_in_current_unit_of_work(request)
            unit_of_work.commit()
            return receipt

    def preview_in_current_unit_of_work(
        self, row: HistoricalOrderWorkbookRow, *, for_update: bool
    ) -> HistoricalOrderAdoptionPreview:
        """Evaluate one row using the caller-owned transaction and lock policy."""
        return self._build_preview(row, for_update=for_update)

    def apply_in_current_unit_of_work(
        self, request: HistoricalOrderAdoptionRequest
    ) -> HistoricalOrderAdoptionReceipt:
        """Persist one adoption without opening or committing a nested transaction."""
        command_fingerprint = _command_fingerprint(request)
        replay = self._replay(request, command_fingerprint)
        if replay is not None:
            return replay
        preview = self._build_preview(request.row, for_update=True)
        if preview.fingerprint != request.preview_fingerprint:
            raise RuntimeError("historical_order_candidate_stale")
        if preview.outcome is HistoricalOrderOutcome.UNMATCHED_CASE:
            return _unmatched_receipt(preview)
        assignment_ids = self._append_assignment_candidates(preview)
        self._ensure_matching_pending_deposit(request, preview)
        receipt = self._repository.persist(request, preview, assignment_ids)
        return receipt

    def _ensure_matching_pending_deposit(
        self,
        request: HistoricalOrderAdoptionRequest,
        preview: HistoricalOrderAdoptionPreview,
    ) -> None:
        if preview.result is not HistoricalOrderResult.MATCHING_PENDING_DEPOSIT:
            return
        if self._matching_pending_deposit is None:
            raise RuntimeError("historical_matching_port_required")
        pairing = preview.pairings[0]
        self._matching_pending_deposit.ensure_pending_deposit_match(
            HistoricalPendingDepositMatchCommand(
                case_no=str(preview.case_no),
                staff_id=int(pairing.staff_id),
                actor=request.actor,
                source_identity=request.row.source_identity,
            )
        )

    def _append_assignment_candidates(
        self, preview: HistoricalOrderAdoptionPreview
    ) -> tuple[int, ...]:
        if (
            preview.outcome is not HistoricalOrderOutcome.ADOPTED
            or preview.case_no is None
        ):
            return ()
        return self._scheduling_historical_assignment.append_completed_assignments(
            preview.case_no,
            tuple(
                (item.staff_id, item.start_date, item.end_date)
                for item in preview.pairings
                if item.resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
            ),
        )

    def _replay(self, request, command_fingerprint):
        stored = self._repository.find_receipt(
            request.idempotency_key,
            request.row.source_identity,
        )
        if stored is None:
            return None
        if str(stored["command_fingerprint"]) != command_fingerprint.value:
            raise RuntimeError("historical_order_idempotency_conflict")
        return HistoricalOrderAdoptionReceipt(
            HistoricalOrderOutcome(str(stored["outcome"])),
            stored.get("case_no"),
            _optional_int(stored.get("resulting_version")),
            int(stored.get("assignment_count") or 0),
            stored.get("review_identity"),
            True,
            PreviewFingerprint(str(stored["preview_fingerprint"])),
        )

    def _build_preview(self, row, *, for_update):
        if (
            not row.case_no
            or not row.client_name
            or not row.asserted_status
            or row.asserted_status is HistoricalOrderSourceStatus.CANCELLED
            or (
                row.asserted_status is HistoricalOrderSourceStatus.DISCUSSION
                and not any(item.name for item in row.caregivers)
            )
        ):
            return _unmatched_preview(row)
        current = self._repository.load_order(row.case_no, row.client_name, for_update=for_update)
        if current is None:
            return _unmatched_preview(row)
        source_issues = row.issue_codes
        if current.client_name != row.client_name:
            return _unmatched_preview(row)
        source = HistoricalOrderSourceFacts(
            row.asserted_status,
            row.actual_start_date,
            row.actual_end_date,
            source_issues,
        )
        candidate = build_historical_order_candidate(
            current,
            source,
            self._clock.today(),
        )
        if candidate.result is HistoricalOrderResult.NOT_ADOPTED:
            return _not_adopted_preview(row, current)
        pairings = self._pairings(row, current, candidate, for_update)
        issues = tuple(
            sorted(
                set(
                    candidate.issue_codes
                    + tuple(
                        code
                        for item in pairings
                        for code in item.issue_codes
                    )
                )
            )
        )
        calendar_issues = _historical_calendar_integrity_issues(candidate, pairings)
        if calendar_issues:
            return _review_required_preview(
                row,
                current,
                candidate,
                pairings,
                tuple(sorted(set(issues + calendar_issues))),
            )
        if (
            candidate.result is HistoricalOrderResult.MATCHING_PENDING_DEPOSIT
            and not _matching_pending_deposit_eligible(row, pairings)
        ):
            return _not_adopted_preview(row, current, pairings, issues)
        return _preview(row, current, candidate, pairings, issues)

    def _pairings(self, row, current, candidate, for_update):
        existing = self._repository.active_assignments(
            current.case_no, for_update=for_update
        )
        result = []
        for source in row.caregivers:
            result.append(
                self._pairing(
                    source,
                    existing,
                    candidate,
                    for_update,
                )
            )
        return tuple(result)

    def _pairing(
        self,
        source,
        existing,
        candidate,
        for_update,
    ):
        canonical_name = _canonical_name(source.name)
        if not source.name:
            return HistoricalPairingCandidate(source.ordinal, canonical_name, None, source.start_date, source.end_date, HistoricalPairingResolution.BLANK, ())
        staff_ids = self._repository.resolve_staff(source.name, for_update=for_update)
        if not staff_ids:
            if _historical_calendar_service_result(candidate.result):
                return HistoricalPairingCandidate(
                    source.ordinal,
                    canonical_name,
                    None,
                    source.start_date,
                    source.end_date,
                    HistoricalPairingResolution.EVIDENCE_ONLY,
                    tuple(sorted(set(source.issue_codes + ("historical_staff_not_found",)))),
                )
            return _pairing_issue(source, canonical_name, HistoricalPairingResolution.STAFF_MISSING, "historical_staff_not_found")
        if len(staff_ids) != 1:
            if _historical_calendar_service_result(candidate.result):
                return HistoricalPairingCandidate(
                    source.ordinal,
                    canonical_name,
                    None,
                    source.start_date,
                    source.end_date,
                    HistoricalPairingResolution.EVIDENCE_ONLY,
                    tuple(sorted(set(source.issue_codes + ("historical_staff_ambiguous",)))),
                )
            return _pairing_issue(source, canonical_name, HistoricalPairingResolution.STAFF_AMBIGUOUS, "historical_staff_ambiguous")
        if source.issue_codes:
            return HistoricalPairingCandidate(source.ordinal, canonical_name, staff_ids[0], source.start_date, source.end_date, HistoricalPairingResolution.EVIDENCE_ONLY, source.issue_codes)
        if (
            candidate.result
            in {
                HistoricalOrderResult.HISTORICAL_IN_SERVICE,
                HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED,
            }
            and source.start_date is not None
            and source.end_date is not None
        ):
            matching = _matching_effective_assignment(existing, staff_ids[0], source)
            if matching is not None:
                return HistoricalPairingCandidate(
                    source.ordinal,
                    canonical_name,
                    staff_ids[0],
                    source.start_date,
                    source.end_date,
                    HistoricalPairingResolution.ASSIGNMENT_REUSED,
                    (),
                    int(matching["id"]),
                )
            return HistoricalPairingCandidate(
                source.ordinal,
                canonical_name,
                staff_ids[0],
                source.start_date,
                source.end_date,
                HistoricalPairingResolution.ASSIGNMENT_CANDIDATE,
                (),
            )
        return HistoricalPairingCandidate(
            source.ordinal,
            canonical_name,
            staff_ids[0],
            source.start_date,
            source.end_date,
            HistoricalPairingResolution.EVIDENCE_ONLY,
            (),
        )


def _service_assignment_allowed(row, current, candidate) -> bool:
    """Status 1 is deposit-paid; service evidence requires a known HCM baseline."""
    return (
        candidate.outcome is HistoricalOrderOutcome.ADOPTED
        and row.asserted_status is HistoricalOrderSourceStatus.DEPOSIT_PAID
        and isinstance(current.planned_start_date, date)
        and isinstance(row.actual_start_date, date)
        and row.actual_start_date != current.planned_start_date
    )


def _historical_calendar_service_result(result):
    return result in {
        HistoricalOrderResult.HISTORICAL_IN_SERVICE,
        HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED,
    }


def _matching_effective_assignment(existing, staff_id, source):
    """Find a completed Scheduling assignment that corroborates a source interval."""
    if source.start_date is None or source.end_date is None:
        return None
    for assignment in existing:
        if assignment.get("status") != "completed":
            continue
        if assignment.get("staff_id") != staff_id:
            continue
        assigned_start = assignment.get("assigned_start_date")
        assigned_end = assignment.get("assigned_end_date")
        if (
            assigned_start == source.start_date
            and assigned_end is not None
            and source.end_date <= assigned_end
        ):
            return assignment
    return None


def _historical_calendar_integrity_issues(candidate, pairings):
    if not _historical_calendar_service_result(candidate.result):
        return ()
    has_staff = any(item.staff_id is not None for item in pairings)
    has_valid_dates = any(
        item.start_date is not None
        and item.end_date is not None
        and isinstance(item.start_date, date)
        and isinstance(item.end_date, date)
        and item.start_date <= item.end_date
        for item in pairings
    )
    has_completed_assignment = any(
        item.resolution
        in {
            HistoricalPairingResolution.ASSIGNMENT_CANDIDATE,
            HistoricalPairingResolution.ASSIGNMENT_REUSED,
        }
        for item in pairings
    )
    issues = []
    if not has_staff:
        issues.append("historical_calendar_staff_missing")
    if not has_valid_dates:
        issues.append("historical_calendar_valid_dates_missing")
    if not has_completed_assignment:
        issues.append("historical_calendar_completed_assignment_missing")
    return tuple(issues)


def _matching_pending_deposit_eligible(row, pairings) -> bool:
    return (
        row.actual_start_date is None
        and len(pairings) == 1
        and pairings[0].staff_id is not None
        and pairings[0].resolution is HistoricalPairingResolution.EVIDENCE_ONLY
        and not pairings[0].issue_codes
    )


def _preview(row, current, candidate, pairings, issues):
    payload = {
        "source_identity": row.source_identity,
        "source_fingerprint": row.source_fingerprint,
        "case_no": current.case_no,
        "candidate_fingerprint": candidate.fingerprint.value,
        "pairings": tuple(_pairing_payload(item) for item in pairings),
        "issue_codes": issues,
    }
    return HistoricalOrderAdoptionPreview(
        row.source_identity,
        row.source_fingerprint,
        candidate.outcome,
        current.case_no,
        current.lifecycle_version,
        candidate.resulting_version,
        current.status.value,
        candidate.after_status.value,
        candidate.date_patch,
        pairings,
        issues,
        fingerprint_payload(payload),
    )


def _review_required_preview(row, current, candidate, pairings, issues):
    payload = {
        "source_identity": row.source_identity,
        "source_fingerprint": row.source_fingerprint,
        "case_no": current.case_no,
        "candidate_fingerprint": candidate.fingerprint.value,
        "outcome": HistoricalOrderOutcome.REVIEW_REQUIRED.value,
        "pairings": tuple(_pairing_payload(item) for item in pairings),
        "issue_codes": tuple(issues),
    }
    return HistoricalOrderAdoptionPreview(
        row.source_identity,
        row.source_fingerprint,
        HistoricalOrderOutcome.REVIEW_REQUIRED,
        current.case_no,
        current.lifecycle_version,
        current.lifecycle_version,
        current.status.value,
        current.status.value,
        (),
        tuple(pairings),
        tuple(issues),
        fingerprint_payload(payload),
    )


def _unmatched_preview(row):
    fingerprint = fingerprint_payload({
        "source_identity": row.source_identity,
        "source_fingerprint": row.source_fingerprint,
        "outcome": HistoricalOrderOutcome.UNMATCHED_CASE.value,
    })
    return HistoricalOrderAdoptionPreview(
        row.source_identity,
        row.source_fingerprint,
        HistoricalOrderOutcome.UNMATCHED_CASE,
        row.case_no,
        None,
        None,
        None,
        None,
        (),
        (),
        tuple(sorted(set(row.issue_codes))),
        fingerprint,
    )


def _not_adopted_preview(row, current, pairings=(), issues=()):
    payload = {
        "source_identity": row.source_identity,
        "source_fingerprint": row.source_fingerprint,
        "case_no": current.case_no,
        "outcome": HistoricalOrderOutcome.UNMATCHED_CASE.value,
        "pairings": tuple(_pairing_payload(item) for item in pairings),
        "issue_codes": tuple(issues),
    }
    return HistoricalOrderAdoptionPreview(
        row.source_identity,
        row.source_fingerprint,
        HistoricalOrderOutcome.UNMATCHED_CASE,
        current.case_no,
        current.lifecycle_version,
        current.lifecycle_version,
        current.status.value,
        current.status.value,
        (),
        tuple(pairings),
        tuple(issues),
        fingerprint_payload(payload),
    )


def _unmatched_receipt(preview):
    return HistoricalOrderAdoptionReceipt(
        HistoricalOrderOutcome.UNMATCHED_CASE,
        preview.case_no,
        None,
        0,
        None,
        False,
        preview.fingerprint,
    )


def _pairing_issue(source, canonical_name, resolution, issue, staff_id=None):
    return HistoricalPairingCandidate(
        source.ordinal,
        canonical_name,
        staff_id,
        source.start_date,
        source.end_date,
        resolution,
        tuple(sorted(set(source.issue_codes + (issue,)))),
    )


def _pairing_payload(item):
    return {
        "ordinal": item.ordinal,
        "staff_id": item.staff_id,
        "start_date": item.start_date.isoformat() if item.start_date else None,
        "end_date": item.end_date.isoformat() if item.end_date else None,
        "resolution": item.resolution.value,
        "issue_codes": item.issue_codes,
        "assignment_id": item.assignment_id,
    }


def _command_fingerprint(request):
    return fingerprint_payload({
        "source_identity": request.row.source_identity,
        "source_fingerprint": request.row.source_fingerprint,
    })


def _canonical_name(name):
    return str(name or "").strip()


def _optional_int(value):
    return None if value is None else int(value)


__all__ = [
    "HistoricalOrderAdoptionPreview",
    "HistoricalOrderAdoptionReceipt",
    "HistoricalOrderAdoptionRequest",
    "HistoricalOrderAdoptionWorkflow",
    "HistoricalPairingCandidate",
    "HistoricalPairingResolution",
    "SchedulingHistoricalAssignmentPort",
]
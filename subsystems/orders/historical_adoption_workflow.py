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
    HistoricalOrderSourceFacts,
    HistoricalOrderSourceStatus,
    build_historical_order_candidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.ports import UnitOfWork
from subsystems.orders.historical_actual_start_rebuild import (
    HistoricalActualStartRebuilder,
)
from subsystems.orders.historical_order_workbook import HistoricalOrderWorkbookRow


class HistoricalPairingResolution(StrEnum):
    BLANK = "blank"
    STAFF_MISSING = "staff_missing"
    STAFF_AMBIGUOUS = "staff_ambiguous"
    EVIDENCE_ONLY = "evidence_only"
    ASSIGNMENT_CANDIDATE = "assignment_candidate"
    ASSIGNMENT_CONFLICT = "assignment_conflict"


@dataclass(frozen=True, slots=True)
class HistoricalPairingCandidate:
    ordinal: int
    masked_name: str
    staff_id: int | None
    start_date: object | None
    end_date: object | None
    resolution: HistoricalPairingResolution
    issue_codes: tuple[str, ...]


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
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._scheduling_historical_assignment = scheduling_historical_assignment
        self._actual_start_rebuilder = actual_start_rebuilder

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
            # Older status-1 receipts can predate the service-evidence bridge.
            # Re-evaluate the immutable source, append only missing historical
            # assignment evidence, then let the delegated canonical command
            # repair Scheduling/Actual Start under its own idempotency key.
            preview = self._build_preview(request.row, for_update=True)
            self._append_assignment_candidates(preview)
            self._rebuild_actual_service_period(request, preview)
            return replay
        preview = self._build_preview(request.row, for_update=True)
        if preview.fingerprint != request.preview_fingerprint:
            raise RuntimeError("historical_order_candidate_stale")
        if preview.outcome is HistoricalOrderOutcome.UNMATCHED_CASE:
            return _unmatched_receipt(preview)
        assignment_ids = self._append_assignment_candidates(preview)
        receipt = self._repository.persist(request, preview, assignment_ids)
        self._rebuild_actual_service_period(request, preview)
        return receipt

    def _append_assignment_candidates(
        self, preview: HistoricalOrderAdoptionPreview
    ) -> tuple[int, ...]:
        if preview.case_no is None:
            return ()
        return self._scheduling_historical_assignment.append_completed_assignments(
            preview.case_no,
            tuple(
                (item.staff_id, item.start_date, item.end_date)
                for item in preview.pairings
                if item.resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
            ),
        )

    def _rebuild_actual_service_period(self, request, preview) -> None:
        if self._actual_start_rebuilder is None:
            return
        if (
            preview.outcome is not HistoricalOrderOutcome.ADOPTED
            or preview.case_no is None
            or request.row.asserted_status is not HistoricalOrderSourceStatus.DEPOSIT_PAID
        ):
            return
        actual_start_date = request.row.actual_start_date
        if not isinstance(actual_start_date, date):
            return
        current = self._repository.load_order(
            preview.case_no,
            request.row.client_name,
            for_update=True,
        )
        if (
            current is None
            or current.planned_start_date == actual_start_date
        ):
            return
        self._actual_start_rebuilder.apply_in_current_unit_of_work(
            case_no=preview.case_no,
            actual_start_date=actual_start_date,
            source_identity=request.row.source_identity,
            actor=request.actor,
            correlation_id=request.correlation_id,
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
        if not row.case_no or not row.client_name:
            return _unmatched_preview(row)
        current = self._repository.load_order(row.case_no, row.client_name, for_update=for_update)
        if current is None:
            return _unmatched_preview(row)
        source_issues = row.issue_codes
        if current.client_name != row.client_name:
            source_issues = tuple(
                sorted(set(source_issues + ("historical_client_name_mismatch",)))
            )
        source = HistoricalOrderSourceFacts(
            row.asserted_status,
            row.actual_start_date,
            row.actual_end_date,
            source_issues,
        )
        candidate = build_historical_order_candidate(current, source)
        pairings = self._pairings(row, current, candidate, for_update)
        issues = tuple(sorted(set(candidate.issue_codes + tuple(code for item in pairings for code in item.issue_codes))))
        return _preview(row, current, candidate, pairings, issues)

    def _pairings(self, row, current, candidate, for_update):
        existing = self._repository.active_assignments(
            current.case_no, for_update=for_update
        )
        service_assignment_allowed = _service_assignment_allowed(
            row, current, candidate
        )
        result = []
        for source in row.caregivers:
            result.append(
                self._pairing(
                    source,
                    existing,
                    candidate,
                    service_assignment_allowed,
                    for_update,
                )
            )
        return tuple(result)

    def _pairing(
        self,
        source,
        existing,
        candidate,
        service_assignment_allowed,
        for_update,
    ):
        masked = _mask_name(source.name)
        if not source.name:
            return HistoricalPairingCandidate(source.ordinal, masked, None, source.start_date, source.end_date, HistoricalPairingResolution.BLANK, ())
        staff_ids = self._repository.resolve_staff(source.name, for_update=for_update)
        if not staff_ids:
            return _pairing_issue(source, masked, HistoricalPairingResolution.STAFF_MISSING, "historical_staff_not_found")
        if len(staff_ids) != 1:
            return _pairing_issue(source, masked, HistoricalPairingResolution.STAFF_AMBIGUOUS, "historical_staff_ambiguous")
        if source.issue_codes:
            return HistoricalPairingCandidate(source.ordinal, masked, staff_ids[0], source.start_date, source.end_date, HistoricalPairingResolution.EVIDENCE_ONLY, source.issue_codes)
        if (
            not source.has_individual_interval
            or source.start_date is None
            or source.end_date is None
        ):
            return _pairing_issue(
                source,
                masked,
                HistoricalPairingResolution.ASSIGNMENT_CONFLICT,
                "historical_assignment_evidence_insufficient",
                staff_ids[0],
            )
        if (
            candidate.outcome is not HistoricalOrderOutcome.ADOPTED
            or not service_assignment_allowed
            or existing
        ):
            return _pairing_issue(source, masked, HistoricalPairingResolution.ASSIGNMENT_CONFLICT, "historical_assignment_conflict", staff_ids[0])
        return HistoricalPairingCandidate(source.ordinal, masked, staff_ids[0], source.start_date, source.end_date, HistoricalPairingResolution.ASSIGNMENT_CANDIDATE, source.issue_codes)


def _service_assignment_allowed(row, current, candidate) -> bool:
    """Status 1 is deposit-paid; service evidence comes from actual-start facts."""
    return (
        candidate.outcome is HistoricalOrderOutcome.ADOPTED
        and row.asserted_status is HistoricalOrderSourceStatus.DEPOSIT_PAID
        and isinstance(row.actual_start_date, date)
        and row.actual_start_date != current.planned_start_date
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


def _pairing_issue(source, masked, resolution, issue, staff_id=None):
    return HistoricalPairingCandidate(
        source.ordinal,
        masked,
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
    }


def _command_fingerprint(request):
    return fingerprint_payload({
        "source_identity": request.row.source_identity,
        "source_fingerprint": request.row.source_fingerprint,
    })


def _mask_name(name):
    text = str(name or "").strip()
    if not text:
        return ""
    if len(text) == 1:
        return "*"
    return text[0] + "*" * (len(text) - 1)


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

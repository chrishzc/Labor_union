"""Assignment-only remediation for legacy historical calendar occupancy gaps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Protocol

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.historical_order_workbook import (
    HistoricalCaregiverSource,
    HistoricalOrderWorkbookRow,
    load_historical_order_workbook,
)


_FAMILY = "orders_historical_calendar_assignment_remediation/v1"
_ALLOWED_STATUSES = frozenset(
    {
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }
)


@dataclass(frozen=True, slots=True)
class HistoricalCalendarAssignmentCaseFacts:
    case_no: str
    client_name: str
    status: OrderLifecycleStatus
    lifecycle_version: int


@dataclass(frozen=True, slots=True)
class HistoricalCalendarAssignmentPreview:
    case_no: str
    caregiver_ordinal: int
    order_status: str
    lifecycle_version: int
    source_content_digest: str
    source_identity: str
    source_fingerprint: str
    staff_id: int | None
    staff_name: str | None
    start_date: date | None
    end_date: date | None
    existing_assignment_id: int | None
    disposition: str
    blockers: tuple[str, ...]
    apply_allowed: bool
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class HistoricalCalendarAssignmentReceipt:
    receipt_key: str
    case_no: str
    caregiver_ordinal: int
    assignment_id: int
    created: bool
    lifecycle_version: int
    source_content_digest: str
    preview_fingerprint: str
    replayed: bool


class HistoricalCalendarAssignmentRemediationError(Exception):
    def __init__(self, code: str, *, blockers: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.blockers = blockers


class HistoricalCalendarAssignmentRemediationRepository(Protocol):
    def load_case(
        self, case_no: str, *, for_update: bool
    ) -> HistoricalCalendarAssignmentCaseFacts | None: ...

    def resolve_staff(self, name: str, *, for_update: bool) -> tuple[int, ...]: ...

    def find_matching_completed_assignment(
        self,
        case_no: str,
        staff_id: int,
        start_date: date,
        end_date: date,
        *,
        for_update: bool,
    ) -> int | None: ...

    def append_completed_assignment(
        self, case_no: str, staff_id: int, start_date: date, end_date: date
    ) -> int: ...

    def load_receipt(self, family: str, key: str): ...

    def save_receipt(
        self,
        family: str,
        key: str,
        request_fingerprint: str,
        preview_fingerprint: str,
        actor: str,
        reason: str,
        result: dict[str, object],
    ) -> None: ...


class HistoricalCalendarAssignmentRemediationApplication:
    def __init__(
        self,
        repository: HistoricalCalendarAssignmentRemediationRepository,
        unit_of_work_factory: Callable[[], object],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(
        self,
        source_path: str | Path,
        case_no: str,
        caregiver_ordinal: int,
    ) -> HistoricalCalendarAssignmentPreview:
        workbook = load_historical_order_workbook(source_path)
        row = _row_for_case(workbook.rows, case_no)
        return preview_row(
            self._repository,
            row,
            workbook.content_digest,
            caregiver_ordinal,
            for_update=False,
        )

    def apply(
        self,
        source_path: str | Path,
        case_no: str,
        caregiver_ordinal: int,
        expected_lifecycle_version: int,
        preview_fingerprint: str,
        idempotency_key: str,
        actor: str,
        reason: str,
    ) -> HistoricalCalendarAssignmentReceipt:
        if not idempotency_key.strip():
            raise HistoricalCalendarAssignmentRemediationError(
                "historical_calendar_assignment_idempotency_key_required"
            )
        if not actor.strip():
            raise HistoricalCalendarAssignmentRemediationError(
                "historical_calendar_assignment_actor_required"
            )
        if not reason.strip():
            raise HistoricalCalendarAssignmentRemediationError(
                "historical_calendar_assignment_reason_required"
            )
        workbook = load_historical_order_workbook(source_path)
        row = _row_for_case(workbook.rows, case_no)
        with self._unit_of_work_factory() as unit_of_work:
            receipt = apply_row(
                self._repository,
                row,
                workbook.content_digest,
                caregiver_ordinal,
                expected_lifecycle_version,
                preview_fingerprint,
                idempotency_key,
                actor,
                reason,
            )
            unit_of_work.commit()
        return receipt


def preview_row(
    repository: HistoricalCalendarAssignmentRemediationRepository,
    row: HistoricalOrderWorkbookRow,
    content_digest: str,
    caregiver_ordinal: int,
    *,
    for_update: bool,
) -> HistoricalCalendarAssignmentPreview:
    if caregiver_ordinal < 1:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_caregiver_ordinal_invalid"
        )
    if not row.case_no:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_case_no_required"
        )
    case = repository.load_case(row.case_no, for_update=for_update)
    if case is None:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_case_not_found"
        )

    source = _caregiver(row, caregiver_ordinal)
    staff_ids = (
        repository.resolve_staff(source.name, for_update=for_update)
        if source is not None and source.name
        else ()
    )
    blockers = _blockers(case, row, source, staff_ids)
    staff_id = staff_ids[0] if len(staff_ids) == 1 else None
    existing_assignment_id = None
    if source is not None and not blockers:
        existing_assignment_id = repository.find_matching_completed_assignment(
            row.case_no,
            int(staff_id),
            source.start_date,
            source.end_date,
            for_update=for_update,
        )

    if blockers:
        disposition = "blocked"
    elif existing_assignment_id is not None:
        disposition = "reuse_existing"
    else:
        disposition = "create_completed_assignment"

    payload = {
        "case_no": row.case_no,
        "caregiver_ordinal": caregiver_ordinal,
        "order_status": case.status.value,
        "lifecycle_version": case.lifecycle_version,
        "source_content_digest": content_digest,
        "source_identity": row.source_identity,
        "source_fingerprint": row.source_fingerprint,
        "staff_id": staff_id,
        "staff_name": None if source is None else source.name,
        "start_date": _iso(None if source is None else source.start_date),
        "end_date": _iso(None if source is None else source.end_date),
        "existing_assignment_id": existing_assignment_id,
        "disposition": disposition,
        "blockers": blockers,
    }
    return HistoricalCalendarAssignmentPreview(
        case_no=row.case_no,
        caregiver_ordinal=caregiver_ordinal,
        order_status=case.status.value,
        lifecycle_version=case.lifecycle_version,
        source_content_digest=content_digest,
        source_identity=row.source_identity,
        source_fingerprint=row.source_fingerprint,
        staff_id=staff_id,
        staff_name=None if source is None else source.name,
        start_date=None if source is None else source.start_date,
        end_date=None if source is None else source.end_date,
        existing_assignment_id=existing_assignment_id,
        disposition=disposition,
        blockers=blockers,
        apply_allowed=not blockers,
        preview_fingerprint=fingerprint_payload(payload).value,
    )


def apply_row(
    repository: HistoricalCalendarAssignmentRemediationRepository,
    row: HistoricalOrderWorkbookRow,
    content_digest: str,
    caregiver_ordinal: int,
    expected_lifecycle_version: int,
    preview_fingerprint: str,
    idempotency_key: str,
    actor: str,
    reason: str,
) -> HistoricalCalendarAssignmentReceipt:
    request_fingerprint = fingerprint_payload(
        {
            "case_no": row.case_no,
            "source_content_digest": content_digest,
            "source_fingerprint": row.source_fingerprint,
            "caregiver_ordinal": caregiver_ordinal,
            "expected_lifecycle_version": expected_lifecycle_version,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor.strip(),
            "reason": reason.strip(),
        }
    ).value
    stored = repository.load_receipt(_FAMILY, idempotency_key)
    if stored is not None:
        if stored["request_fingerprint"] != request_fingerprint:
            raise HistoricalCalendarAssignmentRemediationError(
                "historical_calendar_assignment_idempotency_key_conflict"
            )
        return _receipt_from_snapshot(stored["result_snapshot"], replayed=True)

    current = preview_row(
        repository,
        row,
        content_digest,
        caregiver_ordinal,
        for_update=True,
    )
    if current.lifecycle_version != expected_lifecycle_version:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_stale_preview"
        )
    if current.preview_fingerprint != preview_fingerprint:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_stale_preview"
        )
    if not current.apply_allowed:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_blocked",
            blockers=current.blockers,
        )

    if current.existing_assignment_id is not None:
        assignment_id = current.existing_assignment_id
        created = False
    else:
        assignment_id = repository.append_completed_assignment(
            current.case_no,
            int(current.staff_id),
            current.start_date,
            current.end_date,
        )
        readback = repository.find_matching_completed_assignment(
            current.case_no,
            int(current.staff_id),
            current.start_date,
            current.end_date,
            for_update=True,
        )
        if readback != assignment_id:
            raise HistoricalCalendarAssignmentRemediationError(
                "historical_calendar_assignment_readback_failed"
            )
        created = True

    receipt = HistoricalCalendarAssignmentReceipt(
        receipt_key=idempotency_key,
        case_no=current.case_no,
        caregiver_ordinal=current.caregiver_ordinal,
        assignment_id=assignment_id,
        created=created,
        lifecycle_version=current.lifecycle_version,
        source_content_digest=current.source_content_digest,
        preview_fingerprint=current.preview_fingerprint,
        replayed=False,
    )
    repository.save_receipt(
        _FAMILY,
        idempotency_key,
        request_fingerprint,
        preview_fingerprint,
        actor.strip(),
        reason.strip(),
        _receipt_payload(receipt),
    )
    return receipt


def _row_for_case(
    rows: tuple[HistoricalOrderWorkbookRow, ...],
    case_no: str,
) -> HistoricalOrderWorkbookRow:
    normalized = str(case_no).strip()
    if not normalized:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_case_no_required"
        )
    matches = tuple(row for row in rows if row.case_no == normalized)
    if not matches:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_source_case_not_found"
        )
    if len(matches) != 1:
        raise HistoricalCalendarAssignmentRemediationError(
            "historical_calendar_assignment_source_case_not_unique"
        )
    return matches[0]


def _caregiver(
    row: HistoricalOrderWorkbookRow,
    caregiver_ordinal: int,
) -> HistoricalCaregiverSource | None:
    return next(
        (item for item in row.caregivers if item.ordinal == caregiver_ordinal),
        None,
    )


def _blockers(
    case: HistoricalCalendarAssignmentCaseFacts,
    row: HistoricalOrderWorkbookRow,
    source: HistoricalCaregiverSource | None,
    staff_ids: tuple[int, ...],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if case.status not in _ALLOWED_STATUSES:
        blockers.append("historical_calendar_assignment_status_not_eligible")
    if not row.client_name:
        blockers.append("historical_calendar_assignment_source_client_missing")
    elif row.client_name != case.client_name:
        blockers.append("historical_calendar_assignment_source_client_mismatch")
    if source is None:
        blockers.append("historical_calendar_assignment_caregiver_source_missing")
        return tuple(sorted(set(blockers)))
    if not source.name or not staff_ids:
        blockers.append("historical_calendar_assignment_staff_missing")
    elif len(staff_ids) != 1:
        blockers.append("historical_calendar_assignment_staff_ambiguous")
    if source.start_date is None or source.end_date is None:
        blockers.append("historical_calendar_assignment_dates_missing")
    elif source.start_date > source.end_date:
        blockers.append("historical_calendar_assignment_date_range_invalid")
    date_issue_codes = {
        "historical_order_start_date_invalid",
        "historical_order_end_date_invalid",
        "historical_order_date_range_invalid",
    }
    if source.issue_codes or date_issue_codes.intersection(row.issue_codes):
        blockers.append("historical_calendar_assignment_dates_invalid")
    return tuple(sorted(set(blockers)))


def _receipt_payload(
    receipt: HistoricalCalendarAssignmentReceipt,
) -> dict[str, object]:
    return {
        "receipt_key": receipt.receipt_key,
        "case_no": receipt.case_no,
        "caregiver_ordinal": receipt.caregiver_ordinal,
        "assignment_id": receipt.assignment_id,
        "created": receipt.created,
        "lifecycle_version": receipt.lifecycle_version,
        "source_content_digest": receipt.source_content_digest,
        "preview_fingerprint": receipt.preview_fingerprint,
    }


def _receipt_from_snapshot(snapshot, *, replayed: bool):
    payload = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    return HistoricalCalendarAssignmentReceipt(
        receipt_key=str(payload["receipt_key"]),
        case_no=str(payload["case_no"]),
        caregiver_ordinal=int(payload["caregiver_ordinal"]),
        assignment_id=int(payload["assignment_id"]),
        created=bool(payload["created"]),
        lifecycle_version=int(payload["lifecycle_version"]),
        source_content_digest=str(payload["source_content_digest"]),
        preview_fingerprint=str(payload["preview_fingerprint"]),
        replayed=replayed,
    )


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "HistoricalCalendarAssignmentCaseFacts",
    "HistoricalCalendarAssignmentPreview",
    "HistoricalCalendarAssignmentReceipt",
    "HistoricalCalendarAssignmentRemediationApplication",
    "HistoricalCalendarAssignmentRemediationError",
    "HistoricalCalendarAssignmentRemediationRepository",
    "apply_row",
    "preview_row",
]

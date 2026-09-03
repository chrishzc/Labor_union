"""Assignment-only repair workflow for existing historical order calendar occupancy."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from typing import Callable, Protocol

from domains.orders.historical_adoption import HistoricalOrderCurrentFacts
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, ExpectedVersion
from shared_kernel.ports import UnitOfWork
from subsystems.orders.historical_adoption_workflow import SchedulingHistoricalAssignmentPort


_FAMILY = "historical_completed_assignment_repair/v1"
_REPAIRABLE_STATUSES = frozenset(
    {
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }
)


@dataclass(frozen=True, slots=True)
class HistoricalCompletedAssignmentRepairIntent:
    case_no: str
    staff_name: str | None
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True, slots=True)
class HistoricalCompletedAssignmentRepairPreview:
    case_no: str
    order_status: str | None
    expected_order_version: int | None
    masked_staff_name: str
    staff_id: int | None
    start_date: date | None
    end_date: date | None
    reusable_assignment_id: int | None
    applicable: bool
    reusable: bool
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ApplyHistoricalCompletedAssignmentRepair:
    intent: HistoricalCompletedAssignmentRepairIntent
    expected_order_version: int
    preview_fingerprint: PreviewFingerprint
    idempotency_key: str
    actor: str
    reason: str
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class HistoricalCompletedAssignmentRepairReceipt:
    receipt_key: str
    case_no: str
    order_version: int
    staff_id: int
    start_date: date
    end_date: date
    assignment_id: int
    assignment_created: bool
    reused_existing: bool
    preview_fingerprint: PreviewFingerprint
    replayed: bool = False


class HistoricalCompletedAssignmentRepairError(Exception):
    def __init__(self, error: TypedError) -> None:
        self.error = error
        super().__init__(error.code)


class HistoricalCompletedAssignmentRepairFacts(Protocol):
    def load_order(
        self,
        case_no: str,
        client_name: str,
        *,
        for_update: bool,
    ) -> HistoricalOrderCurrentFacts | None: ...

    def resolve_staff(self, name: str, *, for_update: bool) -> tuple[int, ...]: ...

    def active_assignments(
        self,
        case_no: str,
        *,
        for_update: bool,
    ) -> tuple[dict[str, object], ...]: ...


class HistoricalCompletedAssignmentRepairReceipts(Protocol):
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


class HistoricalCompletedAssignmentRepairWorkflow:
    def __init__(
        self,
        facts: HistoricalCompletedAssignmentRepairFacts,
        receipts: HistoricalCompletedAssignmentRepairReceipts,
        unit_of_work_factory: Callable[[], UnitOfWork],
        assignment_writer: SchedulingHistoricalAssignmentPort,
    ) -> None:
        self._facts = facts
        self._receipts = receipts
        self._unit_of_work_factory = unit_of_work_factory
        self._assignment_writer = assignment_writer

    def preview(
        self,
        intent: HistoricalCompletedAssignmentRepairIntent,
    ) -> HistoricalCompletedAssignmentRepairPreview:
        return self._build_preview(intent, for_update=False)

    def apply(
        self,
        request: ApplyHistoricalCompletedAssignmentRepair,
    ) -> HistoricalCompletedAssignmentRepairReceipt:
        request_fingerprint = _request_fingerprint(request)
        with self._unit_of_work_factory() as unit_of_work:
            stored = self._receipts.load_receipt(_FAMILY, request.idempotency_key)
            if stored is not None:
                return _replay(stored, request_fingerprint, request)

            current = self._build_preview(request.intent, for_update=True)

            # A second locking read is intentional: another command for the same
            # case may have completed while this transaction was waiting on the
            # order root.  The receipt is the idempotency owner, while the order
            # row is the serialization root for assignment-only repairs.
            stored = self._receipts.load_receipt(_FAMILY, request.idempotency_key)
            if stored is not None:
                return _replay(stored, request_fingerprint, request)

            if (
                current.expected_order_version != request.expected_order_version
                or current.fingerprint != request.preview_fingerprint
            ):
                raise _error(
                    request,
                    ErrorCategory.CONFLICT,
                    "historical_assignment_repair_preview_stale",
                    current.expected_order_version,
                )
            if current.blockers:
                raise _error(
                    request,
                    ErrorCategory.DOMAIN_BLOCKED,
                    current.blockers[0],
                    current.expected_order_version,
                    current.blockers,
                )

            assert current.staff_id is not None
            assert current.start_date is not None and current.end_date is not None
            assert current.expected_order_version is not None

            assignment_created = current.reusable_assignment_id is None
            if assignment_created:
                assignment_ids = self._assignment_writer.append_completed_assignments(
                    current.case_no,
                    ((current.staff_id, current.start_date, current.end_date),),
                )
                if len(assignment_ids) != 1:
                    raise _error(
                        request,
                        ErrorCategory.INTERNAL,
                        "historical_assignment_repair_writer_result_invalid",
                        current.expected_order_version,
                    )
                assignment_id = int(assignment_ids[0])
            else:
                assignment_id = int(current.reusable_assignment_id)

            receipt = HistoricalCompletedAssignmentRepairReceipt(
                request.idempotency_key,
                current.case_no,
                current.expected_order_version,
                current.staff_id,
                current.start_date,
                current.end_date,
                assignment_id,
                assignment_created,
                not assignment_created,
                request.preview_fingerprint,
                False,
            )
            self._receipts.save_receipt(
                _FAMILY,
                request.idempotency_key,
                request_fingerprint,
                request.preview_fingerprint.value,
                request.actor,
                request.reason,
                _receipt_payload(receipt),
            )
            unit_of_work.commit()
            return receipt

    def _build_preview(
        self,
        intent: HistoricalCompletedAssignmentRepairIntent,
        *,
        for_update: bool,
    ) -> HistoricalCompletedAssignmentRepairPreview:
        case_no = str(intent.case_no or "").strip()
        staff_name = str(intent.staff_name or "").strip()
        blockers: list[str] = []
        current = None
        staff_ids: tuple[int, ...] = ()
        assignments: tuple[dict[str, object], ...] = ()

        if not case_no:
            blockers.append("historical_assignment_repair_case_missing")
        else:
            # The existing historical-adoption repository intentionally ignores
            # client_name at persistence level; case_no remains the order root.
            current = self._facts.load_order(case_no, "", for_update=for_update)
            if current is None:
                blockers.append("historical_assignment_repair_case_not_found")
            elif current.status not in _REPAIRABLE_STATUSES:
                blockers.append("historical_assignment_repair_order_not_historical_service")

        if not staff_name:
            blockers.append("historical_assignment_repair_staff_missing")
        elif current is not None:
            staff_ids = tuple(self._facts.resolve_staff(staff_name, for_update=for_update))
            if not staff_ids:
                blockers.append("historical_assignment_repair_staff_missing")
            elif len(staff_ids) != 1:
                blockers.append("historical_assignment_repair_staff_ambiguous")

        start_date = intent.start_date
        end_date = intent.end_date
        if start_date is None or end_date is None:
            blockers.append("historical_assignment_repair_date_missing")
        elif (
            not isinstance(start_date, date)
            or not isinstance(end_date, date)
            or start_date > end_date
        ):
            blockers.append("historical_assignment_repair_date_invalid")

        reusable_assignment_id = None
        staff_id = staff_ids[0] if len(staff_ids) == 1 else None
        if (
            current is not None
            and staff_id is not None
            and isinstance(start_date, date)
            and isinstance(end_date, date)
            and start_date <= end_date
        ):
            assignments = tuple(
                self._facts.active_assignments(case_no, for_update=for_update)
            )
            reusable_assignment_id = _matching_completed_assignment_id(
                assignments,
                staff_id,
                start_date,
                end_date,
            )

        blockers_tuple = tuple(dict.fromkeys(blockers))
        fingerprint = fingerprint_payload(
            {
                "case_no": case_no,
                "order_status": None if current is None else current.status.value,
                "order_version": None if current is None else current.lifecycle_version,
                "staff_name": staff_name,
                "staff_ids": staff_ids,
                "start_date": start_date.isoformat() if isinstance(start_date, date) else None,
                "end_date": end_date.isoformat() if isinstance(end_date, date) else None,
                "reusable_assignment_id": reusable_assignment_id,
                "blockers": blockers_tuple,
            }
        )
        return HistoricalCompletedAssignmentRepairPreview(
            case_no,
            None if current is None else current.status.value,
            None if current is None else current.lifecycle_version,
            _mask_name(staff_name),
            staff_id,
            start_date,
            end_date,
            reusable_assignment_id,
            not blockers_tuple,
            reusable_assignment_id is not None,
            blockers_tuple,
            fingerprint,
        )


def _matching_completed_assignment_id(assignments, staff_id, start_date, end_date):
    for assignment in assignments:
        if assignment.get("status") != "completed":
            continue
        if assignment.get("staff_id") != staff_id:
            continue
        if assignment.get("assigned_start_date") != start_date:
            continue
        if assignment.get("assigned_end_date") != end_date:
            continue
        return int(assignment["id"])
    return None


def _request_fingerprint(request: ApplyHistoricalCompletedAssignmentRepair) -> str:
    return fingerprint_payload(
        {
            "intent": {
                "case_no": str(request.intent.case_no or "").strip(),
                "staff_name": str(request.intent.staff_name or "").strip(),
                "start_date": (
                    request.intent.start_date.isoformat()
                    if isinstance(request.intent.start_date, date)
                    else None
                ),
                "end_date": (
                    request.intent.end_date.isoformat()
                    if isinstance(request.intent.end_date, date)
                    else None
                ),
            },
            "expected_order_version": request.expected_order_version,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor,
            "reason": request.reason,
        }
    ).value


def _receipt_payload(receipt: HistoricalCompletedAssignmentRepairReceipt) -> dict[str, object]:
    return {
        "receipt_key": receipt.receipt_key,
        "case_no": receipt.case_no,
        "order_version": receipt.order_version,
        "staff_id": receipt.staff_id,
        "start_date": receipt.start_date.isoformat(),
        "end_date": receipt.end_date.isoformat(),
        "assignment_id": receipt.assignment_id,
        "assignment_created": receipt.assignment_created,
        "reused_existing": receipt.reused_existing,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _receipt_from_snapshot(snapshot) -> HistoricalCompletedAssignmentRepairReceipt:
    payload = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    return HistoricalCompletedAssignmentRepairReceipt(
        str(payload["receipt_key"]),
        str(payload["case_no"]),
        int(payload["order_version"]),
        int(payload["staff_id"]),
        date.fromisoformat(str(payload["start_date"])),
        date.fromisoformat(str(payload["end_date"])),
        int(payload["assignment_id"]),
        bool(payload["assignment_created"]),
        bool(payload["reused_existing"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
        False,
    )


def _replay(stored, request_fingerprint, request):
    if str(stored["request_fingerprint"]) != request_fingerprint:
        raise _error(
            request,
            ErrorCategory.IDEMPOTENCY_MISMATCH,
            "historical_assignment_repair_idempotency_conflict",
        )
    return replace(_receipt_from_snapshot(stored["result_snapshot"]), replayed=True)


def _mask_name(name: str) -> str:
    if not name:
        return ""
    if len(name) == 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)


def _error(
    request,
    category,
    code,
    current_version=None,
    blockers=(),
):
    return HistoricalCompletedAssignmentRepairError(
        TypedError(
            category,
            code,
            "歷史訂單 completed assignment 人工修復失敗。",
            request.correlation_id,
            domain_blockers=tuple(blockers),
            current_version=(
                None
                if current_version is None
                else ExpectedVersion(int(current_version))
            ),
        )
    )


__all__ = [
    "ApplyHistoricalCompletedAssignmentRepair",
    "HistoricalCompletedAssignmentRepairError",
    "HistoricalCompletedAssignmentRepairIntent",
    "HistoricalCompletedAssignmentRepairPreview",
    "HistoricalCompletedAssignmentRepairReceipt",
    "HistoricalCompletedAssignmentRepairWorkflow",
]

"""
File: historical_order_workbook_import.py
Description: 協調訂單歷史 workbook Preview、Apply、replay 與逐列 Orders 採納。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Protocol

from domains.orders.historical_adoption import HistoricalOrderSourceStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionRequest, HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_order_workbook import HistoricalOrderWorkbook, load_historical_order_workbook


class HistoricalOrderWorkbookRepository(Protocol):
    def acquire_lock(self, key: str) -> bool: ...

    def release_lock(self, key: str) -> None: ...

    def load_receipt(self, key: str): ...

    def claim(self, key: str, digest: str, correlation_id: str) -> str: ...

    def find_workbook_receipt(self, key: str): ...

    def save_receipt(
        self,
        key: str,
        digest: str,
        preview_fingerprint: str,
        actor: str,
        result: dict[str, object],
    ) -> None: ...

    def find_open_review_identities(self, source_event_identities: tuple[str, ...]) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class HistoricalOrderStatusCounts:
    cancelled_0: int
    deposit_paid_1: int
    discussion_2: int
    invalid_or_blank: int

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.as_dict().values()):
            raise ValueError("historical_order_status_count_negative")

    @property
    def total(self) -> int:
        return sum(self.as_dict().values())

    def as_dict(self) -> dict[str, int]:
        return {
            "cancelled_0": self.cancelled_0,
            "deposit_paid_1": self.deposit_paid_1,
            "discussion_2": self.discussion_2,
            "invalid_or_blank": self.invalid_or_blank,
        }


@dataclass(frozen=True, slots=True)
class HistoricalOrderWorkbookPreview:
    source_content_digest: str
    sheet_identity: str
    source_row_count: int
    adopted_count: int
    unmatched_case_count: int
    review_required_count: int
    current_conflict_count: int
    assignment_candidate_count: int
    evidence_only_pairing_count: int
    status_counts: HistoricalOrderStatusCounts
    preview_fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "sheet_identity": self.sheet_identity,
            "source_row_count": self.source_row_count,
            "adopted_count": self.adopted_count,
            "unmatched_case_count": self.unmatched_case_count,
            "review_required_count": self.review_required_count,
            "current_conflict_count": self.current_conflict_count,
            "assignment_candidate_count": self.assignment_candidate_count,
            "evidence_only_pairing_count": self.evidence_only_pairing_count,
            "status_counts": self.status_counts.as_dict(),
            "preview_fingerprint": self.preview_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HistoricalOrderWorkbookReceipt:
    source_content_digest: str
    source_row_count: int
    adopted_count: int
    unmatched_case_count: int
    review_required_count: int
    current_conflict_count: int
    assignments_created: int
    replayed_rows: int
    replayed_workbook: bool
    status_counts: HistoricalOrderStatusCounts
    review_references: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "source_row_count": self.source_row_count,
            "adopted_count": self.adopted_count,
            "unmatched_case_count": self.unmatched_case_count,
            "review_required_count": self.review_required_count,
            "current_conflict_count": self.current_conflict_count,
            "assignments_created": self.assignments_created,
            "replayed_rows": self.replayed_rows,
            "replayed_workbook": self.replayed_workbook,
            "status_counts": self.status_counts.as_dict(),
            "review_references": list(self.review_references),
        }


class HistoricalOrderWorkbookConflict(RuntimeError):
    pass


class HistoricalOrderWorkbookUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HistoricalOrderSourceScheduleInterval:
    """One source-backed formal assignment interval.

    The source row is retained here because the workbook preview model does not
    otherwise carry the physical row number.  This is deliberately a small
    diagnostic projection; it is not an additional scheduling authority.
    """

    source_row: int
    pairing_ordinal: int
    case_no: str
    staff_id: int
    start_date: object
    end_date: object

    def as_dict(self) -> dict[str, object]:
        return {
            "source_row": self.source_row,
            "pairing_ordinal": self.pairing_ordinal,
            "case_identity": _mask_case(self.case_no),
            "staff_id": self.staff_id,
            "start_date": _date_value(self.start_date),
            "end_date": _date_value(self.end_date),
        }


@dataclass(frozen=True, slots=True)
class HistoricalOrderSourceScheduleConflict:
    """Deterministic pair of source intervals that cannot coexist."""

    left: HistoricalOrderSourceScheduleInterval
    right: HistoricalOrderSourceScheduleInterval

    def as_dict(self) -> dict[str, object]:
        return {"staff_id": self.left.staff_id, "left": self.left.as_dict(), "right": self.right.as_dict()}


class HistoricalOrderSourceScheduleConflictError(ValueError):
    """Stable source-conflict error with a safe, exact diagnostic projection."""

    def __init__(self, conflicts: tuple[HistoricalOrderSourceScheduleConflict, ...]) -> None:
        self.conflicts = conflicts
        super().__init__("historical_order_source_schedule_conflict")


class HistoricalOrderWorkbookImportService:
    def __init__(self, repository: HistoricalOrderWorkbookRepository, workflow: HistoricalOrderAdoptionWorkflow, unit_of_work_factory: Callable[[], object]) -> None:
        self._repository = repository
        self._workflow = workflow
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, source_path: str) -> HistoricalOrderWorkbookPreview:
        workbook = load_historical_order_workbook(source_path)
        previews = tuple(self._workflow.preview(row) for row in workbook.rows)
        return _preview(workbook, previews)

    def apply(
        self,
        source_path: str,
        key: str,
        supplied_preview_fingerprint: str,
        actor: str,
        correlation_id: str,
    ) -> HistoricalOrderWorkbookReceipt:
        if not self._repository.acquire_lock(key):
            raise HistoricalOrderWorkbookUnavailable("historical_order_workbook_coordinator_lock_timeout")
        try:
            workbook = load_historical_order_workbook(source_path)
            replay = self._stored_replay(key, workbook)
            if replay is not None:
                return replay
            row_previews = tuple(self._workflow.preview(row) for row in workbook.rows)
            preview = self._require_preview(
                workbook, row_previews, supplied_preview_fingerprint
            )
            try:
                with self._unit_of_work_factory() as unit_of_work:
                    if self._repository.claim(key, workbook.content_digest, correlation_id) == "conflict":
                        raise HistoricalOrderWorkbookConflict("historical_order_workbook_idempotency_conflict")
                    receipt = self._apply_rows(
                        workbook, key, actor, correlation_id
                    )
                    self._repository.save_receipt(
                        key,
                        workbook.content_digest,
                        preview.preview_fingerprint,
                        actor,
                        receipt.as_dict(),
                    )
                    unit_of_work.commit()
            except RuntimeError as error:
                if str(error) in {
                    "historical_order_candidate_stale",
                    "historical_order_idempotency_conflict",
                }:
                    raise HistoricalOrderWorkbookConflict(str(error)) from error
                raise
            return receipt
        finally:
            self._repository.release_lock(key)

    def _require_preview(self, workbook, row_previews, supplied):
        preview = _preview(workbook, row_previews)
        if preview.preview_fingerprint != supplied:
            raise HistoricalOrderWorkbookConflict("historical_order_preview_stale")
        return preview

    def _apply_rows(
        self, workbook, key, actor, correlation_id
    ) -> HistoricalOrderWorkbookReceipt:
        outcomes: Counter[str] = Counter()
        assignments_created = 0
        replayed_rows = 0
        review_rows = 0
        review_references: list[str] = []
        for row in workbook.rows:
            locked_preview = self._workflow.preview_in_current_unit_of_work(
                row, for_update=True
            )
            receipt = self._workflow.apply_in_current_unit_of_work(
                _row_request(
                    row,
                    locked_preview.fingerprint,
                    key,
                    actor,
                    correlation_id,
                )
            )
            outcomes[receipt.outcome.value] += 1
            assignments_created += 0 if receipt.replayed else receipt.assignment_count
            replayed_rows += int(receipt.replayed)
            review_rows += int(getattr(receipt, "review_identity", None) is not None)
            review_identity = getattr(receipt, "review_identity", None)
            if review_identity is not None and review_identity not in review_references:
                review_references.append(review_identity)
        _assert_conservation(len(workbook.rows), outcomes)
        return HistoricalOrderWorkbookReceipt(
            workbook.content_digest, len(workbook.rows), outcomes["adopted"], outcomes["unmatched_case"],
            review_rows, outcomes["current_conflict"], assignments_created, replayed_rows, False,
            _status_counts(workbook), tuple(review_references),
        )

    def _stored_replay(self, key: str, workbook: HistoricalOrderWorkbook) -> HistoricalOrderWorkbookReceipt | None:
        stored = self._repository.load_receipt(key)
        if stored is None:
            return None
        if stored["request_fingerprint"] != workbook.content_digest:
            raise HistoricalOrderWorkbookConflict("historical_order_workbook_idempotency_conflict")
        snapshot = {**json.loads(stored["result_snapshot"]), "replayed_workbook": True}
        stored_counts = snapshot.get("status_counts")
        if stored_counts is not None and "completed_1" in stored_counts:
            stored_counts = {
                **stored_counts,
                "deposit_paid_1": stored_counts["completed_1"],
            }
            stored_counts.pop("completed_1", None)
        snapshot["status_counts"] = (
            HistoricalOrderStatusCounts(**stored_counts)
            if stored_counts is not None
            else _status_counts(workbook)
        )
        if "review_references" not in snapshot:
            find_open_reviews = getattr(
                self._repository, "find_open_review_identities", None
            )
            snapshot["review_references"] = tuple(
                find_open_reviews(tuple(row.source_identity for row in workbook.rows))
                if callable(find_open_reviews)
                else ()
            )
        return HistoricalOrderWorkbookReceipt(**snapshot)


def _preview(workbook: HistoricalOrderWorkbook, row_previews) -> HistoricalOrderWorkbookPreview:
    _assert_source_schedule_consistency(row_previews, workbook.rows)
    outcomes = Counter(item.outcome.value for item in row_previews)
    candidates = sum(sum(item.resolution.value == "assignment_candidate" for item in preview.pairings) for preview in row_previews)
    evidence = sum(sum(item.resolution.value == "evidence_only" for item in preview.pairings) for preview in row_previews)
    status_counts = _status_counts(workbook)
    fingerprint = fingerprint_payload({
        "digest": workbook.content_digest,
        "sheet": workbook.sheet_identity,
        "rows": tuple((item.source_identity, item.source_fingerprint, item.fingerprint.value) for item in row_previews),
        "status_counts": status_counts.as_dict(),
    }).value
    review_rows = sum(
        item.outcome.value != "unmatched_case" and bool(getattr(item, "issue_codes", ()))
        for item in row_previews
    )
    return HistoricalOrderWorkbookPreview(
        workbook.content_digest, workbook.sheet_identity, len(workbook.rows), outcomes["adopted"],
        outcomes["unmatched_case"], review_rows, outcomes["current_conflict"],
        candidates, evidence, status_counts, fingerprint,
    )


def _status_counts(workbook: HistoricalOrderWorkbook) -> HistoricalOrderStatusCounts:
    counts = Counter(row.asserted_status for row in workbook.rows)
    result = HistoricalOrderStatusCounts(
        cancelled_0=counts[HistoricalOrderSourceStatus.CANCELLED],
        deposit_paid_1=counts[HistoricalOrderSourceStatus.DEPOSIT_PAID],
        discussion_2=counts[HistoricalOrderSourceStatus.DISCUSSION],
        invalid_or_blank=counts[None],
    )
    if result.total != len(workbook.rows):
        raise RuntimeError("historical_order_status_counts_not_conserved")
    return result


def _row_request(row, fingerprint: PreviewFingerprint, workbook_key: str, actor: str, correlation_id: str) -> HistoricalOrderAdoptionRequest:
    row_hash = sha256(f"{workbook_key}:{row.source_identity}".encode("utf-8")).hexdigest()
    return HistoricalOrderAdoptionRequest(
        row, fingerprint, f"historical-order-row:{row_hash}", actor, "資料匯入中心訂單歷史採納",
        f"{correlation_id}:row:{row.source_row}",
    )


def _assert_conservation(source_rows: int, outcomes: Counter[str]) -> None:
    if sum(outcomes.values()) != source_rows:
        raise RuntimeError("historical_order_workbook_outcomes_not_conserved")


def project_source_schedule_conflicts(
    row_previews,
    source_rows: tuple[object, ...] | None = None,
) -> tuple[HistoricalOrderSourceScheduleConflict, ...]:
    """Project all cross-case overlaps using one deterministic interval rule.

    Source intervals use a strict-overlap boundary: a later source start equal
    to an earlier source end is a legal handoff.  A same-case repeat is allowed
    because a workbook can contain multiple source assertions for one Order;
    distinct cases conflict only when their source service ranges overlap
    strictly (``next_start < previous_end``).
    """

    previews = tuple(row_previews)
    rows = tuple(source_rows) if source_rows is not None else ()
    intervals_by_staff: dict[int, list[HistoricalOrderSourceScheduleInterval]] = {}
    for index, preview in enumerate(previews):
        source_row = getattr(rows[index], "source_row", index) if index < len(rows) else index
        case_no = getattr(preview, "case_no", None)
        if case_no is None:
            continue
        for pairing_index, pairing in enumerate(preview.pairings, start=1):
            if (
                getattr(pairing.resolution, "value", pairing.resolution) == "assignment_candidate"
                and pairing.staff_id is not None
                and pairing.start_date is not None
                and pairing.end_date is not None
            ):
                interval = HistoricalOrderSourceScheduleInterval(
                    source_row,
                    getattr(pairing, "ordinal", pairing_index),
                    case_no,
                    pairing.staff_id,
                    pairing.start_date,
                    pairing.end_date,
                )
                intervals_by_staff.setdefault(pairing.staff_id, []).append(interval)

    conflicts: list[HistoricalOrderSourceScheduleConflict] = []
    for intervals in intervals_by_staff.values():
        ordered = sorted(
            intervals,
            key=lambda item: (
                item.start_date,
                item.end_date,
                item.case_no,
                item.source_row,
                item.pairing_ordinal,
            ),
        )
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if right.start_date >= left.end_date:
                    break
                if left.case_no != right.case_no and right.start_date < left.end_date:
                    conflicts.append(HistoricalOrderSourceScheduleConflict(left, right))

    return tuple(
        sorted(
            conflicts,
            key=lambda item: (
                item.left.staff_id,
                item.left.start_date,
                item.left.end_date,
                item.left.case_no,
                item.left.source_row,
                item.right.start_date,
                item.right.end_date,
                item.right.case_no,
                item.right.source_row,
            ),
        )
    )


def _assert_source_schedule_consistency(row_previews, source_rows=None) -> None:
    """Reject overlapping formal candidates inside one immutable workbook.

    The empty-DB historical migration has no pre-existing scheduling baseline.
    Therefore any overlap between different cases in the submitted source is a
    source-data/parse failure, never an Apply-time replacement decision.
    """
    conflicts = project_source_schedule_conflicts(row_previews, source_rows)
    if conflicts:
        raise HistoricalOrderSourceScheduleConflictError(conflicts)


def _date_value(value: object) -> object:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _mask_case(case_no: str | None) -> str | None:
    if not case_no:
        return None
    return f"***{case_no[-4:]}"


__all__ = [
    "HistoricalOrderWorkbookConflict", "HistoricalOrderWorkbookImportService", "HistoricalOrderWorkbookPreview",
    "HistoricalOrderWorkbookReceipt", "HistoricalOrderWorkbookUnavailable",
    "HistoricalOrderStatusCounts", "HistoricalOrderSourceScheduleConflict",
    "HistoricalOrderSourceScheduleConflictError", "HistoricalOrderSourceScheduleInterval",
    "project_source_schedule_conflicts",
]

"""
File: historical_order_workbook_import.py
Description: 協調訂單歷史 workbook Preview、Apply、replay、跨案件排程衝突排除與逐列採納。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Protocol

from domains.orders.historical_adoption import (
    HistoricalOrderOutcome,
    HistoricalOrderResult,
    HistoricalOrderSourceStatus,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.terms import ServiceTimeTerms
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

    def find_absent_orders(
        self, source_case_nos: tuple[str, ...], *, for_update: bool
    ) -> tuple[HistoricalOrderAbsenceCancellation, ...]: ...

    def cancel_absent_orders(
        self,
        candidates: tuple[HistoricalOrderAbsenceCancellation, ...],
        *,
        workbook_key: str,
        source_content_digest: str,
        actor: str,
        correlation_id: str,
    ) -> int: ...


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
class HistoricalOrderResultCounts:
    not_adopted: int
    matching_pending_deposit: int
    historical_unserved: int
    historical_in_service: int
    historical_service_completed: int

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.as_dict().values()):
            raise ValueError("historical_order_result_count_negative")

    @property
    def total(self) -> int:
        return sum(self.as_dict().values())

    def as_dict(self) -> dict[str, int]:
        return {
            "not_adopted": self.not_adopted,
            "matching_pending_deposit": self.matching_pending_deposit,
            "historical_unserved": self.historical_unserved,
            "historical_in_service": self.historical_in_service,
            "historical_service_completed": self.historical_service_completed,
        }


@dataclass(frozen=True, slots=True)
class HistoricalOrderAbsenceCancellation:
    case_no: str
    before_status: OrderLifecycleStatus
    expected_version: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.case_no, str)
            or not self.case_no
            or self.case_no.strip() != self.case_no
        ):
            raise ValueError("historical_order_absence_case_no_invalid")
        if not isinstance(self.before_status, OrderLifecycleStatus):
            raise TypeError("historical_order_absence_status_invalid")
        if self.before_status is OrderLifecycleStatus.CANCELLED:
            raise ValueError("historical_order_absence_already_cancelled")
        if (
            isinstance(self.expected_version, bool)
            or not isinstance(self.expected_version, int)
            or self.expected_version < 0
        ):
            raise ValueError("historical_order_absence_version_invalid")


@dataclass(frozen=True, slots=True)
class HistoricalOrderWorkbookRowIssue:
    source_row: int
    case_no: str | None
    fields: tuple[str, ...]
    issue_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "source_row": self.source_row,
            "case_no": self.case_no,
            "fields": list(self.fields),
            "issue_codes": list(self.issue_codes),
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
    result_counts: HistoricalOrderResultCounts
    preview_fingerprint: str
    absent_order_cancellations: tuple[HistoricalOrderAbsenceCancellation, ...] = ()
    row_issues: tuple[HistoricalOrderWorkbookRowIssue, ...] = ()

    @property
    def absent_order_cancellation_count(self) -> int:
        return len(self.absent_order_cancellations)

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
            "absent_order_cancellation_count": self.absent_order_cancellation_count,
            "status_counts": self.status_counts.as_dict(),
            "result_counts": self.result_counts.as_dict(),
            "preview_fingerprint": self.preview_fingerprint,
            "row_issues": [item.as_dict() for item in self.row_issues],
        }


@dataclass(frozen=True, slots=True)
class HistoricalOrderWorkbookImportCounts:
    imported_count: int
    duplicate_skipped_count: int
    not_imported_count: int

    def as_dict(self) -> dict[str, int]:
        return {
            "imported_count": self.imported_count,
            "duplicate_skipped_count": self.duplicate_skipped_count,
            "not_imported_count": self.not_imported_count,
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
    result_counts: HistoricalOrderResultCounts
    review_references: tuple[str, ...] = ()
    absent_order_cancellation_count: int = 0
    import_counts: HistoricalOrderWorkbookImportCounts | None = None
    row_issues: tuple[HistoricalOrderWorkbookRowIssue, ...] | None = None

    def __post_init__(self) -> None:
        value = self.absent_order_cancellation_count
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("historical_order_absence_cancellation_count_invalid")
        if self.import_counts is not None:
            counts = self.import_counts.as_dict().values()
            if any(isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts) or sum(counts) != self.source_row_count:
                raise ValueError("historical_order_import_counts_not_conserved")
            if self.row_issues is not None and len(self.row_issues) != self.import_counts.not_imported_count:
                raise ValueError("historical_order_not_imported_rows_not_conserved")

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
            "absent_order_cancellation_count": self.absent_order_cancellation_count,
            "status_counts": self.status_counts.as_dict(),
            "result_counts": self.result_counts.as_dict(),
            "review_references": list(self.review_references),
            "import_counts": None if self.import_counts is None else self.import_counts.as_dict(),
            "row_issues": None if self.row_issues is None else [item.as_dict() for item in self.row_issues],
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
    start_date: date
    end_date: date
    service_time: ServiceTimeTerms | None = None
    confirmed_dates: frozenset[date] = frozenset()

    def as_dict(self) -> dict[str, object]:
        result = {
            "source_row": self.source_row,
            "pairing_ordinal": self.pairing_ordinal,
            "case_identity": _mask_case(self.case_no),
            "staff_id": self.staff_id,
            "start_date": _date_value(self.start_date),
            "end_date": _date_value(self.end_date),
        }
        if self.service_time is not None:
            result["service_time"] = self.service_time.canonical_payload()
        return result


@dataclass(frozen=True, slots=True)
class HistoricalOrderSourceScheduleConflict:
    """Deterministic pair of source intervals that cannot coexist."""

    left: HistoricalOrderSourceScheduleInterval
    right: HistoricalOrderSourceScheduleInterval
    overlap: tuple[datetime, datetime] | None = None

    @property
    def issue_code(self) -> str:
        if self.overlap is None:
            return "historical_order_source_schedule_unconfirmed"
        return "historical_order_source_schedule_conflict"

    def as_dict(self) -> dict[str, object]:
        result = {"staff_id": self.left.staff_id, "left": self.left.as_dict(), "right": self.right.as_dict()}
        if self.overlap:
            result["overlap"] = [instant.isoformat() for instant in self.overlap]
        return result


class HistoricalOrderSourceScheduleConflictError(ValueError):
    """Stable source-conflict error with a safe, exact diagnostic projection."""

    def __init__(self, conflicts: tuple[HistoricalOrderSourceScheduleConflict, ...]) -> None:
        self.conflicts = conflicts
        super().__init__(conflicts[0].issue_code)


@dataclass(frozen=True, slots=True)
class _ConflictExclusion:
    fields: tuple[str, ...]
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ConflictExcludedRowPreview:
    source_identity: str
    source_fingerprint: str
    outcome: HistoricalOrderOutcome
    result: HistoricalOrderResult
    case_no: str | None
    pairings: tuple[object, ...]
    issue_codes: tuple[str, ...]
    conflict_fields: tuple[str, ...]
    fingerprint: PreviewFingerprint


class HistoricalOrderWorkbookImportService:
    def __init__(self, repository: HistoricalOrderWorkbookRepository, workflow: HistoricalOrderAdoptionWorkflow, unit_of_work_factory: Callable[[], object]) -> None:
        self._repository = repository
        self._workflow = workflow
        self._unit_of_work_factory = unit_of_work_factory

    def preview(self, source_path: str) -> HistoricalOrderWorkbookPreview:
        workbook = load_historical_order_workbook(source_path)
        row_previews = tuple(self._workflow.preview(row) for row in workbook.rows)
        absent_orders = self._repository.find_absent_orders(
            _source_case_nos(workbook), for_update=False
        )
        return _preview(workbook, row_previews, absent_orders)

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
            source_case_nos = _source_case_nos(workbook)
            row_previews = tuple(self._workflow.preview(row) for row in workbook.rows)
            absent_orders = self._repository.find_absent_orders(
                source_case_nos, for_update=False
            )
            preview = self._require_preview(
                workbook,
                row_previews,
                absent_orders,
                supplied_preview_fingerprint,
            )
            preview_exclusions = _source_schedule_conflict_exclusions(workbook, row_previews)
            try:
                with self._unit_of_work_factory() as unit_of_work:
                    if self._repository.claim(key, workbook.content_digest, correlation_id) == "conflict":
                        raise HistoricalOrderWorkbookConflict("historical_order_workbook_idempotency_conflict")
                    locked_absent_orders = self._repository.find_absent_orders(
                        source_case_nos, for_update=True
                    )
                    if _absence_snapshot(locked_absent_orders) != _absence_snapshot(
                        preview.absent_order_cancellations
                    ):
                        raise HistoricalOrderWorkbookConflict(
                            "historical_order_absence_preview_stale"
                        )
                    receipt = self._apply_rows(
                        workbook,
                        key,
                        actor,
                        correlation_id,
                        locked_absent_orders,
                        preview_exclusions,
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
                    "historical_order_absence_candidate_stale",
                }:
                    raise HistoricalOrderWorkbookConflict(str(error)) from error
                raise
            return receipt
        finally:
            self._repository.release_lock(key)

    def _require_preview(
        self,
        workbook,
        row_previews,
        absent_orders,
        supplied,
    ):
        preview = _preview(workbook, row_previews, absent_orders)
        if preview.preview_fingerprint != supplied:
            raise HistoricalOrderWorkbookConflict("historical_order_preview_stale")
        return preview

    def _apply_rows(
        self,
        workbook,
        key,
        actor,
        correlation_id,
        absent_orders,
        preview_exclusions=None,
    ) -> HistoricalOrderWorkbookReceipt:
        outcomes: Counter[str] = Counter()
        locked_previews: list[object] = []
        assignments_created = 0
        replayed_rows = 0
        review_rows = 0
        review_references: list[str] = []
        import_counts: Counter[str] = Counter()
        row_issues: list[HistoricalOrderWorkbookRowIssue] = []
        if workbook.rows:
            initial_locked = [
                self._workflow.preview_in_current_unit_of_work(row, for_update=True)
                for row in workbook.rows
            ]
            locked_exclusions = _source_schedule_conflict_exclusions(
                workbook, initial_locked
            )
            expected_exclusions = (
                preview_exclusions
                if preview_exclusions is not None
                else locked_exclusions
            )
            if locked_exclusions != expected_exclusions:
                raise RuntimeError("historical_order_candidate_stale")
        else:
            initial_locked = []
            locked_exclusions = {}

        mutated_cases: set[str] = set()
        for index, row in enumerate(workbook.rows):
            if index in locked_exclusions:
                excluded_preview = _project_excluded_row_preview(
                    initial_locked[index], locked_exclusions[index]
                )
                locked_previews.append(excluded_preview)
                outcomes["current_conflict"] += 1
                import_counts["not_imported_count"] += 1
                issues = _historical_row_issues(
                    replace(workbook, rows=(row,)),
                    (excluded_preview,),
                )
                row_issues.extend(
                    issues
                    or (
                        HistoricalOrderWorkbookRowIssue(
                            row.source_row,
                            row.case_no,
                            ("來源資料",),
                            ("historical_order_source_schedule_conflict",),
                        ),
                    )
                )
                continue

            if row.case_no is not None and row.case_no in mutated_cases:
                locked_preview = self._workflow.preview_in_current_unit_of_work(
                    row, for_update=True
                )
            else:
                locked_preview = initial_locked[index]
            locked_previews.append(locked_preview)
            receipt = self._workflow.apply_in_current_unit_of_work(
                _row_request(
                    row,
                    locked_preview.fingerprint,
                    key,
                    actor,
                    correlation_id,
                )
            )
            if row.case_no is not None:
                mutated_cases.add(row.case_no)
            outcomes[receipt.outcome.value] += 1
            assignments_created += 0 if receipt.replayed else receipt.assignment_count
            replayed_rows += int(receipt.replayed)
            if receipt.replayed:
                import_counts["duplicate_skipped_count"] += 1
            elif receipt.outcome.value == "adopted":
                import_counts["imported_count"] += 1
            else:
                import_counts["not_imported_count"] += 1
                issues = _historical_row_issues(
                    replace(workbook, rows=(row,)),
                    (locked_preview,),
                )
                row_issues.extend(issues or (HistoricalOrderWorkbookRowIssue(row.source_row, row.case_no, ("來源資料",), (receipt.outcome.value,)),))
            review_rows += int(getattr(receipt, "review_identity", None) is not None)
            review_identity = getattr(receipt, "review_identity", None)
            if review_identity is not None and review_identity not in review_references:
                review_references.append(review_identity)

        absent_order_cancellation_count = self._repository.cancel_absent_orders(
            _canonical_absent_orders(absent_orders),
            workbook_key=key,
            source_content_digest=workbook.content_digest,
            actor=actor,
            correlation_id=correlation_id,
        )
        if absent_order_cancellation_count != len(absent_orders):
            raise RuntimeError("historical_order_absence_cancellation_count_mismatch")

        _assert_conservation(len(workbook.rows), outcomes)
        return HistoricalOrderWorkbookReceipt(
            source_content_digest=workbook.content_digest,
            source_row_count=len(workbook.rows),
            adopted_count=outcomes["adopted"],
            unmatched_case_count=outcomes["unmatched_case"],
            review_required_count=review_rows,
            current_conflict_count=outcomes["current_conflict"],
            assignments_created=assignments_created,
            replayed_rows=replayed_rows,
            replayed_workbook=False,
            status_counts=_status_counts(workbook),
            result_counts=_result_counts(tuple(locked_previews)),
            review_references=tuple(review_references),
            absent_order_cancellation_count=absent_order_cancellation_count,
            import_counts=HistoricalOrderWorkbookImportCounts(
                import_counts["imported_count"],
                import_counts["duplicate_skipped_count"],
                import_counts["not_imported_count"],
            ),
            row_issues=tuple(row_issues),
        )

    def _stored_replay(self, key: str, workbook: HistoricalOrderWorkbook) -> HistoricalOrderWorkbookReceipt | None:
        stored = self._repository.load_receipt(key)
        if stored is None:
            return None
        if stored["request_fingerprint"] != workbook.content_digest:
            raise HistoricalOrderWorkbookConflict("historical_order_workbook_idempotency_conflict")
        snapshot = {**json.loads(stored["result_snapshot"]), "replayed_workbook": True}
        snapshot.setdefault("absent_order_cancellation_count", 0)
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
        if "result_counts" not in snapshot:
            snapshot["result_counts"] = _legacy_result_counts(snapshot["status_counts"])
        elif isinstance(snapshot["result_counts"], dict):
            snapshot["result_counts"] = HistoricalOrderResultCounts(
                **snapshot["result_counts"]
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
        if isinstance(snapshot.get("import_counts"), dict):
            snapshot["import_counts"] = HistoricalOrderWorkbookImportCounts(**snapshot["import_counts"])
        if snapshot.get("row_issues") is not None:
            snapshot["row_issues"] = tuple(HistoricalOrderWorkbookRowIssue(**item) for item in snapshot["row_issues"])
        return HistoricalOrderWorkbookReceipt(**snapshot)


def _preview(
    workbook: HistoricalOrderWorkbook,
    row_previews,
    absent_orders=(),
) -> HistoricalOrderWorkbookPreview:
    row_previews = _exclude_source_schedule_conflicts(workbook, row_previews)
    absent_orders = _canonical_absent_orders(absent_orders)
    outcomes = Counter(item.outcome.value for item in row_previews)
    candidates = sum(
        sum(item.resolution.value == "assignment_candidate" for item in preview.pairings)
        for preview in row_previews
    )
    evidence = sum(
        sum(item.resolution.value == "evidence_only" for item in preview.pairings)
        for preview in row_previews
    )
    status_counts = _status_counts(workbook)
    result_counts = _result_counts(row_previews)
    fingerprint = fingerprint_payload({
        "digest": workbook.content_digest,
        "sheet": workbook.sheet_identity,
        "rows": tuple(
            (item.source_identity, item.source_fingerprint, item.fingerprint.value)
            for item in row_previews
        ),
        "status_counts": status_counts.as_dict(),
        "result_counts": result_counts.as_dict(),
        "absent_order_cancellations": _absence_snapshot(absent_orders),
    }).value
    review_rows = outcomes["review_required"]
    row_issues = _historical_row_issues(workbook, row_previews)
    return HistoricalOrderWorkbookPreview(
        source_content_digest=workbook.content_digest,
        sheet_identity=workbook.sheet_identity,
        source_row_count=len(workbook.rows),
        adopted_count=outcomes["adopted"],
        unmatched_case_count=outcomes["unmatched_case"],
        review_required_count=review_rows,
        current_conflict_count=outcomes["current_conflict"],
        assignment_candidate_count=candidates,
        evidence_only_pairing_count=evidence,
        status_counts=status_counts,
        result_counts=result_counts,
        preview_fingerprint=fingerprint,
        absent_order_cancellations=absent_orders,
        row_issues=row_issues,
    )


def _source_schedule_conflict_exclusions(
    workbook: HistoricalOrderWorkbook,
    row_previews,
) -> dict[int, _ConflictExclusion]:
    previews = tuple(row_previews)
    conflicts = project_source_schedule_conflicts(previews, workbook.rows)
    if not conflicts:
        return {}
    indices_by_row_case: dict[tuple[int, str], list[int]] = {}
    for index, (row, preview) in enumerate(zip(workbook.rows, previews, strict=True)):
        case_no = getattr(preview, "case_no", None)
        if isinstance(case_no, str) and case_no:
            indices_by_row_case.setdefault((row.source_row, case_no), []).append(index)

    issue_codes_by_index: dict[int, set[str]] = {}
    fields_by_index: dict[int, set[str]] = {}
    for conflict in conflicts:
        for own, peer in ((conflict.left, conflict.right), (conflict.right, conflict.left)):
            detail_code = (
                f"{conflict.issue_code}_detail:"
                f"row={peer.source_row};"
                f"staff_id={own.staff_id};"
                f"own={_date_value(own.start_date)}~{_date_value(own.end_date)};"
                f"peer={_date_value(peer.start_date)}~{_date_value(peer.end_date)};"
                f"case_no={peer.case_no}"
            )
            if conflict.overlap:
                start, end = conflict.overlap
                detail_code += f";overlap={start.isoformat()}~{end.isoformat()}"
            for row_index in indices_by_row_case.get((own.source_row, own.case_no), ()):
                issue_codes_by_index.setdefault(row_index, set()).update(
                    (conflict.issue_code, detail_code)
                )
                if own.service_time is None and "historical_service_time_unconfirmed" not in workbook.rows[row_index].issue_codes:
                    issue_codes_by_index[row_index].add("historical_service_time_missing")
                fields_by_index.setdefault(row_index, set()).update(
                    ("服務時段", f"第 {own.pairing_ordinal} 位月嫂姓名")
                )

    return {
        row_index: _ConflictExclusion(
            fields=tuple(sorted(fields_by_index[row_index])),
            issue_codes=tuple(sorted(issue_codes_by_index[row_index])),
        )
        for row_index in sorted(issue_codes_by_index)
    }


def _project_excluded_row_preview(
    preview: object,
    exclusion: _ConflictExclusion,
) -> _ConflictExcludedRowPreview:
    merged_issues = tuple(
        sorted(set(getattr(preview, "issue_codes", ())) | set(exclusion.issue_codes))
    )
    excluded_fingerprint = fingerprint_payload(
        {
            "base": preview.fingerprint.value,
            "excluded_conflict": exclusion.issue_codes,
            "excluded_fields": exclusion.fields,
        }
    )
    return _ConflictExcludedRowPreview(
        source_identity=preview.source_identity,
        source_fingerprint=preview.source_fingerprint,
        outcome=HistoricalOrderOutcome.CURRENT_CONFLICT,
        result=HistoricalOrderResult.NOT_ADOPTED,
        case_no=getattr(preview, "case_no", None),
        pairings=(),
        issue_codes=merged_issues,
        conflict_fields=exclusion.fields,
        fingerprint=excluded_fingerprint,
    )


def _exclude_source_schedule_conflicts(
    workbook: HistoricalOrderWorkbook,
    row_previews,
) -> tuple[object, ...]:
    previews = tuple(row_previews)
    exclusions = _source_schedule_conflict_exclusions(workbook, previews)
    if not exclusions:
        return previews
    return tuple(
        _project_excluded_row_preview(preview, exclusions[index])
        if index in exclusions
        else preview
        for index, preview in enumerate(previews)
    )


def _historical_row_issues(
    workbook: HistoricalOrderWorkbook,
    row_previews: tuple[object, ...],
) -> tuple[HistoricalOrderWorkbookRowIssue, ...]:
    results: list[HistoricalOrderWorkbookRowIssue] = []
    for row, preview in zip(workbook.rows, row_previews, strict=True):
        issues = set(row.issue_codes) | set(getattr(preview, "issue_codes", ()))
        fields = {
            field
            for issue in issues
            for field in _historical_issue_fields(issue)
        } | set(getattr(preview, "conflict_fields", ()))
        for pairing in getattr(preview, "pairings", ()):
            if getattr(pairing, "issue_codes", ()):
                fields.add(f"第 {pairing.ordinal} 位月嫂姓名")
        if issues:
            results.append(
                HistoricalOrderWorkbookRowIssue(
                    row.source_row,
                    row.case_no,
                    tuple(sorted(fields)) or ("來源資料",),
                    tuple(sorted(issues)),
                )
            )
    return tuple(results)


def _historical_issue_fields(issue_code: str) -> tuple[str, ...]:
    if issue_code == "historical_case_no_missing":
        return ("案件編號",)
    if issue_code == "historical_client_name_missing":
        return ("客戶姓名",)
    if issue_code == "historical_status_invalid":
        return ("訂單狀態",)
    if issue_code.startswith("historical_order_source_schedule_") or issue_code == "historical_service_time_unconfirmed":
        return ("服務時段",)
    if "staff" in issue_code:
        return ("月嫂姓名",)
    if issue_code.endswith("_start_date_invalid"):
        return ("開始日期",)
    if issue_code.endswith("_end_date_invalid"):
        return ("結束日期",)
    if issue_code.endswith("_date_range_invalid"):
        return ("開始日期", "結束日期")
    return ()


def _source_case_nos(workbook: HistoricalOrderWorkbook) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                row.case_no
                for row in workbook.rows
                if isinstance(row.case_no, str) and row.case_no
            }
        )
    )


def _canonical_absent_orders(values) -> tuple[HistoricalOrderAbsenceCancellation, ...]:
    result = tuple(values)
    if any(not isinstance(item, HistoricalOrderAbsenceCancellation) for item in result):
        raise TypeError("historical_order_absence_candidate_invalid")
    ordered = tuple(
        sorted(
            result,
            key=lambda item: (
                item.case_no,
                item.before_status.value,
                item.expected_version,
            ),
        )
    )
    if len({item.case_no for item in ordered}) != len(ordered):
        raise ValueError("historical_order_absence_case_no_duplicated")
    return ordered


def _absence_snapshot(values) -> tuple[tuple[str, str, int], ...]:
    return tuple(
        (item.case_no, item.before_status.value, item.expected_version)
        for item in _canonical_absent_orders(values)
    )


def _result_counts(row_previews) -> HistoricalOrderResultCounts:
    counts = Counter(_preview_result(item) for item in row_previews)
    result = HistoricalOrderResultCounts(
        not_adopted=counts[HistoricalOrderResult.NOT_ADOPTED],
        matching_pending_deposit=counts[HistoricalOrderResult.MATCHING_PENDING_DEPOSIT],
        historical_unserved=counts[HistoricalOrderResult.HISTORICAL_UNSERVED],
        historical_in_service=counts[HistoricalOrderResult.HISTORICAL_IN_SERVICE],
        historical_service_completed=counts[HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED],
    )
    if result.total != len(row_previews):
        raise RuntimeError("historical_order_result_counts_not_conserved")
    return result


def _preview_result(item: object) -> HistoricalOrderResult:
    """Read the new workflow result with a bounded compatibility fallback.

    The fallback only serves in-process legacy workflow doubles which predate
    the result field.  Production previews always carry the explicit result.
    """

    result = getattr(item, "result", None)
    if isinstance(result, HistoricalOrderResult):
        return result
    if getattr(getattr(item, "outcome", None), "value", None) == "unmatched_case":
        return HistoricalOrderResult.NOT_ADOPTED
    return HistoricalOrderResult.HISTORICAL_UNSERVED


def _legacy_result_counts(
    status_counts: HistoricalOrderStatusCounts,
) -> HistoricalOrderResultCounts:
    """Conserve old immutable receipts without rereading mutable Order facts."""

    return HistoricalOrderResultCounts(
        not_adopted=status_counts.cancelled_0 + status_counts.invalid_or_blank,
        matching_pending_deposit=status_counts.discussion_2,
        historical_unserved=status_counts.deposit_paid_1,
        historical_in_service=0,
        historical_service_completed=0,
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
    """Distinguish proven collisions from source intervals requiring evidence."""
    rows = source_rows or ()
    intervals_by_staff: dict[int, list[HistoricalOrderSourceScheduleInterval]] = {}
    for index, preview in enumerate(row_previews):
        row = rows[index] if index < len(rows) else None
        source_row = getattr(row, "source_row", index)
        case_no = getattr(preview, "case_no", None)
        if case_no is None:
            continue
        service_time = getattr(row, "service_time", None)
        confirmed_dates = frozenset(getattr(preview, "canonical_service_dates", ()) or ())
        for pairing_index, pairing in enumerate(preview.pairings, start=1):
            resolution = getattr(pairing.resolution, "value", pairing.resolution)
            result = getattr(preview, "result", None)
            eligible = (
                resolution == "assignment_candidate" and result is None
            ) or (
                resolution in {"assignment_candidate", "assignment_reused", "evidence_only"}
                and result in {
                    HistoricalOrderResult.HISTORICAL_IN_SERVICE,
                    HistoricalOrderResult.HISTORICAL_SERVICE_COMPLETED,
                }
            )
            if not eligible or pairing.staff_id is None:
                continue
            start = min(confirmed_dates) if confirmed_dates else pairing.start_date
            end = max(confirmed_dates) if confirmed_dates else pairing.end_date
            if not isinstance(start, date) or not isinstance(end, date) or start > end:
                continue
            interval = HistoricalOrderSourceScheduleInterval(
                source_row, getattr(pairing, "ordinal", pairing_index),
                case_no, pairing.staff_id, start, end, service_time, confirmed_dates,
            )
            intervals_by_staff.setdefault(pairing.staff_id, []).append(interval)

    conflicts: list[HistoricalOrderSourceScheduleConflict] = []
    for staff_id in sorted(intervals_by_staff):
        ordered = sorted(intervals_by_staff[staff_id], key=lambda item: (
            item.start_date, item.end_date, item.case_no, item.source_row, item.pairing_ordinal,
        ))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                if (right.start_date - left.end_date).days > 1:
                    break
                if left.case_no != right.case_no:
                    conflict = _compare_source_intervals(left, right)
                    if conflict is not None:
                        conflicts.append(conflict)
    return tuple(conflicts)


def _compare_source_intervals(left, right):
    if left.service_time is None or right.service_time is None:
        left_end = left.end_date + timedelta(days=left.service_time.end_day_offset if left.service_time else 0)
        right_end = right.end_date + timedelta(days=right.service_time.end_day_offset if right.service_time else 0)
        if max(left.start_date, right.start_date) <= min(left_end, right_end):
            return HistoricalOrderSourceScheduleConflict(left, right)
        return None

    pending = False
    # A service anchored on one date can only touch that date and its successor.
    for delta in (0, 1, -1):
        shift = timedelta(days=delta)
        start = max(left.start_date, right.start_date - shift)
        end = min(left.end_date, right.end_date - shift)
        if start > end:
            continue
        if left.confirmed_dates:
            candidates = sorted(left.confirmed_dates)
        elif right.confirmed_dates:
            candidates = sorted(day - shift for day in right.confirmed_dates)
        else:
            candidates = sorted({start, end, left.start_date, left.end_date,
                                 right.start_date - shift, right.end_date - shift})
        for anchor in candidates:
            other = anchor + shift
            if not start <= anchor <= end or (
                right.confirmed_dates and other not in right.confirmed_dates
            ):
                continue
            left_interval = left.service_time.service_interval(anchor)
            right_interval = right.service_time.service_interval(other)
            if left_interval is None or right_interval is None:
                pending = True
                continue
            overlap = max(left_interval[0], right_interval[0]), min(left_interval[1], right_interval[1])
            if overlap[0] >= overlap[1]:
                continue
            proven_left = left.confirmed_dates or {left.start_date, left.end_date}
            proven_right = right.confirmed_dates or {right.start_date, right.end_date}
            if anchor in proven_left and other in proven_right:
                return HistoricalOrderSourceScheduleConflict(left, right, overlap)
            pending = True
    return HistoricalOrderSourceScheduleConflict(left, right) if pending else None


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
    "HistoricalOrderAbsenceCancellation", "HistoricalOrderStatusCounts",
    "HistoricalOrderSourceScheduleConflict",
    "HistoricalOrderSourceScheduleConflictError", "HistoricalOrderSourceScheduleInterval",
    "project_source_schedule_conflicts",
]

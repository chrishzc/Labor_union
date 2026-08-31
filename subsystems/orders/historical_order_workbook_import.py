"""
File: historical_order_workbook_import.py
Description: 協調訂單歷史 workbook Preview、Apply、replay 與逐列 Orders 採納。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Protocol

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.orders.historical_adoption_workflow import HistoricalOrderAdoptionRequest, HistoricalOrderAdoptionWorkflow
from subsystems.orders.historical_order_workbook import HistoricalOrderWorkbook, load_historical_order_workbook


class HistoricalOrderWorkbookRepository(Protocol):
    def find_workbook_receipt(self, key: str): ...

    def save_workbook_receipt(self, key: str, receipt) -> None: ...


@dataclass(frozen=True, slots=True)
class HistoricalOrderStatusCounts:
    cancelled_0: int
    completed_1: int
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
            "completed_1": self.completed_1,
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
        }


class HistoricalOrderWorkbookConflict(RuntimeError):
    pass


class HistoricalOrderWorkbookUnavailable(RuntimeError):
    pass


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
            row_previews = tuple(self._workflow.preview(row) for row in workbook.rows)
            replay = self._stored_replay(key, workbook)
            if replay is not None and not _requires_replay_refresh(row_previews):
                return replay
            preview = self._require_preview(
                workbook, row_previews, supplied_preview_fingerprint
            )
            if replay is not None:
                return self._apply_rows(
                    workbook, key, actor, correlation_id, row_previews
                )
            with self._unit_of_work_factory() as unit_of_work:
                if self._repository.claim(key, workbook.content_digest, correlation_id) == "conflict":
                    raise HistoricalOrderWorkbookConflict("historical_order_workbook_idempotency_conflict")
                unit_of_work.commit()
            receipt = self._apply_rows(
                workbook, key, actor, correlation_id, row_previews
            )
            with self._unit_of_work_factory() as unit_of_work:
                self._repository.save_receipt(key, workbook.content_digest, preview.preview_fingerprint, actor, receipt.as_dict())
                unit_of_work.commit()
            return receipt
        finally:
            self._repository.release_lock(key)

    def _require_preview(self, workbook, row_previews, supplied):
        preview = _preview(workbook, row_previews)
        if preview.preview_fingerprint != supplied:
            raise ValueError("historical_order_preview_stale")
        return preview

    def _apply_rows(
        self, workbook, key, actor, correlation_id, row_previews
    ) -> HistoricalOrderWorkbookReceipt:
        outcomes: Counter[str] = Counter()
        assignments_created = 0
        replayed_rows = 0
        review_rows = 0
        for row, row_preview in zip(workbook.rows, row_previews, strict=True):
            receipt = self._workflow.apply(_row_request(row, row_preview.fingerprint, key, actor, correlation_id))
            if receipt.replayed and _requires_replay_refresh((row_preview,)):
                refresh_row = replace(
                    row,
                    source_identity=(
                        f"{row.source_identity}:refresh:{row_preview.fingerprint.value}"
                    ),
                )
                refresh_preview = self._workflow.preview(refresh_row)
                if _requires_replay_refresh((refresh_preview,)):
                    receipt = self._workflow.apply(
                        _row_request(
                            refresh_row,
                            refresh_preview.fingerprint,
                            key,
                            actor,
                            correlation_id,
                        )
                    )
            outcomes[receipt.outcome.value] += 1
            assignments_created += 0 if receipt.replayed else receipt.assignment_count
            replayed_rows += int(receipt.replayed)
            review_rows += int(getattr(receipt, "review_identity", None) is not None)
        _assert_conservation(len(workbook.rows), outcomes)
        return HistoricalOrderWorkbookReceipt(
            workbook.content_digest, len(workbook.rows), outcomes["adopted"], outcomes["unmatched_case"],
            review_rows, outcomes["current_conflict"], assignments_created, replayed_rows, False,
            _status_counts(workbook),
        )

    def _stored_replay(self, key: str, workbook: HistoricalOrderWorkbook) -> HistoricalOrderWorkbookReceipt | None:
        stored = self._repository.load_receipt(key)
        if stored is None:
            return None
        if stored["request_fingerprint"] != workbook.content_digest:
            raise HistoricalOrderWorkbookConflict("historical_order_workbook_idempotency_conflict")
        snapshot = {**json.loads(stored["result_snapshot"]), "replayed_workbook": True}
        stored_counts = snapshot.get("status_counts")
        snapshot["status_counts"] = (
            HistoricalOrderStatusCounts(**stored_counts)
            if stored_counts is not None
            else _status_counts(workbook)
        )
        return HistoricalOrderWorkbookReceipt(**snapshot)


def _preview(workbook: HistoricalOrderWorkbook, row_previews) -> HistoricalOrderWorkbookPreview:
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
        cancelled_0=counts[OrderLifecycleStatus.CANCELLED],
        completed_1=counts[OrderLifecycleStatus.COMPLETED],
        discussion_2=counts[OrderLifecycleStatus.DISCUSSION],
        invalid_or_blank=counts[None],
    )
    if result.total != len(workbook.rows):
        raise RuntimeError("historical_order_status_counts_not_conserved")
    return result


def _requires_replay_refresh(row_previews) -> bool:
    return any(
        (
            getattr(preview, "expected_version", None) is not None
            and getattr(preview, "resulting_version", None)
            != getattr(preview, "expected_version", None)
        )
        or bool(getattr(preview, "date_patch", ()))
        or any(
            pairing.resolution.value == "assignment_candidate"
            for pairing in preview.pairings
        )
        for preview in row_previews
    )


def _row_request(row, fingerprint: PreviewFingerprint, workbook_key: str, actor: str, correlation_id: str) -> HistoricalOrderAdoptionRequest:
    row_hash = sha256(f"{workbook_key}:{row.source_identity}".encode("utf-8")).hexdigest()
    return HistoricalOrderAdoptionRequest(
        row, fingerprint, f"historical-order-row:{row_hash}", actor, "資料匯入中心訂單歷史採納",
        f"{correlation_id}:row:{row.source_row}",
    )


def _assert_conservation(source_rows: int, outcomes: Counter[str]) -> None:
    if sum(outcomes.values()) != source_rows:
        raise RuntimeError("historical_order_workbook_outcomes_not_conserved")


__all__ = [
    "HistoricalOrderWorkbookConflict", "HistoricalOrderWorkbookImportService", "HistoricalOrderWorkbookPreview",
    "HistoricalOrderWorkbookReceipt", "HistoricalOrderWorkbookUnavailable",
    "HistoricalOrderStatusCounts",
]

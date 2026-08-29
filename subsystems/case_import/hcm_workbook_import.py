"""
File: hcm_workbook_import.py
Description: 協調HCM workbook Preview、Apply、跨identity摘要replay與結果查詢。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd

from infrastructure.mysql.hcm_workbook_import_repository import HcmWorkbookImportRepository
from shared_kernel.clock import TAIPEI_TIME_ZONE


class HcmRowIntake(Protocol):
    def load_frame(self, source_path: str) -> pd.DataFrame | None: ...

    def import_rows(self, frame: pd.DataFrame, source_path: str) -> dict[str, object]: ...

    def preview_rows(self, frame: pd.DataFrame, source_path: str) -> dict[str, int]: ...


@dataclass(frozen=True)
class HcmWorkbookPreview:
    source_content_digest: str
    source_row_count: int
    ready_count: int
    ready_with_warning_count: int
    review_required_count: int
    preview_fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "source_row_count": self.source_row_count,
            "ready_count": self.ready_count,
            "ready_with_warning_count": self.ready_with_warning_count,
            "review_required_count": self.review_required_count,
            "preview_fingerprint": self.preview_fingerprint,
        }


@dataclass(frozen=True)
class HcmWorkbookRowOutcome:
    source_row: int
    case_no: str | None
    outcome: str
    problem_identity: str | None
    problem_fields: tuple[str, ...]
    issue_codes: tuple[str, ...]
    referral_occurrence_identities: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "source_row": self.source_row,
            "case_no": self.case_no,
            "outcome": self.outcome,
            "problem_identity": self.problem_identity,
            "problem_fields": list(self.problem_fields),
            "issue_codes": list(self.issue_codes),
            "referral_occurrence_identities": list(self.referral_occurrence_identities),
        }


@dataclass(frozen=True)
class HcmWorkbookReceipt:
    source_content_digest: str
    source_row_count: int
    inserted_count: int
    inserted_with_warning_count: int
    exact_replay_count: int
    review_required_count: int
    failed_count: int
    replayed_workbook: bool
    row_outcomes_available: bool = False
    legacy_summary_only: bool = True
    row_outcomes: tuple[HcmWorkbookRowOutcome, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "source_row_count": self.source_row_count,
            "inserted_count": self.inserted_count,
            "inserted_with_warning_count": self.inserted_with_warning_count,
            "exact_replay_count": self.exact_replay_count,
            "review_required_count": self.review_required_count,
            "failed_count": self.failed_count,
            "replayed_workbook": self.replayed_workbook,
            "row_outcomes_available": self.row_outcomes_available,
            "legacy_summary_only": self.legacy_summary_only,
            "row_outcomes": [item.as_dict() for item in self.row_outcomes],
        }


@dataclass(frozen=True)
class HcmWorkbookResultRecord:
    receipt_id: int
    completed_at: datetime
    receipt: HcmWorkbookReceipt

    def __post_init__(self) -> None:
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("hcm_workbook_result_completed_at_timezone_required")

    def as_dict(self) -> dict[str, object]:
        return {
            "receipt_id": self.receipt_id,
            "completed_at": self.completed_at,
            **self.receipt.as_dict(),
        }


@dataclass(frozen=True)
class HcmWorkbookResultPage:
    items: tuple[HcmWorkbookResultRecord, ...]
    next_cursor: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "items": [item.as_dict() for item in self.items],
            "next_cursor": self.next_cursor,
        }


class HcmWorkbookConflict(RuntimeError):
    pass


class HcmWorkbookUnavailable(RuntimeError):
    pass


class HcmWorkbookImportService:
    def __init__(self, repository: HcmWorkbookImportRepository, intake: HcmRowIntake, unit_of_work_factory: Callable[[], object]) -> None:
        self._repository = repository
        self._intake = intake
        self._unit_of_work_factory = unit_of_work_factory

    def ingest(self, frame: pd.DataFrame, source_path: str, key: str, actor: str, correlation_id: str) -> HcmWorkbookReceipt:
        digest = _workbook_digest(source_path)
        if not self._repository.acquire_lock(key):
            raise HcmWorkbookUnavailable("hcm_workbook_coordinator_lock_timeout")
        try:
            replay = self._stored_replay(key, digest)
            if replay is not None:
                return replay
            digest_replay = self._stored_digest_replay(digest)
            if digest_replay is not None:
                return digest_replay
            with self._unit_of_work_factory() as unit_of_work:
                claim = self._repository.claim(key, digest, correlation_id)
                if claim == "conflict":
                    raise HcmWorkbookConflict("hcm_workbook_idempotency_conflict")
                unit_of_work.commit()
            outcomes = self._intake.import_rows(frame, source_path)
            _assert_terminal_row_outcomes(len(frame), outcomes)
            receipt = _receipt(digest, len(frame), outcomes, False)
            with self._unit_of_work_factory() as unit_of_work:
                self._repository.save_receipt(key, digest, actor, receipt.as_dict())
                unit_of_work.commit()
            return receipt
        finally:
            self._repository.release_lock(key)

    def preview(self, frame: pd.DataFrame, source_path: str) -> HcmWorkbookPreview:
        digest = _workbook_digest(source_path)
        outcomes = self._intake.preview_rows(frame, source_path)
        ready_count = int(outcomes.get("ready", 0))
        ready_with_warning_count = int(outcomes.get("ready_with_warning", 0))
        review_count = int(outcomes.get("review_required", 0))
        if ready_count + ready_with_warning_count + review_count != len(frame):
            raise ValueError("hcm_preview_row_outcomes_not_conserved")
        fingerprint = _preview_fingerprint(
            digest, len(frame), ready_count, ready_with_warning_count, review_count,
        )
        return HcmWorkbookPreview(
            digest, len(frame), ready_count, ready_with_warning_count, review_count, fingerprint,
        )

    def apply(
        self,
        frame: pd.DataFrame,
        source_path: str,
        preview_fingerprint: str,
        key: str,
        actor: str,
        correlation_id: str,
    ) -> HcmWorkbookReceipt:
        preview = self.preview(frame, source_path)
        if preview.preview_fingerprint != preview_fingerprint:
            raise HcmWorkbookConflict("hcm_workbook_preview_stale")
        return self.ingest(frame, source_path, key, actor, correlation_id)

    def load_frame(self, source_path: str) -> pd.DataFrame | None:
        return self._intake.load_frame(source_path)

    def query_recent_results(
        self,
        *,
        limit: int,
        before_receipt_id: int | None,
    ) -> HcmWorkbookResultPage:
        rows = self._repository.query_recent_receipts(
            limit=limit,
            before_receipt_id=before_receipt_id,
        )
        items = tuple(
            HcmWorkbookResultRecord(
                receipt_id=int(row["id"]),
                completed_at=_as_business_datetime(row["created_at"]),
                receipt=_receipt_from_payload(
                    json.loads(row["result_snapshot"]),
                    source_digest=str(row["request_fingerprint"]),
                    replayed=False,
                ),
            )
            for row in rows
        )
        return HcmWorkbookResultPage(
            items,
            items[-1].receipt_id if len(items) == limit else None,
        )

    def _stored_replay(self, key: str, digest: str) -> HcmWorkbookReceipt | None:
        stored = self._repository.load_receipt(key)
        if stored is None:
            return None
        if stored["request_fingerprint"] != digest:
            raise HcmWorkbookConflict("hcm_workbook_idempotency_conflict")
        return _receipt_from_payload(
            json.loads(stored["result_snapshot"]),
            source_digest=digest,
            replayed=True,
        )

    def _stored_digest_replay(self, digest: str) -> HcmWorkbookReceipt | None:
        stored = self._repository.load_receipt_by_digest(digest)
        if stored is None:
            return None
        return _receipt_from_payload(
            json.loads(stored["result_snapshot"]),
            source_digest=digest,
            replayed=True,
        )


def _as_business_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("hcm_workbook_result_completed_at_invalid")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=TAIPEI_TIME_ZONE)
    return value.astimezone(TAIPEI_TIME_ZONE)


def _workbook_digest(source_path: str) -> str:
    return sha256(Path(source_path).read_bytes()).hexdigest()


def _preview_fingerprint(
    digest: str, source_rows: int, ready: int, ready_with_warning: int, review: int,
) -> str:
    payload = {
        "ready_count": ready,
        "ready_with_warning_count": ready_with_warning,
        "review_required_count": review,
        "source_content_digest": digest,
        "source_row_count": source_rows,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _receipt(digest: str, source_rows: int, outcomes: dict[str, object], replayed: bool) -> HcmWorkbookReceipt:
    row_outcomes = tuple(_row_outcome(item) for item in outcomes.get("row_outcomes", ()))
    row_outcomes_available = len(row_outcomes) == source_rows
    return HcmWorkbookReceipt(
        digest, source_rows, int(outcomes.get("inserted", 0)),
        int(outcomes.get("inserted_with_warning", 0)), int(outcomes.get("exact_replay", 0)),
        int(outcomes.get("review_required", 0)), int(outcomes.get("failed", 0)), replayed,
        row_outcomes_available, not row_outcomes_available, row_outcomes if row_outcomes_available else (),
    )


def _assert_terminal_row_outcomes(source_rows: int, outcomes: dict[str, object]) -> None:
    """A terminal workbook receipt is valid only when every source row has one outcome."""
    terminal_rows = sum(
        int(outcomes.get(name, 0))
        for name in ("inserted", "inserted_with_warning", "exact_replay", "review_required", "failed")
    )
    if terminal_rows != source_rows:
        raise ValueError("hcm_import_row_outcomes_not_conserved")
    rows = outcomes.get("row_outcomes")
    if rows is not None:
        parsed = tuple(_row_outcome(item) for item in rows)
        if len(parsed) != source_rows:
            raise ValueError("hcm_import_row_outcomes_not_conserved")
        expected = {
            name: int(outcomes.get(name, 0))
            for name in ("inserted", "inserted_with_warning", "exact_replay", "review_required", "failed")
        }
        actual = {name: 0 for name in expected}
        for item in parsed:
            if item.outcome not in actual:
                raise ValueError("hcm_import_row_outcome_invalid")
            actual[item.outcome] += 1
        if actual != expected:
            raise ValueError("hcm_import_row_outcomes_not_conserved")


def _row_outcome(value) -> HcmWorkbookRowOutcome:
    if not isinstance(value, dict):
        raise ValueError("hcm_import_row_outcome_invalid")
    outcome = str(value.get("outcome") or "")
    if outcome not in {"inserted", "inserted_with_warning", "exact_replay", "review_required", "failed"}:
        raise ValueError("hcm_import_row_outcome_invalid")
    source_row = value.get("source_row")
    if not isinstance(source_row, int) or isinstance(source_row, bool) or source_row < 1:
        raise ValueError("hcm_import_row_outcome_invalid")
    return HcmWorkbookRowOutcome(
        source_row,
        None if value.get("case_no") is None else str(value["case_no"]),
        outcome,
        None if value.get("problem_identity") is None else str(value["problem_identity"]),
        tuple(str(item) for item in value.get("problem_fields", ())),
        tuple(str(item) for item in value.get("issue_codes", ())),
        tuple(str(item) for item in value.get("referral_occurrence_identities", ())),
    )


def _receipt_from_payload(payload, *, source_digest: str, replayed: bool) -> HcmWorkbookReceipt:
    if not isinstance(payload, dict):
        raise ValueError("hcm_workbook_receipt_corrupt")
    stored_digest = payload.get("source_content_digest")
    if stored_digest is not None and str(stored_digest) != source_digest:
        raise ValueError("hcm_workbook_receipt_corrupt")
    rows_value = payload.get("row_outcomes")
    rows = tuple(_row_outcome(item) for item in rows_value) if isinstance(rows_value, list) else ()
    available = bool(payload.get("row_outcomes_available")) and len(rows) == int(payload.get("source_row_count", 0))
    receipt = HcmWorkbookReceipt(
        source_digest,
        int(payload.get("source_row_count", 0)),
        int(payload.get("inserted_count", 0)),
        int(payload.get("inserted_with_warning_count", 0)),
        int(payload.get("exact_replay_count", 0)),
        int(payload.get("review_required_count", 0)),
        int(payload.get("failed_count", 0)),
        replayed,
        available,
        not available,
        rows if available else (),
    )
    _assert_terminal_row_outcomes(receipt.source_row_count, {
        "inserted": receipt.inserted_count,
        "inserted_with_warning": receipt.inserted_with_warning_count,
        "exact_replay": receipt.exact_replay_count,
        "review_required": receipt.review_required_count,
        "failed": receipt.failed_count,
        **({"row_outcomes": [item.as_dict() for item in receipt.row_outcomes]} if available else {}),
    })
    return receipt

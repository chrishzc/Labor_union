"""
File: hcm_workbook_import.py
Description: 協調 HCM workbook replay、conflict 與逐列 typed intake。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from infrastructure.mysql.hcm_workbook_import_repository import HcmWorkbookImportRepository


class HcmRowIntake(Protocol):
    def load_frame(self, source_path: str) -> pd.DataFrame | None: ...

    def import_rows(self, frame: pd.DataFrame, source_path: str) -> dict[str, int]: ...

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
class HcmWorkbookReceipt:
    source_content_digest: str
    source_row_count: int
    inserted_count: int
    inserted_with_warning_count: int
    exact_replay_count: int
    review_required_count: int
    failed_count: int
    replayed_workbook: bool

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
        }


class HcmWorkbookConflict(RuntimeError):
    pass


class HcmWorkbookUnavailable(RuntimeError):
    pass


class HcmWorkbookImportService:
    def __init__(self, repository: HcmWorkbookImportRepository, intake: HcmRowIntake) -> None:
        self._repository = repository
        self._intake = intake

    def ingest(self, frame: pd.DataFrame, source_path: str, key: str, actor: str, correlation_id: str) -> HcmWorkbookReceipt:
        digest = _workbook_digest(source_path)
        if not self._repository.acquire_lock(key):
            raise HcmWorkbookUnavailable("hcm_workbook_coordinator_lock_timeout")
        try:
            replay = self._stored_replay(key, digest)
            if replay is not None:
                return replay
            claim = self._repository.claim(key, digest, correlation_id)
            if claim == "conflict":
                raise HcmWorkbookConflict("hcm_workbook_idempotency_conflict")
            outcomes = self._intake.import_rows(frame, source_path)
            _assert_terminal_row_outcomes(len(frame), outcomes)
            receipt = _receipt(digest, len(frame), outcomes, False)
            self._repository.save_receipt(key, digest, actor, receipt.as_dict())
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

    def _stored_replay(self, key: str, digest: str) -> HcmWorkbookReceipt | None:
        stored = self._repository.load_receipt(key)
        if stored is None:
            return None
        if stored["request_fingerprint"] != digest:
            raise HcmWorkbookConflict("hcm_workbook_idempotency_conflict")
        payload = {**json.loads(stored["result_snapshot"]), "replayed_workbook": True}
        return HcmWorkbookReceipt(**payload)


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


def _receipt(digest: str, source_rows: int, outcomes: dict[str, int], replayed: bool) -> HcmWorkbookReceipt:
    return HcmWorkbookReceipt(
        digest, source_rows, int(outcomes.get("inserted", 0)),
        int(outcomes.get("inserted_with_warning", 0)), int(outcomes.get("exact_replay", 0)),
        int(outcomes.get("review_required", 0)), int(outcomes.get("failed", 0)), replayed,
    )


def _assert_terminal_row_outcomes(source_rows: int, outcomes: dict[str, int]) -> None:
    """A terminal workbook receipt is valid only when every source row has one outcome."""
    terminal_rows = sum(
        int(outcomes.get(name, 0))
        for name in ("inserted", "inserted_with_warning", "exact_replay", "review_required", "failed")
    )
    if terminal_rows != source_rows:
        raise ValueError("hcm_import_row_outcomes_not_conserved")

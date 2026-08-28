"""
File: test_historical_order_workbook_import.py
Description: 驗證訂單歷史 workbook claim、terminal replay、conflict 與逐列結果守恆。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from domains.orders.historical_adoption import HistoricalOrderOutcome
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders import historical_order_workbook_import as module
from subsystems.orders.historical_order_workbook import HistoricalOrderWorkbook, HistoricalOrderWorkbookRow


class _Repository:
    def __init__(self) -> None:
        self.claims: dict[str, str] = {}
        self.receipts: dict[str, dict] = {}
        self.locked: list[str] = []

    def acquire_lock(self, key):
        self.locked.append(key)
        return True

    def release_lock(self, key):
        self.locked.remove(key)

    def load_receipt(self, key):
        return self.receipts.get(key)

    def claim(self, key, digest, correlation_id):
        prior = self.claims.get(key)
        if prior and prior != digest:
            return "conflict"
        self.claims[key] = digest
        return "created"

    def save_receipt(self, key, digest, preview_fingerprint, actor, result):
        self.receipts[key] = {"request_fingerprint": digest, "result_snapshot": json.dumps(result)}


class _Workflow:
    def __init__(self) -> None:
        self.apply_calls = 0

    def preview(self, row):
        return SimpleNamespace(
            source_identity=row.source_identity,
            source_fingerprint=row.source_fingerprint,
            outcome=HistoricalOrderOutcome.ADOPTED,
            pairings=(),
            fingerprint=PreviewFingerprint("1" * 64),
        )

    def apply(self, request):
        self.apply_calls += 1
        return SimpleNamespace(outcome=HistoricalOrderOutcome.ADOPTED, replayed=False, assignment_count=0)


def test_workbook_apply_replays_terminal_receipt_and_conflicts_before_row_apply(monkeypatch):
    original = _workbook("a" * 64)
    different = _workbook("b" * 64)
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: original if path == "first.xlsx" else different)
    repository = _Repository()
    workflow = _Workflow()
    service = module.HistoricalOrderWorkbookImportService(repository, workflow)
    preview = service.preview("first.xlsx")

    first = service.apply("first.xlsx", "workbook-key", preview.preview_fingerprint, "operator", "correlation")
    replay = service.apply("first.xlsx", "workbook-key", preview.preview_fingerprint, "operator", "correlation")

    assert first.replayed_workbook is False
    assert replay.replayed_workbook is True
    assert workflow.apply_calls == 1
    with pytest.raises(module.HistoricalOrderWorkbookConflict):
        service.apply("different.xlsx", "workbook-key", preview.preview_fingerprint, "operator", "correlation")
    assert workflow.apply_calls == 1


def test_apply_rejects_a_stale_preview_before_row_apply(monkeypatch):
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: _workbook("c" * 64))
    workflow = _Workflow()
    service = module.HistoricalOrderWorkbookImportService(_Repository(), workflow)

    with pytest.raises(ValueError, match="historical_order_preview_stale"):
        service.apply("first.xlsx", "workbook-key", "0" * 64, "operator", "correlation")

    assert workflow.apply_calls == 0


def test_preview_and_receipt_expose_conserved_zero_one_two_status_counts(monkeypatch):
    workbook = _workbook_with_statuses()
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: workbook)
    service = module.HistoricalOrderWorkbookImportService(_Repository(), _Workflow())

    preview = service.preview("statuses.xlsx")
    receipt = service.apply(
        "statuses.xlsx", "status-counts-key", preview.preview_fingerprint, "operator", "correlation",
    )

    assert preview.status_counts.as_dict() == {
        "cancelled_0": 1,
        "completed_1": 1,
        "discussion_2": 1,
        "invalid_or_blank": 1,
    }
    assert receipt.status_counts == preview.status_counts


def test_legacy_stored_receipt_replay_derives_status_counts_from_same_workbook(monkeypatch):
    workbook = _workbook_with_statuses()
    repository = _Repository()
    repository.receipts["legacy-key"] = {
        "request_fingerprint": workbook.content_digest,
        "result_snapshot": json.dumps({
            "source_content_digest": workbook.content_digest,
            "source_row_count": 4,
            "adopted_count": 4,
            "unmatched_case_count": 0,
            "review_required_count": 0,
            "current_conflict_count": 0,
            "assignments_created": 0,
            "replayed_rows": 0,
            "replayed_workbook": False,
        }),
    }
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: workbook)

    replay = module.HistoricalOrderWorkbookImportService(repository, _Workflow()).apply(
        "statuses.xlsx", "legacy-key", "0" * 64, "operator", "correlation",
    )

    assert replay.replayed_workbook is True
    assert replay.status_counts.total == 4


def _workbook(digest: str) -> HistoricalOrderWorkbook:
    row = HistoricalOrderWorkbookRow(2, f"historical-orders:{digest}:row:2", "d" * 64, "CASE-1", "客戶甲", None, None, None, (), ())
    return HistoricalOrderWorkbook(digest, "e" * 64, "任意名稱", (row,))


def _workbook_with_statuses() -> HistoricalOrderWorkbook:
    statuses = (
        module.OrderLifecycleStatus.CANCELLED,
        module.OrderLifecycleStatus.COMPLETED,
        module.OrderLifecycleStatus.DISCUSSION,
        None,
    )
    rows = tuple(
        HistoricalOrderWorkbookRow(
            index + 2,
            f"historical-orders:{'f' * 64}:row:{index + 2}",
            str(index) * 64,
            f"CASE-{index}",
            f"客戶{index}",
            status,
            None,
            None,
            (),
            (),
        )
        for index, status in enumerate(statuses)
    )
    return HistoricalOrderWorkbook("f" * 64, "e" * 64, "任意名稱", rows)

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


def _workbook(digest: str) -> HistoricalOrderWorkbook:
    row = HistoricalOrderWorkbookRow(2, f"historical-orders:{digest}:row:2", "d" * 64, "CASE-1", "客戶甲", None, None, None, (), ())
    return HistoricalOrderWorkbook(digest, "e" * 64, "任意名稱", (row,))

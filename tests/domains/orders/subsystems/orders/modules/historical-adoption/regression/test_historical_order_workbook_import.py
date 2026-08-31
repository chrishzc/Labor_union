"""
File: test_historical_order_workbook_import.py
Description: 驗證訂單歷史 workbook claim、terminal replay、conflict 與逐列結果守恆。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from domains.orders.historical_adoption import HistoricalOrderOutcome, HistoricalOrderSourceStatus
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


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


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


class _StatefulWorkflow(_Workflow):
    def __init__(self) -> None:
        super().__init__()
        self.versions: dict[str, int] = {}

    def preview(self, row):
        version = self.versions.get(row.case_no, 0)
        return SimpleNamespace(
            source_identity=row.source_identity,
            source_fingerprint=row.source_fingerprint,
            outcome=HistoricalOrderOutcome.ADOPTED,
            pairings=(),
            fingerprint=PreviewFingerprint(f"{version:064x}"),
        )

    def apply(self, request):
        return self.apply_in_current_unit_of_work(request)

    def preview_in_current_unit_of_work(self, row, *, for_update):
        assert for_update is True
        return self.preview(row)

    def apply_in_current_unit_of_work(self, request):
        current = self.preview(request.row)
        if current.fingerprint != request.preview_fingerprint:
            raise RuntimeError("historical_order_candidate_stale")
        self.apply_calls += 1
        self.versions[request.row.case_no] = self.versions.get(request.row.case_no, 0) + 1
        return SimpleNamespace(
            outcome=HistoricalOrderOutcome.ADOPTED,
            replayed=False,
            assignment_count=0,
            review_identity=None,
        )


class _StaleWorkflow(_Workflow):
    def apply(self, request):
        raise RuntimeError("historical_order_candidate_stale")


def test_workbook_apply_replays_terminal_receipt_and_conflicts_before_row_apply(monkeypatch):
    original = _workbook("a" * 64)
    different = _workbook("b" * 64)
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: original if path == "first.xlsx" else different)
    repository = _Repository()
    workflow = _Workflow()
    service = module.HistoricalOrderWorkbookImportService(repository, workflow, _UnitOfWork)
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
    service = module.HistoricalOrderWorkbookImportService(_Repository(), workflow, _UnitOfWork)

    with pytest.raises(ValueError, match="historical_order_preview_stale"):
        service.apply("first.xlsx", "workbook-key", "0" * 64, "operator", "correlation")

    assert workflow.apply_calls == 0


def test_apply_refreshes_a_later_row_after_the_same_case_was_changed_by_this_workbook(monkeypatch):
    workbook = _workbook_with_repeated_case()
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: workbook)
    workflow = _StatefulWorkflow()
    service = module.HistoricalOrderWorkbookImportService(
        _Repository(), workflow, _UnitOfWork
    )
    preview = service.preview("repeated-case.xlsx")

    receipt = service.apply(
        "repeated-case.xlsx",
        "repeated-case-key",
        preview.preview_fingerprint,
        "operator",
        "correlation",
    )

    assert receipt.source_row_count == 2
    assert receipt.adopted_count == 2
    assert workflow.apply_calls == 2


def test_row_stale_is_exposed_as_a_workbook_conflict_instead_of_an_internal_error(monkeypatch):
    workbook = _workbook("7" * 64)
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: workbook)
    service = module.HistoricalOrderWorkbookImportService(
        _Repository(), _StaleWorkflow(), _UnitOfWork
    )
    preview = service.preview("stale.xlsx")

    with pytest.raises(
        module.HistoricalOrderWorkbookConflict,
        match="historical_order_candidate_stale",
    ):
        service.apply(
            "stale.xlsx",
            "stale-key",
            preview.preview_fingerprint,
            "operator",
            "correlation",
        )


def test_preview_and_receipt_expose_conserved_zero_one_two_status_counts(monkeypatch):
    workbook = _workbook_with_statuses()
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: workbook)
    service = module.HistoricalOrderWorkbookImportService(_Repository(), _Workflow(), _UnitOfWork)

    preview = service.preview("statuses.xlsx")
    receipt = service.apply(
        "statuses.xlsx", "status-counts-key", preview.preview_fingerprint, "operator", "correlation",
    )

    assert preview.status_counts.as_dict() == {
        "cancelled_0": 1,
        "deposit_paid_1": 1,
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
            "status_counts": {
                "cancelled_0": 1,
                "completed_1": 1,
                "discussion_2": 1,
                "invalid_or_blank": 1,
            },
        }),
    }
    monkeypatch.setattr(module, "load_historical_order_workbook", lambda path: workbook)

    replay = module.HistoricalOrderWorkbookImportService(repository, _Workflow(), _UnitOfWork).apply(
        "statuses.xlsx", "legacy-key", "0" * 64, "operator", "correlation",
    )

    assert replay.replayed_workbook is True
    assert replay.status_counts.total == 4
    assert replay.status_counts.deposit_paid_1 == 1


def _workbook(digest: str) -> HistoricalOrderWorkbook:
    row = HistoricalOrderWorkbookRow(2, f"historical-orders:{digest}:row:2", "d" * 64, "CASE-1", "客戶甲", None, None, None, (), ())
    return HistoricalOrderWorkbook(digest, "e" * 64, "任意名稱", (row,))


def _workbook_with_statuses() -> HistoricalOrderWorkbook:
    statuses = (
        HistoricalOrderSourceStatus.CANCELLED,
        HistoricalOrderSourceStatus.DEPOSIT_PAID,
        HistoricalOrderSourceStatus.DISCUSSION,
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


def _workbook_with_repeated_case() -> HistoricalOrderWorkbook:
    rows = tuple(
        HistoricalOrderWorkbookRow(
            source_row,
            f"historical-orders:{'9' * 64}:row:{source_row}",
            str(source_row) * 64,
            "CASE-REPEATED",
            "客戶甲",
            HistoricalOrderSourceStatus.DEPOSIT_PAID,
            None,
            None,
            (),
            (),
        )
        for source_row in (2, 3)
    )
    return HistoricalOrderWorkbook("9" * 64, "8" * 64, "任意名稱", rows)

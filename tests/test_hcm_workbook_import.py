"""
File: test_hcm_workbook_import.py
Description: 驗證 HCM workbook command receipt 的 replay 與 conflict 邊界。
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from subsystems.case_import.hcm_workbook_import import HcmWorkbookConflict, HcmWorkbookImportService


class _Repository:
    def __init__(self) -> None:
        self.receipts = {}
        self.claims = {}
        self.locked = []
        self.intake_calls = 0

    def acquire_lock(self, key):
        self.locked.append(key)
        return True

    def release_lock(self, key):
        self.locked.remove(key)

    def load_receipt(self, key):
        return self.receipts.get(key)

    def claim(self, key, digest, correlation_id):
        existing = self.claims.get(key)
        if existing and existing != digest:
            return "conflict"
        self.claims[key] = digest
        return "created"

    def save_receipt(self, key, digest, actor, result):
        self.receipts[key] = {"request_fingerprint": digest, "result_snapshot": json.dumps(result)}


class _Intake:
    def __init__(self, repository) -> None:
        self._repository = repository

    def load_frame(self, source_path):
        return pd.DataFrame({"案件": ["A"]})

    def import_rows(self, frame, source_path):
        self._repository.intake_calls += 1
        return {"inserted": len(frame), "exact_replay": 0, "review_required": 0, "failed": 0}


class _IncompleteIntake(_Intake):
    def import_rows(self, frame, source_path):
        return {"inserted": 1, "exact_replay": 0, "review_required": 0, "failed": 0}


def test_same_key_and_digest_returns_terminal_workbook_receipt(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"same workbook")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository))

    first = service.ingest(pd.DataFrame({"案件": ["A"]}), str(workbook), "key-1", "operator", "corr-1")
    replay = service.ingest(pd.DataFrame({"案件": ["A"]}), str(workbook), "key-1", "operator", "corr-2")

    assert first.replayed_workbook is False
    assert replay.replayed_workbook is True
    assert repository.intake_calls == 1
    assert repository.locked == []


def test_same_key_and_different_digest_conflicts_before_row_intake(tmp_path):
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository))

    service.ingest(pd.DataFrame({"案件": ["A"]}), str(first), "key-1", "operator", "corr-1")
    with pytest.raises(HcmWorkbookConflict):
        service.ingest(pd.DataFrame({"案件": ["B"]}), str(second), "key-1", "operator", "corr-2")

    assert repository.intake_calls == 1
    assert repository.locked == []


def test_incomplete_row_outcomes_do_not_create_a_terminal_receipt(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"one incomplete outcome")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _IncompleteIntake(repository))

    with pytest.raises(ValueError, match="hcm_import_row_outcomes_not_conserved"):
        service.ingest(pd.DataFrame({"案件": ["A", "B"]}), str(workbook), "key-1", "operator", "corr-1")

    assert repository.receipts == {}

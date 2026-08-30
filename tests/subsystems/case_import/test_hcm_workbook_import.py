"""
File: test_hcm_workbook_import.py
Description: 驗證HCM workbook receipt依identity或摘要replay及conflict邊界。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

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

    def load_receipt_by_digest(self, digest):
        return next((receipt for receipt in self.receipts.values() if receipt["request_fingerprint"] == digest), None)

    def claim(self, key, digest, correlation_id):
        existing = self.claims.get(key)
        if existing and existing != digest:
            return "conflict"
        self.claims[key] = digest
        return "created"

    def save_receipt(self, key, digest, actor, result):
        self.receipts[key] = {"request_fingerprint": digest, "result_snapshot": json.dumps(result)}

    def query_recent_receipts(self, *, limit, before_receipt_id):
        del limit, before_receipt_id
        return tuple(self.recent_rows)


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _RecordingUnitOfWork(_UnitOfWork):
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def __exit__(self, exception_type, *_):
        if exception_type is not None:
            self.rollbacks += 1
        return False

    def commit(self):
        self.commits += 1


class _Intake:
    def __init__(self, repository) -> None:
        self._repository = repository
        repository.recent_rows = []

    def load_frame(self, source_path):
        return pd.DataFrame({"案件": ["A"]})

    def import_rows(self, frame, source_path):
        self._repository.intake_calls += 1
        return {
            "inserted": len(frame), "inserted_with_warning": 0, "exact_replay": 0,
            "review_required": 0, "failed": 0,
        }

    def preview_rows(self, frame, source_path):
        return {"ready": len(frame), "ready_with_warning": 0, "review_required": 0}


class _CurrentUowIntake(_Intake):
    def import_rows(self, frame, source_path):
        raise AssertionError("workbook composition must borrow its UoW")

    def import_rows_in_current_uow(self, frame, source_path):
        return _Intake.import_rows(self, frame, source_path)


class _FailingCurrentUowIntake(_CurrentUowIntake):
    def import_rows_in_current_uow(self, frame, source_path):
        raise RuntimeError("orders_reconciliation_failed")


class _IncompleteIntake(_Intake):
    def import_rows(self, frame, source_path):
        return {
            "inserted": 1, "inserted_with_warning": 0, "exact_replay": 0,
            "review_required": 0, "failed": 0,
        }


class _WarningIntake(_Intake):
    def import_rows(self, frame, source_path):
        self._repository.intake_calls += 1
        return {
            "inserted": 0, "inserted_with_warning": len(frame), "exact_replay": 0,
            "review_required": 0, "failed": 0,
        }

    def preview_rows(self, frame, source_path):
        return {"ready": 0, "ready_with_warning": len(frame), "review_required": 0}


class _DetailedIntake(_Intake):
    def import_rows(self, frame, source_path):
        self._repository.intake_calls += 1
        return {
            "inserted": 1,
            "inserted_with_warning": 1,
            "exact_replay": 0,
            "review_required": 0,
            "failed": 0,
            "row_outcomes": [
                {"source_row": 1, "case_no": "115000001", "outcome": "inserted", "problem_identity": None, "problem_fields": [], "issue_codes": [], "referral_occurrence_identities": []},
                {"source_row": 2, "case_no": "115000002", "outcome": "inserted_with_warning", "problem_identity": "hcm-review:warning", "problem_fields": ["行動電話"], "issue_codes": ["hcm_field_invalid:行動電話"], "referral_occurrence_identities": ["warning-2"]},
            ],
        }


def test_same_key_and_digest_returns_terminal_workbook_receipt(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"same workbook")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository), _UnitOfWork)

    first = service.ingest(pd.DataFrame({"案件": ["A"]}), str(workbook), "key-1", "operator", "corr-1")
    replay = service.ingest(pd.DataFrame({"案件": ["A"]}), str(workbook), "key-1", "operator", "corr-2")

    assert first.replayed_workbook is False
    assert replay.replayed_workbook is True
    assert repository.intake_calls == 1
    assert repository.locked == []


def test_ingest_keeps_claim_rows_and_workbook_receipt_in_one_outer_uow(tmp_path):
    workbook = tmp_path / "single-uow.xlsx"
    workbook.write_bytes(b"single workbook transaction")
    repository = _Repository()
    unit_of_work = _RecordingUnitOfWork()
    service = HcmWorkbookImportService(
        repository, _CurrentUowIntake(repository), lambda: unit_of_work,
    )

    receipt = service.ingest(
        pd.DataFrame({"案件": ["A"]}), str(workbook), "key-single-uow", "operator", "corr-1",
    )

    assert receipt.inserted_count == 1
    assert unit_of_work.commits == 1
    assert unit_of_work.rollbacks == 0


def test_ingest_rolls_back_claim_and_receipt_when_current_uow_step_fails(tmp_path):
    workbook = tmp_path / "failed-single-uow.xlsx"
    workbook.write_bytes(b"failed workbook transaction")
    repository = _Repository()
    unit_of_work = _RecordingUnitOfWork()
    service = HcmWorkbookImportService(
        repository, _FailingCurrentUowIntake(repository), lambda: unit_of_work,
    )

    with pytest.raises(RuntimeError, match="orders_reconciliation_failed"):
        service.ingest(
            pd.DataFrame({"案件": ["A"]}), str(workbook), "key-failed-uow", "operator", "corr-1",
        )

    assert unit_of_work.commits == 0
    assert unit_of_work.rollbacks == 1
    assert repository.receipts == {}


def test_same_digest_with_a_new_key_returns_the_existing_terminal_receipt(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"same workbook new key")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository), _UnitOfWork)

    first = service.ingest(pd.DataFrame({"案件": ["A"]}), str(workbook), "key-1", "operator", "corr-1")
    replay = service.ingest(pd.DataFrame({"案件": ["A"]}), str(workbook), "key-2", "operator", "corr-2")

    assert first.replayed_workbook is False
    assert replay.replayed_workbook is True
    assert repository.intake_calls == 1
    assert "key-2" not in repository.claims


def test_preview_is_zero_write_and_apply_requires_matching_fingerprint(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"previewed workbook")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository), _UnitOfWork)
    frame = pd.DataFrame({"案件": ["A"]})

    preview = service.preview(frame, str(workbook))

    assert preview.ready_count == 1
    assert repository.claims == {}
    assert repository.receipts == {}
    receipt = service.apply(
        frame, str(workbook), preview.preview_fingerprint,
        "key-1", "operator", "corr-1",
    )
    assert receipt.inserted_count == 1


def test_partial_formal_cases_are_explicit_in_preview_and_terminal_receipt(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"partial formal cases")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _WarningIntake(repository), _UnitOfWork)
    frame = pd.DataFrame({"案件": ["A", "B"]})

    preview = service.preview(frame, str(workbook))
    receipt = service.apply(
        frame, str(workbook), preview.preview_fingerprint,
        "key-1", "operator", "corr-1",
    )

    assert preview.ready_count == 0
    assert preview.ready_with_warning_count == 2
    assert receipt.inserted_with_warning_count == 2


def test_apply_rejects_stale_preview_before_row_intake(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"stale workbook")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository), _UnitOfWork)

    with pytest.raises(HcmWorkbookConflict, match="hcm_workbook_preview_stale"):
        service.apply(
            pd.DataFrame({"案件": ["A"]}), str(workbook), "0" * 64,
            "key-1", "operator", "corr-1",
        )

    assert repository.intake_calls == 0
    assert repository.claims == {}


def test_same_key_and_different_digest_conflicts_before_row_intake(tmp_path):
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository), _UnitOfWork)

    service.ingest(pd.DataFrame({"案件": ["A"]}), str(first), "key-1", "operator", "corr-1")
    with pytest.raises(HcmWorkbookConflict):
        service.ingest(pd.DataFrame({"案件": ["B"]}), str(second), "key-1", "operator", "corr-2")

    assert repository.intake_calls == 1
    assert repository.locked == []


def test_incomplete_row_outcomes_do_not_create_a_terminal_receipt(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"one incomplete outcome")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _IncompleteIntake(repository), _UnitOfWork)

    with pytest.raises(ValueError, match="hcm_import_row_outcomes_not_conserved"):
        service.ingest(pd.DataFrame({"案件": ["A", "B"]}), str(workbook), "key-1", "operator", "corr-1")

    assert repository.receipts == {}


def test_detailed_receipt_preserves_batch_membership_and_problem_lineage(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"detailed workbook")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _DetailedIntake(repository), _UnitOfWork)

    receipt = service.ingest(
        pd.DataFrame({"案件": ["A", "B"]}),
        str(workbook),
        "key-detail",
        "operator",
        "corr-detail",
    )

    assert receipt.row_outcomes_available is True
    assert receipt.legacy_summary_only is False
    assert [row.case_no for row in receipt.row_outcomes] == ["115000001", "115000002"]
    assert receipt.row_outcomes[1].problem_fields == ("行動電話",)


def test_recent_results_keep_legacy_receipt_membership_unavailable(tmp_path):
    workbook = tmp_path / "hcm.xlsx"
    workbook.write_bytes(b"legacy workbook")
    repository = _Repository()
    service = HcmWorkbookImportService(repository, _Intake(repository), _UnitOfWork)
    repository.recent_rows = [{
        "id": 9,
        "request_fingerprint": "a" * 64,
        "result_snapshot": json.dumps({
            "source_row_count": 1,
            "inserted_count": 1,
            "inserted_with_warning_count": 0,
            "exact_replay_count": 0,
            "review_required_count": 0,
            "failed_count": 0,
            "replayed_workbook": False,
        }),
        "created_at": datetime(2026, 8, 17, 12, 0, 0),
    }]

    page = service.query_recent_results(limit=20, before_receipt_id=None)

    assert page.items[0].receipt.legacy_summary_only is True
    assert page.items[0].receipt.row_outcomes_available is False
    assert page.items[0].receipt.row_outcomes == ()
    assert page.items[0].completed_at.utcoffset() == timedelta(hours=8)
    assert page.items[0].completed_at.isoformat().endswith("+08:00")

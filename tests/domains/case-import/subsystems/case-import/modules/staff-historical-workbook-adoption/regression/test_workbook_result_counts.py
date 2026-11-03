"""Workbook totals count successful staff once, including rows committed before resume."""

import copy
import json

import pytest

from subsystems.case_import.staff_historical_workbook import StaffHistoricalWorkbook, StaffHistoricalWorkbookRow
from subsystems.case_import.staff_historical_workbook_adoption import StaffHistoricalWorkbookService


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        pass


class _Repository:
    def __init__(self):
        self.staff = {}
        self.receipts = {}

    def load_staff(self, identity_card, *, for_update):
        return [self.staff[identity_card]] if identity_card in self.staff else []

    def create_staff(self, record):
        staff_id = len(self.staff) + 1
        self.staff[record["identity_card"]] = {**record, "id": staff_id}
        return staff_id

    def apply_scalar_patch(self, staff_id, patch):
        staff = next(root for root in self.staff.values() if root["id"] == staff_id)
        staff.update(patch)

    def merge_bank_accounts(self, *_args, **_kwargs):
        return False, False

    def merge_relation(self, *_args, **_kwargs):
        return False, False

    def claim(self, key, *_args):
        return key not in self.receipts

    def find_receipt(self, key):
        return self.receipts.get(key)

    def save_receipt(self, **values):
        assert values["key"] not in self.receipts
        self.receipts[values["key"]] = values


def _workbook(identities=None):
    # 49 source rows, including 12 further rows for the first 23 of 37 staff.
    identities = list(range(23)) + list(range(12)) + list(range(23, 37)) if identities is None else identities
    rows = tuple(StaffHistoricalWorkbookRow(
        source_row,
        {"identity_card": f"SYNTH-{identity}", "name": f"Synthetic {identity}",
         "registered_at": f"2026-11-{1 if source_row <= 24 else 2:02d} 00:00:00",
         "email": None if source_row <= 24 else f"synthetic-{identity}@example.test"},
        (), (), {},
    ) for source_row, identity in enumerate(identities, start=2))
    return StaffHistoricalWorkbook("a" * 64, "synthetic-sheet", rows)


def _service(repository):
    return StaffHistoricalWorkbookService(
        object(), object(), _UnitOfWork, repository_factory=lambda _: repository,
    )


@pytest.mark.parametrize("committed_rows", [0, 35, 49])
def test_49_rows_count_37_staff_and_12_duplicates_on_first_run_or_resume(committed_rows):
    workbook = _workbook()
    repository = _Repository()
    service = _service(repository)
    for row in workbook.rows[:committed_rows]:
        service._apply_row(workbook, row)

    receipt = service._apply_rows(workbook, "b" * 64)

    assert receipt.source_row_count == 49
    assert receipt.created_count == 37
    assert receipt.adopted_existing_count == 0
    assert receipt.exact_replay_count == 12
    assert receipt.blocked_identity_count == receipt.identity_conflict_count == 0
    assert len(repository.staff) == 37
    assert len(repository.receipts) == 49
    # Duplicate rows must still adopt newer valid data even though they count as skipped.
    assert repository.staff["SYNTH-0"]["email"] == "synthetic-0@example.test"


def test_distinct_existing_staff_are_counted_as_adopted_once():
    workbook = _workbook([0, 1, 0])
    repository = _Repository()
    for row in workbook.rows[:2]:
        repository.create_staff(row.record)

    receipt = _service(repository)._apply_rows(workbook, "b" * 64)

    assert receipt.source_row_count == 3
    assert receipt.created_count == 0
    assert receipt.adopted_existing_count == 2
    assert receipt.exact_replay_count == 1


def test_old_14_imported_35_skipped_receipt_uses_original_row_evidence_without_writes(monkeypatch):
    workbook = _workbook()
    repository = _Repository()
    service = _service(repository)
    receipt = service._apply_rows(workbook, "b" * 64)
    old_payload = {**receipt.as_dict(), "created_count": 14, "adopted_existing_count": 0,
                   "exact_replay_count": 35, "review_required_count": 7, "row_issues": None}
    stored = {"request_fingerprint": workbook.source_content_digest, "result_snapshot": json.dumps(old_payload)}
    original_rows = copy.deepcopy(repository.receipts)
    original_stored = copy.deepcopy(stored)

    def unexpected_write_or_fresh_read(*_args, **_kwargs):
        pytest.fail("Receipt replay must only read historical row receipts")

    for method in ("load_staff", "create_staff", "claim", "save_receipt", "apply_scalar_patch", "merge_bank_accounts", "merge_relation"):
        monkeypatch.setattr(repository, method, unexpected_write_or_fresh_read)

    result = service._replay(stored, workbook)

    assert (result.source_row_count, result.created_count, result.adopted_existing_count, result.exact_replay_count) == (49, 37, 0, 12)
    assert result.replayed_workbook is True
    assert result.review_required_count == 7
    assert result.row_issues is None
    assert repository.receipts == original_rows
    assert stored == original_stored


def test_incomplete_historical_row_evidence_keeps_original_aggregate():
    workbook = _workbook()
    repository = _Repository()
    service = _service(repository)
    receipt = service._apply_rows(workbook, "b" * 64)
    old_payload = {**receipt.as_dict(), "created_count": 14, "exact_replay_count": 35}
    repository.receipts.pop(next(iter(repository.receipts)))

    result = service._replay({"request_fingerprint": workbook.source_content_digest,
                              "result_snapshot": json.dumps(old_payload)}, workbook)

    assert result.created_count == 14
    assert result.exact_replay_count == 35


def test_rejected_rows_remain_not_imported_and_are_not_hidden_by_identity_deduplication(monkeypatch):
    workbook = _workbook([0, 0, 0, 1])
    service = _service(_Repository())
    monkeypatch.setattr(service, "_apply_row", lambda _, row: {
        2: ("created", False), 3: ("identity_conflict", True),
        4: ("adopted_existing", True), 5: ("blocked_identity", True),
    }[row.source_row])

    result = service._apply_rows(workbook, "b" * 64)

    assert (result.created_count, result.adopted_existing_count, result.exact_replay_count) == (1, 0, 1)
    assert result.identity_conflict_count == result.blocked_identity_count == 1
    assert [issue["source_row"] for issue in result.row_issues] == [3, 5]

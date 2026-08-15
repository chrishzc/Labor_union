"""
File: test_client_beclass_workbook_import.py
Description: 驗證 Client BeClass temporary workbook 的 Preview、Apply、replay 與 review 邊界。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from subsystems.case_import import client_beclass_workbook_import as intake


_DIGEST = "a" * 64
_SHEET = "b" * 64


class _Connection:
    def __init__(self) -> None:
        self.begins = 0
        self.commits = 0
        self.rollbacks = 0

    def begin(self) -> None:
        self.begins += 1

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Repository:
    def __init__(self) -> None:
        self.connection = _Connection()
        self.workbook_receipt = None
        self.rows: dict[str, dict] = {}
        self.created: list[dict] = []
        self.saved_workbook = None
        self.locks = []

    def acquire_lock(self, key):
        self.locks.append(key)
        return True

    def release_lock(self, key):
        self.locks.remove(key)

    def load_workbook_receipt(self, key):
        return self.workbook_receipt

    def source_state(self, payload):
        if payload["query_no"] == "EXISTING-1":
            return "exact"
        if payload["query_no"] == "CHANGED-1":
            return "conflict"
        return "absent"

    def resolve_unique_client_case(self, name, phone):
        return {"id": 7, "case_no": "HCM-0007"} if name == "測試客戶" and phone == "0912345678" else None

    def claim_workbook(self, key, fingerprint, correlation):
        return "created"

    def load_row_receipt(self, key):
        return self.rows.get(key)

    def claim_row(self, key, fingerprint, correlation):
        return "created"

    def create_bound_source_if_absent(self, payload, client_case):
        if payload["query_no"] == "EXISTING-1":
            return None
        self.created.append({**payload, "client_id": client_case["id"], "bound_case_no": client_case["case_no"]})
        return len(self.created)

    def require_matching_client_root(self, receipt):
        return None

    def save_row_receipt(self, key, fingerprint, root_id, outcome, review_identity, actor):
        self.rows[key] = {"request_fingerprint": fingerprint, "root_id": root_id}

    def save_workbook_receipt(self, key, fingerprint, preview, actor, result):
        self.saved_workbook = result


def _valid_row(query_no="CASE-1"):
    return {
        "查詢序號": query_no, "報名時間": "2026-08-14", "姓名": "測試客戶",
        "Email": "client@example.invalid", "出生年": 1990, "月": 1, "日": 2,
        "行動電話": "0912345678", "補助款退款:銀行代號+分行代號": "", "銀行帳號": "",
    }


def _workbook(*rows):
    return intake._Workbook(_DIGEST, _SHEET, tuple((ordinal, row) for ordinal, row in enumerate(rows, start=2)))


def test_preview_is_read_only_and_keeps_invalid_rows_as_review(monkeypatch):
    repository = _Repository()
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row(), {**_valid_row(""), "姓名": ""}))

    preview = intake.ClientBeClassWorkbookImportService(repository).preview("ignored.xlsx")

    assert preview.source_row_count == 2
    assert preview.create_count == 1
    assert preview.review_required_count == 1
    assert repository.created == []
    assert repository.connection.commits == 0


def test_apply_creates_valid_row_and_records_invalid_review(monkeypatch):
    repository = _Repository()
    service = intake.ClientBeClassWorkbookImportService(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row(), {**_valid_row("BAD"), "姓名": ""}))
    monkeypatch.setattr(intake, "record_invalid_beclass_row", lambda *args, **kwargs: "beclass-review:test")
    preview = service.preview("ignored.xlsx")

    receipt = service.apply("ignored.xlsx", "client-test-key", preview.preview_fingerprint, "admin", "corr")

    assert receipt.created_count == 1
    assert receipt.review_required_count == 1
    assert receipt.exact_replay_count == 0
    assert repository.created[0]["query_no"] == "CASE-1"
    assert repository.saved_workbook == receipt.as_dict()
    assert repository.locks == []


def test_apply_rejects_preview_fingerprint_drift(monkeypatch):
    repository = _Repository()
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))

    with pytest.raises(intake.ClientBeClassWorkbookConflict, match="client_beclass_preview_stale"):
        intake.ClientBeClassWorkbookImportService(repository).apply("ignored.xlsx", "key", "f" * 64, "admin", "corr")

    assert repository.created == []


def test_row_receipt_replays_without_creating_a_second_root(monkeypatch):
    repository = _Repository()
    service = intake.ClientBeClassWorkbookImportService(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")
    first = service.apply("ignored.xlsx", "key-one", preview.preview_fingerprint, "admin", "corr")
    second_preview = service.preview("ignored.xlsx")
    second = service.apply("ignored.xlsx", "key-two", second_preview.preview_fingerprint, "admin", "corr")

    assert first.created_count == 1
    assert second.exact_replay_count == 1
    assert len(repository.created) == 1


def test_existing_query_number_is_reported_as_existing_source_not_a_binding_conflict(monkeypatch):
    repository = _Repository()
    service = intake.ClientBeClassWorkbookImportService(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("EXISTING-1")))
    preview = service.preview("ignored.xlsx")

    receipt = service.apply("ignored.xlsx", "key", preview.preview_fingerprint, "admin", "corr")

    assert preview.existing_source_count == 1
    assert receipt.existing_source_count == 1
    assert repository.created == []


def test_existing_query_number_with_changed_payload_creates_review(monkeypatch):
    repository = _Repository()
    service = intake.ClientBeClassWorkbookImportService(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("CHANGED-1")))
    monkeypatch.setattr(intake, "record_invalid_beclass_row", lambda *args, **kwargs: "beclass-review:changed")
    preview = service.preview("ignored.xlsx")

    receipt = service.apply(
        "ignored.xlsx",
        "changed-key",
        preview.preview_fingerprint,
        "admin",
        "corr",
    )

    assert preview.existing_conflict_count == 1
    assert receipt.existing_conflict_count == 1
    assert receipt.existing_source_count == 0
    assert repository.created == []

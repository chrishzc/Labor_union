"""
File: test_review_intake_translation.py
Description: Regression coverage for Staff historical workbook review intake translation.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from api.dependencies import staff_historical_workbook as dependency
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from subsystems.case_import.beclass_review_intake import record_invalid_beclass_row
from subsystems.case_import.staff_historical_workbook_adoption import (
    StaffHistoricalWorkbookReceipt,
    StaffHistoricalWorkbookService,
)
from subsystems.case_import import staff_historical_workbook_adoption as workflow


class _ReviewRepository:
    def __init__(self) -> None:
        self.appended = []

    def load(self, review_identity: str, *, for_update: bool):
        del review_identity, for_update
        return None

    def append_invalid_row(self, root) -> None:
        self.appended.append(root)


def test_staff_historical_review_translates_workbook_context_for_intake_recorder():
    repository = _ReviewRepository()
    service = StaffHistoricalWorkbookService(
        object(),
        workbook_repository=object(),
        unit_of_work_factory=lambda: None,
        repository_factory=lambda _connection: repository,
        review_recorder=record_invalid_beclass_row,
    )
    workbook = SimpleNamespace(
        source_content_digest="a" * 64,
        sheet_identity="月嫂歷史",
    )
    row = SimpleNamespace(
        source_row=7,
        record={
            "identity_card": "A123456789",
            "name": "測試月嫂",
            "phone": "0912345678",
            "address": "測試地址",
        },
    )

    review_identity = service._record_review(
        workbook=workbook,
        row=row,
        issues=("historical_nonempty_conflict:bank_accounts",),
    )

    assert review_identity.startswith("beclass-review:")
    assert len(repository.appended) == 1
    root = repository.appended[0]
    assert root.source_sheet == "月嫂歷史"
    assert root.source_row == 7
    assert root.masked_identifier == "staff-***-6789"
    assert root.source_payload == {
        "source_field_count": 4,
        "has_identity_card": True,
        "has_name": True,
        "has_phone": True,
        "has_address": True,
    }
    assert root.issue_codes == ("historical_nonempty_conflict:bank_accounts",)


def test_staff_historical_dependency_routes_review_to_beclass_repository(monkeypatch):
    review_repository = _ReviewRepository()
    monkeypatch.setattr(
        dependency,
        "MySqlBeClassImportReviewRepository",
        lambda _connection: review_repository,
    )

    review_identity = dependency._record_staff_historical_review(
        object(),
        source_kind=BeClassImportSourceKind.STAFF,
        source_content_digest="b" * 64,
        source_sheet="月嫂歷史",
        source_row=8,
        masked_identifier="staff-***-6789",
        source_payload={"has_identity_card": True},
        issue_codes=("staff_field_invalid:EMAIL",),
        repository=object(),
    )

    assert review_identity.startswith("beclass-review:")
    assert len(review_repository.appended) == 1
    assert review_repository.appended[0].issue_codes == ("staff_field_invalid:EMAIL",)


def test_staff_historical_exact_replay_precedes_fresh_preview_check(monkeypatch):
    digest = "c" * 64
    stored = StaffHistoricalWorkbookReceipt(
        source_content_digest=digest,
        source_row_count=1,
        created_count=1,
        adopted_existing_count=0,
        exact_replay_count=0,
        blocked_identity_count=0,
        identity_conflict_count=0,
        review_required_count=1,
        preview_fingerprint="d" * 64,
        replayed_workbook=False,
    )
    workbook_repository = SimpleNamespace(
        acquire_lock=lambda _key: True,
        release_lock=lambda _key: None,
        load_receipt=lambda _key: {
            "request_fingerprint": digest,
            "result_snapshot": json.dumps(stored.as_dict()),
        },
    )
    service = StaffHistoricalWorkbookService(
        object(), workbook_repository, unit_of_work_factory=lambda: None
    )
    monkeypatch.setattr(
        workflow,
        "load_staff_historical_workbook",
        lambda _path, _revision: SimpleNamespace(source_content_digest=digest),
    )
    monkeypatch.setattr(
        service,
        "_preview",
        lambda _workbook: (_ for _ in ()).throw(
            AssertionError("exact replay must not require a fresh preview")
        ),
    )

    replay = service.apply(
        "staff.xlsx",
        None,
        preview_fingerprint="stale-client-preview",
        key="same-command-key",
        actor="test-admin",
        correlation_id="same-correlation",
    )

    assert replay.replayed_workbook is True
    assert replay.source_content_digest == digest

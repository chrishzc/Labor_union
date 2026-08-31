"""
File: test_client_beclass_workbook_import.py
Description: 驗證 Client BeClass temporary workbook 的 Preview、Apply、replay 與 review 邊界。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from domains.case_import.client_beclass_binding import (
    ClientCaseBindingResolution,
    ClientCaseBindingStatus,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql import hcm_beclass_reconciliation_adapter as reconciliation_adapter
from subsystems.case_import import client_beclass_workbook_import as intake
from subsystems.jobs.contracts import validate_command_key


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
        self.workbook_receipts = {}
        self.rows: dict[str, dict] = {}
        self.created: list[dict] = []
        self.saved_workbook = None
        self.locks = []
        self.binding_lock_modes = []
        self.replay_bound_cases = ()
        self.lineage = []
        self.binding_resolution = ClientCaseBindingResolution(
            ClientCaseBindingStatus.UNIQUE, 1, 1, 7, "HCM-0007"
        )

    def acquire_lock(self, key):
        self.locks.append(key)
        return True

    def release_lock(self, key):
        self.locks.remove(key)

    def load_workbook_receipt(self, key):
        return self.workbook_receipts.get(key)

    def source_state(self, payload):
        if payload["query_no"] == "EXISTING-1":
            return "exact"
        if payload["query_no"] == "CHANGED-1":
            return "conflict"
        return "absent"

    def resolve_unique_client_case(self, name, phone):
        return {"id": 7, "case_no": "HCM-0007"} if name == "測試客戶" and phone == "0912345678" else None

    def resolve_client_case_binding(self, name, phone, *, for_update):
        del name, phone
        self.binding_lock_modes.append(for_update)
        return self.binding_resolution

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

    def bound_case_no_for_root(self, root_id):
        return "HCM-0007" if root_id is not None else None

    def bound_source_for_query(self, query_no):
        return {"root_id": 77, "case_no": "HCM-0007"}

    def bound_case_nos_for_workbook(self, digest):
        del digest
        return self.replay_bound_cases

    def save_row_receipt(self, key, fingerprint, root_id, outcome, review_identity, actor):
        result_identity = f"admin_command_receipt:{len(self.rows) + 1}"
        self.rows[key] = {
            "request_fingerprint": fingerprint,
            "root_id": root_id,
            "outcome": outcome,
            "accepted_result_identity": result_identity,
        }
        return result_identity

    def append_case_pairing_lineage(self, original_review_identity, accepted_source_event_identity, accepted_result_identity, accepted_root_id=None):
        self.lineage.append(
            (
                original_review_identity,
                accepted_source_event_identity,
                accepted_result_identity,
                accepted_root_id,
                self.connection.commits,
            )
        )

    def save_workbook_receipt(self, key, fingerprint, preview, actor, result, *, original_review_identity=None):
        self.saved_workbook = result
        if original_review_identity is not None:
            result = {
                **result,
                "_lineage_original_review_identity": original_review_identity,
            }
        self.workbook_receipts[key] = {
            "request_fingerprint": fingerprint,
            "result_snapshot": json.dumps(result),
        }


class _MissingReceiptIdentityRepository(_Repository):
    def save_row_receipt(self, key, fingerprint, root_id, outcome, review_identity, actor):
        super().save_row_receipt(key, fingerprint, root_id, outcome, review_identity, actor)
        return None


class _Reconciliation:
    def __init__(self, *, error=None):
        self.calls = []
        self.event_count = 0
        self._applied_cases = set()
        self.error = error

    def reconcile(self, case_no):
        self.calls.append(case_no)
        if self.error is not None:
            raise self.error
        if case_no not in self._applied_cases:
            self._applied_cases.add(case_no)
            self.event_count += 1
        return SimpleNamespace(status="reconciled")


def _service(repository, reconciliation=None, pairing_rechecks=None):
    return intake.ClientBeClassWorkbookImportService(
        repository,
        reconciliation or _Reconciliation(),
        lambda: MySqlUnitOfWork(repository.connection),
        pairing_rechecks=pairing_rechecks,
    )


def _valid_row(query_no="CASE-1"):
    return {
        "查詢序號": query_no, "報名時間": "2026-08-14", "姓名": "測試客戶",
        "Email": "client@example.invalid", "出生年": 1990, "月": 1, "日": 2,
        "行動電話": "0912345678", "補助款退款:銀行代號+分行代號": "", "銀行帳號": "",
    }


def _workbook(*rows):
    return intake._Workbook(_DIGEST, _SHEET, tuple((ordinal, row) for ordinal, row in enumerate(rows, start=2)))


def test_validation_issue_codes_preserve_missing_vs_invalid_without_raw_values():
    issue_codes = intake._client_validation_issue_codes(
        {
            "姓名": "不可空值",
            "Email": "格式不正確：sensitive@example.invalid",
        }
    )

    assert issue_codes == (
        "client_field_invalid:Email",
        "client_field_missing:姓名",
    )
    assert "sensitive@example.invalid" not in "|".join(issue_codes)


def test_preview_is_read_only_and_keeps_invalid_rows_as_review(monkeypatch):
    repository = _Repository()
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row(), {**_valid_row(""), "姓名": ""}))

    preview = _service(repository).preview("ignored.xlsx")

    assert preview.source_row_count == 2
    assert preview.create_count == 1
    assert preview.review_required_count == 1
    assert repository.created == []
    assert repository.connection.commits == 0
    assert repository.binding_lock_modes == [False]


def test_apply_creates_valid_row_and_records_invalid_review(monkeypatch):
    repository = _Repository()
    reconciliation = _Reconciliation()
    service = _service(repository, reconciliation)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row(), {**_valid_row("BAD"), "姓名": ""}))
    monkeypatch.setattr(intake, "record_invalid_beclass_row", lambda *args, **kwargs: "beclass-review:test")
    preview = service.preview("ignored.xlsx")

    receipt = service.apply("ignored.xlsx", "client-test-key", preview.preview_fingerprint, "admin", "corr")

    assert receipt.created_count == 1
    assert receipt.review_required_count == 1
    assert receipt.exact_replay_count == 0
    assert repository.created[0]["query_no"] == "CASE-1"
    assert repository.binding_lock_modes == [False, False, True]
    assert reconciliation.calls == ["HCM-0007"]
    assert "CASE-1" not in reconciliation.calls
    assert repository.saved_workbook == receipt.as_dict()
    assert repository.locks == []


def test_apply_persists_explicit_cross_source_lineage_in_row_uow(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    receipt = service.apply(
        "ignored.xlsx", "lineage-key", preview.preview_fingerprint,
        "admin", "corr", "beclass-review:original",
    )

    assert receipt.created_count == 1
    assert repository.lineage == [
        (
            "beclass-review:original",
            f"client-beclass-workbook:{_DIGEST}:row:2",
            "admin_command_receipt:1",
            1,
            2,
        )
    ]


def test_reconciliation_does_not_append_retired_hcm_pairing_anomaly_recheck(
    monkeypatch,
):
    connection = _Connection()
    requests = []
    sink = SimpleNamespace(
        append_case_pairing_recheck=lambda request: requests.append(request)
    )
    adapter = reconciliation_adapter.MySqlHcmBeClassReconciliationAdapter(
        connection,
        sink,
    )
    monkeypatch.setattr(
        reconciliation_adapter,
        "reconcile_with_port",
        lambda _port, case_no: SimpleNamespace(status="reconciled", case_no=case_no),
    )
    monkeypatch.setattr(
        adapter,
        "load_pair_facts",
        lambda _case_no: {
            "hcm_count": 1,
            "beclass_count": 1,
            "hcm_version": 4,
            "beclass_id": 8,
            "query_no": "Q-8",
        },
    )

    result = adapter.reconcile("HCM-0007")

    assert result.status == "reconciled"
    assert requests == []
    assert connection.commits == 0


def test_apply_does_not_infer_lineage_for_missing_original_review(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    service.apply("ignored.xlsx", "no-lineage-key", preview.preview_fingerprint, "admin", "corr")

    assert repository.lineage == []


def test_exact_replay_does_not_append_duplicate_lineage(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    first = service.apply(
        "ignored.xlsx", "lineage-replay-key", preview.preview_fingerprint,
        "admin", "corr", "beclass-review:original",
    )
    replay = service.apply(
        "ignored.xlsx", "lineage-replay-key", preview.preview_fingerprint,
        "admin", "corr", "beclass-review:original",
    )

    assert first.created_count == 1
    assert replay.replayed_workbook is True
    assert len(repository.lineage) == 1


def test_existing_row_replay_can_link_later_explicit_review(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    service.apply(
        "ignored.xlsx", "row-replay-without-lineage", preview.preview_fingerprint,
        "admin", "corr",
    )
    service.apply(
        "ignored.xlsx", "row-replay-with-lineage", preview.preview_fingerprint,
        "admin", "corr", "beclass-review:original",
    )

    assert repository.lineage == [
        (
            "beclass-review:original",
            f"client-beclass-workbook:{_DIGEST}:row:2",
            "admin_command_receipt:1",
            1,
            6,
        )
    ]


def test_same_workbook_key_with_different_review_identity_conflicts(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    service.apply(
        "ignored.xlsx", "lineage-conflicting-key", preview.preview_fingerprint,
        "admin", "corr", "beclass-review:original",
    )

    with pytest.raises(
        intake.ClientBeClassWorkbookConflict,
        match="client_beclass_lineage_idempotency_conflict",
    ):
        service.apply(
            "ignored.xlsx", "lineage-conflicting-key", preview.preview_fingerprint,
            "admin", "corr", "beclass-review:other",
        )

    assert len(repository.lineage) == 1


def test_lineage_requires_durable_accepted_result_identity(monkeypatch):
    repository = _MissingReceiptIdentityRepository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    with pytest.raises(
        intake.ClientBeClassWorkbookConflict,
        match="client_beclass_accepted_result_identity_missing",
    ):
        service.apply(
            "ignored.xlsx", "lineage-missing-result", preview.preview_fingerprint,
            "admin", "corr", "beclass-review:original",
        )

    assert repository.lineage == []
    assert repository.connection.rollbacks == 1


def test_conflicting_row_with_original_review_remains_review_without_lineage(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("CHANGED-1")))
    monkeypatch.setattr(intake, "record_invalid_beclass_row", lambda *args, **kwargs: "beclass-review:conflict")
    preview = service.preview("ignored.xlsx")

    receipt = service.apply(
        "ignored.xlsx", "lineage-conflict-key", preview.preview_fingerprint,
        "admin", "corr", "beclass-review:original",
    )

    assert receipt.existing_conflict_count == 1
    assert repository.lineage == []


def test_apply_rejects_preview_fingerprint_drift(monkeypatch):
    repository = _Repository()
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))

    with pytest.raises(intake.ClientBeClassWorkbookConflict, match="client_beclass_preview_stale"):
        _service(repository).apply("ignored.xlsx", "key", "f" * 64, "admin", "corr")

    assert repository.created == []


def test_row_receipt_replays_without_creating_a_second_root(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")
    first = service.apply("ignored.xlsx", "key-one", preview.preview_fingerprint, "admin", "corr")
    second_preview = service.preview("ignored.xlsx")
    second = service.apply("ignored.xlsx", "key-two", second_preview.preview_fingerprint, "admin", "corr")

    assert first.created_count == 1
    assert second.exact_replay_count == 1
    assert len(repository.created) == 1


def test_same_workbook_replay_recovers_reconciliation_without_duplicate_event(
    monkeypatch,
):
    repository = _Repository()
    reconciliation = _Reconciliation()
    service = _service(repository, reconciliation)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    first = service.apply(
        "ignored.xlsx", "same-key", preview.preview_fingerprint, "admin", "corr"
    )
    repository.replay_bound_cases = ("HCM-0007",)
    replay = service.apply(
        "ignored.xlsx", "same-key", preview.preview_fingerprint, "admin", "corr"
    )

    assert first.replayed_workbook is False
    assert replay.replayed_workbook is True
    assert reconciliation.calls == ["HCM-0007", "HCM-0007"]
    assert reconciliation.event_count == 1


def test_reconciliation_failure_rolls_back_row_before_receipt(monkeypatch):
    repository = _Repository()
    service = _service(
        repository, _Reconciliation(error=RuntimeError("downstream unavailable"))
    )
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    with pytest.raises(RuntimeError, match="downstream unavailable"):
        service.apply(
            "ignored.xlsx", "failure-key", preview.preview_fingerprint, "admin", "corr"
        )

    assert repository.rows == {}
    assert repository.saved_workbook is None
    assert repository.connection.rollbacks == 1


def test_existing_query_number_is_reported_as_existing_source_not_a_binding_conflict(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("EXISTING-1")))
    preview = service.preview("ignored.xlsx")

    receipt = service.apply("ignored.xlsx", "key", preview.preview_fingerprint, "admin", "corr")

    assert preview.existing_source_count == 1
    assert receipt.existing_source_count == 1
    assert repository.created == []


def test_existing_exact_accepted_source_can_link_explicit_review(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("EXISTING-1")))
    preview = service.preview("ignored.xlsx")

    receipt = service.apply(
        "ignored.xlsx", "existing-lineage-key", preview.preview_fingerprint,
        "admin", "corr", "beclass-review:original",
    )

    assert receipt.existing_source_count == 1
    assert repository.lineage == [
        (
            "beclass-review:original",
            f"client-beclass-workbook:{_DIGEST}:row:2",
            "admin_command_receipt:1",
            77,
            2,
        )
    ]


def test_existing_query_number_with_changed_payload_creates_review(monkeypatch):
    repository = _Repository()
    recheck_identities = []

    class PairingRechecks:
        def append_case_pairing_recheck(self, request):
            recheck_identities.append(validate_command_key(request.intent_identity))

    service = _service(repository, pairing_rechecks=PairingRechecks())
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
    assert len(recheck_identities) == 1
    assert recheck_identities[0].endswith(":import-003")


@pytest.mark.parametrize(
    ("status", "client_count", "case_count", "expected_issue"),
    (
        ("no_client", 0, 0, "client_case_binding_no_client"),
        ("multiple_clients", 2, 0, "client_case_binding_multiple_clients"),
        ("case_not_unique", 1, 2, "client_case_binding_case_not_unique"),
    ),
)
def test_binding_review_preserves_real_candidate_classification_without_pii(
    monkeypatch, status, client_count, case_count, expected_issue
):
    repository = _Repository()
    repository.binding_resolution = ClientCaseBindingResolution(
        ClientCaseBindingStatus(status), client_count, case_count
    )
    captured = {}
    monkeypatch.setattr(
        intake,
        "_load_workbook",
        lambda _: _workbook(_valid_row("BIND-REVIEW")),
    )
    monkeypatch.setattr(
        intake,
        "record_invalid_beclass_row",
        lambda *args, **kwargs: captured.update(kwargs) or "beclass-review:binding",
    )
    service = _service(repository)
    preview = service.preview("ignored.xlsx")

    receipt = service.apply(
        "ignored.xlsx", "binding-key", preview.preview_fingerprint, "admin", "corr"
    )

    assert receipt.existing_conflict_count == 1
    assert captured["issue_codes"] == (expected_issue,)
    assert captured["source_payload"] == {
        "has_name": True,
        "has_phone": True,
        "has_query_no": True,
        "source_field_count": 15,
        "client_candidate_count": client_count,
        "case_candidate_count": case_count,
    }

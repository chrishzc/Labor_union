"""
File: test_client_beclass_workbook_import.py
Description: 驗證 Client BeClass temporary workbook 的 Preview、Apply、replay 與 review 邊界。
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from openpyxl import Workbook, load_workbook
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError

from api.routes import client_beclass_import as workbook_route
from api.schemas.client_beclass_import import ClientBeClassWorkbookPreviewView, ClientBeClassWorkbookReceiptView
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.terms_workflow import TermsWorkflowError

from infrastructure.mysql import hcm_beclass_reconciliation_adapter as reconciliation_adapter
from infrastructure.mysql.beclass_correction_repository import MySqlBeClassCorrectionRepository
from infrastructure.mysql.client_beclass_workbook_import_repository import ClientBeClassWorkbookImportRepository
from infrastructure.mysql.mysql_adapter import get_connection
from domains.case_import.client_beclass_binding import (
    ClientCaseBindingResolution,
    ClientCaseBindingStatus,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import import client_beclass_workbook_import as intake
from subsystems.case_import.beclass_correction_workflow import BeClassCorrectionWorkflow
from subsystems.case_import.hcm_beclass_reconciliation import reconcile_hcm_beclass_cooking


_DIGEST = "a" * 64
_SHEET = "b" * 64


def test_workbook_lock_timeout_explains_lock_wait_and_retains_typed_code(tmp_path, monkeypatch):
    uploaded = tmp_path / "lock-test.xlsx"
    uploaded.write_bytes(b"synthetic")

    async def persist(_):
        return uploaded

    async def execute(operation, path):
        return operation(path)

    def locked(_):
        raise intake.ClientBeClassWorkbookUnavailable("client_beclass_workbook_coordinator_lock_timeout")

    monkeypatch.setattr(workbook_route, "_persist_workbook", persist)
    monkeypatch.setattr(workbook_route, "run_in_threadpool", execute)
    with pytest.raises(HTTPException) as caught:
        # Both I/O boundaries are immediate fakes; exercise the error mapping
        # without opening the event loop's socket pair in the restricted runner.
        workbook_route._with_workbook(None, locked, "ok", "synthetic-lock-check").send(None)
    assert caught.value.status_code == 503
    error = caught.value.detail["error"]
    assert error["code"] == "client_beclass_workbook_coordinator_lock_timeout"
    assert "等待協調鎖 30 秒" in error["message"]
    assert error["retryable"] is True
    assert not uploaded.exists()


@pytest.mark.parametrize("category, expected_status", [
    (ErrorCategory.CONFLICT, 409), (ErrorCategory.DOMAIN_BLOCKED, 409),
    (ErrorCategory.VALIDATION, 422),
])
def test_workbook_preserves_terms_errors_and_removes_temporary_upload(tmp_path, monkeypatch, category, expected_status):
    uploaded = tmp_path / "workbook.xlsx"
    uploaded.write_bytes(b"test upload")

    async def persist(_):
        return uploaded

    def apply(*_, **__):
        raise TermsWorkflowError(TypedError(
            category, "terms_apply_mode_changed", "Terms changed after preview.",
            CorrelationId("inner-terms"),
        ))

    monkeypatch.setattr(workbook_route, "_persist_workbook", persist)
    app = FastAPI()
    app.include_router(workbook_route.router)
    app.dependency_overrides[workbook_route.require_admin] = lambda: AdminPrincipal(
        1, "test-admin", "Test Admin", "system_admin",
    )
    app.dependency_overrides[workbook_route.get_client_beclass_workbook_import_service] = (
        lambda: SimpleNamespace(apply=apply)
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/case-import/client-beclass/workbooks/apply",
            files={"workbook": ("workbook.xlsx", b"test upload")},
            data={"preview_fingerprint": "a" * 64},
            headers={"Idempotency-Key": "test-key", "X-Correlation-ID": "workbook-request"},
        )

    assert response.status_code == expected_status
    error = response.json()["detail"]["error"]
    assert error["category"] == category.value
    assert error["code"] == "terms_apply_mode_changed"
    assert error["correlation_id"] == "workbook-request"
    assert not uploaded.exists()


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

    def case_availability(self, name, phone, *, for_update, case_no=None, allow_partial_match=False):
        number = case_no or self.binding_resolution.case_no
        return intake.ClientBeClassCaseAvailability(
            (intake.ClientBeClassCaseCandidate(
                number, 7, name, intake.mask_client_beclass_phone(phone), None, None, None,
            ),),
            {},
        )

    def claim_workbook(self, key, fingerprint, correlation):
        return "created"

    def load_row_receipt(self, key):
        return self.rows.get(key)

    def claim_row(self, key, fingerprint, correlation):
        return "created"

    def create_bound_source_if_absent(self, payload, client_case, *, allow_additional_case=False):
        if payload["query_no"] == "EXISTING-1":
            return None
        self.created.append({**payload, "client_id": client_case["id"], "bound_case_no": client_case["case_no"]})
        return len(self.created)

    def require_matching_client_root(self, receipt):
        return None

    def bound_case_no_for_root(self, root_id):
        return "HCM-0007" if root_id is not None else None

    def bound_sources_for_query(self, query_no):
        return ({"root_id": 77, "case_no": "HCM-0007"},)

    def save_row_receipt(self, key, fingerprint, root_id, outcome, review_identity, actor):
        result_identity = f"admin_command_receipt:{len(self.rows) + 1}"
        self.rows[key] = {
            "request_fingerprint": fingerprint,
            "root_id": root_id,
            "outcome": outcome,
            "review_identity": review_identity,
            "accepted_result_identity": result_identity,
        }
        return result_identity

    def save_workbook_receipt(self, key, fingerprint, preview, actor, result):
        self.saved_workbook = result
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


def _service(repository, reconciliation=None):
    return intake.ClientBeClassWorkbookImportService(
        repository,
        reconciliation or _Reconciliation(),
        lambda: MySqlUnitOfWork(repository.connection),
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
    assert tuple(issue.as_dict() for issue in preview.row_issues) == (
        {
            "source_row": 3,
            "query_no": None,
            "fields": ["姓名", "查詢序號"],
            "issue_codes": [
                "client_field_missing:姓名",
                "client_field_missing:查詢序號",
            ],
        },
    )
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
    assert receipt.as_dict()["row_issues"] == [{"source_row": 3, "query_no": "BAD", "fields": ["姓名"], "issue_codes": ["client_field_missing:姓名"]}]
    replay = service.apply("ignored.xlsx", "client-test-key", preview.preview_fingerprint, "admin", "corr")
    assert replay.as_dict()["row_issues"] == receipt.as_dict()["row_issues"]
    assert repository.created[0]["query_no"] == "CASE-1"
    assert repository.binding_lock_modes == [False, False, True]
    assert reconciliation.calls == ["HCM-0007"]
    assert "CASE-1" not in reconciliation.calls
    assert repository.saved_workbook == receipt.as_dict()
    assert repository.locks == []


@pytest.mark.parametrize("care_fields, expected_note, invalid_birth", [
    ({}, None, False),
    ({"特殊照護時應注意事項": "Synthetic care note"}, "Synthetic care note", False),
    ({"特殊照護時應注意事項": "Synthetic care note", "特殊計費:胎數": "invalid"}, "Synthetic care note", True),
])
def test_optional_care_fields_do_not_block_source_or_other_registry_values(monkeypatch, care_fields, expected_note, invalid_birth):
    from api.schemas.client_registry import ClientRegistryOrderInformationView
    from domains.case_import.order_information import project_order_information

    repository = _Repository()
    service = _service(repository)
    row = {**_valid_row(), **care_fields}
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(row))
    preview = service.preview("ignored.xlsx")
    receipt = service.apply("ignored.xlsx", "partial-care", preview.preview_fingerprint, "admin", "partial-care")

    assert receipt.created_count == 1
    assert receipt.review_required_count == 0
    source = json.loads(repository.created[0]["survey_details"])
    assert all(source[key] == value for key, value in care_fields.items())
    projection = project_order_information(source)
    view = ClientRegistryOrderInformationView(status="ready", values=projection.values, field_issues=projection.issues)
    assert view.values.special_care_notes == expected_note
    assert view.values.dietary_habits is None
    assert (view.field_issues.get("multi_birth_count") == "invalid") is invalid_birth


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


@pytest.mark.parametrize("replay_kind", ["same_key", "new_key", "same_source"])
@pytest.mark.parametrize("manual_value", [False, None])
def test_reimport_preserves_manual_cooking_edit(monkeypatch, replay_kind, manual_value):
    repository = _Repository()

    class CookingReconciliation:
        requires_cooking = None
        version = 1

        def reconcile(self, case_no):
            return reconcile_hcm_beclass_cooking(self, case_no)

        def load_pair_facts(self, case_no):
            source = repository.created[0]
            assert source["bound_case_no"] == case_no
            return {
                "hcm_count": 1, "beclass_count": 1, "beclass_id": 1,
                "requires_cooking": self.requires_cooking, "survey_details": source["survey_details"],
            }

        def record_cooking_review(self, *_args):
            raise AssertionError("The survey has an explicit cooking answer")

        def apply_cooking_terms(self, _case_no, _source_id, requires_cooking):
            self.requires_cooking = requires_cooking
            self.version += 1

    reconciliation = CookingReconciliation()
    service = _service(repository, reconciliation)
    source_row = {**_valid_row(), "是否需要下廚：": "需要下廚"}
    workbook = _workbook(source_row)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: workbook)
    preview = service.preview("ignored.xlsx")
    first = service.apply("ignored.xlsx", "first", preview.preview_fingerprint, "admin", "corr")
    assert first.created_count == 1
    assert (reconciliation.requires_cooking, reconciliation.version) == (True, 2)

    reconciliation.requires_cooking = manual_value
    reconciliation.version += 1
    saved_source = dict(repository.created[0])
    saved_first_receipt = dict(repository.workbook_receipts["first"])
    key = "first" if replay_kind == "same_key" else "again"
    if replay_kind == "same_source":
        workbook = intake._Workbook("c" * 64, workbook.sheet_identity, workbook.rows)
        monkeypatch.setattr(repository, "source_state", lambda _payload: "exact")
    if replay_kind != "same_key":
        preview = service.preview("ignored.xlsx")
    replay = service.apply("ignored.xlsx", key, preview.preview_fingerprint, "admin", "corr")

    assert replay.replayed_workbook is (replay_kind == "same_key")
    assert (replay.created_count, replay.exact_replay_count, replay.existing_source_count) == (
        int(replay_kind == "same_key"), int(replay_kind == "new_key"), int(replay_kind == "same_source"),
    )
    assert reconciliation.requires_cooking is manual_value
    assert reconciliation.version == 3
    assert repository.created == [saved_source]
    assert repository.workbook_receipts["first"] == saved_first_receipt


@pytest.mark.parametrize("locked_after_acceptance", [False, True])
def test_same_workbook_replay_preserves_receipt_without_duplicate_event(
    monkeypatch, locked_after_acceptance,
):
    repository = _Repository()
    reconciliation = _Reconciliation()
    service = _service(repository, reconciliation)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    first = service.apply(
        "ignored.xlsx", "same-key", preview.preview_fingerprint, "admin", "corr"
    )
    if locked_after_acceptance:
        reconciliation.error = ValueError("service_data_locked")
    replay = service.apply(
        "ignored.xlsx", "same-key", preview.preview_fingerprint, "admin", "corr"
    )

    assert first.replayed_workbook is False
    assert replay.replayed_workbook is True
    assert replay.created_count == first.created_count == 1
    assert replay.row_issues == first.row_issues == ()
    assert reconciliation.calls == ["HCM-0007"]
    assert reconciliation.event_count == 1
    assert repository.connection.rollbacks == 0


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_reconciliation_failure_rolls_back_row_before_receipt(monkeypatch, error_type):
    repository = _Repository()
    service = _service(
        repository, _Reconciliation(error=error_type("downstream unavailable"))
    )
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx")

    with pytest.raises(error_type, match="downstream unavailable"):
        service.apply(
            "ignored.xlsx", "failure-key", preview.preview_fingerprint, "admin", "corr"
        )

    assert repository.rows == {}
    assert repository.saved_workbook is None
    assert repository.connection.rollbacks == 1


def test_automatic_row_lock_keeps_existing_source_and_imports_later_row(monkeypatch):
    repository = _Repository()
    reconciliation = _Reconciliation()
    service = _service(repository, reconciliation)
    locked = _valid_row("BC-LOCKED")
    ready = {**_valid_row("BC-READY"), "姓名": "另一位測試客戶"}
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(
        _valid_row("EXISTING-1"), locked, ready,
    ))

    def resolve(name, phone, *, for_update):
        case_no = "HCM-READY" if name == ready["姓名"] else "HCM-0007"
        return ClientCaseBindingResolution(ClientCaseBindingStatus.UNIQUE, 1, 1, 7, case_no)

    def reconcile(case_no):
        if case_no == "HCM-0007":
            raise TermsWorkflowError(TypedError(
                ErrorCategory.DOMAIN_BLOCKED, "service_data_locked",
                "The cooking requirement cannot be corrected.", CorrelationId("cooking"),
            ))

    monkeypatch.setattr(repository, "resolve_client_case_binding", resolve)
    monkeypatch.setattr(reconciliation, "reconcile", reconcile)
    reviews = []
    monkeypatch.setattr(intake, "record_invalid_beclass_row",
                        lambda *args, **kwargs: reviews.append(kwargs) or "review:locked")
    preview = service.preview("ignored.xlsx")
    receipt = service.apply("ignored.xlsx", "mixed-auto", preview.preview_fingerprint, "admin", "corr")

    assert receipt.source_row_count == 3
    assert receipt.created_count == 2
    assert receipt.existing_source_count == 1
    assert receipt.existing_conflict_count == 0
    assert receipt.row_issues == ()
    assert [(review["identifier"], review["issue_codes"]) for review in reviews] == [
        ("BC-LOCKED", ("service_data_locked",)),
    ]
    assert repository.created[0]["email"] == locked["Email"]
    assert tuple(repository.rows) == (
        f"client-beclass-workbook:{_DIGEST}:row:2",
        f"client-beclass-workbook:{_DIGEST}:row:3",
        f"client-beclass-workbook:{_DIGEST}:row:4",
    )
    assert repository.connection.rollbacks == 0
    assert repository.rows[f"client-beclass-workbook:{_DIGEST}:row:3"]["review_identity"] == "review:locked"


def test_existing_query_number_is_reported_as_existing_source_not_a_binding_conflict(monkeypatch):
    repository = _Repository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("EXISTING-1")))
    preview = service.preview("ignored.xlsx")

    receipt = service.apply("ignored.xlsx", "key", preview.preview_fingerprint, "admin", "corr")

    assert preview.existing_source_count == 1
    assert receipt.existing_source_count == 1
    assert repository.created == []


def test_existing_query_number_with_changed_payload_creates_review(monkeypatch):
    repository = _Repository()
    service = _service(repository)
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
    assert preview.row_issues[0].as_dict() == {
        "source_row": 2,
        "query_no": "CHANGED-1",
        "fields": ["查詢序號"],
        "issue_codes": ["client_beclass_source_payload_conflict"],
    }
    assert receipt.existing_conflict_count == 1
    assert receipt.existing_source_count == 0
    assert repository.created == []


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


class _ManualPairingRepository(_Repository):
    def __init__(self):
        super().__init__()
        self.binding_resolution = ClientCaseBindingResolution(
            ClientCaseBindingStatus.CASE_NOT_UNIQUE, 1, 3
        )
        self.claims = {}
        self.unavailable = set()
        self.other_client_cases = set()
        self.partial_match_cases = set()
        self.nonmatching_cases = set()

    def load_workbook_claim(self, key):
        return self.claims.get(key)

    def claim_workbook(self, key, fingerprint, correlation):
        return "created" if self.claims.setdefault(key, fingerprint) == fingerprint else "conflict"

    def case_availability(self, name, phone, *, for_update, case_no=None, allow_partial_match=False):
        if for_update:
            assert case_no is not None
        unavailable = self.unavailable | {row["bound_case_no"] for row in self.created}
        candidates = tuple(
            intake.ClientBeClassCaseCandidate(
                number, 8 if number in self.other_client_cases else 7, name,
                intake.mask_client_beclass_phone(phone), "新竹市",
                f"2026-08-0{index} 09:30:00", f"2026-09-0{index}",
                full_identity_match=number not in self.partial_match_cases,
            )
            for index, number in enumerate(("HCM-A", "HCM-B", "HCM-C"), start=1)
            if number not in unavailable | self.nonmatching_cases and (case_no is None or case_no == number)
        )
        return intake.ClientBeClassCaseAvailability(candidates, {})

    def source_state(self, payload):
        if any(row["query_no"] == payload["query_no"] for row in self.created):
            return "exact"
        return super().source_state(payload)

    def bound_case_no_for_root(self, root_id):
        return self.created[root_id - 1]["bound_case_no"] if root_id else None


@pytest.mark.parametrize("matched_field", ["name", "phone", None])
def test_workbook_single_identity_match_requires_manual_pairing(monkeypatch, matched_field):
    row = _valid_row()
    case = {
        "case_no": "HCM-0007", "client_id": 7, "hcm_client_id": 8,
        "name": row["姓名"] if matched_field == "name" else "另一位測試客戶",
        "phone": row["行動電話"] if matched_field == "phone" else "0999999999",
        "city": None, "created_at": None, "start_date": None,
    }

    class CandidateCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, sql, params):
            if "FROM clients c STRAIGHT_JOIN orders" in sql:
                name_hit = case["name"] == params[0]
                phone_hit = case["phone"] == params[1]
                eligible = (name_hit or phone_hit) if " OR " in sql else (name_hit and phone_hit)
                selected = len(params) == 2 or params[2] == case["case_no"]
                self.rows = (case,) if eligible and selected else ()
            elif "FROM beclass_records" in sql or "SELECT client.id FROM clients" in sql:
                self.rows = ()
            else:
                pytest.fail(f"Unexpected case lookup query: {sql}")

        def fetchall(self):
            return self.rows

    repository = _ManualPairingRepository()
    lookup = ClientBeClassWorkbookImportRepository(SimpleNamespace(cursor=CandidateCursor))
    monkeypatch.setattr(repository, "resolve_client_case_binding", lookup.resolve_client_case_binding)
    monkeypatch.setattr(repository, "case_availability", lookup.case_availability)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(row))
    service = _service(repository)

    automatic = service.preview("ignored.xlsx")
    assert automatic.create_count == 0
    assert automatic.existing_conflict_count == 1
    preview = service.preview("ignored.xlsx", manual_pairing=True)
    assert repository.created == []
    if matched_field is None:
        assert preview.manual_rows == ()
        assert preview.existing_conflict_count == 1
        return

    assert preview.create_count == 0
    assert [candidate.case_no for candidate in preview.candidates] == ["HCM-0007"]
    assert [item.case_nos for item in preview.manual_rows] == [("HCM-0007",)]
    receipt = service.apply(
        "ignored.xlsx", "confirmed", preview.preview_fingerprint, "admin", "corr",
        manual_pairings=((2, "HCM-0007"),),
    )
    assert receipt.created_count == 1
    assert repository.created[0]["bound_case_no"] == "HCM-0007"
    assert repository.created[0]["phone"] == row["行動電話"]
    assert repository.created[0]["name"] == row["姓名"]


@pytest.mark.parametrize("target_taken", [False, True])
def test_same_client_workbook_confirmed_case_pairings_and_receipt(tmp_path, monkeypatch, target_taken):
    repository = _ManualPairingRepository()
    service = _service(repository)
    upload = tmp_path / "synthetic.xlsx"
    file = Workbook()
    file.active.append(list(_valid_row()))
    for query_no in ("BC-FIRST", "BC-SECOND"):
        file.active.append(list(_valid_row(query_no).values()))
    file.save(upload)
    file.close()

    async def persist(_):
        temporary = tmp_path / "request.xlsx"
        temporary.write_bytes(upload.read_bytes())
        return temporary

    async def execute(operation, path):
        return operation(path)

    monkeypatch.setattr(workbook_route, "_persist_workbook", persist)
    monkeypatch.setattr(workbook_route, "run_in_threadpool", execute)
    principal = AdminPrincipal(1, "test-admin", "Test Admin", "system_admin")

    def route_result(coroutine):
        with pytest.raises(StopIteration) as completed:
            coroutine.send(None)
        return completed.value.value.data

    preview = ClientBeClassWorkbookPreviewView.model_validate(route_result(
        workbook_route.preview_client_beclass_workbook(None, "corr", principal, service)
    ))
    assert repository.created == [] and repository.connection.commits == 0
    assert [row.case_nos for row in preview.manual_rows] == [["HCM-A", "HCM-B", "HCM-C"]] * 2
    assert len(preview.candidates) == 3
    assert preview.manual_rows[0].masked_phone == "09•••••678"
    selections = ((2, "HCM-B"), (3, "HCM-A"))

    with pytest.raises(ValueError, match="pairings_required"):
        service.apply(str(upload), "missing", preview.preview_fingerprint, "admin", "corr", manual_pairings=())
    with pytest.raises(ValueError, match="pairings_not_unique"):
        service.apply(str(upload), "duplicate", preview.preview_fingerprint, "admin", "corr",
                      manual_pairings=((2, "HCM-A"), (3, "HCM-A")))
    assert repository.created == []
    if target_taken:
        repository.unavailable.add("HCM-B")
    form = json.dumps([{"source_row": row, "case_no": case_no} for row, case_no in selections])

    def apply(form_data=form):
        return ClientBeClassWorkbookReceiptView.model_validate(route_result(
            workbook_route.apply_client_beclass_workbook(
                None, preview.preview_fingerprint, "pairings-key", "corr", principal, service, form_data
            )
        ))

    receipt = apply()
    expected = [("BC-SECOND", "HCM-A")] if target_taken else [("BC-FIRST", "HCM-B"), ("BC-SECOND", "HCM-A")]
    assert [(row["query_no"], row["bound_case_no"]) for row in repository.created] == expected
    assert [(binding.query_no, binding.case_no) for binding in receipt.manual_bindings] == expected
    assert receipt.created_count == len(expected)
    assert receipt.existing_conflict_count == int(target_taken)
    if target_taken:
        assert receipt.row_issues[0].issue_codes == ["case_import_candidate_stale"]
        fresh = service.preview(str(upload), manual_pairing=True)
        assert [(row.source_row, row.case_nos) for row in fresh.manual_rows] == [(2, ("HCM-C",))]
        recovered = service.apply(str(upload), "new-key", fresh.preview_fingerprint, "admin", "corr",
                                  manual_pairings=((2, "HCM-C"),))
        assert recovered.manual_bindings[0].case_no == "HCM-C"
    replay = apply()
    assert replay.replayed_workbook and replay.manual_bindings == receipt.manual_bindings
    with pytest.raises(HTTPException) as conflict:
        apply(form.replace("HCM-B", "HCM-C"))
    assert conflict.value.status_code == 409


@pytest.mark.parametrize(
    ("has_hcm", "origin", "occupant_client", "issue_code"),
    [
        (True, "imported", 7, "client_beclass_case_already_bound"),
        (True, "imported", 8, "client_beclass_case_already_bound"),
        (True, "admin_manual", None, "client_beclass_case_manually_registered"),
        (False, None, None, "client_beclass_hcm_case_missing"),
    ],
)
def test_workbook_reports_current_case_unavailability(
    monkeypatch, has_hcm, origin, occupant_client, issue_code,
):
    case_a, case_b = "HCM-0007", "HCM-0008"

    class CandidateCursor:
        blocked = False
        rows = ()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, sql, params):
            if "FROM clients c STRAIGHT_JOIN orders" in sql:
                cases = (params[2],) if len(params) == 3 else case_nos
                self.rows = tuple(
                    {
                        "case_no": case, "client_id": 7, "name": params[0],
                        "phone": params[1], "city": None, "created_at": None,
                        "start_date": None, "hcm_client_id": (
                            None if self.blocked and case == case_a and not has_hcm else 7
                        ),
                    }
                    for case in cases if case in case_nos
                    and (not self.blocked or has_hcm or case != case_a or "LEFT JOIN clients hcm" in sql)
                )
            elif "FROM beclass_records" in sql:
                self.rows = (
                    ({"bound_case_no": case_a, "record_origin": origin},)
                    if self.blocked and origin and case_a in params
                    and ("client_id=%s" not in sql or occupant_client in (None, params[0]))
                    else ()
                )
            else:
                pytest.fail(f"Unexpected case availability query: {sql}")

        def fetchall(self):
            return self.rows

    case_nos = (case_a,)
    cursor = CandidateCursor()
    repository = _ManualPairingRepository()
    lookup = ClientBeClassWorkbookImportRepository(SimpleNamespace(cursor=lambda: cursor))
    monkeypatch.setattr(repository, "case_availability", lookup.case_availability)
    service = _service(repository)
    workbook = _workbook(_valid_row("BC-BLOCKED"))
    monkeypatch.setattr(intake, "_load_workbook", lambda _: workbook)
    repository.binding_resolution = ClientCaseBindingResolution(
        ClientCaseBindingStatus.UNIQUE, 1, 1, 7, case_a,
    )
    assert service.preview("ignored.xlsx").create_count == 1
    cursor.blocked = True
    preview = service.preview("ignored.xlsx")
    assert preview.existing_conflict_count == 1
    assert preview.row_issues[0].issue_codes == (issue_code,)

    cursor.blocked = False
    automatic_preview = service.preview("ignored.xlsx")
    with monkeypatch.context() as patch:
        patch.setattr(service, "_claim_workbook", lambda *_: setattr(cursor, "blocked", True))
        automatic = service.apply(
            "ignored.xlsx", "automatic-key", automatic_preview.preview_fingerprint, "admin", "corr",
        )
    assert automatic.existing_conflict_count == 1
    assert automatic.row_issues[0].issue_codes == (issue_code,)
    assert repository.created == []

    case_nos = (case_a, case_b)
    repository.binding_resolution = ClientCaseBindingResolution(
        ClientCaseBindingStatus.CASE_NOT_UNIQUE, 1, 2,
    )
    cursor.blocked = False
    pending = service.preview("ignored.xlsx", manual_pairing=True)
    assert pending.manual_rows[0].case_nos == (case_a, case_b)
    cursor.blocked = True
    receipt = service.apply("ignored.xlsx", "blocked-key", pending.preview_fingerprint, "admin", "corr",
                            manual_pairings=((2, case_a), (2, case_b)))
    assert receipt.existing_conflict_count == 1
    assert receipt.row_issues[0].issue_codes == (issue_code,)
    assert repository.created == []


def test_confirmed_pairings_resume_after_rows_commit_before_workbook_receipt(monkeypatch):
    repository = _ManualPairingRepository()
    service = _service(repository)
    workbook = _workbook(_valid_row("BC-FIRST"), _valid_row("BC-SECOND"))
    monkeypatch.setattr(intake, "_load_workbook", lambda _: workbook)
    preview = service.preview("ignored.xlsx", manual_pairing=True)
    selections = ((2, "HCM-B"), (3, "HCM-A"))

    def apply():
        return service.apply("ignored.xlsx", "resume-key", preview.preview_fingerprint, "admin", "corr",
                             manual_pairings=selections)

    def fail_receipt(*_):
        raise RuntimeError("test: workbook receipt unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(repository, "save_workbook_receipt", fail_receipt)
        with pytest.raises(RuntimeError, match="workbook receipt unavailable"):
            apply()

    assert len(repository.created) == 2
    resumed = apply()
    assert len(repository.created) == resumed.created_count == 2
    assert [(item.source_row, item.case_no) for item in resumed.manual_bindings] == list(selections)


@pytest.mark.parametrize("second_case", [
    "same_client", "matching_other_id", "partial_match_other_id", "occupied", "different_identity",
])
def test_one_questionnaire_applies_to_two_cases_atomically(monkeypatch, second_case):
    repository = _ManualPairingRepository()
    service = _service(repository)
    workbook = _workbook(_valid_row("BC-SHARED"))
    monkeypatch.setattr(intake, "_load_workbook", lambda _: workbook)
    selections = ((2, "HCM-A"), (2, "HCM-B"))
    if second_case in {"matching_other_id", "partial_match_other_id"}:
        repository.other_client_cases.add("HCM-B")
    if second_case == "partial_match_other_id":
        repository.partial_match_cases.add("HCM-B")
    preview = service.preview("ignored.xlsx", manual_pairing=True)
    if second_case == "occupied":
        repository.unavailable.add("HCM-B")
    if second_case == "different_identity":
        repository.nonmatching_cases.add("HCM-B")

    receipt = service.apply("ignored.xlsx", "shared-key", preview.preview_fingerprint, "admin", "corr",
                            manual_pairings=selections)
    if second_case in {"occupied", "different_identity", "partial_match_other_id"}:
        assert repository.created == []
        assert receipt.existing_conflict_count == 1
        assert receipt.manual_bindings == ()
        return

    assert receipt.created_count == receipt.source_row_count == 1
    assert [(item.source_row, item.case_no) for item in receipt.manual_bindings] == list(selections)
    replay = service.apply("ignored.xlsx", "shared-key", preview.preview_fingerprint, "admin", "corr",
                           manual_pairings=tuple(reversed(selections)))
    assert replay.replayed_workbook and replay.manual_bindings == receipt.manual_bindings
    assert [(row["query_no"], row["bound_case_no"]) for row in repository.created] == [
        ("BC-SHARED", "HCM-A"), ("BC-SHARED", "HCM-B"),
    ]
    assert [row["client_id"] for row in repository.created] == [7, 8 if second_case == "matching_other_id" else 7]


def test_locked_cooking_preserves_all_confirmed_bindings(monkeypatch):
    repository = _ManualPairingRepository()
    reconciliation = _Reconciliation()
    service = _service(repository, reconciliation)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(
        _valid_row("BC-LOCKED"), _valid_row("BC-READY"),
    ))

    def reconcile(case_no):
        if case_no == "HCM-B":
            raise TermsWorkflowError(TypedError(
                ErrorCategory.DOMAIN_BLOCKED, "service_data_locked",
                "The cooking requirement cannot be corrected.", CorrelationId("cooking"),
            ))

    monkeypatch.setattr(reconciliation, "reconcile", reconcile)
    reviews = []
    monkeypatch.setattr(intake, "record_invalid_beclass_row",
                        lambda *args, **kwargs: reviews.append(kwargs) or "review:locked")
    app = FastAPI()
    app.include_router(workbook_route.router)
    app.dependency_overrides[workbook_route.require_admin] = lambda: AdminPrincipal(
        1, "test-admin", "Test Admin", "system_admin",
    )
    app.dependency_overrides[workbook_route.get_client_beclass_workbook_import_service] = lambda: service
    selections = ((2, "HCM-A"), (2, "HCM-B"), (3, "HCM-C"))
    pairings = [{"source_row": row, "case_no": case} for row, case in selections]
    with TestClient(app) as client:
        files = {"workbook": ("mixed.xlsx", b"synthetic workbook rows")}
        preview = client.post("/api/v1/case-import/client-beclass/workbooks/preview", files=files)
        assert preview.status_code == 200
        response = client.post(
            "/api/v1/case-import/client-beclass/workbooks/apply",
            files=files,
            data={"preview_fingerprint": preview.json()["data"]["preview_fingerprint"],
                  "manual_pairings": json.dumps(pairings)},
            headers={"Idempotency-Key": "mixed-rows", "X-Correlation-ID": "mixed-rows"},
        )

    assert response.status_code == 200, response.json()
    result = ClientBeClassWorkbookReceiptView.model_validate(response.json()["data"])
    assert result.source_row_count == 2
    assert result.created_count == 2
    assert result.existing_conflict_count == 0
    assert [(item.source_row, item.case_no) for item in result.manual_bindings] == list(selections)
    assert result.row_issues == []
    assert [item["bound_case_no"] for item in repository.created] == ["HCM-A", "HCM-B", "HCM-C"]
    assert len(repository.rows) == 3
    assert {repository.bound_case_no_for_root(row["root_id"]): row["review_identity"]
            for row in repository.rows.values()} == {"HCM-A": None, "HCM-B": "review:locked", "HCM-C": None}
    assert len(reviews) == 1
    assert reviews[0]["issue_codes"] == ("service_data_locked",)


def test_multi_case_questionnaire_round_trip_in_disposable_mysql(tmp_path):
    database = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE", "")
    if (
        not database.startswith("lu_test_")
        or os.getenv("DB_DATABASE") != database
        or os.getenv("DB_HOST") not in {"localhost", "127.0.0.1"}
        or os.getenv("APP_ENV") != "development"
    ):
        pytest.skip("requires an explicitly configured local disposable MySQL database")

    scenario = uuid4().hex[:12]
    case_a, case_b = (f"MC-{scenario}-{suffix}" for suffix in ("A", "B"))
    query_no = f"BC-{scenario}"
    source_row = _valid_row(query_no)
    source_row["姓名"] = f"測試客戶-{scenario}"
    source_row["管理者註記事項"] = "來源註記"
    source_row["市話"] = "0212345678"
    source_row["是否需要下廚："] = "需要下廚"
    file = Workbook()
    file.active.append(list(source_row))
    file.active.append(list(source_row.values()))
    upload = str(tmp_path / "multi-case.xlsx")
    file.save(upload)
    file.close()

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients (case_no,name,phone,email) VALUES (%s,%s,%s,%s)",
                (case_a, source_row["姓名"], source_row["行動電話"], source_row["Email"]),
            )
            client_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO clients (case_no,name,phone) VALUES (%s,%s,%s)",
                (case_b, source_row["姓名"], source_row["行動電話"]),
            )
            second_client_id = int(cursor.lastrowid)
            cursor.executemany(
                "INSERT INTO orders (case_no,client_id,status,requires_cooking) VALUES (%s,%s,'洽談中',%s)",
                [(case_a, client_id, None), (case_b, second_client_id, False)],
            )
            cursor.execute(
                "SELECT case_no,lifecycle_version FROM orders WHERE case_no IN (%s,%s) ORDER BY case_no",
                (case_a, case_b),
            )
            initial_order_versions = tuple(row["lifecycle_version"] for row in cursor.fetchall())
        connection.commit()

        repository = ClientBeClassWorkbookImportRepository(connection)
        service = intake.ClientBeClassWorkbookImportService(
            repository,
            reconciliation_adapter.MySqlHcmBeClassReconciliationAdapter(connection),
            lambda: MySqlUnitOfWork(connection),
        )
        initial = service.preview(upload, manual_pairing=True)
        assert initial.manual_rows[0].case_nos == (case_a, case_b)
        selected = ((2, case_a), (2, case_b))

        def apply():
            return service.apply(upload, scenario, initial.preview_fingerprint, "test", scenario,
                                 manual_pairings=selected)

        receipt = apply()
        assert receipt.created_count == 1
        assert [(item.source_row, item.case_no) for item in receipt.manual_bindings] == list(selected)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT requires_cooking,lifecycle_version FROM orders WHERE case_no IN (%s,%s) ORDER BY case_no",
                (case_a, case_b),
            )
            assert tuple((row["requires_cooking"], row["lifecycle_version"]) for row in cursor.fetchall()) == (
                (True, initial_order_versions[0] + 1), (False, initial_order_versions[1]),
            )

        correction_key = f"{scenario}-correction"
        corrections = BeClassCorrectionWorkflow(
            MySqlBeClassCorrectionRepository(connection), lambda: MySqlUnitOfWork(connection),
        )
        changes = {"admin_notes": "承辦補正", "tel": None}
        expected = ExpectedVersion(0)
        correction = corrections.preview(case_a, changes, expected)
        assert correction.before == {"admin_notes": "來源註記", "tel": "0212345678"}
        corrected = corrections.apply(
            case_a, changes, expected, correction.preview_fingerprint, IdempotencyKey(correction_key),
            ActorContext("test"), "驗證既有補正", CorrelationId(scenario),
        )
        assert corrected.resulting_version == 1
        assert {field: corrected.readback.effective[field] for field in changes} == changes

        with connection.cursor() as cursor:
            cursor.executemany(
                "UPDATE orders SET requires_cooking=%s,lifecycle_version=lifecycle_version+1 WHERE case_no=%s",
                [(False, case_a), (None, case_b)],
            )
            cursor.execute("UPDATE clients SET email=NULL,city=%s WHERE id=%s", ("臺北市", client_id))
            cursor.execute("UPDATE clients SET name=%s WHERE id=%s", (f"測試改名-{scenario}", second_client_id))
        connection.commit()

        stored = repository.bound_sources_for_query(query_no)
        assert [item["case_no"] for item in stored] == [case_a, case_b]
        roots = tuple(item["root_id"] for item in stored)
        assert roots[0] != roots[1]

        def owner_snapshot():
            with connection.cursor() as cursor:
                snapshots = []
                for query, params in (
                    ("SELECT * FROM clients WHERE id IN (%s,%s) ORDER BY id", (client_id, second_client_id)),
                    ("SELECT * FROM orders WHERE case_no IN (%s,%s) ORDER BY case_no", (case_a, case_b)),
                    ("SELECT * FROM beclass_records WHERE bound_case_no IN (%s,%s) ORDER BY id", (case_a, case_b)),
                    ("SELECT * FROM beclass_record_correction_states WHERE beclass_record_id IN (%s,%s)", roots),
                    ("SELECT * FROM beclass_record_correction_events WHERE beclass_record_id IN (%s,%s) ORDER BY id", roots),
                    ("SELECT * FROM admin_command_receipts WHERE idempotency_key IN (%s,%s) ORDER BY id",
                     (scenario, correction_key)),
                ):
                    cursor.execute(query, params)
                    snapshots.append(tuple(cursor.fetchall()))
            return tuple(snapshots), tuple(corrections.query(case_no) for case_no in (case_a, case_b))

        before = owner_snapshot()
        assert apply().manual_bindings == receipt.manual_bindings
        assert owner_snapshot() == before

        repeated_preview = service.preview(upload, manual_pairing=True)
        assert repeated_preview.existing_source_count == 1
        repeated = service.apply(upload, f"{scenario}-new", repeated_preview.preview_fingerprint,
                                 "test", scenario, manual_pairings=())
        assert repeated.existing_source_count == 1
        assert owner_snapshot() == before

        file = load_workbook(upload)
        file.properties.title = "同來源另存活頁簿"
        resaved = str(tmp_path / "resaved.xlsx")
        file.save(resaved)
        resaved_preview = service.preview(resaved)
        assert resaved_preview.source_content_digest != initial.source_content_digest
        resaved_receipt = service.apply(
            resaved, f"{scenario}-resaved", resaved_preview.preview_fingerprint, "test", scenario,
        )
        assert resaved_receipt.existing_source_count == 1
        assert owner_snapshot() == before

        file.active["A2"] = f"new-{query_no}"
        duplicate_case = str(tmp_path / "duplicate-case.xlsx")
        file.save(duplicate_case)
        file.close()
        occupied_preview = service.preview(duplicate_case)
        assert occupied_preview.existing_conflict_count == 1
        occupied = service.apply(
            duplicate_case, f"{scenario}-duplicate", occupied_preview.preview_fingerprint, "test", scenario,
        )
        assert occupied.existing_conflict_count == 1
        assert occupied.row_issues[0].issue_codes == ("client_beclass_case_already_bound",)
        assert owner_snapshot() == before

        with connection.cursor() as cursor, pytest.raises(IntegrityError) as duplicate:
            cursor.execute(
                "INSERT INTO beclass_records (query_no,client_id,bound_case_no) VALUES (%s,%s,%s)",
                (query_no, client_id, case_a),
            )
        assert duplicate.value.args[0] == 1062
    finally:
        connection.close()


@pytest.mark.parametrize("bank, account, expected_bank, expected_account, warning_fields", [
    ("中文0041234", "00123456789", "0041234", "00123456789", ()),
    ("銀行 ００４／分行 １-２３４", "001234", "0041234", "001234", ()),
    ("銀行004，分行1234", "中文001234", "0041234", None, ("銀行帳號",)),
    ("銀行", "帳號", None, None, ("補助款退款:銀行代號+分行代號", "銀行帳號")),
    ("銀行004／分行123", "001234", None, "001234", ("補助款退款:銀行代號+分行代號",)),
    ("銀行004／分行12345", "001234", None, "001234", ("補助款退款:銀行代號+分行代號",)),
    ("００４-１２３４", "００１-２３４", "0041234", "001234", ()),
    ("0041234", "", "0041234", None, ()),
    ("", "001234", None, "001234", ()),
    ("", "", None, None, ()),
    (" - - ", "001234", None, "001234", ()),
])
def test_repairable_bank_fields_import_independently_and_keep_created_receipt(
    monkeypatch, bank, account, expected_bank, expected_account, warning_fields,
):
    class WarningRepository(_Repository):
        def save_row_receipt(self, key, fingerprint, root_id, outcome, review_identity, actor):
            result = super().save_row_receipt(key, fingerprint, root_id, outcome, review_identity, actor)
            self.rows[key]["review_identity"] = review_identity
            return result

    repository = WarningRepository()
    row = {**_valid_row(), "補助款退款:銀行代號+分行代號": bank, "銀行帳號": account}
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(row))
    reviews = []
    monkeypatch.setattr(intake, "record_invalid_beclass_row", lambda *args, **kwargs: reviews.append(kwargs) or "review:warning")
    service = _service(repository)
    preview = service.preview("ignored.xlsx")
    assert (preview.create_count, preview.review_required_count, preview.row_issues) == (1, 0, ())
    receipt = service.apply("ignored.xlsx", "repairable-bank", preview.preview_fingerprint, "admin", "corr")
    assert (receipt.created_count, receipt.review_required_count, receipt.row_issues) == (1, 0, ())
    assert repository.created[0]["refund_bank_code"] == expected_bank
    assert repository.created[0]["refund_account_no"] == expected_account
    saved = next(iter(repository.rows.values()))
    assert saved["outcome"] == "created"
    assert saved["root_id"] == 1
    assert saved["review_identity"] == ("review:warning" if warning_fields else None)
    if warning_fields:
        assert reviews[0]["identifier"] == "CASE-1"
        assert set(reviews[0]["issue_codes"]) == {"client_field_invalid:" + field for field in warning_fields}
        assert "refund_account_no" not in reviews[0]["source_payload"]
        assert "refund_bank_code" not in reviews[0]["source_payload"]
    replay = service.apply("ignored.xlsx", "repairable-bank", preview.preview_fingerprint, "admin", "corr")
    assert replay.replayed_workbook
    assert len(repository.created) == 1


def test_repairable_email_city_do_not_bypass_identity_or_source_conflicts(monkeypatch):
    repository = _Repository()
    row = {**_valid_row("CHANGED-1"), "Email": "invalid", "縣市": "unknown", "銀行帳號": "中文00123"}
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(row))
    service = _service(repository)
    preview = service.preview("ignored.xlsx")
    assert (preview.create_count, preview.existing_conflict_count) == (0, 1)
    assert preview.row_issues[0].issue_codes == ("client_beclass_source_payload_conflict",)
    missing_identity = {**row, "查詢序號": "", "姓名": "", "行動電話": ""}
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(missing_identity))
    preview = service.preview("ignored.xlsx")
    assert preview.review_required_count == 1
    assert set(preview.row_issues[0].fields) == {"查詢序號", "姓名", "行動電話"}
    assert not repository.created


@pytest.mark.parametrize("all_discarded", [False, True])
def test_manual_duplicate_can_be_discarded_without_blocking_other_rows(monkeypatch, all_discarded):
    repository = _ManualPairingRepository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("KEEP"), _valid_row("DROP")))
    preview = service.preview("ignored.xlsx", manual_pairing=True)
    selections = () if all_discarded else ((2, "HCM-A"),)
    discarded = (2, 3) if all_discarded else (3,)
    receipt = service.apply("ignored.xlsx", "discard", preview.preview_fingerprint, "admin", "corr",
                            manual_pairings=selections, discarded_rows=discarded)
    assert receipt.created_count == (0 if all_discarded else 1)
    assert receipt.review_required_count == len(discarded)
    assert all(row["query_no"] != "DROP" for row in repository.created)
    assert [(issue.source_row, issue.query_no, issue.issue_codes) for issue in receipt.row_issues] == [
        (row, "KEEP" if row == 2 else "DROP", ("client_beclass_row_discarded",)) for row in discarded
    ]
    replay = service.apply("ignored.xlsx", "discard", preview.preview_fingerprint, "admin", "corr",
                           manual_pairings=selections, discarded_rows=discarded)
    assert replay.replayed_workbook
    with pytest.raises(intake.ClientBeClassWorkbookConflict):
        service.apply("ignored.xlsx", "discard", preview.preview_fingerprint, "admin", "corr",
                      manual_pairings=selections, discarded_rows=())


def test_discard_cannot_overlap_pairing_or_hide_an_unresolved_row(monkeypatch):
    repository = _ManualPairingRepository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row("KEEP"), _valid_row("DROP")))
    preview = service.preview("ignored.xlsx", manual_pairing=True)
    with pytest.raises(ValueError, match="discarded_rows_overlap"):
        service.apply("ignored.xlsx", "overlap", preview.preview_fingerprint, "admin", "corr",
                      manual_pairings=((2, "HCM-A"),), discarded_rows=(2,))
    with pytest.raises(ValueError, match="manual_pairings_required"):
        service.apply("ignored.xlsx", "unresolved", preview.preview_fingerprint, "admin", "corr",
                      manual_pairings=(), discarded_rows=(3,))
    assert repository.created == []


def test_discard_rejects_automatic_row_even_with_a_matching_preview(monkeypatch):
    class AutomaticRowRepository(_Repository):
        def load_workbook_claim(self, key):
            return None

    repository = AutomaticRowRepository()
    service = _service(repository)
    monkeypatch.setattr(intake, "_load_workbook", lambda _: _workbook(_valid_row()))
    preview = service.preview("ignored.xlsx", manual_pairing=True)
    with pytest.raises(ValueError, match="discarded_rows_not_manual"):
        service.apply("ignored.xlsx", "auto-discard", preview.preview_fingerprint, "admin", "corr",
                      manual_pairings=(), discarded_rows=(2,))
    assert repository.created == []

"""
File: test_client_beclass_workbook_import.py
Description: 驗證 Client BeClass temporary workbook 的 Preview、Apply、replay 與 review 邊界。
"""

from __future__ import annotations

import json
import os
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from openpyxl import Workbook
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError

from api.routes import client_beclass_import as workbook_route
from api.schemas.client_beclass_import import ClientBeClassWorkbookPreviewView, ClientBeClassWorkbookReceiptView
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.terms_workflow import TermsWorkflowError

from domains.orders.terms import OrderCookingRequirementFacts, OrderTerms, ServiceTimeTerms
from infrastructure.mysql import hcm_beclass_reconciliation_adapter as reconciliation_adapter
from infrastructure.mysql.beclass_correction_repository import MySqlBeClassCorrectionRepository
from infrastructure.mysql.client_beclass_workbook_import_repository import ClientBeClassWorkbookImportRepository
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import ExpectedVersion
from shared_kernel.money import MoneyNTD
from domains.case_import.client_beclass_binding import (
    ClientCaseBindingResolution,
    ClientCaseBindingStatus,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.case_import import client_beclass_workbook_import as intake


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


@pytest.mark.parametrize("versions", [(None, None), (0, 0), (4, 7), (None, 7)])
@pytest.mark.parametrize("requires_formal_apply", [False, True])
def test_cooking_reconciliation_preserves_preview_contract(monkeypatch, versions, requires_formal_apply):
    terms = OrderTerms(
        date(2026, 9, 10), 5, 8, MoneyNTD(0),
        ServiceTimeTerms(None, None, None), False,
    )
    connection = object()
    repository = SimpleNamespace(
        load_for_preview=lambda case_no: SimpleNamespace(order=SimpleNamespace(terms=terms)),
        load_cooking_requirement=lambda case_no: OrderCookingRequirementFacts(case_no, 2, False, False),
    )
    requests = []

    class Workflow:
        def __init__(self, selected_repository, uow_factory, clock):
            assert selected_repository is repository

        def preview(self, case_no, proposed_terms):
            assert case_no == "CASE-7"
            assert proposed_terms.requires_cooking is True
            return SimpleNamespace(
                after=proposed_terms, order_version=2, scheduling_version=0,
                client_finance_version=versions[0], payroll_version=versions[1],
                fingerprint="preview",
                requires_formal_apply=requires_formal_apply,
            )

        def apply_in_current_uow(self, request):
            requests.append(request)

    monkeypatch.setattr(
        reconciliation_adapter, "MySqlOrderTermsRepository", lambda selected_connection: repository
    )
    monkeypatch.setattr(reconciliation_adapter, "OrderTermsWorkflow", Workflow)

    reconciliation_adapter.MySqlHcmBeClassReconciliationAdapter(connection).apply_cooking_terms(
        "CASE-7", 7, True
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.expected_order_version == ExpectedVersion(2)
    assert request.expected_scheduling_version == ExpectedVersion(0)
    for actual, version in zip(
        (request.expected_client_finance_version, request.expected_payroll_version), versions
    ):
        assert actual == (None if version is None else ExpectedVersion(version))
    assert request.proposed_terms.requires_cooking is True
    assert request.requires_formal_apply is requires_formal_apply


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

    def load_workbook_claim(self, key):
        return self.claims.get(key)

    def claim_workbook(self, key, fingerprint, correlation):
        return "created" if self.claims.setdefault(key, fingerprint) == fingerprint else "conflict"

    def available_case_candidates(self, name, phone, *, for_update, case_no=None):
        if for_update:
            assert case_no is not None
        unavailable = self.unavailable | {row["bound_case_no"] for row in self.created}
        return tuple(
            intake.ClientBeClassCaseCandidate(
                number, 8 if number in self.other_client_cases else 7, name,
                intake.mask_client_beclass_phone(phone), "新竹市",
                f"2026-08-0{index} 09:30:00", f"2026-09-0{index}",
            )
            for index, number in enumerate(("HCM-A", "HCM-B", "HCM-C"), start=1)
            if number not in unavailable and (case_no is None or case_no == number)
        )

    def source_state(self, payload):
        if any(row["query_no"] == payload["query_no"] for row in self.created):
            return "exact"
        return super().source_state(payload)

    def bound_case_no_for_root(self, root_id):
        return self.created[root_id - 1]["bound_case_no"] if root_id else None


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


@pytest.mark.parametrize("second_case", ["same_client", "occupied", "other_client"])
def test_one_questionnaire_applies_to_two_cases_atomically(monkeypatch, second_case):
    repository = _ManualPairingRepository()
    service = _service(repository)
    workbook = _workbook(_valid_row("BC-SHARED"))
    monkeypatch.setattr(intake, "_load_workbook", lambda _: workbook)
    selections = ((2, "HCM-A"), (2, "HCM-B"))
    if second_case == "other_client":
        repository.other_client_cases.add("HCM-B")
    preview = service.preview("ignored.xlsx", manual_pairing=True)
    if second_case == "occupied":
        repository.unavailable.add("HCM-B")

    receipt = service.apply("ignored.xlsx", "shared-key", preview.preview_fingerprint, "admin", "corr",
                            manual_pairings=selections)
    if second_case != "same_client":
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
                "INSERT INTO clients (case_no,name,phone) VALUES (%s,%s,%s)",
                (case_a, source_row["姓名"], source_row["行動電話"]),
            )
            client_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO clients (case_no,name) VALUES (%s,%s)", (case_b, "HCM 建檔"))
            cursor.executemany(
                "INSERT INTO orders (case_no,client_id,status) VALUES (%s,%s,'洽談中')",
                [(case_a, client_id), (case_b, client_id)],
            )
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
        assert apply().manual_bindings == receipt.manual_bindings
        repeated_preview = service.preview(upload, manual_pairing=True)
        assert repeated_preview.existing_source_count == 1
        repeated = service.apply(upload, f"{scenario}-new", repeated_preview.preview_fingerprint,
                                 "test", scenario, manual_pairings=())
        assert repeated.existing_source_count == 1
        stored = repository.bound_sources_for_query(query_no)
        assert [item["case_no"] for item in stored] == [case_a, case_b]
        corrections = MySqlBeClassCorrectionRepository(connection)
        roots = [corrections.load(case_no, for_update=False)["beclass_record_id"] for case_no in (case_a, case_b)]
        assert roots == [item["root_id"] for item in stored] and roots[0] != roots[1]
        with connection.cursor() as cursor, pytest.raises(IntegrityError) as duplicate:
            cursor.execute(
                "INSERT INTO beclass_records (query_no,client_id,bound_case_no) VALUES (%s,%s,%s)",
                (query_no, client_id, case_a),
            )
        assert duplicate.value.args[0] == 1062
    finally:
        connection.close()

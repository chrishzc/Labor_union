"""Manual refund source binding and original owner orchestration, without SQL."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
from infrastructure.mysql.client_refund_reversal_repository import (
    MySqlClientRefundReversalRepository, _manual_refund_facts, _refund_bank_facts,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest, ClientRefundReversalError, ClientRefundReversalFacts,
    ClientRefundReversalSelection, ClientRefundReversalWorkflow, ManualClientRefundSource,
    ClientRefundReversalStorageError,
)
from subsystems.finance_import.case_manual_supplement import (
    CaseManualSupplementService, _bank_references, _supplement_command,
)
from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork


class NoSqlConnection:
    def cursor(self):
        raise AssertionError("project SQL is forbidden in manual refund port tests")
    def commit(self):
        raise AssertionError("the borrowed owner may not commit the outer transaction")


def _fixture(amount=300, *, overage=False, purpose=ClientRefundPurpose.CUSTOMER_REFUND):
    target = "subsidy-return:CASE-1" if purpose is ClientRefundPurpose.SUBSIDY_RETURN else "refund:CASE-1"
    command = _supplement_command(
        "CASE-1", "sinopac", "client_refund", target, amount,
        "2026-11-06", "", "admin_user_id:7", allow_overage_disposition=overage,
    )
    source = ManualClientRefundSource(
        16, command["case_no"], command["target_item"], amount, command["transaction_date"],
        ActorContext(command["actor"]), fingerprint_payload(command).value, overage, refund_purpose=purpose,
    )
    selection = ClientRefundReversalSelection(
        source.case_no, ClientFinanceCorrectionType.REFUND_OVERAGE if overage else ClientFinanceCorrectionType.REFUND,
        purpose, ("16",), (source.target_item,),
        allow_partial_refund_recovery=not overage,
    )
    row = {
        "id": 16, "format_id": "sinopac", "transaction_date": date(2026, 11, 6),
        "debit": amount, "credit": None, "direction": "outgoing", "currency": "TWD",
        "effective_classification_type": "client_subsidy_return" if purpose is ClientRefundPurpose.SUBSIDY_RETURN else "client_refund", "reconciliation_status": "pending",
        "ledger_entry_id": None, "resolved_counterparty_account": None,
        "bank_references": _bank_references("sinopac", "", "", "synthetic", manual_command=command,
                                             allow_overage_disposition=overage),
    }
    obligation = {"obligation_identity": source.target_item, "case_no": source.case_no,
                  "obligation_type": "subsidy_return" if purpose is ClientRefundPurpose.SUBSIDY_RETURN else "refund", "direction": "payable_to_client",
                  "status": "open", "amount_due_ntd": 1000}
    return source, selection, row, obligation


@pytest.mark.parametrize("amount,overage,remaining,recovery,purpose", [
    (1000, False, 0, 0, ClientRefundPurpose.CUSTOMER_REFUND),
    (300, False, 700, 0, ClientRefundPurpose.CUSTOMER_REFUND),
    (970, False, 30, 0, ClientRefundPurpose.CUSTOMER_REFUND),
    (1100, True, 0, 100, ClientRefundPurpose.CUSTOMER_REFUND),
    (1000, False, 0, 0, ClientRefundPurpose.SUBSIDY_RETURN),
    (300, False, 700, 0, ClientRefundPurpose.SUBSIDY_RETURN),
    (970, False, 30, 0, ClientRefundPurpose.SUBSIDY_RETURN),
])
def test_manual_refund_uses_original_owner_and_borrowed_transaction(monkeypatch, amount, overage, remaining, recovery, purpose):
    import subsystems.finance_import.case_manual_supplement as service_module
    source, selection, row, obligation = _fixture(amount, overage=overage, purpose=purpose)
    connection = NoSqlConnection()
    instances = []

    class Repository(MySqlClientRefundReversalRepository):
        def __init__(self, actual_connection, *, manual_source):
            assert actual_connection is connection
            super().__init__(actual_connection, manual_source=manual_source)
            assert manual_source == source
            self.events, self.stored = [], None
            self.version, self.remaining, self.recovery = 3, 1000, 0
            instances.append(self)
        def load(self, actual_selection, *, for_update):
            assert actual_selection == selection
            self._manual_source.validate_selection(actual_selection)
            return ClientRefundReversalFacts(3, **_manual_refund_facts(source, actual_selection, (row,), (obligation,)))
        def find_receipt(self, _key): return self.stored
        def append_ledger_entries(self, candidate):
            self.events.append("ledger")
            self.candidate = candidate
            self.applied_request = self._require_request()
        def append_allocations(self, candidate): self.events.append("allocations")
        def update_projection(self, candidate, version):
            self.events.append("projection")
            self.remaining -= sum(item.amount.amount for item in candidate.allocations)
            self.version = version
        def establish_over_refund_recovery(self, candidate, _version):
            self.events.append("recovery")
            self.recovery = candidate.recovery_amount.amount
        def append_outbox(self, _candidate, _version): self.events.append("outbox")
        def save_receipt(self, _key, receipt):
            self.events.append("receipt")
            self.stored = receipt

    monkeypatch.setattr(service_module, "MySqlClientRefundReversalRepository", Repository)
    receipt = CaseManualSupplementService(connection)._post_client_refund(
        source.case_no, source.row_id, source.target_item, amount, source.transaction_date,
        "manual-key", source.actor.actor_id, "", source.command_digest,
        allow_overage_disposition=overage,
        refund_purpose=purpose,
    )
    repository = instances[0]
    assert repository._request is None  # the service always clears its borrowed request
    assert repository.events == ["ledger", "allocations", "projection"] + (["recovery"] if recovery else []) + ["outbox", "receipt"]
    assert repository.remaining == remaining and repository.recovery == recovery
    assert repository.version == receipt.account_version == 4
    assert repository.candidate.amount.amount == amount
    assert repository.candidate.entries[0].entry_type == ("subsidy_return" if purpose is ClientRefundPurpose.SUBSIDY_RETURN else "refund")
    assert repository.candidate.entries[0].finance_import_row_identity == "16"
    assert repository.candidate.transfer_fee.amount == 0
    before = list(repository.events)
    replay = ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork).apply(repository.applied_request)
    assert replay is receipt and repository.events == before
    with pytest.raises(ClientRefundReversalError) as mismatch:
        ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork).apply(
            replace(repository.applied_request, reason="changed command"))
    assert mismatch.value.error.code == "client_finance_idempotency_conflict"
    assert repository.events == before


@pytest.mark.parametrize("field,value", [
    ("id", 17), ("format_id", "taishin"), ("debit", 301), ("credit", 1),
    ("direction", "incoming"), ("currency", "USD"), ("effective_classification_type", "staff_payout"),
    ("reconciliation_status", "reconciled"), ("ledger_entry_id", 5), ("transaction_date", date(2026, 11, 5)),
])
def test_manual_source_rejects_changed_or_used_source_row(field, value):
    source, selection, row, obligation = _fixture()
    row[field] = value
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        _manual_refund_facts(source, selection, (row,), (obligation,))


@pytest.mark.parametrize("field,value", [
    ("actor", "admin_user_id:8"), ("case_no", "CASE-2"), ("target_item", "refund:CASE-2"),
    ("amount_ntd", 301), ("transaction_date", "2026-11-05"), ("direction", "client_receipt"),
    ("allow_overage_disposition", True),
])
def test_manual_source_rejects_forged_command_even_with_recomputed_metadata_digest(field, value):
    source, selection, row, obligation = _fixture()
    references = row["bank_references"]
    references["manual_command"][field] = value
    references["manual_command_digest"] = fingerprint_payload(references["manual_command"]).value
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        _manual_refund_facts(source, selection, (row,), (obligation,))


@pytest.mark.parametrize("kind", ["wrong_source", "missing_provenance", "duplicate_row", "duplicate_obligation"])
def test_manual_source_requires_one_exact_source_and_target(kind):
    source, selection, row, obligation = _fixture()
    if kind == "wrong_source": row["bank_references"]["source"] = "bank_import"
    if kind == "missing_provenance": row["bank_references"].pop("manual_command")
    rows = (row, row) if kind == "duplicate_row" else (row,)
    obligations = (obligation, obligation) if kind == "duplicate_obligation" else (obligation,)
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        _manual_refund_facts(source, selection, rows, obligations)


@pytest.mark.parametrize("kind", ["invalid_json", "changed_reason", "changed_overage", "changed_digest"])
def test_manual_source_rejects_malformed_or_inconsistent_provenance(kind):
    source, selection, row, obligation = _fixture()
    if kind == "invalid_json": row["bank_references"] = "{"
    if kind == "changed_reason": row["bank_references"]["reason"] = "changed"
    if kind == "changed_overage": row["bank_references"]["allow_overage_disposition"] = True
    if kind == "changed_digest": row["bank_references"]["manual_command_digest"] = "0" * 64
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        _manual_refund_facts(source, selection, (row,), (obligation,))


@pytest.mark.parametrize("field,value", [
    ("case_no", "CASE-2"), ("obligation_identity", "refund:CASE-2"), ("direction", "receivable_from_client"),
    ("status", "settled"), ("obligation_type", "subsidy_return"), ("amount_due_ntd", 0),
])
def test_manual_source_keeps_current_owner_target_guards(field, value):
    source, selection, row, obligation = _fixture()
    obligation[field] = value
    with pytest.raises(ValueError, match="client_obligation_not_found"):
        _manual_refund_facts(source, selection, (row,), (obligation,))


def test_manual_metadata_alone_does_not_bypass_ordinary_bank_recipient_checks():
    _, _, row, _ = _fixture()
    facts = _refund_bank_facts((row,), "CASE-1", ClientRefundPurpose.CUSTOMER_REFUND, "synthetic-snapshot-account")
    assert facts[0].eligible is False
    repository = MySqlClientRefundReversalRepository(NoSqlConnection())
    assert repository._manual_source is None
    with pytest.raises(TypeError):
        MySqlClientRefundReversalRepository(NoSqlConnection(), manual_source={"eligible": True})


@pytest.mark.parametrize("kind", ["wrong_classification", "wrong_obligation_type", "wrong_purpose", "overage", "advance", "raw_purpose"])
def test_manual_subsidy_source_cannot_reclassify_customer_refund_or_create_advance(kind):
    source, selection, row, obligation = _fixture(purpose=ClientRefundPurpose.SUBSIDY_RETURN)
    if kind == "wrong_classification":
        row["effective_classification_type"] = "client_refund"
    elif kind == "wrong_obligation_type":
        obligation["obligation_type"] = "refund"
    elif kind == "wrong_purpose":
        selection = replace(selection, refund_purpose=ClientRefundPurpose.CUSTOMER_REFUND)
    elif kind == "overage":
        with pytest.raises(ValueError, match="invalid_client_refund_intent"):
            replace(source, allow_overage_disposition=True)
        return
    else:
        with pytest.raises(ValueError, match="manual_refund_source_invalid"):
            replace(source, refund_purpose=ClientRefundPurpose.SUBSIDY_ADVANCE if kind == "advance" else "subsidy_return")
        return
    with pytest.raises(ValueError, match="client_obligation_not_found" if kind == "wrong_obligation_type" else "manual_refund_source_mismatch"):
        _manual_refund_facts(source, selection, (row,), (obligation,))


@pytest.mark.parametrize("proof", [None, True])
def test_subsidy_manual_metadata_requires_typed_validated_binding_for_new_scheme_path(proof):
    source, selection, row, obligation = _fixture(purpose=ClientRefundPurpose.SUBSIDY_RETURN)
    facts = ClientRefundReversalFacts(3, **_manual_refund_facts(source, selection, (row,), (obligation,)))
    class Repository:
        def load(self, _selection, *, for_update):
            return replace(facts, manual_source=proof)
    with pytest.raises(ClientRefundReversalError) as caught:
        ClientRefundReversalWorkflow(Repository(), BorrowedTransactionUnitOfWork).preview(selection, CorrelationId("manual-test"))
    assert caught.value.error.code == ("subsidy_advance_settlement_ambiguous" if proof is None else "manual_refund_source_invalid")


def test_bound_actor_and_selection_cannot_be_changed_before_any_sql():
    source, selection, _, _ = _fixture()
    repository = MySqlClientRefundReversalRepository(NoSqlConnection(), manual_source=source)
    request = ClientRefundReversalApplyRequest(selection, ExpectedVersion(3), fingerprint_payload({}),
        IdempotencyKey("manual-key"), ActorContext("admin_user_id:8"), "", CorrelationId("manual-test"))
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        repository.bind_apply_request(request)
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        repository.bind_apply_request(replace(request, actor=source.actor, reason="changed audit reason"))
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        repository.load(replace(selection, case_no="CASE-2"), for_update=True)
    with pytest.raises(ValueError, match="manual_refund_source_mismatch"):
        repository.load(replace(selection, refund_purpose=ClientRefundPurpose.SUBSIDY_RETURN,
                                allow_partial_refund_recovery=False), for_update=True)
    assert repository._request is None


def test_manual_source_drift_between_preview_and_apply_is_rejected_before_writes():
    source, selection, row, obligation = _fixture()
    class Repository(MySqlClientRefundReversalRepository):
        def load(self, selection, *, for_update):
            return ClientRefundReversalFacts(3, **_manual_refund_facts(source, selection, (row,), (obligation,)))
        def find_receipt(self, _key): return None
        def append_ledger_entries(self, _candidate): raise AssertionError("a changed source must never reach the writer")
    repository = Repository(NoSqlConnection(), manual_source=source)
    workflow = ClientRefundReversalWorkflow(repository, BorrowedTransactionUnitOfWork)
    preview = workflow.preview(selection, CorrelationId("manual-test"))
    request = ClientRefundReversalApplyRequest(selection, ExpectedVersion(3), preview.fingerprint,
        IdempotencyKey("manual-key"), source.actor, "", CorrelationId("manual-test"))
    repository.bind_apply_request(request)
    row["debit"] = 301
    with pytest.raises(ClientRefundReversalError) as caught:
        workflow.apply(request)
    assert caught.value.error.code == "manual_refund_source_mismatch"


def test_public_manual_command_does_not_accept_an_internal_source_binding():
    from api.routes.finance_statement_workspace import CaseManualSupplementBody
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CaseManualSupplementBody.model_validate({
            "bank": "sinopac", "direction": "client_refund", "target_item": "refund:CASE-1",
            "amount_ntd": 300, "transaction_date": "2026-11-06", "manual_source": {"eligible": True},
        })


@pytest.mark.parametrize("amount,overage,code", [(1100, False, "allocation_exceeds_obligation"),
    (1000, True, "client_refund_overage_required"), (970, True, "client_refund_overage_required")])
def test_owner_rejects_unapproved_overpayment_or_nonexcess_overage_before_writes(amount, overage, code):
    source, selection, row, obligation = _fixture(amount, overage=overage)
    class Repository:
        def load(self, selection, *, for_update):
            return ClientRefundReversalFacts(3, **_manual_refund_facts(source, selection, (row,), (obligation,)))
    with pytest.raises(ClientRefundReversalError) as caught:
        ClientRefundReversalWorkflow(Repository(), BorrowedTransactionUnitOfWork).preview(selection, CorrelationId("manual-test"))
    assert caught.value.error.code == code


@pytest.mark.parametrize("category,code,status", [
    ("domain_blocked", "manual_refund_source_mismatch", 422),
    ("conflict", "client_finance_candidate_stale", 409),
    ("unavailable", "transaction_failed", 503),
])
def test_manual_refund_http_preserves_owner_failure_without_success(monkeypatch, category, code, status):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api.routes.finance_statement_workspace as routes
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import get_accounting_workspace
    from shared_kernel.errors import ErrorCategory, TypedError
    events = []
    class Connection(NoSqlConnection):
        def rollback(self): events.append("rollback")
    class Service:
        def __init__(self, _connection): pass
        def execute(self, **command):
            assert command["actor"] == "admin_user_id:7"
            assert command["allow_overage_disposition"] is True
            raise ClientRefundReversalError(TypedError(ErrorCategory(category), code,
                "Refund rejected.", CorrelationId("manual-test")))
    def query(_case): raise AssertionError("a failed refund must not produce a successful case view")
    monkeypatch.setattr(routes, "CaseManualSupplementService", Service)
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_accounting_workspace] = lambda: SimpleNamespace(state=SimpleNamespace(connection=Connection()), query=query)
    with TestClient(app) as client:
        response = client.post("/cases/CASE-1/manual-supplement", headers={"Idempotency-Key": "manual-key"},
            json={"bank": "sinopac", "direction": "client_refund", "target_item": "refund:CASE-1",
                  "amount_ntd": 1100, "transaction_date": "2026-11-06", "allow_overage_disposition": True})
    assert response.status_code == status
    assert response.json()["detail"]["error"]["code"] == code
    assert events == ["rollback"]


@pytest.mark.parametrize("retryable,status,category", [(True, 503, "unavailable"), (False, 500, "internal")])
def test_manual_refund_preview_storage_failure_reaches_typed_http_rollback(monkeypatch, retryable, status, category):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api.routes.finance_statement_workspace as routes
    import subsystems.finance_import.case_manual_supplement as service_module
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import get_accounting_workspace
    events = []
    class Connection(NoSqlConnection):
        def rollback(self): events.append("rollback")
    class Repository(MySqlClientRefundReversalRepository):
        def load(self, selection, *, for_update):
            self._manual_source.validate_selection(selection)
            raise ClientRefundReversalStorageError("private storage failure", retryable=retryable)
    class Service(CaseManualSupplementService):
        def execute(self, **command):
            payload = _supplement_command(command["case_no"], command["bank"], command["direction"],
                command["target_item"], command["amount_ntd"], command["transaction_date"], "", command["actor"])
            return self._post_client_refund(command["case_no"], 16, command["target_item"],
                command["amount_ntd"], command["transaction_date"], command["idempotency_key"],
                command["actor"], "", fingerprint_payload(payload).value)
    def query(_case): raise AssertionError("storage failure must not produce a successful case view")
    monkeypatch.setattr(service_module, "MySqlClientRefundReversalRepository", Repository)
    monkeypatch.setattr(routes, "CaseManualSupplementService", Service)
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_accounting_workspace] = lambda: SimpleNamespace(state=SimpleNamespace(connection=Connection()), query=query)
    with TestClient(app) as client:
        response = client.post("/cases/CASE-1/manual-supplement", headers={"Idempotency-Key": "manual-key"},
            json={"bank": "sinopac", "direction": "client_refund", "target_item": "refund:CASE-1",
                  "amount_ntd": 300, "transaction_date": "2026-11-06"})
    assert response.status_code == status
    error = response.json()["detail"]["error"]
    assert error["category"] == category and error["code"] == "transaction_failed"
    assert error["retryable"] is retryable
    assert events == ["rollback"]

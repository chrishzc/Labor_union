"""Actual owner workflow with typed repository ports; project SQL is forbidden."""

import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_accounting_workspace
import api.routes.finance_statement_workspace as routes
from domains.client_finance.reconciliation import ClientObligation, IncomingBankFact, MoneyNTD, PaymentStage
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.client_finance.reconciliation_workflow import ClientReconciliationError, ClientReconciliationFacts
from subsystems.finance_import.accounting_workspace import CaseAccounting
import subsystems.finance_import.case_manual_supplement as manual
from subsystems.finance_import.statement_archive import StatementCommandConflict


class NoSqlConnection:
    def __init__(self): self.commits = 0; self.rollbacks = 0; self.begins = 0
    def begin(self): self.begins += 1
    def cursor(self): raise AssertionError("project SQL is forbidden")
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


class ReceiptPort:
    def __init__(self, amount, *, missing_refund_account=False):
        self.amount = amount
        self.missing_refund_account = missing_refund_account
        self.effects = []
        self.selections = []
        self.request = None

    def load(self, selection, *, for_update):
        self.selections.append(selection)
        return ClientReconciliationFacts(
            7, (IncomingBankFact("9", MoneyNTD(self.amount), PaymentStage.DEPOSIT),),
            (ClientObligation("deposit:CASE", "CASE", MoneyNTD(1000), PaymentStage.DEPOSIT),),
        )

    def find_receipt(self, key): return None
    def bind_apply_request(self, request): self.request = request
    def clear_apply_request(self): self.request = None
    def append_ledger_entries(self, candidate): self.effects.append(("ledger", candidate.bank_total.amount))
    def append_allocations(self, candidate):
        self.effects.append(("allocation", sum(item.amount.amount for item in candidate.allocations)))
    def update_projection(self, selection, version): self.effects.append(("projection", version))
    def establish_overage_refund(self, candidate, version):
        if self.missing_refund_account:
            raise ValueError("client_refund_recipient_snapshot_missing")
        self.effects.append(("refund", candidate.overage_amount.amount))
    def append_orders_deposit_intent(self, candidate): self.effects.append(("deposit_intent", candidate.status.value))
    def append_anomaly_intent(self, candidate): self.effects.append(("anomaly_intent", candidate.status.value))
    def save_receipt(self, key, stored): self.effects.append(("receipt", stored.receipt.status.value))


def post_through_owner(monkeypatch, amount, *, allow_overage=False, missing_refund_account=False):
    connection = NoSqlConnection()
    port = ReceiptPort(amount, missing_refund_account=missing_refund_account)
    monkeypatch.setattr(manual, "MySqlClientReceiptReconciliationRepository", lambda actual: port if actual is connection else None)
    service = manual.CaseManualSupplementService(connection)
    return connection, port, lambda: service._post_client_receipt(
        "CASE", 9, "deposit:CASE", "deposit", "manual-key", "admin_user_id:1", "",
        allow_overage_disposition=allow_overage,
    )


@pytest.mark.parametrize("amount,allow_overage,status,allocated,refund", [
    (1000, False, "exact", 1000, None),
    (1000, True, "exact", 1000, None),
    (300, False, "partial", 300, None),
    (1100, True, "overage", 1000, 100),
])
def test_manual_selection_runs_existing_owner_and_preserves_cash(monkeypatch, amount, allow_overage, status, allocated, refund):
    connection, port, post = post_through_owner(monkeypatch, amount, allow_overage=allow_overage)
    receipt = post()
    assert receipt.status.value == status
    assert ("ledger", amount) in port.effects
    assert ("allocation", allocated) in port.effects
    assert [value for kind, value in port.effects if kind == "refund"] == ([] if refund is None else [refund])
    assert port.effects[-1] == ("receipt", status)
    assert all(selection.allow_overage_disposition is allow_overage for selection in port.selections)
    assert all(selection.allow_partial_receipt is (not allow_overage) for selection in port.selections)
    assert port.request is None
    assert connection.commits == connection.rollbacks == 0


def test_manual_overage_without_explicit_intent_is_blocked_before_owner_writes(monkeypatch):
    connection, port, post = post_through_owner(monkeypatch, 1100)
    with pytest.raises(ClientReconciliationError) as failure:
        post()
    assert failure.value.error.code == "client_receipt_overpaid"
    assert port.effects == []
    assert port.request is None
    assert connection.commits == 0


def test_overage_intent_does_not_also_enable_partial_receipt(monkeypatch):
    _, port, post = post_through_owner(monkeypatch, 300, allow_overage=True)
    with pytest.raises(ClientReconciliationError) as failure:
        post()
    assert failure.value.error.code == "client_receipt_underpaid"
    assert port.effects == []


def test_explicit_overage_missing_refund_account_keeps_typed_blocker(monkeypatch):
    connection, port, post = post_through_owner(monkeypatch, 1100, allow_overage=True, missing_refund_account=True)
    with pytest.raises(manual.ManualSupplementBlocked) as failure:
        post()
    assert failure.value.error.code == "client_refund_recipient_snapshot_missing"
    assert ("ledger", 1100) in port.effects and ("allocation", 1000) in port.effects
    assert not any(kind in {"refund", "receipt"} for kind, _ in port.effects)
    assert port.request is None and connection.commits == 0
    # This port records calls, not SQL persistence or transaction rollback.


def command(allow_overage=False):
    return manual._supplement_command(
        "CASE", "sinopac", "client_receipt", "deposit:CASE", 1100,
        "2026-11-06", "", "admin_user_id:1", allow_overage_disposition=allow_overage,
    )


def test_false_intent_preserves_saved_canonical_and_legacy_receipts_but_true_never_borrows_them():
    old = {"case_no": "CASE", "bank": "sinopac", "direction": "client_receipt",
           "target_item": "deposit:CASE", "amount_ntd": 1100, "transaction_date": "2026-11-06",
           "reason": "", "actor": "admin_user_id:1"}
    assert command() == old
    old_canonical = fingerprint_payload(old).value
    legacy = hashlib.sha256(b"CASE:sinopac:client_receipt:deposit:CASE:1100:2026-11-06:\xe4\xba\xba\xe5\xb7\xa5\xe8\xa3\x9c\xe7\x99\xbb:admin_user_id:1").hexdigest()
    assert manual._replay_reason(command(), old_canonical) is None
    assert manual._replay_reason(command(), legacy) == "人工補登"
    selected_digest = fingerprint_payload(command(True)).value
    assert selected_digest != old_canonical
    assert manual._replay_reason(command(True), selected_digest) is None
    for requested, saved in ((command(True), legacy), (command(True), old_canonical), (command(), selected_digest)):
        with pytest.raises(StatementCommandConflict, match="idempotency_conflict"):
            manual._replay_reason(requested, saved)


@pytest.mark.parametrize("direction", ["staff_salary", "government_subsidy"])
def test_overage_choice_is_not_accepted_for_other_directions(direction):
    with pytest.raises(ValueError, match="invalid_client_receipt_intent"):
        manual.CaseManualSupplementService(NoSqlConnection()).execute(
            "CASE", "sinopac", direction, "target", 1100, "2026-11-06", None, "key", "admin_user_id:1",
            allow_overage_disposition=True,
        )


@pytest.mark.parametrize("allow_overage", [False, True])
def test_http_passes_explicit_choice_and_rolls_back_missing_refund_source(monkeypatch, allow_overage):
    connection = NoSqlConnection()
    observed = []
    case = CaseAccounting("CASE", "Synthetic", 1000, 1000, None, None, 0, (), (), (), ())
    amount = 1100 if allow_overage else 1000
    port = ReceiptPort(amount, missing_refund_account=allow_overage)
    monkeypatch.setattr(manual, "MySqlClientReceiptReconciliationRepository", lambda actual: port if actual is connection else None)

    class Service(manual.CaseManualSupplementService):
        def execute(self, **request):
            # Replace only SQL-backed source ingestion, then run the production
            # helper, actual owner workflow and typed repository port.
            observed.append(request)
            return self._post_client_receipt(
                request["case_no"], 9, request["target_item"], "deposit",
                request["idempotency_key"], request["actor"], request["reason"] or "",
                allow_overage_disposition=request["allow_overage_disposition"],
            )

    monkeypatch.setattr("subsystems.finance_import.case_manual_supplement.CaseManualSupplementService", Service)
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="synthetic")
    app.dependency_overrides[get_accounting_workspace] = lambda: SimpleNamespace(
        state=SimpleNamespace(connection=connection), query=lambda _: case,
    )
    with TestClient(app) as client:
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json={
            "bank": "sinopac", "direction": "client_receipt", "target_item": "deposit:CASE",
            "amount_ntd": amount, "transaction_date": "2026-11-06", "allow_overage_disposition": allow_overage,
        })
    assert observed[0]["allow_overage_disposition"] is allow_overage
    assert response.status_code == (422 if allow_overage else 200)
    assert connection.begins == 1
    assert connection.commits == (0 if allow_overage else 1)
    assert connection.rollbacks == (1 if allow_overage else 0)
    if allow_overage:
        assert response.json()["detail"]["error"]["code"] == "client_refund_recipient_snapshot_missing"
        assert ("ledger", 1100) in port.effects and ("allocation", 1000) in port.effects
        assert not any(kind == "receipt" for kind, _ in port.effects)


@pytest.mark.parametrize("value", [1, "true"])
def test_http_body_requires_a_real_boolean(value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        routes.CaseManualSupplementBody(
            bank="sinopac", direction="client_receipt", target_item="target", amount_ntd=100,
            transaction_date="2026-11-06", allow_overage_disposition=value,
        )


@pytest.mark.parametrize("failure,expected_status", [("query_validation", 422), ("query_storage", 503), ("view_validation", 422)])
def test_manual_route_validates_readback_before_commit(monkeypatch, failure, expected_status):
    from pymysql import MySQLError
    connection = NoSqlConnection()
    calls = []

    class Service:
        def __init__(self, actual): assert actual is connection
        def execute(self, **request): calls.append("execute")

    def query(case_no):
        calls.append("query")
        assert connection.commits == 0
        if failure == "query_validation": raise ValueError("synthetic_readback_invalid")
        if failure == "query_storage": raise MySQLError("synthetic_readback_unavailable")
        return CaseAccounting(None, "Synthetic", 1000, 1000, None, None, 0, (), (), (), ())

    monkeypatch.setattr("subsystems.finance_import.case_manual_supplement.CaseManualSupplementService", Service)
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="synthetic")
    app.dependency_overrides[get_accounting_workspace] = lambda: SimpleNamespace(state=SimpleNamespace(connection=connection), query=query)
    with TestClient(app) as client:
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json={
            "bank": "sinopac", "direction": "client_receipt", "target_item": "deposit:CASE",
            "amount_ntd": 1000, "transaction_date": "2026-11-06",
        })
    assert response.status_code == expected_status
    assert calls == ["execute", "query"]
    assert connection.begins == 1 and connection.commits == 0 and connection.rollbacks == 1

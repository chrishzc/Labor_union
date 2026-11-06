"""Public replacement command through real orchestration and typed ports, never SQL.

The port model proves calls and typed readback; it does not prove MySQL persistence,
locking, transaction atomicity, concurrent uniqueness, or production data.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_accounting_workspace
import api.routes.finance_statement_workspace as routes
from domains.client_finance.reconciliation import ClientObligation, IncomingBankFact, MoneyNTD, PaymentStage
from domains.finance_import.statement_archive import CaseArrangement
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.client_finance.case_accounting_query import ClientAccountingItem, ClientAccountingTransaction
from subsystems.client_finance.reconciliation_workflow import ClientReconciliationFacts
from subsystems.finance_import.accounting_workspace import AccountingBankFact, AccountingConflict, AccountingWorkspace
import subsystems.finance_import.case_manual_supplement as manual
import infrastructure.mysql.case_manual_supplement_source_store as source_adapter
from domains.staff_payables.reconciliation import (
    StaffPaymentSourceKind, StaffPayableFacts, StaffPayoutEvent, project_staff_payable,
)
from infrastructure.mysql.staff_payout_repository import _manual_staff_payout_fact
from subsystems.staff_payables.case_accounting_query import StaffAccountingItem, StaffAccountingTransaction
from subsystems.staff_payables.payout_reconciliation import StaffPayoutReconciliationFacts, StaffPayoutRepositoryUnavailable
from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository, _manual_refund_facts
from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalFacts, ClientRefundReversalStorageError


class NoSqlConnection:
    def __init__(self): self.events = []; self.on_rollback = lambda: None
    def cursor(self): raise AssertionError("Project SQL, including fake SQL, is forbidden")
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback"); self.on_rollback()


class CommandSourcePort:
    """Source-specific typed session; never parses or executes SQL."""
    def __init__(self, direction="client_receipt", subtype="deposit"):
        self.direction = direction
        self.subtype = subtype
        self.target_item = {"staff_salary": "staff:CASE", "client_receipt": "deposit:CASE"}.get(direction,
            "subsidy-return:CASE" if subtype == "subsidy_return" else "refund:CASE")
        self.events = []
        self.rows = {}
        self.commands = {}
        self.entry = None
        self.current = True
        self.resolved = True

    @contextmanager
    def session(self):
        self.events.append("session")
        yield self

    def require_case(self, case_no):
        assert case_no == "CASE"
        self.events.append("case_lock")

    def find_command(self, key):
        self.events.append("command_lock")
        return self.commands.get(key)

    def lock_target(self, case_no, direction, target_item):
        self.events.append("target_lock")
        assert (case_no, direction, target_item) == ("CASE", self.direction, self.target_item)
        if not self.current: raise AccountingConflict("manual_supplement_target_not_current")
        if direction == "staff_salary":
            return manual.ManualSupplementTarget(staff_id=7, remaining_ntd=1000)
        return manual.ManualSupplementTarget(obligation_type=self.subtype, remaining_ntd=1000)

    def resolve_virtual_account(self, case_no):
        self.events.append("resolve")
        return {"result": "resolved", "virtual_account": "SYNTHETIC123456"} if self.resolved else {"result": "pending", "reason": "virtual_account_not_mapped"}

    def append_source(self, row):
        assert isinstance(row, manual.ManualSupplementSourceRow)
        assert len(row.values) == 14
        self.events.append("source")
        self.rows[9] = row
        return 9

    def posted_entry_id(self, direction, case_no, row_id, target_item, obligation_type):
        assert self.entry is not None
        assert (direction, case_no, row_id, target_item, obligation_type) == (
            self.direction, "CASE", 9, self.target_item, None if direction == "staff_salary" else self.subtype)
        self.events.append("owner_readback")
        return self.entry["entry_id"]

    def save_command(self, key, digest, row_id, actor):
        assert self.entry is not None and actor == self.entry["actor"]
        self.events.append("command_receipt")
        self.commands[key] = manual.ManualSupplementStoredCommand(command_digest=digest, result_identity=f"manual:{row_id}")

    def load_replay_source(self, identity):
        self.events.append("replay_source")
        assert identity == "manual:9"
        row = self.rows[9].values
        return manual.ManualSupplementReplayFacts(9, {
            "format_id": row[1], "transaction_date": row[2], "credit": row[4], "debit": row[5], "bank_references": row[9],
        })

    def load_replay_entries(self, row_id, command):
        assert row_id == 9
        self.events.append("replay_owner")
        return (self.entry,)


class ReceiptOwnerPort:
    """Existing ClientReconciliationWorkflow's repository, with real Domain decisions."""
    def __init__(self, source, *, missing_refund_account=False):
        self.source = source
        self.effects = []
        self.request = None
        self.receipt = None
        self.allocated = 0
        self.refund = 0
        self.missing_refund_account = missing_refund_account

    def load(self, selection, *, for_update):
        assert selection.bank_fact_identities == ("9",)
        row = self.source.rows[9].values
        assert row[11:13] == ("client_receipt", "pending")
        references = json.loads(row[9])
        assert references["source"] == "manual_supplement"
        assert references["reason"] == ""
        assert references["銷帳編號"] == row[8] == "SYNTHETIC123456"
        return ClientReconciliationFacts(7,
            (IncomingBankFact("9", MoneyNTD(row[4]), PaymentStage.DEPOSIT),),
            (ClientObligation("deposit:CASE", "CASE", MoneyNTD(1000), PaymentStage.DEPOSIT),))

    def find_receipt(self, key): return self.receipt
    def bind_apply_request(self, request): self.request = request
    def clear_apply_request(self): self.request = None
    def append_ledger_entries(self, candidate):
        self.effects.append(("ledger", candidate.bank_total.amount))
        self.source.entry = {"entry_id": 41, "target_item": "deposit:CASE", "amount_ntd": candidate.bank_total.amount,
                             "actor": self.request.actor.actor_id, "entry_type": "receipt", "obligation_type": "deposit"}
    def append_allocations(self, candidate):
        self.allocated = sum(item.amount.amount for item in candidate.allocations)
        self.effects.append(("allocation", self.allocated))
    def update_projection(self, selection, version): self.effects.append(("projection", version))
    def establish_overage_refund(self, candidate, version):
        if self.missing_refund_account: raise ValueError("client_refund_recipient_snapshot_missing")
        self.refund = candidate.overage_amount.amount
        self.effects.append(("refund", self.refund))
    def append_orders_deposit_intent(self, candidate): self.effects.append(("deposit_intent", candidate.status.value))
    def append_anomaly_intent(self, candidate): self.effects.append(("anomaly_intent", candidate.status.value))
    def save_receipt(self, key, receipt):
        self.receipt = receipt
        self.effects.append(("receipt", receipt.receipt.status.value))

    def query_items(self, case_no, *, for_update=False):
        assert case_no == "CASE"
        items = (ClientAccountingItem("deposit:CASE", "receivable", "訂金", "client", 1000, self.allocated,
                 self.source.entry is not None, "8", None, payment_stage="deposit"),)
        if self.refund:
            items += (ClientAccountingItem("refund:overage", "payable", "超收退款", "client", self.refund, 0, False, "8", None),)
        transactions = () if self.source.entry is None else (ClientAccountingTransaction(
            "41", "deposit:CASE", "2026-11-06", "receipt", self.source.entry["amount_ntd"], "sinopac"),)
        return items, transactions


class AccountingState:
    def __init__(self, connection): self.connection = connection
    def case_client(self, case_no): assert case_no == "CASE"; return "Synthetic"
    def dismissed(self, case_no, *, for_update=False): return {}
    def arrangement(self, case_no): return CaseArrangement(case_no)
    def marker(self, case_no): return None


def make_client(monkeypatch, *, missing_refund_account=False, query_failure=False):
    connection = NoSqlConnection()
    source = CommandSourcePort()
    owner = ReceiptOwnerPort(source, missing_refund_account=missing_refund_account)
    monkeypatch.setattr(source_adapter, "MySqlManualSupplementSourceStore", lambda actual: source if actual is connection else None)
    monkeypatch.setattr(manual, "MySqlClientReceiptReconciliationRepository", lambda actual: owner if actual is connection else None)
    def bank(case_no):
        return () if not source.rows else (AccountingBankFact("9", "2026-11-06", "in", source.rows[9].values[4], ("CASE",), "sinopac", "C"),)
    workspace = AccountingWorkspace(AccountingState(connection), owner.query_items, lambda *args, **kwargs: ((), ()), bank=bank)
    original_query = workspace.query
    def query(case_no):
        assert connection.events == []  # Readback/view must succeed before outer commit.
        if query_failure: raise ValueError("synthetic_readback_failure")
        return original_query(case_no)
    workspace.query = query
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="synthetic")
    app.dependency_overrides[get_accounting_workspace] = lambda: workspace
    return TestClient(app), connection, source, owner


def payload(amount=1000, allow_overage=False):
    return {"bank": "sinopac", "direction": "client_receipt", "target_item": "deposit:CASE", "amount_ntd": amount,
            "transaction_date": "2026-11-06", "reason": "", "allow_overage_disposition": allow_overage}


@pytest.mark.parametrize("amount,allow_overage,allocated,refund,status", [(300, False, 300, 0, "partial"), (1000, False, 1000, 0, "exact"), (1100, True, 1000, 100, "overage")])
def test_public_case_command_runs_real_service_owner_and_typed_readback(monkeypatch, amount, allow_overage, allocated, refund, status):
    client, connection, source, owner = make_client(monkeypatch)
    with client:
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json=payload(amount, allow_overage))
    assert response.status_code == 200, response.text
    view = response.json()["data"]
    assert view["received_ntd"] == allocated
    assert view["remaining_in_ntd"] == 1000 - allocated
    assert view["bank_facts"][0]["amount_ntd"] == amount
    assert view["transactions"][0]["amount_ntd"] == amount
    assert view["payable_ntd"] == (refund or None)
    assert owner.effects[0:2] == [("ledger", amount), ("allocation", allocated)]
    assert owner.effects[-1] == ("receipt", status)
    assert owner.refund == refund
    assert owner.request is None
    assert source.events == ["session", "case_lock", "command_lock", "target_lock", "resolve", "source", "owner_readback", "command_receipt"]
    assert connection.events == ["commit"]
    command = manual._supplement_command("CASE", "sinopac", "client_receipt", "deposit:CASE", amount, "2026-11-06", "", "admin_user_id:1", allow_overage_disposition=allow_overage)
    assert source.commands["key"]["command_digest"] == fingerprint_payload(command).value


def test_real_command_replays_original_ids_before_current_target_validation_and_rejects_mutation(monkeypatch):
    client, connection, source, owner = make_client(monkeypatch)
    with client:
        first = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json=payload())
        assert first.status_code == 200
        effects = tuple(owner.effects)
        source.current = False
        source.events.clear(); connection.events.clear()
        replay = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json=payload())
        assert replay.status_code == 200 and replay.json() == first.json()
        assert source.events == ["session", "case_lock", "command_lock", "replay_source", "replay_owner"]
        assert tuple(owner.effects) == effects and len(source.rows) == len(source.commands) == 1
        result = manual.CaseManualSupplementService(connection, source_store=source).execute(
            "CASE", "sinopac", "client_receipt", "deposit:CASE", 1000, "2026-11-06", "", "key", "admin_user_id:1")
        assert (result.row_id, result.entry_id) == (9, 41)
        connection.events.clear(); source.events.clear()
        conflict = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json=payload(900))
    assert conflict.status_code == 409
    assert source.events == ["session", "case_lock", "command_lock"]
    assert connection.events == ["rollback"] and tuple(owner.effects) == effects


@pytest.mark.parametrize("failure,status,code", [("target", 409, "accounting_source_changed"), ("resolver", 422, "virtual_account_not_mapped"),
    ("overage", 422, "client_receipt_overpaid"), ("refund_account", 422, "client_refund_recipient_snapshot_missing"), ("readback", 422, "invalid_statement_command")])
def test_real_command_failures_never_commit_and_preserve_owner_blocker(monkeypatch, failure, status, code):
    client, connection, source, owner = make_client(monkeypatch, missing_refund_account=failure == "refund_account", query_failure=failure == "readback")
    source.current = failure != "target"; source.resolved = failure != "resolver"
    with client:
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"},
                               json=payload(1100 if failure in {"overage", "refund_account"} else 1000, failure == "refund_account"))
    assert response.status_code == status, response.text
    assert response.json()["detail"]["error"]["code"] == code
    assert connection.events == ["rollback"]
    if failure in {"target", "resolver"}:
        assert source.rows == source.commands == {} and owner.effects == []
    if failure in {"overage", "refund_account"}:
        assert source.commands == {}
    # Rollback dispatch is proven; MySQL rollback atomicity is deliberately NOT_RUN.


def test_replay_checks_original_source_and_owner_proof_without_new_writes(monkeypatch):
    client, connection, source, owner = make_client(monkeypatch)
    with client:
        assert client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json=payload()).status_code == 200
        connection.events.clear(); source.events.clear()
        source.entry = {**source.entry, "actor": "admin_user_id:2"}
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "key"}, json=payload())
    assert response.status_code == 409
    assert source.events == ["session", "case_lock", "command_lock", "replay_source", "replay_owner"]
    assert connection.events == ["rollback"]


def outgoing_metadata(source):
    """Project the actual source row into the original adapter's bounded input."""
    row = source.rows[9]
    return {"id": 9, "format_id": row.format_id, "transaction_date": date.fromisoformat(row.transaction_date),
            "direction": row.direction, "debit": row.debit, "credit": row.credit,
            "classification_type": row.classification_type, "effective_classification_type": row.classification_type,
            "reconciliation_status": row.reconciliation_status, "bank_references": row.bank_references,
            "dedup_fingerprint": row.dedup_fingerprint, "currency": "TWD", "payout_event_id": None,
            "ledger_entry_id": None, "resolved_counterparty_account": None}


class StaffOwnerPort:
    def __init__(self, source, context, failure=None):
        self.source, self.context, self.failure = source, context, failure
        self.request = None
        self.obligation = StaffPayableFacts(source.target_item, 7, MoneyNTD(1000), ())
        self.projected = project_staff_payable(self.obligation)
        self.candidate = None
        self.calls = []
        self.loads = 0

    def load(self, selection, *, for_update):
        self.loads += 1
        row = outgoing_metadata(self.source)
        if self.failure == "source": row["bank_references"] = "{}"
        target = {"obligation_identity": self.source.target_item, "case_no": "CASE", "staff_id": 7,
                  "direction": "payable_to_staff", "status": "open", "projection_status": "payable",
                  "amount_due_ntd": 1000, "net_paid_ntd": 0, "balance_ntd": 1000}
        proof = _manual_staff_payout_fact(self.context, selection, (row,), (target,), (self.obligation,))
        return StaffPayoutReconciliationFacts(4, 8, (), (), (self.obligation,), manual_source=proof)
    def find_receipt(self, key): return None
    def bind_apply_request(self, request): self.context.validate_selection(request.selection); self.request = request
    def clear_apply_request(self): self.request = None
    def append_events(self, candidate):
        if self.failure == "storage": raise StaffPayoutRepositoryUnavailable("synthetic storage unavailable")
        self.calls.append("events"); self.candidate = candidate
        self.source.entry = {"entry_id": 41, "target_item": self.source.target_item,
            "amount_ntd": candidate.bank_total.amount, "actor": self.request.actor.actor_id}
    def append_obligation_links(self, candidate): self.calls.append("links")
    def append_overpayment_recovery(self, candidate): raise AssertionError("Staff has no manual overpayment intent")
    def update_payable_projection(self, selection, version, status):
        events = tuple(StaffPayoutEvent(item.identity, item.event_type, item.amount) for item in self.candidate.events)
        self.projected = project_staff_payable(replace(self.obligation, events=events))
        assert self.projected.status is status
        self.calls.append("projection")
    def append_outbox(self, candidate): self.calls.append("outbox")
    def save_receipt(self, key, stored): self.calls.append("receipt")
    def query_items(self, case_no, *, for_update=False):
        assert case_no == "CASE"
        paid = self.projected.net_paid.amount
        items = (StaffAccountingItem(self.source.target_item, "payable", "月嫂薪資", "staff", 1000, paid,
                                     self.source.entry is not None, "5", None),)
        transactions = () if self.source.entry is None else (StaffAccountingTransaction(
            "41", self.source.target_item, "2026-11-06", "payout", self.source.entry["amount_ntd"], "sinopac"),)
        return items, transactions


class RefundOwnerPort(MySqlClientRefundReversalRepository):
    """Retain the real adapter's typed bind and pure source-proof validation."""
    def __init__(self, connection, source, context, failure=None):
        super().__init__(connection, manual_source=context)
        self.source, self.failure = source, failure
        self.calls = []
        self.loads = 0
        self.allocated = 0
        self.recovery = 0
        self.candidate = None

    def load(self, selection, *, for_update):
        self.loads += 1
        row = outgoing_metadata(self.source)
        if self.failure == "source": row["bank_references"] = "{}"
        obligation = {"obligation_identity": self.source.target_item, "case_no": "CASE",
            "obligation_type": self.source.subtype, "direction": "payable_to_client", "status": "open", "amount_due_ntd": 1000}
        return ClientRefundReversalFacts(3, **_manual_refund_facts(self._manual_source, selection, (row,), (obligation,)))
    def find_receipt(self, key): return None
    def append_ledger_entries(self, candidate):
        if self.failure == "storage": raise ClientRefundReversalStorageError("synthetic storage unavailable", retryable=True)
        self.candidate = candidate; self.calls.append("ledger")
        self.source.entry = {"entry_id": 41, "target_item": self.source.target_item, "amount_ntd": candidate.amount.amount,
            "actor": self._require_request().actor.actor_id, "entry_type": candidate.entries[0].entry_type,
            "obligation_type": self.source.subtype}
    def append_allocations(self, candidate): self.calls.append("allocations")
    def update_projection(self, candidate, version):
        self.allocated = sum(item.amount.amount for item in candidate.allocations)
        self.calls.append("projection")
    def establish_over_refund_recovery(self, candidate, version):
        self.recovery = candidate.recovery_amount.amount; self.calls.append("recovery")
    def append_outbox(self, candidate, version): self.calls.append("outbox")
    def save_receipt(self, key, stored): self.calls.append("receipt")
    def query_items(self, case_no, *, for_update=False):
        assert case_no == "CASE"
        items = (ClientAccountingItem(self.source.target_item, "payable", "補助退款" if self.source.subtype == "subsidy_return" else "客戶退款",
            "client", 1000, self.allocated, self.source.entry is not None, "4", None),)
        if self.recovery:
            items += (ClientAccountingItem("recovery:41", "receivable", "超付追償", "client", self.recovery, 0, False, "4", None),)
        transactions = () if self.source.entry is None else (ClientAccountingTransaction(
            "41", self.source.target_item, "2026-11-06", self.source.entry["entry_type"], self.source.entry["amount_ntd"], "sinopac"),)
        return items, transactions


def make_outgoing_client(monkeypatch, direction, subtype, *, failure=None):
    connection = NoSqlConnection()
    source = CommandSourcePort(direction, subtype)
    owners = []
    monkeypatch.setattr(source_adapter, "MySqlManualSupplementSourceStore", lambda actual: source if actual is connection else None)
    def repository(actual, *, manual_source):
        assert actual is connection
        owner = StaffOwnerPort(source, manual_source, failure) if direction == "staff_salary" else RefundOwnerPort(actual, source, manual_source, failure)
        owners.append(owner)
        return owner
    monkeypatch.setattr(manual, "MySqlStaffPayoutRepository" if direction == "staff_salary" else "MySqlClientRefundReversalRepository", repository)
    # The typed transaction port discards staged source changes on rollback. This
    # tests dispatch only; it makes no assertion about real MySQL atomicity.
    def rollback_staged_source(): source.rows.clear(); source.commands.clear(); source.entry = None
    connection.on_rollback = rollback_staged_source
    def items(case_no, *, for_update=False):
        return owners[-1].query_items(case_no, for_update=for_update) if owners else ((), ())
    def bank(case_no):
        if not source.rows: return ()
        cash_flow = "PS" if direction == "staff_salary" else "RT" if subtype == "subsidy_return" else "RS"
        return (AccountingBankFact("9", "2026-11-06", "out", source.rows[9].debit, ("CASE",), source.rows[9].format_id, cash_flow),)
    empty = lambda *args, **kwargs: ((), ())
    workspace = AccountingWorkspace(AccountingState(connection), empty if direction == "staff_salary" else items,
                                    items if direction == "staff_salary" else empty, bank=bank)
    actual_query = workspace.query
    def query(case_no):
        assert connection.events == []
        return actual_query(case_no)
    workspace.query = query
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, username="synthetic")
    app.dependency_overrides[get_accounting_workspace] = lambda: workspace
    return TestClient(app), connection, source, owners


def outgoing_payload(source, amount, *, overage=False):
    return {"bank": "taishin" if source.subtype == "subsidy_return" else "sinopac", "direction": source.direction,
            "target_item": source.target_item, "amount_ntd": amount, "transaction_date": "2026-11-06",
            "reason": "", "allow_overage_disposition": overage}


@pytest.mark.parametrize("direction,subtype,amount,overage,remaining,recovery", [
    ("staff_salary", "staff", 1000, False, 0, 0),
    ("staff_salary", "staff", 970, False, 30, 0),
    ("client_refund", "refund", 1000, False, 0, 0),
    ("client_refund", "refund", 970, False, 30, 0),
    ("client_refund", "subsidy_return", 1000, False, 0, 0),
    ("client_refund", "subsidy_return", 300, False, 700, 0),
    ("client_refund", "refund", 1100, True, 0, 100),
])
def test_outgoing_public_command_runs_real_service_owner_query_and_original_id_replay(
        monkeypatch, direction, subtype, amount, overage, remaining, recovery):
    client, connection, source, owners = make_outgoing_client(monkeypatch, direction, subtype)
    body = outgoing_payload(source, amount, overage=overage)
    with client:
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "outgoing-key"}, json=body)
        assert response.status_code == 200, response.text
        view = response.json()["data"]
        assert view["paid_ntd"] == min(amount, 1000) and view["remaining_out_ntd"] == remaining
        assert view["bank_facts"][0]["amount_ntd"] == view["transactions"][0]["amount_ntd"] == amount
        assert view["bank_facts"][0]["cash_flow"] == ("PS" if direction == "staff_salary" else "RT" if subtype == "subsidy_return" else "RS")
        assert connection.events == ["commit"] and len(owners) == 1
        owner = owners[0]
        assert owner.candidate.transfer_fee.amount == 0 and owner.loads == 2
        if direction == "staff_salary":
            assert owner.candidate.events[0].payment_source_kind is StaffPaymentSourceKind.MANUAL_SUPPLEMENT
            assert owner.projected.balance.amount == remaining
            assert owner.calls == ["events", "links", "projection", "outbox", "receipt"]
            assert owner.request is None
        else:
            assert owner.candidate.entries[0].entry_type == ("subsidy_return" if subtype == "subsidy_return" else "refund")
            assert owner.recovery == recovery
            assert owner.calls == ["ledger", "allocations", "projection"] + (["recovery"] if recovery else []) + ["outbox", "receipt"]
            assert owner._request is None
            assert view["receivable_ntd"] == (recovery or None)
        assert source.events == ["session", "case_lock", "command_lock", "target_lock", "resolve", "source", "owner_readback", "command_receipt"]
        source.current = False  # Fully-settled/changed current target cannot invalidate the receipt.
        connection.events.clear(); source.events.clear()
        replay = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "outgoing-key"}, json=body)
        assert replay.status_code == 200 and replay.json() == response.json()
        assert len(owners) == 1 and owner.loads == 2
        assert source.events == ["session", "case_lock", "command_lock", "replay_source", "replay_owner"]
        result = manual.CaseManualSupplementService(connection, source_store=source).execute(
            case_no="CASE", **body, idempotency_key="outgoing-key", actor="admin_user_id:1")
        assert (result.row_id, result.entry_id, result.target_item) == (9, 41, source.target_item)
        assert len(source.rows) == len(source.commands) == 1


@pytest.mark.parametrize("direction,subtype,failure,status,code", [
    ("staff_salary", "staff", "source", 422, "manual_staff_source_mismatch"),
    ("staff_salary", "staff", "storage", 503, "transaction_failed"),
    ("client_refund", "refund", "source", 422, "manual_refund_source_mismatch"),
    ("client_refund", "refund", "storage", 503, "transaction_failed"),
    ("client_refund", "subsidy_return", "source", 422, "manual_refund_source_mismatch"),
    ("client_refund", "subsidy_return", "storage", 503, "transaction_failed"),
])
def test_outgoing_real_owner_refusal_rolls_back_staged_source_without_receipt(
        monkeypatch, direction, subtype, failure, status, code):
    client, connection, source, owners = make_outgoing_client(monkeypatch, direction, subtype, failure=failure)
    with client:
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "outgoing-key"}, json=outgoing_payload(source, 970))
    assert response.status_code == status, response.text
    error = response.json()["detail"]["error"]
    assert error["code"] == code and error["retryable"] is (failure == "storage")
    assert connection.events == ["rollback"] and source.rows == source.commands == {} and source.entry is None
    assert source.events == ["session", "case_lock", "command_lock", "target_lock", "resolve", "source"]
    assert len(owners) == 1 and owners[0].calls == []
    assert owners[0].loads == (1 if failure == "source" else 2)


def test_subsidy_return_never_borrows_general_refund_overage_intent_or_writes_source(monkeypatch):
    client, connection, source, owners = make_outgoing_client(monkeypatch, "client_refund", "subsidy_return")
    with client:
        response = client.post("/cases/CASE/manual-supplement", headers={"Idempotency-Key": "outgoing-key"}, json=outgoing_payload(source, 1100, overage=True))
    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "invalid_client_refund_intent"
    assert connection.events == ["rollback"] and owners == [] and source.rows == source.commands == {}
    assert source.events == ["session", "case_lock", "command_lock", "target_lock"]

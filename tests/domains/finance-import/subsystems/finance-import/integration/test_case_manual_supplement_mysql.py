"""Opt-in manual source -> actual owner Preview/Apply -> committed MySQL evidence.

Caller provisions a fresh canonical lu_test_* database. No drop/reset or real data.
"""
import json
import os
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymysql
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_accounting_workspace
from api.routes.finance_statement_workspace import router
from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
from infrastructure.mysql.case_manual_supplement_repository import MySqlCaseManualSupplementRepository
from infrastructure.mysql.manual_supplement_evidence import manual_source_matches
from subsystems.finance_import.case_manual_supplement import CaseManualSupplementService, ManualSupplementConflict

pytestmark = pytest.mark.skipif(os.getenv("MANUAL_SUPPLEMENT_MYSQL") != "1", reason="explicit disposable MySQL acceptance")


@pytest.fixture
def connection():
    assert os.getenv("APP_ENV") == "development"
    host, database = os.environ["LABOR_UNION_TEST_MYSQL_HOST"], os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"]
    assert host in {"localhost", "127.0.0.1"} and database.startswith("lu_test_")
    connection = pymysql.connect(host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE() db")
        assert cursor.fetchone()["db"] == database
    connection.rollback()
    yield connection
    connection.rollback()
    connection.close()


def seed(connection, direction, *, amount=10000, refund_account=False):
    with connection.cursor() as cursor:
        while True:
            case = f"{200 + int(uuid4().hex[:6], 16) % 700:03d}{int(uuid4().hex[:6], 16) % 1000:06d}"
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s", (case,))
            if cursor.fetchone() is None:
                break
        cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'Synthetic Manual Client')", (case,))
        cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'服務中')", (case, cursor.lastrowid))
        cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)", (case,))
        identity = f"manual-test:{case}:{direction}"
        if direction == "staff_salary":
            cursor.execute("INSERT INTO staff(name) VALUES ('合成補登月嫂')")
            staff_id = cursor.lastrowid
            cursor.execute("UPDATE orders SET staff_id=%s WHERE case_no=%s", (staff_id, case))
            cursor.execute("INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status) VALUES (%s,%s,1,'completed')", (case, staff_id))
            assignment = cursor.lastrowid
            cursor.execute("INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,%s,'2026-10-15',%s,0,1,%s,'synthetic','original payable')", (identity, assignment, case, staff_id, amount, 'a'*64, identity))
            cursor.execute("INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,amount_due_ntd,due_date,status,current_event_id,payroll_version) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',%s,'2026-10-15','open',%s,1)", (identity, assignment, case, staff_id, amount, cursor.lastrowid))
        else:
            kind, way = ("first", "receivable_from_client") if direction == "client_receipt" else ("refund", "payable_to_client")
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,'established',0,%s,'2026-10-19',%s,0,%s,'synthetic','original obligation')", (identity, case, kind, way, amount, identity, identity))
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,%s,%s,%s,'2026-10-19','open',%s,0)", (identity, case, kind, way, amount, cursor.lastrowid))
        if refund_account:
            cursor.execute("INSERT INTO beclass_records(query_no,bound_case_no,refund_bank_code,refund_account_no) VALUES (%s,%s,%s,%s)", (identity, case, '0'.zfill(7), str(int(uuid4().hex[:10], 16)).zfill(12)))
    connection.commit()
    return case, identity


def command(case, target, direction, *, bank="sinopac", cash=10000, mode="exact", key=None):
    return dict(case_no=case, bank=bank, direction=direction, target_item=target, amount_ntd=cash,
                transaction_date="2026-10-20", reason=None, idempotency_key=key or uuid4().hex,
                actor="synthetic", settlement_mode=mode)


def snapshot(connection, case, target, direction):
    with connection.cursor() as cursor:
        if direction == "staff_salary":
            cursor.execute("SELECT balance_ntd AS remaining,net_paid_ntd AS paid FROM staff_payable_projections WHERE obligation_identity=%s", (target,))
            row = cursor.fetchone()
            remaining, paid = (10000, 0) if row is None else (int(row["remaining"]), int(row["paid"]))
            cursor.execute("SELECT COUNT(*) n,COALESCE(SUM(e.amount_ntd),0) cash FROM staff_payout_events e JOIN staff_obligations o ON o.staff_id=e.staff_id WHERE o.obligation_identity=%s", (target,))
        else:
            cursor.execute("SELECT amount_due_ntd FROM client_obligations WHERE obligation_identity=%s", (target,))
            remaining, paid = int(cursor.fetchone()["amount_due_ntd"]), None
            cursor.execute("SELECT COUNT(*) n,COALESCE(SUM(amount_ntd),0) cash FROM client_ledger_entries WHERE case_no=%s", (case,))
        financial = cursor.fetchone()
        cursor.execute("SELECT COALESCE(SUM(amount_due_ntd),0) amount FROM client_obligations WHERE case_no=%s AND direction='payable_to_client'", (case,))
        return dict(remaining=remaining, paid=paid, entries=financial["n"], cash=int(financial["cash"]), refunds=int(cursor.fetchone()["amount"]))


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
@pytest.mark.parametrize("direction", ["client_receipt", "staff_salary", "client_refund"])
@pytest.mark.parametrize("mode,cash,remaining", [("exact", 10000, 0), ("partial", 9000, 1000)])
def test_real_owner_full_partial_original_receipt_and_no_duplicate(connection, bank, direction, mode, cash, remaining):
    case, target = seed(connection, direction)
    service = CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection))
    request = command(case, target, direction, bank=bank, cash=cash, mode=mode)
    result = service.execute(**request)
    connection.commit()
    before = snapshot(connection, case, target, direction)
    assert before["remaining"] == remaining and before["cash"] == cash and before["entries"] == 1
    assert service.execute(**request) == result
    connection.commit()
    assert snapshot(connection, case, target, direction) == before
    with pytest.raises(ManualSupplementConflict):
        service.execute(**{**request, "amount_ntd": cash + 1})
    connection.rollback()
    assert snapshot(connection, case, target, direction) == before
    with connection.cursor() as cursor:
        cursor.execute("SELECT counterparty_account,resolved_counterparty_account,source_bank_account,bank_references,raw_payload FROM finance_import_rows WHERE id=%s", (result.row_id,))
        source = cursor.fetchone()
        assert all(source[key] is None for key in ("counterparty_account", "resolved_counterparty_account", "source_bank_account"))
        assert "帳號" not in json.loads(source["raw_payload"])
        cursor.execute("SELECT COUNT(*) n FROM finance_statement_commands WHERE idempotency_key=%s", (request["idempotency_key"],))
        assert cursor.fetchone()["n"] == 1
    if mode == "partial":
        topup = service.execute(**command(case, target, direction, bank=bank, cash=1000))
        connection.commit()
        assert snapshot(connection, case, target, direction)["remaining"] == 0
        assert topup.row_id != result.row_id


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
def test_client_overage_uses_real_refund_owner_and_replay(connection, bank):
    case, target = seed(connection, "client_receipt", refund_account=True)
    service = CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection))
    request = command(case, target, "client_receipt", bank=bank, cash=12000, mode="overage")
    result = service.execute(**request)
    connection.commit()
    state = snapshot(connection, case, target, "client_receipt")
    assert state == dict(remaining=0, paid=None, entries=1, cash=12000, refunds=2000)
    with connection.cursor() as cursor:
        cursor.execute("SELECT SUM(a.amount_ntd) amount FROM client_ledger_obligation_allocations a JOIN client_ledger_entries e ON e.id=a.ledger_entry_id WHERE e.finance_import_row_id=%s", (result.row_id,))
        assert int(cursor.fetchone()["amount"]) == 10000
    assert service.execute(**request) == result
    connection.commit()
    assert snapshot(connection, case, target, "client_receipt") == state


def test_equal_partial_payments_with_distinct_keys_are_distinct_transactions(connection):
    case,target=seed(connection,"client_receipt")
    service=CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection))
    first=command(case,target,"client_receipt",cash=5000,mode="partial")
    second={**first,"idempotency_key":uuid4().hex}
    a=service.execute(**first);connection.commit()
    b=service.execute(**second);connection.commit()
    assert a.row_id!=b.row_id
    assert service.execute(**first)==a and service.execute(**second)==b
    connection.commit()
    assert snapshot(connection,case,target,"client_receipt")==dict(remaining=0,paid=None,entries=2,cash=10000,refunds=0)


def test_http_failure_rolls_back_source_command_and_owner_writes(connection):
    case, target = seed(connection, "client_receipt")
    application = build_accounting_workspace(connection)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_accounting_workspace] = lambda: application
    body = command(case, target, "client_receipt", cash=12000, mode="overage")
    key = body.pop("idempotency_key")
    body.pop("actor"); body.pop("case_no")
    with TestClient(app) as client:
        response = client.post(f"/cases/{case}/manual-supplement", json=body, headers={"Idempotency-Key": key})
    assert response.status_code == 422
    assert snapshot(connection, case, target, "client_receipt")["entries"] == 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) n FROM finance_statement_commands WHERE idempotency_key=%s", (key,))
        assert cursor.fetchone()["n"] == 0
        cursor.execute("SELECT COUNT(*) n FROM finance_import_rows WHERE JSON_UNQUOTE(JSON_EXTRACT(bank_references,'$.manual_supplement.key'))=%s", (key,))
        assert cursor.fetchone()["n"] == 0


def test_unbound_json_flag_cannot_supply_manual_recipient_proof(connection):
    case, target = seed(connection, "client_refund")
    with connection.cursor() as cursor:
        row = {"id": 123, "bank_references": {"manual_supplement": {"key": "forged", "digest": "a"*64,
              "actor": "synthetic", "case_no": case, "direction": "client_refund", "obligations": [target]}}}
        assert not manual_source_matches(cursor, row, case_no=case, direction="client_refund", obligations=(target,))


@pytest.mark.parametrize("direction",["staff_salary","client_refund"])
def test_copying_valid_manual_metadata_to_a_bank_row_does_not_bypass_account_check(connection,direction):
    from shared_kernel.identities import CorrelationId
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalWorkflow,ClientRefundReversalSelection,ClientRefundReversalError
    from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
    from domains.staff_payables.reconciliation import StaffPayoutEventType
    from subsystems.staff_payables.payout_reconciliation import StaffPayoutReconciliationWorkflow,StaffPayoutSelection,StaffPayoutReconciliationError
    from infrastructure.mysql.staff_payout_repository import MySqlStaffPayoutRepository
    from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork
    case,target=seed(connection,direction)
    receipt=CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection)).execute(**command(case,target,direction,cash=9000,mode="partial"))
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,batch_id,format_id,transaction_date,direction,credit,debit,currency,summary,memo,bank_references,warnings,classification_type,reconciliation_status,raw_payload) SELECT %s,batch_id,format_id,transaction_date,direction,credit,1000,currency,summary,memo,bank_references,warnings,classification_type,'pending',raw_payload FROM finance_import_rows WHERE id=%s",(uuid4().hex+uuid4().hex,receipt.row_id))
        copied=str(cursor.lastrowid)
    if direction=="staff_salary":
        workflow=StaffPayoutReconciliationWorkflow(MySqlStaffPayoutRepository(connection),BorrowedTransactionUnitOfWork)
        selection=StaffPayoutSelection(StaffPayoutEventType.PAYOUT,(copied,),(target,))
        expected,code=StaffPayoutReconciliationError,"staff_bank_account_ambiguous"
    else:
        workflow=ClientRefundReversalWorkflow(MySqlClientRefundReversalRepository(connection),BorrowedTransactionUnitOfWork)
        selection=ClientRefundReversalSelection(case,ClientFinanceCorrectionType.REFUND,bank_fact_identities=(copied,),obligation_identities=(target,))
        expected,code=ClientRefundReversalError,"client_refund_source_account_missing"
    with pytest.raises(expected) as error:workflow.preview(selection,CorrelationId("synthetic-forged-row"))
    assert error.value.error.code==code
    connection.rollback()


def test_wrong_case_target_rejects_without_source(connection):
    case, target = seed(connection, "client_receipt")
    other, _ = seed(connection, "client_receipt")
    request = command(other, target, "client_receipt")
    with pytest.raises(ValueError, match="manual_target_not_open_in_case"):
        CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection)).execute(**request)
    connection.rollback()


@pytest.mark.parametrize("direction", ["staff_salary", "client_refund"])
@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
def test_outgoing_100_fee_and_overpayment_use_original_rules(connection, direction, bank):
    service = CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection))
    for cash, mode in ((9900, "exact"), (10100, "overage")):
        case, target = seed(connection, direction)
        request = command(case, target, direction, cash=cash, mode=mode, bank=bank)
        receipt = service.execute(**request)
        connection.commit()
        before = snapshot(connection, case, target, direction)
        assert before["remaining"] == 0 and before["cash"] == cash
        assert service.execute(**request) == receipt
        connection.commit()
        assert snapshot(connection, case, target, direction) == before
        with connection.cursor() as cursor:
            if mode == "overage":
                if direction == "client_refund":
                    cursor.execute("SELECT amount_due_ntd FROM client_over_refund_recoveries WHERE case_no=%s", (case,))
                else:
                    cursor.execute("SELECT remaining_amount_ntd AS amount_due_ntd FROM staff_overpayment_recoveries WHERE staff_id=(SELECT staff_id FROM staff_obligations WHERE obligation_identity=%s)", (target,))
                assert int(cursor.fetchone()["amount_due_ntd"]) == 100


def test_real_http_returns_same_receipt_and_changed_content_conflicts(connection):
    case, target = seed(connection, "client_receipt")
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_accounting_workspace] = lambda: build_accounting_workspace(connection)
    body = command(case, target, "client_receipt")
    key = body.pop("idempotency_key"); body.pop("actor"); body.pop("case_no")
    with TestClient(app) as client:
        first = client.post(f"/cases/{case}/manual-supplement", json=body, headers={"Idempotency-Key":key})
        assert first.status_code == 200, first.text
        again = client.post(f"/cases/{case}/manual-supplement", json=body, headers={"Idempotency-Key":key})
        assert again.status_code == 200, again.text
        assert again.json()["data"]["manual_supplement_receipt"] == first.json()["data"]["manual_supplement_receipt"]
        for field, changed in (("amount_ntd",9999),("settlement_mode","partial"),("reason","changed")):
            conflict = client.post(f"/cases/{case}/manual-supplement", json={**body,field:changed}, headers={"Idempotency-Key":key})
            assert conflict.status_code == 409
    assert snapshot(connection,case,target,"client_receipt")["entries"] == 1


def test_failure_after_owner_apply_rolls_back_all_effects(connection, monkeypatch):
    case, target = seed(connection, "client_receipt", refund_account=True)
    app = FastAPI(); app.include_router(router)
    application = build_accounting_workspace(connection)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_accounting_workspace] = lambda: application
    monkeypatch.setattr(application,"query",lambda _: (_ for _ in ()).throw(ValueError("readback_failure")))
    body = command(case,target,"client_receipt",cash=12000,mode="overage")
    key=body.pop("idempotency_key"); body.pop("actor"); body.pop("case_no")
    with TestClient(app) as client:
        assert client.post(f"/cases/{case}/manual-supplement",json=body,headers={"Idempotency-Key":key}).status_code==422
    assert snapshot(connection,case,target,"client_receipt")==dict(remaining=10000,paid=None,entries=0,cash=0,refunds=0)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) n FROM finance_statement_commands WHERE idempotency_key=%s",(key,))
        assert cursor.fetchone()["n"]==0


@pytest.mark.parametrize("different_case",[False,True])
def test_concurrent_same_key_serializes_to_original_or_conflict(connection,different_case):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    case,target=seed(connection,"client_receipt")
    other,second=seed(connection,"client_receipt") if different_case else (case,target)
    key=uuid4().hex; barrier=Barrier(2)
    def worker(selected,target_item):
        config=dict(host=os.environ['LABOR_UNION_TEST_MYSQL_HOST'],port=int(os.environ['LABOR_UNION_TEST_MYSQL_PORT']),
            user=os.environ['LABOR_UNION_TEST_MYSQL_USER'],password=os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'],
            database=os.environ['LABOR_UNION_TEST_MYSQL_DATABASE'],cursorclass=pymysql.cursors.DictCursor,autocommit=False)
        conn=pymysql.connect(**config)
        try:
            barrier.wait(timeout=10)
            receipt=CaseManualSupplementService(MySqlCaseManualSupplementRepository(conn)).execute(**command(selected,target_item,"client_receipt",key=key))
            conn.commit();return receipt
        except ManualSupplementConflict:
            conn.rollback();return "conflict"
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(worker,case,target);b=pool.submit(worker,other,second)
        results=[a.result(timeout=20),b.result(timeout=20)]
    if different_case:assert results.count("conflict")==1
    else:assert results[0]==results[1]
    connection.rollback()
    total=snapshot(connection,case,target,"client_receipt")["entries"]
    if different_case:total+=snapshot(connection,other,second,"client_receipt")["entries"]
    assert total==1

"""Manual Staff Payables source validation and real workflow ports; never SQL."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from domains.staff_payables.reconciliation import (
    StaffPaymentSourceKind, StaffPayableFacts, StaffPayoutEvent, StaffPayoutEventType,
    StaffPayoutDifferenceMode, StaffPayoutReopenFact, OutgoingBankFact,
    build_staff_payout_candidate, build_staff_payout_reopen_candidate, project_staff_payable,
    ManualStaffPayoutFact,
)
from infrastructure.mysql.staff_payout_repository import (
    _manual_staff_payout_fact, _EventPersistenceMetadata, _event_insert_values,
    _reopen_event_metadata, _ReopenReference,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutReconciliationFacts, StaffPayoutReconciliationError, ManualStaffPayoutSource,
    StaffPayoutRepositoryUnavailable,
    StaffPayoutReconciliationWorkflow, StaffPayoutSelection,
)
import subsystems.finance_import.case_manual_supplement as manual


class NoSqlConnection:
    def cursor(self): raise AssertionError("Project SQL is forbidden")
    def commit(self): raise AssertionError("Child workflow cannot commit the outer connection")


def fixture(amount=300):
    command = manual._supplement_command("CASE", "sinopac", "staff_salary", "staff:CASE", amount,
        "2026-11-06", "", "admin_user_id:1")
    digest = fingerprint_payload(command).value
    source = ManualStaffPayoutSource(9, "CASE", "staff:CASE", 7, amount, "2026-11-06", ActorContext("admin_user_id:1"), digest)
    row = {"id":9,"format_id":"sinopac","direction":"outgoing","debit":amount,"credit":None,
        "transaction_date":date(2026,11,6),"classification_type":"staff_payout","reconciliation_status":"pending",
        "payout_event_id":None,"currency":"TWD","dedup_fingerprint":"raw:9",
        "bank_references":manual._bank_references("sinopac","","","",manual_command=command)}
    target = {"obligation_identity":"staff:CASE","case_no":"CASE","staff_id":7,
        "direction":"payable_to_staff","status":"open","projection_status":"partially_paid",
        "amount_due_ntd":1000,"net_paid_ntd":100,"balance_ntd":900}
    obligation = StaffPayableFacts("staff:CASE",7,MoneyNTD(1000),(
        StaffPayoutEvent("prior:1",StaffPayoutEventType.PAYOUT,MoneyNTD(100)),))
    return source,row,target,obligation


class Port:
    def __init__(self, source, row, target, obligation):
        self.source=source;self.row=row;self.target=target;self.obligation=obligation
        self.calls=[];self.request=None;self.candidate=None;self.result=None
    def load(self, selection, *, for_update):
        fact=_manual_staff_payout_fact(self.source,selection,(self.row,),(self.target,),(self.obligation,))
        return StaffPayoutReconciliationFacts(4,8,(),(),(self.obligation,),manual_source=fact)
    def find_receipt(self,key):return None
    def bind_apply_request(self,request):self.source.validate_selection(request.selection);self.request=request
    def clear_apply_request(self):self.request=None
    def append_events(self,candidate):self.candidate=candidate;self.calls.append("events")
    def append_obligation_links(self,candidate):self.calls.append("links")
    def append_overpayment_recovery(self,candidate):raise AssertionError("No manual overpayment intent exists")
    def update_payable_projection(self,selection,version,status):
        extra=tuple(StaffPayoutEvent(item.identity,item.event_type,item.amount) for item in self.candidate.events)
        self.result=project_staff_payable(replace(self.obligation,events=self.obligation.events+extra))
        assert self.result.status is status
        self.calls.append("projection")
    def append_outbox(self,candidate):self.calls.append("outbox")
    def save_receipt(self,key,stored):self.calls.append("receipt")


@pytest.mark.parametrize("amount,paid,balance,status",[(300,400,600,"partially_paid"),(870,970,30,"partially_paid"),(900,1000,0,"completed")])
def test_manual_staff_service_uses_real_owner_with_no_bank_hash_or_fee(monkeypatch,amount,paid,balance,status):
    source,row,target,obligation=fixture(amount)
    port=Port(source,row,target,obligation)
    monkeypatch.setattr(manual,"MySqlStaffPayoutRepository",lambda connection,*,manual_source: port if manual_source==source else None)
    receipt=manual.CaseManualSupplementService(NoSqlConnection())._post_staff_payout(
        "CASE",9,"staff:CASE",7,amount,900,"2026-11-06","key","admin_user_id:1","",source.command_digest)
    assert receipt.resulting_status.value==status
    assert port.candidate.events[0].payment_source_kind is StaffPaymentSourceKind.MANUAL_SUPPLEMENT
    assert port.candidate.transfer_fee.amount==0
    assert port.candidate.bank_total.amount==amount
    assert sum(item.allocated_amount.amount for item in port.candidate.obligation_links)==amount
    assert (port.result.net_paid.amount,port.result.balance.amount)==(paid,balance)
    assert port.calls==["events","links","projection","outbox","receipt"]
    assert port.request is None
    metadata=_EventPersistenceMetadata(date(2026,11,6),None,9,None,StaffPaymentSourceKind.MANUAL_SUPPLEMENT)
    request=SimpleNamespace(idempotency_key=IdempotencyKey("key"),actor=source.actor,reason="")
    values=_event_insert_values(request,port.candidate.events[0],metadata,1)
    assert values[5:7]==(None,"manual_supplement")


@pytest.mark.parametrize("mutation",["wrong-case","wrong-staff","wrong-actor","wrong-amount","wrong-date","claimed","projection","digest"])
def test_manual_staff_source_rejects_mismatched_server_metadata_before_effects(monkeypatch,mutation):
    source,row,target,obligation=fixture()
    if mutation=="wrong-case":target["case_no"]="OTHER"
    elif mutation=="wrong-staff":target["staff_id"]=8
    elif mutation=="wrong-actor":row["bank_references"]["manual_command"]["actor"]="admin_user_id:2"
    elif mutation=="wrong-amount":row["debit"]=301
    elif mutation=="wrong-date":row["transaction_date"]=date(2026,11,5)
    elif mutation=="claimed":row["payout_event_id"]=1
    elif mutation=="projection":target["balance_ntd"]=800
    else:row["bank_references"]["manual_command_digest"]="0"*64
    port=Port(source,row,target,obligation)
    monkeypatch.setattr(manual,"MySqlStaffPayoutRepository",lambda *args,**kwargs:port)
    with pytest.raises(StaffPayoutReconciliationError):
        manual.CaseManualSupplementService(NoSqlConnection())._post_staff_payout(
            "CASE",9,"staff:CASE",7,300,900,"2026-11-06","key","admin_user_id:1","",source.command_digest)
    assert port.calls==[]


def test_manual_staff_overpayment_is_blocked_and_bank_account_guard_remains(monkeypatch):
    source,row,target,obligation=fixture(901)
    port=Port(source,row,target,obligation)
    monkeypatch.setattr(manual,"MySqlStaffPayoutRepository",lambda *args,**kwargs:port)
    with pytest.raises(StaffPayoutReconciliationError,match="staff_payout_difference_mode_invalid"):
        manual.CaseManualSupplementService(NoSqlConnection())._post_staff_payout(
            "CASE",9,"staff:CASE",7,901,900,"2026-11-06","key","admin_user_id:1","",source.command_digest)
    assert port.calls==[]
    with pytest.raises(ValueError,match="staff_bank_account_ambiguous"):
        build_staff_payout_candidate((OutgoingBankFact("bank:9",7,MoneyNTD(900)),),(obligation,),require_primary_account_owner=True)
    fact=ManualStaffPayoutFact("9","CASE","staff:CASE",7,MoneyNTD(900),source.command_digest,"raw:9")
    with pytest.raises(ValueError,match="outgoing_bank_fact_not_eligible"):
        build_staff_payout_candidate((fact,),(obligation,),require_primary_account_owner=True)


@pytest.mark.parametrize("field,value",[("actor",ActorContext("display-name")),("command_digest","invalid"),("staff_id",True)])
def test_manual_staff_context_is_closed_and_requires_authenticated_identity_and_digest(field,value):
    source,*_=fixture()
    with pytest.raises(ValueError):
        replace(source,**{field:value})


@pytest.mark.parametrize("kind,bank_hash",[(StaffPaymentSourceKind.MANUAL_SUPPLEMENT,None),(StaffPaymentSourceKind.LEGACY_UNSPECIFIED,"a"*64),(StaffPaymentSourceKind.BANK_STATEMENT,"b"*64)])
def test_reversal_preserves_original_payment_source_without_inventing_bank_hash(kind,bank_hash):
    _,_,_,obligation=fixture()
    reference=_ReopenReference(StaffPayoutEventType.REVERSAL,1,None,date(2026,11,7))
    metadata=_reopen_event_metadata(reference,{"payment_source_kind":kind.value,"bank_account_identity_hash":bank_hash},())
    fact=StaffPayoutReopenFact("reversal:1",StaffPayoutEventType.REVERSAL,7,MoneyNTD(100),"prior:1",payment_source_kind=kind)
    candidate=build_staff_payout_reopen_candidate(fact,(obligation,))
    assert metadata.payment_source_kind is candidate.event.payment_source_kind is kind
    assert metadata.bank_account_identity_hash==bank_hash


def test_bank_return_has_bank_source_even_if_original_payment_was_manual():
    reference=_ReopenReference(StaffPayoutEventType.RETURN,1,10,None)
    metadata=_reopen_event_metadata(reference,{"payment_source_kind":"manual_supplement","bank_account_identity_hash":None},
        ({"id":10,"transaction_date":date(2026,11,7),"resolved_counterparty_account":"synthetic-account"},))
    assert metadata.payment_source_kind is StaffPaymentSourceKind.BANK_STATEMENT
    assert isinstance(metadata.bank_account_identity_hash,str) and len(metadata.bank_account_identity_hash)==64


@pytest.mark.parametrize("kind,bank_hash",[(StaffPaymentSourceKind.MANUAL_SUPPLEMENT,"a"*64),
    (StaffPaymentSourceKind.BANK_STATEMENT,None),(StaffPaymentSourceKind.LEGACY_UNSPECIFIED,None)])
def test_event_values_reject_fake_manual_hash_and_missing_bank_hash_before_sql(kind,bank_hash):
    from domains.staff_payables.reconciliation import StaffPayoutLedgerEventCandidate, StaffPayoutEventStatus
    event=StaffPayoutLedgerEventCandidate("event:9",StaffPayoutEventType.PAYOUT,StaffPayoutEventStatus.SUCCEEDED,
        7,MoneyNTD(300),payment_source_kind=kind)
    metadata=_EventPersistenceMetadata(date(2026,11,6),bank_hash,9,None,kind)
    with pytest.raises(ValueError,match="staff_payment_source_invalid"):
        _event_insert_values(SimpleNamespace(),event,metadata,1)


@pytest.mark.parametrize("failure,status",[(None,200),("scope",404),("projection",409),("storage",503),("preview_storage",503)])
def test_manual_staff_actual_workflow_reaches_original_route_commit_or_typed_rollback(monkeypatch,failure,status):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api.routes.finance_statement_workspace as routes
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import get_accounting_workspace
    from subsystems.finance_import.accounting_workspace import CaseAccounting
    source,row,target,obligation=fixture()
    if failure=="scope":target["case_no"]="OTHER"
    if failure=="projection":target["balance_ntd"]=800
    class BoundaryPort(Port):
        def load(self,selection,*,for_update):
            if failure=="preview_storage":raise StaffPayoutRepositoryUnavailable("synthetic preview storage failure")
            return super().load(selection,for_update=for_update)
        def append_events(self,candidate):
            if failure=="storage":raise StaffPayoutRepositoryUnavailable("synthetic storage failure")
            super().append_events(candidate)
    port=BoundaryPort(source,row,target,obligation)
    class Connection(NoSqlConnection):
        def __init__(self):self.commits=0;self.rollbacks=0
        def commit(self):self.commits+=1
        def rollback(self):self.rollbacks+=1
    connection=Connection()
    monkeypatch.setattr(manual,"MySqlStaffPayoutRepository",lambda *args,**kwargs:port)
    class Service(manual.CaseManualSupplementService):
        def execute(self,**command):
            # Replace SQL staging only, then invoke the real service helper and owner.
            return self._post_staff_payout(command["case_no"],9,command["target_item"],7,command["amount_ntd"],900,
                command["transaction_date"],command["idempotency_key"],command["actor"],command["reason"] or "",source.command_digest)
    monkeypatch.setattr(routes,"CaseManualSupplementService",Service)
    case=CaseAccounting("CASE","Synthetic",None,None,1000,400,0,(),(),(),())
    query_calls=[]
    def query(case_no):
        query_calls.append(case_no)
        return case
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[require_admin]=lambda:SimpleNamespace(id=1,username="synthetic")
    app.dependency_overrides[get_accounting_workspace]=lambda:SimpleNamespace(
        state=SimpleNamespace(connection=connection),query=query)
    with TestClient(app) as client:
        response=client.post("/cases/CASE/manual-supplement",headers={"Idempotency-Key":"key"},json={
            "bank":"sinopac","direction":"staff_salary","target_item":"staff:CASE","amount_ntd":300,
            "transaction_date":"2026-11-06"})
    assert response.status_code==status
    assert (connection.commits,connection.rollbacks)==((1,0) if failure is None else (0,1))
    if failure is None:assert port.result.balance.amount==600
    else:assert port.calls==[]
    assert query_calls==(["CASE"] if failure is None else [])
    if failure=="preview_storage":
        error=response.json()["detail"]["error"]
        assert error["category"]=="unavailable" and error["code"]=="transaction_failed"
        assert error["retryable"] is True


@pytest.mark.parametrize("manual_source",[False,True])
def test_existing_closed_public_preview_hides_only_internal_payment_source(manual_source):
    from api.routes.staff_payout import _preview_payload
    from shared_kernel.identities import CorrelationId
    from domains.staff_payables.reconciliation import StaffPrimaryBankAccount
    source,row,target,obligation=fixture(900)
    selection=StaffPayoutSelection(StaffPayoutEventType.PAYOUT,("9",),("staff:CASE",))
    if manual_source:repository=Port(source,row,target,obligation)
    else:
        facts=StaffPayoutReconciliationFacts(4,8,(OutgoingBankFact("9",7,MoneyNTD(900),"synthetic-account"),),
            (StaffPrimaryBankAccount("synthetic-account",7),),(obligation,))
        repository=SimpleNamespace(load=lambda selection,**kwargs:facts)
    preview=StaffPayoutReconciliationWorkflow(repository,lambda:None).preview(selection,CorrelationId("public-preview"))
    public=_preview_payload(preview,StaffPayoutEventType.PAYOUT)
    assert "payment_source_kind" not in public.model_dump()["candidate"]["events"][0]
    assert public.candidate.events[0].amount.amount==900


def test_public_preview_keeps_rejecting_unknown_fields(monkeypatch):
    import api.routes.staff_payout as route
    from shared_kernel.identities import CorrelationId
    from pydantic import ValidationError
    source,row,target,obligation=fixture(900)
    selection=StaffPayoutSelection(StaffPayoutEventType.PAYOUT,("9",),("staff:CASE",))
    preview=StaffPayoutReconciliationWorkflow(Port(source,row,target,obligation),lambda:None).preview(selection,CorrelationId("public-preview"))
    payload=route._materialize(preview.candidate)
    payload["events"][0]["unexpected_internal_field"]="invalid"
    monkeypatch.setattr(route,"_materialize",lambda candidate:payload)
    with pytest.raises(ValidationError):route._preview_payload(preview,StaffPayoutEventType.PAYOUT)


def test_manual_reversal_uses_the_unchanged_closed_public_event_view():
    from api.routes.staff_payout import _preview_payload
    _,_,_,obligation=fixture()
    fact=StaffPayoutReopenFact("reversal:1",StaffPayoutEventType.REVERSAL,7,MoneyNTD(100),"prior:1",
        payment_source_kind=StaffPaymentSourceKind.MANUAL_SUPPLEMENT)
    candidate=build_staff_payout_reopen_candidate(fact,(obligation,))
    preview=SimpleNamespace(candidate=candidate,staff_payables_version=4,bank_facts_version=8,fingerprint=candidate.fingerprint)
    public=_preview_payload(preview,StaffPayoutEventType.REVERSAL)
    assert "payment_source_kind" not in public.model_dump()["candidate"]["event"]
    assert public.candidate.event.amount.amount==100

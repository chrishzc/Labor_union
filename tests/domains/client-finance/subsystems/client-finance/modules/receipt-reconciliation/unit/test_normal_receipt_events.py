"""Successful non-deposit receipts must not fabricate financial anomalies."""
from types import SimpleNamespace
import json
import pytest

from domains.client_finance.reconciliation import PaymentStage, IncomingBankFact, ClientObligation
from shared_kernel.money import MoneyNTD
from shared_kernel.identities import ExpectedVersion, IdempotencyKey, ActorContext, CorrelationId
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationFacts, ClientReconciliationWorkflow, ReconciliationSelection, ClientReconciliationApplyRequest,
)


@pytest.mark.parametrize('stage',list(PaymentStage))
@pytest.mark.parametrize('overage',[False,True])
def test_only_real_discrepancies_create_anomaly_intents(stage,overage):
    calls=[]
    class Repo:
        def load(self,*_,**__):return ClientReconciliationFacts(1,
            (IncomingBankFact('bank',MoneyNTD(110 if overage else 100),stage),),
            (ClientObligation('ob','CASE',MoneyNTD(100),stage),))
        def find_receipt(self,_):return None
        def validate_overage_refund_recipient(self,_):pass
        def append_ledger_entries(self,_):calls.append('ledger')
        def append_allocations(self,_):calls.append('allocation')
        def update_projection(self,*_):calls.append('projection')
        def establish_overage_refund(self,*_):calls.append('overage-refund')
        def append_orders_deposit_intent(self,_):calls.append('deposit')
        def append_anomaly_intent(self,_):calls.append('anomaly')
        def save_receipt(self,*_):calls.append('receipt')
    class Unit:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def commit(self):calls.append('commit')
    selection=ReconciliationSelection('CASE',stage,('bank',),('ob',),allow_overage_disposition=overage)
    workflow=ClientReconciliationWorkflow(Repo(),Unit);preview=workflow.preview(selection)
    workflow.apply(ClientReconciliationApplyRequest(selection,ExpectedVersion(1),preview.fingerprint,
        IdempotencyKey('test'),ActorContext('synthetic'),'test',CorrelationId('test')))
    assert ('anomaly' in calls)==(overage and stage is not PaymentStage.DEPOSIT)
    assert ('deposit' in calls)==(stage is PaymentStage.DEPOSIT)
    assert calls[-1]=='commit'


def test_second_payment_success_marker_uses_the_existing_projection_outbox():
    from infrastructure.mysql.client_receipt_reconciliation_repository import _append_projection_outbox
    written=[]
    cursor=SimpleNamespace(execute=lambda sql,params:written.append((sql,params)))
    for stage in (PaymentStage.FIRST,PaymentStage.SECOND):
        request=SimpleNamespace(selection=ReconciliationSelection('CASE',stage,('bank',),('ob',)),idempotency_key=IdempotencyKey('test'))
        _append_projection_outbox(cursor,request,'a'*64,2,{'ob':100})
        _,parameters=written[-1];payload=json.loads(parameters[3])
        assert parameters[1]=='projection_refresh'
        assert payload.get('line_second_payment_notification',False)==(stage is PaymentStage.SECOND)
        if stage is PaymentStage.SECOND:
            assert payload['obligation_identities']==['ob'] and payload['amount_ntd']==100


def test_partial_deposit_does_not_release_order_or_claim_customer_payment_complete():
    calls=[]
    class Repo:
        def load(self,*_,**__):return ClientReconciliationFacts(1,(IncomingBankFact('bank',MoneyNTD(9000),PaymentStage.DEPOSIT),),(ClientObligation('ob','CASE',MoneyNTD(10000),PaymentStage.DEPOSIT),))
        def find_receipt(self,_):return None
        def append_ledger_entries(self,candidate):calls.append(('cash',candidate.bank_total.amount))
        def append_allocations(self,candidate):calls.append(('allocated',sum(a.amount.amount for a in candidate.allocations)))
        def update_projection(self,*_):calls.append('projection')
        def append_orders_deposit_intent(self,_):raise AssertionError('partial deposit must not release order')
        def append_anomaly_intent(self,_):raise AssertionError('staff choice must not create another warning')
        def save_receipt(self,*_):calls.append('receipt')
    class Unit:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def commit(self):calls.append('commit')
    selection=ReconciliationSelection('CASE',PaymentStage.DEPOSIT,('bank',),('ob',),allow_partial_receipt=True)
    workflow=ClientReconciliationWorkflow(Repo(),Unit);preview=workflow.preview(selection)
    receipt=workflow.apply(ClientReconciliationApplyRequest(selection,ExpectedVersion(1),preview.fingerprint,IdempotencyKey('partial'),ActorContext('synthetic'),'餘額續收',CorrelationId('partial')))
    assert receipt.status.value=='partial' and ('cash',9000) in calls and ('allocated',9000) in calls
    assert calls[-1]=='commit'
    from infrastructure.mysql.client_receipt_reconciliation_repository import _append_projection_outbox
    written=[]
    cursor=SimpleNamespace(execute=lambda sql,params:written.append(params))
    request=SimpleNamespace(selection=ReconciliationSelection('CASE',PaymentStage.FIRST,('bank',),('ob',),allow_partial_receipt=True),idempotency_key=IdempotencyKey('partial'))
    _append_projection_outbox(cursor,request,'a'*64,2,{'ob':10000},fully_settled=False)
    assert not json.loads(written[0][3]).get('line_first_payment_notification')
    _append_projection_outbox(cursor,request,'b'*64,3,{'ob':1000},fully_settled=True,receipt_amounts={'ob':1000})
    assert json.loads(written[-1][3])['amount_ntd']==1000

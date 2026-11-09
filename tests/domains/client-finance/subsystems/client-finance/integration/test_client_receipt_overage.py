from domains.client_finance.reconciliation import (
    ClientObligation,
    IncomingBankFact,
    PaymentStage,
    ReconciliationStatus,
    build_reconciliation_candidate,
)
from shared_kernel.money import MoneyNTD
import pytest

from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationError,
    ClientReconciliationFacts,
    ClientReconciliationWorkflow,
    ReconciliationSelection,
)


@pytest.mark.parametrize('amounts', [(9000,1000),(5000,5000)])
@pytest.mark.parametrize('missing_due', [False,True])
def test_combined_same_case_receipt_preview_apply_and_replay_preserve_each_source(amounts, missing_due):
    from datetime import date
    banks = tuple(IncomingBankFact(str(i),MoneyNTD(amount),None) for i,amount in enumerate(amounts,1))
    obligation = ClientObligation('first:CASE','CASE',MoneyNTD(10000),PaymentStage.FIRST,
                                  None if missing_due else date(2026,10,15))
    class Repository:
        version=0
        receipts={}
        entries=[]
        allocations=[]
        commits=0
        def load(self, selection, *, for_update):
            return ClientReconciliationFacts(self.version, banks if not self.entries else (),
                                              (obligation,) if not self.entries else ())
        def find_receipt(self,key): return self.receipts.get(key.value)
        def append_ledger_entries(self,candidate): self.entries.extend(banks)
        def append_allocations(self,candidate): self.allocations.extend(candidate.allocations)
        def update_projection(self,selection,version): self.version=version
        def append_orders_deposit_intent(self,candidate): pass
        def append_anomaly_intent(self,candidate): raise AssertionError('exact combined cash is not an anomaly')
        def validate_overage_refund_recipient(self,case): raise AssertionError('exact collection does not require a refund account')
        def save_receipt(self,key,receipt): self.receipts[key.value]=receipt
        def bind_apply_request(self,request): pass
        def clear_apply_request(self): pass
    repository=Repository()
    class Unit:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def commit(self):repository.commits+=1
    workflow=ClientReconciliationWorkflow(repository,Unit)
    selection=ReconciliationSelection('CASE',None,('1','2'),('first:CASE',))
    preview=workflow.preview(selection)
    assert preview.candidate.status is ReconciliationStatus.EXACT
    assert preview.candidate.blockers == ()
    assert preview.candidate.bank_total.amount == preview.candidate.obligation_total.amount == 10000
    assert repository.entries == repository.allocations == []
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from api.routes.client_receipt_reconciliation import router
    from api.dependencies.admin_auth import require_system_admin
    from api.dependencies.client_receipt_reconciliation import ClientReceiptReconciliationApplication, get_client_receipt_reconciliation_application
    application=ClientReceiptReconciliationApplication(repository,workflow)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_system_admin]=lambda:SimpleNamespace(username='synthetic')
    app.dependency_overrides[get_client_receipt_reconciliation_application]=lambda:application
    base='/api/v1/orders/CASE/client-finance/receipt-reconciliation'
    body={'payment_stage':None,'finance_import_row_ids':[1,2],'obligation_identities':['first:CASE']}
    with TestClient(app) as client:
        response=client.post(base+'/preview',json=body)
        assert response.status_code==200,response.text
        payload=response.json()['data']
        assert payload['candidate']['status']=='exact'
        assert payload['preview_fingerprint']==preview.fingerprint.value
        assert repository.entries==repository.allocations==[]
        command={**body,'expected_account_version':0,'preview_fingerprint':payload['preview_fingerprint'],'reason':'合成同案合計足額'}
        headers={'Idempotency-Key':'combined','X-Correlation-ID':'combined'}
        applied=client.post(base+'/apply',json=command,headers=headers)
        assert applied.status_code==200,applied.text
        receipt=applied.json()['data']
        assert receipt['status']==payload['candidate']['status']
        assert receipt['ledger_entry_count']==2
        replay=client.post(base+'/apply',json=command,headers=headers)
        assert replay.status_code==200 and replay.json()['data']==receipt
    assert repository.allocations == list(preview.candidate.allocations)
    assert [(entry.identity,entry.amount.amount) for entry in repository.entries] == [('1',amounts[0]),('2',amounts[1])]
    assert sum(item.amount.amount for item in repository.allocations) == 10000
    assert len(repository.entries)==2 and len(repository.allocations)==2
    assert repository.version==repository.commits==1
    assert obligation.due_date is None if missing_due else obligation.due_date == date(2026,10,15)


def test_client_receipt_overage_is_blocked_by_the_normal_action() -> None:
    candidate = build_reconciliation_candidate(_bank_facts(3000), _obligations(2500))

    assert candidate.status is ReconciliationStatus.REVIEW_REQUIRED
    assert candidate.blockers == ("client_receipt_overpaid",)
    assert candidate.allocations == ()


def test_client_receipt_overage_disposition_preserves_cash_and_creates_refund_amount() -> None:
    candidate = build_reconciliation_candidate(
        _bank_facts(3000),
        _obligations(2500),
        allow_overage_disposition=True,
    )

    assert candidate.status is ReconciliationStatus.OVERAGE
    assert candidate.bank_total == MoneyNTD(3000)
    assert sum(item.amount.amount for item in candidate.allocations) == 2500
    assert candidate.overage_amount == MoneyNTD(500)
    assert candidate.blockers == ("client_receipt_overpaid",)


def _bank_facts(amount: int) -> tuple[IncomingBankFact, ...]:
    return (IncomingBankFact("row-1", MoneyNTD(amount), PaymentStage.DEPOSIT),)


def _obligations(amount: int) -> tuple[ClientObligation, ...]:
    return (
        ClientObligation(
            "case-1:deposit",
            "case-1",
            MoneyNTD(amount),
            PaymentStage.DEPOSIT,
        ),
    )


def test_partial_receipt_requires_explicit_choice_and_preserves_unreceived_balance():
    normal = build_reconciliation_candidate(_bank_facts(9000), _obligations(10000))
    assert normal.status is ReconciliationStatus.REVIEW_REQUIRED
    assert normal.allocations == ()
    selected = build_reconciliation_candidate(_bank_facts(9000), _obligations(10000), allow_partial_receipt=True)
    assert selected.status is ReconciliationStatus.PARTIAL
    assert selected.bank_total.amount == 9000
    assert selected.obligation_total.amount - sum(a.amount.amount for a in selected.allocations) == 1000
    assert selected.settlement_identity != normal.settlement_identity
    assert selected.overage_amount.amount == 0


def test_two_same_case_bank_entries_can_be_reconciled_directly_by_their_total():
    banks = tuple(IncomingBankFact(str(i), MoneyNTD(value), PaymentStage.DEPOSIT) for i,value in enumerate((9000,1000)))
    candidate = build_reconciliation_candidate(banks, _obligations(10000))
    assert candidate.status is ReconciliationStatus.EXACT
    assert not candidate.blockers
    assert [a.amount.amount for a in candidate.allocations] == [9000,1000]


def test_case_level_preview_api_accepts_multiple_stages_without_a_phase_picker():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.client_receipt_reconciliation import router
    from api.dependencies.client_receipt_reconciliation import get_client_receipt_reconciliation_application
    from api.dependencies.admin_auth import require_system_admin
    from types import SimpleNamespace
    class Repository:
        def load(self, selection, *, for_update):
            return ClientReconciliationFacts(1,tuple(IncomingBankFact(str(identity),MoneyNTD(amount),selection.payment_stage) for identity,amount in ((9,9000),(10,1000))),tuple(ClientObligation(stage,'CASE',MoneyNTD(5000),PaymentStage(stage)) for stage in ('first','second')))
    workflow=ClientReconciliationWorkflow(Repository(),lambda:None)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_system_admin]=lambda:object()
    app.dependency_overrides[get_client_receipt_reconciliation_application]=lambda:SimpleNamespace(preview=workflow.preview)
    with TestClient(app) as client:
        response=client.post('/api/v1/orders/CASE/client-finance/receipt-reconciliation/preview',json={'finance_import_row_ids':[9,10],'obligation_identities':['first','second']})
    assert response.status_code==200
    assert response.json()['data']['candidate']['payment_stage'] is None
    assert response.json()['data']['candidate']['status']=='exact'


def test_missing_refund_account_has_the_same_preview_and_fresh_apply_reason_before_writes():
    from unittest.mock import MagicMock, Mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.client_receipt_reconciliation import router
    from api.dependencies.client_receipt_reconciliation import ClientReceiptReconciliationApplication, get_client_receipt_reconciliation_application
    from api.dependencies.admin_auth import require_system_admin
    from types import SimpleNamespace

    repository=Mock()
    repository.load.return_value=ClientReconciliationFacts(1,_bank_facts(3000),_obligations(2500))
    repository.find_receipt.return_value=None
    unit=MagicMock()
    workflow=ClientReconciliationWorkflow(repository,lambda:unit)
    selection=ReconciliationSelection('case-1',PaymentStage.DEPOSIT,('row-1',),('case-1:deposit',),allow_overage_disposition=True)
    valid=workflow.preview(selection)
    repository.validate_overage_refund_recipient.side_effect=ValueError('client_refund_recipient_snapshot_missing')
    # A preview accepted before the account disappeared must still fail before the first writer.
    request=ClientReconciliationApplyRequest(selection,ExpectedVersion(1),valid.fingerprint,IdempotencyKey('missing-account'),ActorContext('synthetic'),'多收另列退款',CorrelationId('missing-account'))
    with pytest.raises(ValueError,match='^client_refund_recipient_snapshot_missing$'):
        workflow.preview(selection)
    with pytest.raises(ValueError,match='^client_refund_recipient_snapshot_missing$'):
        workflow.apply(request)
    for name in ('append_ledger_entries','append_allocations','update_projection','establish_overage_refund','save_receipt'):
        getattr(repository,name).assert_not_called()
    unit.commit.assert_not_called()

    # Exercise the public API error envelope too, preserving the original formal failure code.
    repository.load.return_value=ClientReconciliationFacts(1,(IncomingBankFact('9',MoneyNTD(3000),PaymentStage.DEPOSIT),),_obligations(2500))
    application=ClientReceiptReconciliationApplication(repository,workflow)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_system_admin]=lambda:SimpleNamespace(username='synthetic')
    app.dependency_overrides[get_client_receipt_reconciliation_application]=lambda:application
    body={'payment_stage':'deposit','finance_import_row_ids':[9],'obligation_identities':['case-1:deposit']}
    with TestClient(app) as client:
        preview=client.post('/api/v1/orders/case-1/client-finance/receipt-reconciliation/overage/preview',json=body)
        applied=client.post('/api/v1/orders/case-1/client-finance/receipt-reconciliation/overage/apply',json={**body,'expected_account_version':1,'preview_fingerprint':'c'*64,'reason':''},headers={'Idempotency-Key':'api-missing-account','X-Correlation-ID':'api-missing-account'})
    assert preview.status_code==applied.status_code==422
    assert preview.json()['detail']['error']['code']==applied.json()['detail']['error']['code']=='client_refund_recipient_snapshot_missing'
    repository.append_ledger_entries.assert_not_called()


@pytest.mark.parametrize('amount,allow_partial,allow_overage,expected',[
    (2500,False,False,'exact'),(2000,True,False,'partial'),
    (3000,False,False,'review_required'),(2500,False,True,'exact'),
])
def test_account_check_only_runs_when_the_preview_actually_creates_an_overage_refund(amount,allow_partial,allow_overage,expected):
    from unittest.mock import Mock
    repository=Mock()
    repository.load.return_value=ClientReconciliationFacts(1,_bank_facts(amount),_obligations(2500))
    repository.validate_overage_refund_recipient.side_effect=AssertionError('No refund is being created')
    selection=ReconciliationSelection('case-1',PaymentStage.DEPOSIT,('row-1',),('case-1:deposit',),allow_overage_disposition=allow_overage,allow_partial_receipt=allow_partial)
    assert ClientReconciliationWorkflow(repository,lambda:None).preview(selection).candidate.status.value==expected
    repository.validate_overage_refund_recipient.assert_not_called()


@pytest.mark.parametrize('rows',[
    (),({'refund_bank_code':'0000000','refund_account_no':None},),
    ({'refund_bank_code':None,'refund_account_no':'000000001'},),
    ({'refund_bank_code':'0000000','refund_account_no':'000000001'},)*2,
])
def test_overage_preflight_and_snapshot_writer_use_the_same_effective_account_reader_without_preview_writes(rows):
    from unittest.mock import MagicMock
    from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository,_insert_refund_recipient_snapshot
    cursor=MagicMock();cursor.fetchall.return_value=rows;cursor.fetchone.return_value=None
    connection=MagicMock();connection.cursor.return_value.__enter__.return_value=cursor
    repository=MySqlClientReceiptReconciliationRepository(connection)
    with pytest.raises(ValueError,match='^client_refund_recipient_snapshot_missing$'):
        repository.validate_overage_refund_recipient('case-1')
    assert all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list)
    with pytest.raises(ValueError,match='^client_refund_recipient_snapshot_missing$'):
        _insert_refund_recipient_snapshot(cursor,'refund:case-1','case-1','receipt_overage')
    assert all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list)

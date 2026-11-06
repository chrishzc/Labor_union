"""Actual manual-initial API/application with typed persistence ports; no SQL."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import OperationalError
import pytest

from api.dependencies.admin_auth import require_system_admin
import api.routes.government_subsidy_periods as routes
from domains.government_subsidy.period_reconciliation import (
    GovernmentPeriodBalance, PeriodReconciliationConflict, SubsidyPeriod, SubsidyPeriodLine, require_government_initial_receipt,
)
from infrastructure.mysql.government_subsidy_manual_period_source import (
    manual_initial_references, require_manual_initial_source, verified_manual_initial_receipt,
    manual_initial_receipt_readback,
)
from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource, _cash_flow
from infrastructure.mysql.finance_statement_archive_repository import _successful_statement_rows
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.government_subsidy.period_reconciliation import (
    ManualInitialPeriodReceipt, ManualInitialPeriodSource, PeriodCoverage, PeriodReconciliationApplication, SubsidyPeriodView,
)


def command(amount=1000, handling='exact', **changes):
    return replace(ManualInitialPeriodReceipt(SubsidyPeriod('quarter',2026,1),amount,date(2027,11,6),handling,'',2,'manual-key','admin:1'), **changes)


def source_row(cmd, *, status='pending'):
    return {'id':9,'format_id':'legacy','transaction_date':cmd.paid_on,'direction':'incoming','credit':cmd.amount_ntd,
            'debit':None,'currency':'TWD','classification_type':'government_subsidy','reconciliation_status':status,
            'bank_references':manual_initial_references(cmd),'raw_payload':{'摘要':'人工補登','存入':cmd.amount_ntd}}


def period_entry(cmd):
    return {'period_unit':cmd.period.unit,'period_year':cmd.period.year,'period_index':cmd.period.index,
            'finance_import_row_id':9,'amount_ntd':cmd.amount_ntd,'paid_on':cmd.paid_on,'actor':cmd.actor,
            'idempotency_key':cmd.owner_key,'reversal_of_id':None}


def stored_receipt_fields(cmd):
    return {'stored_key':cmd.key,'stored_digest':cmd.digest,'stored_actor':cmd.actor,'stored_result_identity':'government-manual:9:42'}


class ManualPort:
    def __init__(self, failure=None):
        self.failure=failure; self.calls=[]; self.rows={}; self.receipts={}; self.entries={}
        self.view=SubsidyPeriodView(SubsidyPeriod('quarter',2026,1),2,
            (SubsidyPeriodLine('CASE-1',date(2026,1,15),1000,None),),1000,(),(),(),(),True)
    def find_manual_initial_replay(self, cmd):
        self.calls.append('replay')
        prior=self.receipts.get(cmd.key)
        if prior is None:return None
        if prior!=cmd.digest:raise PeriodReconciliationConflict('subsidy_period_manual_idempotency_conflict')
        if not verified_manual_initial_receipt(self.rows[9],self.entries[42]):
            raise PeriodReconciliationConflict('subsidy_period_manual_source_invalid')
        return 42
    def query(self, period, *, lock=False):
        assert period==self.view.period
        self.calls.append('lock_query' if lock else 'query')
        if not lock and self.failure=='query_storage':raise OperationalError(2006,'synthetic readback unavailable')
        if not lock and self.failure=='view':
            return replace(self.view,coverage=(replace(self.view.coverage[0],source_label='raw-untrusted-label'),))
        if not lock and self.failure=='coverage_missing':return replace(self.view,coverage=())
        if not lock and self.failure=='readback_amount':return replace(self.view,coverage=(replace(self.view.coverage[0],amount_ntd=999),))
        if not lock and self.failure=='typed_view':return replace(self.view,lines=(replace(self.view.lines[0],amount_ntd='not-money'),))
        if not lock and self.failure=='unsafe_view':return replace(self.view,lines=(replace(self.view.lines[0],amount_ntd=9007199254740992),))
        return self.view
    def append_manual_initial_source(self, cmd):
        self.calls.append('append_source');self.rows[9]=source_row(cmd)
        return ManualInitialPeriodSource(9,cmd)
    def save_manual_initial(self, view, source):
        self.calls.append('source_proof')
        if self.failure=='source':self.rows[9]['bank_references']['manual_command_digest']='0'*64
        require_manual_initial_source(source,self.rows[9])
        self.calls.append('bank_guards')
        if self.failure=='bank':raise PeriodReconciliationConflict('subsidy_period_bank_already_used')
        if self.failure=='storage':raise OperationalError(2006,'synthetic source storage unavailable')
        expected=require_government_initial_receipt(view.lines,source.command.amount_ntd,source.command.handling)
        self.calls.extend(['owner_save','members','client_sync','balance','operation'])
        cmd=source.command
        self.entries[42]=period_entry(cmd);self.rows[9]['reconciliation_status']='reconciled'
        balance=GovernmentPeriodBalance('government-period:42',42,'original',None,'receivable',expected,cmd.amount_ntd,0,0)
        self.view=replace(view,version=3,coverage=(PeriodCoverage(42,cmd.period,cmd.amount_ntd,0,balance.settled,'人工補登'),),
            recorded_lines=view.lines,balances=(balance,),can_reconcile=False)
        return 42
    def save_manual_initial_receipt(self, cmd, source, identity):
        self.calls.append('command_receipt');assert (source.row_id,identity)==(9,42)
        self.receipts[cmd.key]=cmd.digest
    def read_manual_initial_receipt(self, cmd, identity):
        self.calls.append('proof_readback')
        row={**self.rows[9],**stored_receipt_fields(cmd),'receipt_id':identity,'period_receipt':self.entries[identity]}
        if self.failure=='proof_source':row['bank_references']=manual_initial_references(replace(cmd,key='other-key'))
        return manual_initial_receipt_readback((row,),cmd,identity)


class NoSqlConnection:
    def __init__(self, port):self.port=port;self.events=[];self.snapshot=None
    def cursor(self):raise AssertionError('Project SQL including fake SQL is forbidden')
    def begin(self):
        self.events.append('begin');self.snapshot=deepcopy((self.port.rows,self.port.receipts,self.port.entries,self.port.view))
    def commit(self):self.events.append('commit')
    def rollback(self):
        self.events.append('rollback')
        self.port.rows,self.port.receipts,self.port.entries,self.port.view=self.snapshot


def client_for(*, failure=None, principal=None):
    port=ManualPort(failure);connection=NoSqlConnection(port)
    application=PeriodReconciliationApplication(port,lambda:MySqlUnitOfWork(connection))
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[require_system_admin]=lambda:principal or AdminPrincipal(1,'synthetic','Synthetic','system_admin')
    app.dependency_overrides[routes.get_application]=lambda:application
    return TestClient(app),port,connection


def body(amount=1000,handling='exact',**changes):
    return {'unit':'quarter','year':2026,'index':1,'amount_ntd':amount,'paid_on':'2027-11-06',
            'handling':handling,'reason':'','expected_version':2,'key':'manual-key',**changes}


@pytest.mark.parametrize('amount,handling,remaining,refund',[(1000,'exact',0,0),(300,'partial',700,0),(1100,'refund_excess',0,100)])
def test_public_initial_manual_receipt_uses_original_domain_and_typed_readback_without_bank_fabrication(amount,handling,remaining,refund):
    client,port,connection=client_for()
    with client:response=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body(amount,handling))
    assert response.status_code==200,response.text
    data=response.json()['data'];assert data['receipt_id']==42
    assert data['receipt']=={'receipt_id':42,'period':{'unit':'quarter','year':2026,'index':1},
        'amount_ntd':amount,'paid_on':'2027-11-06','source_label':'人工補登','key':'manual-key'}
    assert data['view']['period']=={'unit':'quarter','year':2026,'index':1}  # paid date never chooses period
    assert data['view']['coverage'][0]['source_label']=='人工補登'
    assert data['view']['balances'][0]['remaining_ntd']==remaining and data['view']['balances'][0]['refund_due_ntd']==refund
    assert port.calls==['replay','lock_query','append_source','source_proof','bank_guards','owner_save','members','client_sync','balance','operation','command_receipt','query','proof_readback']
    assert connection.events==['begin','commit']
    row=port.rows[9]
    assert row['format_id']=='legacy' and row.get('source_file') is None and row.get('source_bank_account') is None
    assert row.get('provider_message_id') is None and row.get('batch_id') is None
    assert len(port.rows)==len(port.entries)==len(port.receipts)==1


def test_same_original_command_replays_before_first_only_gate_and_new_or_changed_command_cannot_duplicate():
    client,port,connection=client_for()
    with client:
        first=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body())
        assert first.status_code==200
        port.calls.clear();connection.events.clear()
        replay=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body())
        assert replay.status_code==200 and replay.json()==first.json()
        assert port.calls==['replay','query','proof_readback'] and connection.events==['begin','commit']
        port.calls.clear();connection.events.clear()
        changed=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body(reason='changed'))
        assert changed.status_code==409 and port.calls==['replay']
        assert connection.events==['begin','rollback']
        port.calls.clear();connection.events.clear()
        new=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body(key='another-key',expected_version=3))
        assert new.status_code==409 and new.json()['detail']['error']['code']=='subsidy_period_already_covered'
        assert port.calls==['replay','lock_query'] and connection.events==['begin','rollback']
    assert len(port.rows)==len(port.entries)==len(port.receipts)==1


@pytest.mark.parametrize('failure,status,code',[
    ('source',409,'subsidy_period_manual_source_invalid'),('bank',409,'subsidy_period_bank_already_used'),
    ('storage',503,'transaction_failed'),('query_storage',503,'transaction_failed'),('view',409,'subsidy_period_manual_readback_invalid'),
    ('coverage_missing',409,'subsidy_period_manual_readback_invalid'),('readback_amount',409,'subsidy_period_manual_readback_invalid'),
    ('typed_view',422,'subsidy_period_manual_initial_invalid'),
    ('proof_source',409,'subsidy_period_manual_readback_invalid'),
    ('unsafe_view',422,'subsidy_period_manual_numeric_unrepresentable'),
])
def test_source_owner_or_precommit_readback_failure_rolls_back_the_same_transaction(failure,status,code):
    client,port,connection=client_for(failure=failure)
    with client:response=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body())
    assert response.status_code==status,response.text
    assert response.json()['detail']['error']['code']==code
    if failure=='unsafe_view':assert '勿為提交而改動金額' in response.json()['detail']['error']['message']
    assert connection.events==['begin','rollback'] and port.rows==port.entries==port.receipts=={}
    # This proves real UoW rollback dispatch over typed staged ports, not SQL atomicity.


@pytest.mark.parametrize('state,code', [('stale','subsidy_period_stale'),('balance','subsidy_period_already_covered'),
    ('blocked','subsidy_case_already_covered'),('incomplete','subsidy_period_incomplete'),('handling','subsidy_period_handling_required')])
def test_first_receipt_preconditions_reject_before_any_source_append(state,code):
    client,port,connection=client_for()
    if state=='balance':port.view=replace(port.view,balances=(GovernmentPeriodBalance('old',8,'original',None,'receivable',1000,1000,0,0),))
    if state=='blocked':port.view=replace(port.view,blocked_cases=('CASE-1',))
    if state=='incomplete':port.view=replace(port.view,lines=(SubsidyPeriodLine('CASE-1',date(2026,1,15),None,'missing'),))
    with client:response=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body(
        300 if state=='handling' else 1000,expected_version=1 if state=='stale' else 2))
    assert response.status_code==409 and response.json()['detail']['error']['code']==code
    assert port.rows=={} and port.calls==['replay','lock_query'] and connection.events==['begin','rollback']


@pytest.mark.parametrize('extra',[{'action':'receipt'},{'action':'refund'},{'bank_row_id':7},{'actor':'admin:2'},{'bank':'taishin'},{'amount_ntd':True},{'amount_ntd':9007199254740992}])
def test_manual_initial_transport_rejects_followups_and_caller_owned_provenance(extra):
    client,port,connection=client_for()
    with client:response=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body(**extra))
    assert response.status_code==422 and port.calls==[] and connection.events==[]
    if extra.get('amount_ntd')==9007199254740992:
        assert response.json()['detail'][0]['type']=='subsidy_period_manual_numeric_unrepresentable'
        assert '勿為提交而改動金額' in response.json()['detail'][0]['msg']


@pytest.mark.parametrize('field,value', [('credit',1001),('transaction_date',date(2027,11,5)),('format_id','taishin'),
    ('direction','outgoing'),('currency','USD'),('classification_type','client_receipt'),('reconciliation_status','reconciled'),
    ('batch_id',1),('source_reference','fake-provider-id'),('source_file','fake-bank-statement'),('source_bank_account','fake-account')])
def test_typed_manual_source_proof_rejects_metadata_drift(field,value):
    cmd=command();source=ManualInitialPeriodSource(9,cmd)
    with pytest.raises(PeriodReconciliationConflict,match='manual_source_invalid'):
        require_manual_initial_source(source,{**source_row(cmd),field:value})


def test_manual_cash_readback_and_export_use_exact_receipt_proof_and_never_guess_taishin_or_allocate_to_cases():
    cmd=command();entry=period_entry(cmd)
    row={**source_row(cmd,status='reconciled'),'government_proof':1,'case_no':'CASE-1','period_receipt':entry}
    assert _cash_flow(row)==(None,'G')
    assert _cash_flow({**row,'period_receipt':{**entry,'actor':'admin:2'}})==(None,None)
    assert _cash_flow({**row,'period_receipt':None})==(None,None)
    facts=MySqlMonthlyAccountingSource._facts((row,{**row,'case_no':'CASE-2'}))
    assert len(facts)==1 and facts[0].amount_ntd==1000 and facts[0].cases==('CASE-1','CASE-2')
    assert facts[0].bank is None and facts[0].cash_flow=='G'
    exported=_successful_statement_rows((row,{**row,'case_no':'CASE-2'}),())
    assert len(exported)==1 and exported[0].source=='人工補登' and exported[0].bank=='manual'
    assert exported[0].cases==('CASE-1','CASE-2') and dict(exported[0].fields)['存入']==1000


@pytest.mark.parametrize('change', [{'actor':'admin:2'}, {'period':SubsidyPeriod('quarter',2026,2)}, {'handling':'partial'}, {'reason':'other'}])
def test_a_recomputed_metadata_digest_cannot_replace_the_server_command(change):
    original=command();forged=replace(original,**change)
    row=source_row(original);row['bank_references']=manual_initial_references(forged)
    with pytest.raises(PeriodReconciliationConflict,match='manual_source_invalid'):
        require_manual_initial_source(ManualInitialPeriodSource(9,original),row)


def test_original_immutable_receipt_replays_after_a_legal_bank_reversal_without_fabricating_current_coverage():
    client,port,connection=client_for()
    with client:
        first=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body())
        assert first.status_code==200
        port.view=replace(port.view,coverage=(),balances=(),can_reconcile=True)
        port.calls.clear();connection.events.clear()
        replay=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body())
    assert replay.status_code==200
    data=replay.json()['data']
    assert data['receipt_id']==42 and data['receipt']==first.json()['data']['receipt']
    assert data['view']['coverage']==[] and port.calls==['replay','query','proof_readback']
    assert connection.events==['begin','commit'] and len(port.rows)==len(port.entries)==1
    # The typed port models the authorized reversal's current query only;
    # actual bank reversal persistence is unchanged and not executed here.


@pytest.mark.parametrize('paid_on',[0,1793923200,1793923200.0,True,'2027-11-06T00:00:00','2027-11-06T00:00:00Z','2027-02-30'])
def test_actual_paid_date_accepts_only_a_valid_iso_calendar_date_string(paid_on):
    client,port,connection=client_for()
    with client:response=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body(paid_on=paid_on))
    assert response.status_code==422 and port.calls==[] and connection.events==[]


def test_manual_source_requires_an_immutable_persisted_admin_identity():
    client,port,connection=client_for(principal=AdminPrincipal(None,'synthetic','Synthetic','system_admin'))
    with client:response=client.post('/api/v1/government-subsidy/periods/manual-initial-receipt',json=body())
    assert response.status_code==403 and response.json()['detail']['error']['code']=='subsidy_period_manual_actor_required'
    assert port.calls==[] and connection.events==[]


def test_original_long_key_is_preserved_while_the_existing_owner_receipt_key_stays_bounded():
    cmd=command(key='a'*191)
    assert len(cmd.owner_key)<=100 and manual_initial_references(cmd)['manual_command']['key']==cmd.key
    row={**source_row(cmd,status='reconciled'),**stored_receipt_fields(cmd),'receipt_id':42,'period_receipt':period_entry(cmd)}
    receipt=manual_initial_receipt_readback((row,),cmd,42)
    assert receipt.key==cmd.key and receipt.paid_on==row['period_receipt']['paid_on']


@pytest.mark.parametrize('field,value', [('stored_key','other-key'),('stored_digest','0'*64),('stored_actor','admin:2'),
    ('stored_result_identity','government-manual:99:42'),('receipt_id',43)])
def test_immutable_readback_requires_the_actual_original_command_receipt(field,value):
    cmd=command()
    row={**source_row(cmd,status='reconciled'),**stored_receipt_fields(cmd),'receipt_id':42,'period_receipt':period_entry(cmd)}
    row[field]=value
    with pytest.raises(PeriodReconciliationConflict,match='manual_readback_invalid'):
        manual_initial_receipt_readback((row,),cmd,42)


def test_successful_statement_http_export_keeps_one_manual_period_cash_row_and_its_actual_source_label():
    from io import BytesIO
    from openpyxl import load_workbook
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import get_statement_archive_application
    import api.routes.finance_statement_workspace as archive_routes
    from subsystems.finance_import.statement_archive import StatementArchiveApplication
    cmd=command()
    row={**source_row(cmd,status='reconciled'),'period_receipt':period_entry(cmd),'case_no':'CASE-1'}
    class ArchivePort:
        def export_rows(self):return _successful_statement_rows((row,{**row,'case_no':'CASE-2'}),())
    application=StatementArchiveApplication(ArchivePort(),lambda:None)
    app=FastAPI();app.include_router(archive_routes.router)
    app.dependency_overrides[require_admin]=lambda:AdminPrincipal(1,'synthetic','Synthetic','system_admin')
    app.dependency_overrides[get_statement_archive_application]=lambda:application
    with TestClient(app) as client:response=client.get('/statements/export')
    assert response.status_code==200
    workbook=load_workbook(BytesIO(response.content),read_only=True)
    values=list(workbook.active.values);headers=values[0]
    assert len(values)==2 and values[1][headers.index('存入')]==1000
    assert values[1][headers.index('資料來源')]=='人工補登'
    assert values[1][headers.index('關聯案件')]=='CASE-1,CASE-2'

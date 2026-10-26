"""Complete HCM -> automatic charges/refund -> second-payment settlement, real MySQL."""
from datetime import date,datetime,timedelta,timezone
import os,runpy
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.mysql import mysql_adapter
from api.dependencies.hcm_import import get_hcm_workbook_import_service
from infrastructure.mysql.second_payment_notification_repository import MySqlSecondPaymentNotificationRepository

DATABASE=os.getenv('LABOR_UNION_TEST_MYSQL_DATABASE')
pytestmark=pytest.mark.skipif(not DATABASE,reason='requires explicitly prepared disposable localhost database')

@pytest.fixture
def isolated(monkeypatch):
    assert DATABASE.startswith('lu_test_') and mysql_adapter.DB_CONFIG['host'] in ('localhost','127.0.0.1')
    assert os.getenv('APP_ENV')=='development'
    monkeypatch.setitem(mysql_adapter.DB_CONFIG,'database',DATABASE)
    monkeypatch.setenv('LINE_CHANNEL_ACCESS_TOKEN','');monkeypatch.setenv('REDIS_URL','')
    yield

def rows(sql,args=()):
    c=mysql_adapter.get_connection()
    try:
        with c.cursor() as q:q.execute(sql,args);return tuple(q.fetchall())
    finally:c.close()

def workbook(path,case,days):
    pd.DataFrame([{'項次':1,'案件狀態':'洽談中','查詢序號(案件編號)':case,'報名時間(建檔)':'2026/10/26 09:00:00',
      'IP位址':'127.0.0.1','姓名':'合成長案' if days>20 else '合成短案','性別':'女','行動電話':'0987654321',
      '縣市':'新竹市','地址':'新竹市東區測試路901號','身分資格':'補助市民','服務時間':'9小時 09:00-18:00',
      '預產期/預計服務開始月份':'2026/11/09','預計服務日期':'2026/11/09','希望服務天數':days,
      '居住型態':'大樓','生產方式':'自然產','服務方式':'連續服務','寶寶資訊':'單胞胎','其他事項':'隔離驗證'}]).to_excel(path,index=False)

@pytest.mark.parametrize('case,days,second',[('115000901',20,0),('115000902',30,27000)])
def test_complete_hcm_posts_all_applicable_charges_and_refund_atomically(isolated,tmp_path,case,days,second):
    path=tmp_path/(case+'.xlsx');workbook(path,case,days)
    dependency=get_hcm_workbook_import_service()
    try:
        service=next(dependency);frame=service.load_frame(str(path));plan=service.preview(frame,str(path))
        assert plan.ready_count==1 and plan.review_required_count==plan.ready_with_warning_count==0
        assert rows('SELECT case_no FROM orders WHERE case_no=%s',(case,))==()
        receipt=service.apply(frame,str(path),plan.preview_fingerprint,'six-fixes-hcm:'+case,'synthetic','six-fixes-hcm:'+case)
        assert receipt.inserted_count==1 and receipt.failed_count==0
        values={r['obligation_type']:r for r in rows('SELECT obligation_type,amount_due_ntd,due_date,direction FROM client_obligations WHERE case_no=%s',(case,))}
        assert int(values['deposit']['amount_due_ntd'])==13500
        assert int(values['first']['amount_due_ntd'])==40500
        assert int(values['subsidy_return']['amount_due_ntd'])==12000
        assert values['subsidy_return']['direction']=='payable_to_client'
        if second:
            assert int(values['second']['amount_due_ntd'])==second
            assert values['second']['due_date']==date(2026,11,24)
        else:assert 'second' not in values
        snapshot=rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))
        replay=service.apply(frame,str(path),plan.preview_fingerprint,'six-fixes-hcm:'+case,'synthetic','six-fixes-hcm:'+case)
        assert replay.replayed_workbook
        assert rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))==snapshot
        assert rows('SELECT id FROM client_ledger_entries WHERE case_no=%s',(case,))==()
        assert rows('SELECT id FROM line_delivery_tasks')==()
    finally:dependency.close()

def test_nonzero_second_stage_due_day_settlement_and_zero_stage_exclusion(isolated):
    case='115000902';c=mysql_adapter.get_connection()
    try:
        repository=MySqlSecondPaymentNotificationRepository(c)
        short=repository.current('115000901');assert short is None or short.required_amount==0
        value=repository.current(case);assert value and value.required_amount==value.remaining_amount==27000
        assert not any(r.case_no==case for r in repository.find_due_candidates(date(2026,11,23)))
        due=next(r for r in repository.find_due_candidates(date(2026,11,24)) if r.case_no==case)
        assert due.event(datetime(2026,11,24,tzinfo=timezone.utc)).event_code=='client.second_payment_due'
        c.rollback()
    finally:c.close()
    from api.routes.finance_import import router
    from api.dependencies import admin_auth
    from subsystems.access.authentication_session import AdminPrincipal
    app=FastAPI();app.include_router(router)
    for name in ('require_admin','require_system_admin','require_persisted_admin'):
        app.dependency_overrides[getattr(admin_auth,name)]=lambda:AdminPrincipal(1,'synthetic','Synthetic','system_admin')
    # Reuse the existing real bank import -> durable job -> receipt verification.
    support=runpy.run_path('tests/domains/scheduling/subsystems/scheduling/integration/test_complex_service_accounting_mysql.py')
    with TestClient(app,headers={'X-Correlation-ID':'six-fixes-bank'}) as http:
        for sequence,amount in ((25,13500),(26,40500),(27,27000)):
            support['bank'](http,case,amount,sequence)
    c=mysql_adapter.get_connection()
    try:
        repository=MySqlSecondPaymentNotificationRepository(c)
        paid=repository.current(case);assert paid and paid.remaining_amount==0
        assert not any(r.case_no==case for r in repository.find_due_candidates(date(2026,11,24)))
        settled=next(r for r in repository.find_settlement_candidates() if r.case_no==case)
        assert settled.settled_amount==27000
        assert settled.event(datetime(2026,11,24,tzinfo=timezone.utc)).event_code=='client.second_payment_settled'
        c.rollback()
    finally:c.close()
    assert rows('SELECT id FROM line_delivery_tasks')==()

def test_import_and_new_accounting_roll_back_together_on_failure(isolated,monkeypatch):
    from infrastructure.mysql.case_architecture_bootstrap_repository import MySqlCaseArchitectureBootstrapRepository
    from api.dependencies.case_import import build_case_import_application
    from subsystems.case_import.hcm_adapter import build_hcm_case_import_intent
    from subsystems.case_import.case_import_workflow import ApplyCaseImport,CaseImportWorkflowError
    from shared_kernel.identities import ActorContext,CorrelationId,ExpectedVersion,IdempotencyKey
    original=MySqlCaseArchitectureBootstrapRepository.synchronize_client_charges
    def fail_after_sync(self,*args):
        original(self,*args);raise RuntimeError('synthetic transaction rollback')
    monkeypatch.setattr(MySqlCaseArchitectureBootstrapRepository,'synchronize_client_charges',fail_after_sync)
    case='115000903';start=date(2026,11,9)
    intent=build_hcm_case_import_intent({'case_no':case,'name':'合成回滾','phone':'0987654321','identity_status':'補助市民',
        'service_days':30,'created_at':datetime(2026,10,26),'service_start_date':start,'service_time':'9小時 09:00-18:00',
        'service_type':'連續服務','baby_info':'單胞胎'},start+timedelta(days=29))
    c=mysql_adapter.get_connection()
    try:
        application=build_case_import_application(c);preview=application.preview(intent,CorrelationId('rollback-preview'))
        with pytest.raises(CaseImportWorkflowError):
            application.apply(ApplyCaseImport(intent,ExpectedVersion(0),preview.fingerprint,IdempotencyKey('six-fixes-rollback'),
                ActorContext('synthetic'),'',CorrelationId('rollback-apply')))
    finally:c.close()
    for table in ('clients','orders','client_finance_accounts','client_obligations','case_import_receipts','client_obligation_events'):
        assert rows(f'SELECT case_no FROM {table} WHERE case_no=%s',(case,))==()

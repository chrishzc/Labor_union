"""Real XLSX -> durable job -> owner ledgers, with every accounting transition checked.

Only the explicitly configured disposable localhost database is used. Service
execution roots are named synthetic fixtures; completion itself uses its real API.
"""
from argparse import Namespace
from datetime import date, timedelta
from io import BytesIO
import os
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infrastructure.mysql import mysql_adapter

DATABASE = os.getenv('LABOR_UNION_TEST_MYSQL_DATABASE')
pytestmark = pytest.mark.skipif(not DATABASE, reason='requires disposable localhost MySQL')


def seed_case(case):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as c:
            c.execute("INSERT INTO clients(case_no,name,identity_status,created_at) VALUES (%s,'Synthetic accounting','一般市民','2026-09-01')", (case,))
            client_id = c.lastrowid
            c.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,'2026-11-01',30,8,0,'08:00:00','17:00:00',0)", (case, client_id))
        connection.commit()
    finally:
        connection.close()


def accounting_snapshot(case):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as c:
            result = {}
            for name, sql in {
                'obligations': 'SELECT obligation_type,amount_due_ntd,status FROM client_obligations WHERE case_no=%s ORDER BY obligation_type',
                'receipts': "SELECT COUNT(*) AS count,COALESCE(SUM(amount_ntd),0) AS total FROM client_ledger_entries WHERE case_no=%s AND entry_type='receipt'",
                'staff': 'SELECT amount_due_ntd,due_date,status FROM staff_obligations WHERE case_no=%s',
                'order': 'SELECT status,lifecycle_version,staff_payment_due_date FROM orders WHERE case_no=%s',
                'signatures': 'SELECT COUNT(*) AS count FROM contract_signing_events WHERE case_no=%s',
                'deposit': 'SELECT settlement_state FROM client_deposit_settlement_projection WHERE case_no=%s',
            }.items():
                c.execute(sql, (case,))
                result[name] = list(c.fetchall())
            return result
    finally:
        connection.close()


def workbook(case, amount, *, sequence, invalid=False):
    """Synthetic Sinopac source, using the real canonical virtual-account rule."""
    headers = ['帳號','交易日','計息日','入帳日','摘要','幣別','支出','存入','餘額','銷帳編號','交易參考編號','','更正註記','存摺備註']
    year, serial = int(case[:3]), int(case[3:])
    row = ['123456789012',f'2026/11/{sequence:02d} 09:08:07',f'2026/11/{sequence:02d}',f'2026/11/{sequence:02d}',
           '轉帳','TWD',None,amount,100000+sequence,f'99781699{year:03d}{serial:03d}',f'{case}:{sequence}','synthetic',None,'fixture']
    if invalid:
        row[7] = 100.5
    out = BytesIO()
    pd.DataFrame([headers,row]).to_excel(out, sheet_name='來源', index=False, header=False)
    return out.getvalue()


def run_finance_jobs():
    """Run only Finance Import jobs; no product lifespan or provider worker."""
    from api.dependencies.durable_job_handlers import finance_import_batch_apply_handler
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from subsystems.jobs.durable_job_worker import DurableJobWorker
    connection = mysql_adapter.get_connection()
    try:
        worker = DurableJobWorker(BackgroundJobRepository(connection), connection,
            {'finance_import_batch_apply': finance_import_batch_apply_handler}, 'isolated-accounting', retry_delay_seconds=0)
        return worker.recover_and_run_once()
    finally:
        connection.close()


def seed_actual_service(case):
    """Confirmed execution fixture, not a fake financial completion or payout."""
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as c:
            c.execute("INSERT INTO staff(name) VALUES ('Synthetic accounting staff')")
            staff = c.lastrowid
            c.execute("INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) VALUES (%s,1,1,'effective',1,'synthetic','confirmed actual-service fixture')", (case,))
            generation = c.lastrowid
            c.execute('UPDATE scheduling_aggregates SET effective_generation_id=%s,generation_counter=1,aggregate_version=1 WHERE case_no=%s',(generation,case))
            c.execute("INSERT INTO case_staff_assignments(case_no,generation_id,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status) VALUES (%s,%s,%s,1,'2026-11-01','2026-11-30','completed')",(case,generation,staff))
            assignment = c.lastrowid
            c.execute("INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) VALUES (%s,'approved-rates-v1','citizen',300,'一般市民')",(assignment,))
            for i in range(30):
                c.execute('INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,%s,1,0,1)',(case,staff,assignment,generation,date(2026,11,1)+timedelta(days=i)))
            c.execute("UPDATE orders SET status='服務中',actual_start_date='2026-11-01',actual_end_date='2026-11-30' WHERE case_no=%s",(case,))
        connection.commit()
    finally:
        connection.close()


@pytest.fixture(scope='module')
def client():
    assert DATABASE.startswith('lu_test_') and os.environ['APP_ENV'] == 'development'
    assert os.environ['LABOR_UNION_TEST_MYSQL_HOST'] in {'localhost','127.0.0.1'}
    from scripts.bootstrap_disposable_mysql_schema import bootstrap
    target = DATABASE + '_bank_chain'
    bootstrap(Namespace(host=os.environ['LABOR_UNION_TEST_MYSQL_HOST'],port=int(os.environ['LABOR_UNION_TEST_MYSQL_PORT']),
        user=os.environ['LABOR_UNION_TEST_MYSQL_USER'],password=os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'],database=target,confirm_database=target))
    from api.dependencies import admin_auth
    from api.routes.finance_import import router as bank_router
    from api.routes.order_intake_terms_bootstrap import router as intake_router
    from api.routes.order_auto_completion import router as completion_router
    from subsystems.access.authentication_session import AdminPrincipal
    api = FastAPI()
    for router in (bank_router,intake_router,completion_router):
        api.include_router(router)
    principal = AdminPrincipal(1,'isolated-accounting','Synthetic','system_admin')
    for name in ('require_admin','require_system_admin','require_persisted_admin'):
        api.dependency_overrides[getattr(admin_auth,name)] = lambda: principal
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG,'database',target)
        with TestClient(api) as client:
            yield client


def _verify_accounting_chain(client,complete_before_last_receipt):
    case = f'116{int(uuid4().hex[:6],16)%1000:06d}'
    seed_case(case)
    before = accounting_snapshot(case)
    assert before['obligations'] == [] and before['staff'] == []
    url = f'/api/v1/orders/{case}/intake-completion'
    response = client.post(url+'/preview',json={})
    assert response.status_code == 200,response.text
    preview = response.json()['data']
    assert accounting_snapshot(case) == before
    response = client.post(url+'/apply',json={'expected_lifecycle_version':preview['lifecycle_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':''},
        headers={'Idempotency-Key':case+':intake','X-Correlation-ID':case})
    assert response.status_code == 200,response.text
    initial = accounting_snapshot(case)
    assert {r['obligation_type']:int(r['amount_due_ntd']) for r in initial['obligations']} == {'deposit':12000,'first':36000,'second':24000}
    assert initial['signatures'] == [{'count':0}] and initial['staff'] == []

    def complete():
        seed_actual_service(case)
        response = client.post(f'/api/v1/orders/{case}/service-completion/preview',json={'evaluation_at':'2026-12-01T00:00:00+08:00'})
        assert response.status_code == 200,response.text
        plan = response.json()['data']
        body = {'evaluation_at':plan['evaluation_at'],'expected_order_version':plan['expected_order_version'],'preview_fingerprint':plan['fingerprint'],'reason':''}
        headers = {'Idempotency-Key':case+':complete','X-Correlation-ID':case}
        response = client.post(f'/api/v1/orders/{case}/service-completion/apply',json=body,headers=headers)
        assert response.status_code == 200,response.text
        saved = accounting_snapshot(case)
        replay = client.post(f'/api/v1/orders/{case}/service-completion/apply',json=body,headers=headers)
        assert replay.status_code == 200,replay.text
        assert accounting_snapshot(case) == saved
        return saved

    for i, amount in enumerate((12000,36000,24000),1):
        if i == 3 and complete_before_last_receipt:
            saved = complete()
            assert all(r['obligation_type'] != 'subsidy_return' for r in saved['obligations'])
            assert len(saved['staff']) == 1 and int(saved['staff'][0]['amount_due_ntd']) == 72000
        bank_before = accounting_snapshot(case)
        headers = {'Idempotency-Key':case+f':bank:{i}','X-Correlation-ID':case}
        contents = workbook(case,amount,sequence=i)
        response = client.post('/api/v1/finance-import/workbooks/ingest',headers=headers,files={'workbook':(f'bank-{i}.xlsx',contents,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        assert response.status_code == 200,response.text
        batch = response.json()['data']['batch_identity']
        assert accounting_snapshot(case) == bank_before
        response = client.post('/api/v1/finance-import/batches/preview',json={'batch_identity':batch})
        assert response.status_code == 200,response.text
        plan = response.json()['data']
        assert plan['apply_allowed'] and plan['counts']['ready_dispatch'] == 1,plan
        assert accounting_snapshot(case) == bank_before
        body = {'batch_identity':batch,'expected_batch_version':plan['batch_version'],'preview_fingerprint':plan['preview_fingerprint'],'reason':''}
        headers['Idempotency-Key'] += ':apply'
        accepted = client.post('/api/v1/finance-import/batches/apply',json=body,headers=headers)
        assert accepted.status_code == 202,accepted.text
        job = accepted.json()['data']['job_id']
        assert accounting_snapshot(case) == bank_before
        replay = client.post('/api/v1/finance-import/batches/apply',json=body,headers=headers)
        assert replay.status_code == 202 and replay.json()['data']['job_id'] == job
        assert run_finance_jobs()
        result = client.get(f'/api/v1/finance-import/jobs/{job}/batch-outcome')
        assert result.status_code == 200,result.text
        assert result.json()['data']['status'] == 'succeeded',result.text
        assert result.json()['data']['receipt']['reconciled_count'] == 1,result.text
        manifest = client.get(f'/api/v1/finance-import/batches/{batch}/manifest')
        reviews = client.get(f'/api/v1/finance-import/batches/{batch}/review-rows')
        assert manifest.status_code == reviews.status_code == 200
        assert manifest.json()['data']['review_count'] == 0
        assert reviews.json()['data']['items'] == []
        saved = accounting_snapshot(case)
        assert saved['receipts'] == [{'count':i,'total':sum((12000,36000,24000)[:i])}]
        assert saved['deposit'] == [{'settlement_state':'settled'}]
        assert client.post('/api/v1/finance-import/batches/apply',json=body,headers=headers).status_code == 202
        assert not run_finance_jobs()
        assert accounting_snapshot(case) == saved
    final = accounting_snapshot(case) if complete_before_last_receipt else complete()
    assert final['order'][0]['status'] == '訂單完成'
    assert str(final['order'][0]['staff_payment_due_date']) == '2026-12-15'
    returns = [r for r in final['obligations'] if r['obligation_type'] == 'subsidy_return']
    assert len(returns) == 1 and int(returns[0]['amount_due_ntd']) == 12000
    assert len(final['staff']) == 1 and int(final['staff'][0]['amount_due_ntd']) == 72000
    assert final['receipts'] == [{'count':3,'total':72000}]

    return case


@pytest.mark.parametrize('complete_before_last_receipt',[False,True])
def test_each_bank_stage_and_completion_updates_accounting_once(client,complete_before_last_receipt):
    _verify_accounting_chain(client,complete_before_last_receipt)


def test_subsidy_funding_is_checked_before_dispatch_and_updates_after_government_receipt(client):
    case = _verify_accounting_chain(client,False)
    connection = mysql_adapter.get_connection()
    account = '7' * 12 + case[-4:]
    try:
        with connection.cursor() as c:
            c.execute('SELECT id,staff_id FROM case_staff_assignments WHERE case_no=%s',(case,))
            assignment = c.fetchone()
            c.execute("SELECT obligation_identity FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))
            refund = c.fetchone()['obligation_identity']
            c.execute("INSERT INTO subsidy_claim_batches(application_year,quarter,revision,status,requested_amount,approved_amount,paid_amount,submitted_at,approved_at) VALUES (2026,4,1,'approved',72000,12000,0,'2026-12-01','2026-12-02')")
            batch = c.lastrowid
            c.execute('INSERT INTO subsidy_claim_batch_items(batch_id,case_no,assignment_id,staff_id,claimed_hours,unit_price,requested_amount,approved_amount) VALUES (%s,%s,%s,%s,240,300,72000,12000)',(batch,case,assignment['id'],assignment['staff_id']))
            item = c.lastrowid
            c.execute('INSERT INTO client_subsidy_return_claim_item_links(obligation_identity,claim_item_id,entitled_amount_ntd) VALUES (%s,%s,12000)',(refund,item))
            c.execute("INSERT INTO government_subsidy_batch_accounts(batch_id,aggregate_version,requested_total_ntd,approved_total_ntd,net_allocated_ntd,outstanding_ntd,status) VALUES (%s,1,72000,12000,0,12000,'approved')",(batch,))
            c.execute("INSERT INTO client_refund_recipient_snapshots(refund_obligation_identity,case_no,bank_code,bank_account,source_kind) VALUES (%s,%s,'synthetic',%s,'test-fixture')",(refund,case,account))
        connection.commit()
    finally:
        connection.close()

    def source(*, government=False, repacked=False):
        columns = ['序號','交易日期','交易時間','帳務日期','摘要','支出金額','存入金額','帳戶餘額','備註']
        day = '2027/01/10' if government else '2027/01/15'
        row = ['0001',day,'09:08:07',day,'轉帳',None if government else 12000,12000 if government else None,100000,'新竹市政府' if government else '補助退款 '+account]
        output = BytesIO()
        pd.DataFrame([columns,row]).to_excel(output,sheet_name='重匯來源' if repacked else '來源',index=False,header=False)
        return output.getvalue()

    def ingest_and_preview(contents,key):
        r = client.post('/api/v1/finance-import/workbooks/ingest',files={'workbook':('subsidy.xlsx',contents,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},headers={'Idempotency-Key':key,'X-Correlation-ID':case})
        assert r.status_code==200,r.text
        batch_identity = r.json()['data']['batch_identity']
        r = client.post('/api/v1/finance-import/batches/preview',json={'batch_identity':batch_identity})
        assert r.status_code==200,r.text
        return r.json()['data']

    def post(plan,key):
        r = client.post('/api/v1/finance-import/batches/apply',json={'batch_identity':plan['batch_identity'],'expected_batch_version':plan['batch_version'],'preview_fingerprint':plan['preview_fingerprint'],'reason':''},headers={'Idempotency-Key':key,'X-Correlation-ID':case})
        assert r.status_code==202,r.text
        assert run_finance_jobs()
        r = client.get('/api/v1/finance-import/jobs/'+r.json()['data']['job_id']+'/batch-outcome')
        assert r.status_code==200 and r.json()['data']['status']=='succeeded',r.text
        assert r.json()['data']['receipt']['reconciled_count']==1,r.text

    refund_bytes = source()
    before = accounting_snapshot(case)
    pending = ingest_and_preview(refund_bytes,case+':refund-source')
    assert pending['counts']['ready_dispatch']==0 and pending['counts']['business_pending']==1,pending
    assert 'subsidy_advance_not_due' in pending['rows'][0]['evidence']
    assert accounting_snapshot(case)==before
    government = ingest_and_preview(source(government=True),case+':government-source')
    assert government['counts']['ready_dispatch']==1,government
    post(government,case+':government-apply')
    funded = ingest_and_preview(source(repacked=True),case+':refund-repacked-source')
    assert funded['batch_identity'] != pending['batch_identity']
    assert funded['rows'][0]['row_identity'] == pending['rows'][0]['row_identity']
    assert funded['counts']['canonical_created'] == 0
    assert funded['counts']['ready_dispatch']==1 and funded['counts']['business_pending']==0,funded
    post(funded,case+':refund-apply')
    saved = accounting_snapshot(case)
    assert next(r for r in saved['obligations'] if r['obligation_type']=='subsidy_return')['status']=='settled'
    assert saved['receipts']==before['receipts']
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as c:
            c.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries WHERE case_no=%s AND entry_type<>'receipt'",(case,))
            assert c.fetchall()==[{'entry_type':'subsidy_return','amount_ntd':12000}]
            c.execute('SELECT net_allocated_ntd,outstanding_ntd,status FROM government_subsidy_batch_accounts WHERE batch_id=%s',(batch,))
            assert c.fetchone()=={'net_allocated_ntd':12000,'outstanding_ntd':0,'status':'paid'}
    finally:
        connection.close()

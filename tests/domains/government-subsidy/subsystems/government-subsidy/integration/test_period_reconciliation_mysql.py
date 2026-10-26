"""Actual owner/API transactions against an explicitly supplied isolated MySQL DB."""
import os,json,runpy
from datetime import date,timedelta
from uuid import uuid4
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.mysql import mysql_adapter

pytestmark=pytest.mark.skipif(not os.getenv('SUBSIDY_PERIOD_TEST_DB'),reason='explicit disposable local subsidy DB required')
support=runpy.run_path('tests/domains/scheduling/subsystems/scheduling/integration/test_complex_service_accounting_mysql.py')


@pytest.fixture(scope='module')
def http():
    from api.dependencies import admin_auth
    from api.routes import government_subsidy_periods,government_subsidy,order_intake_terms_bootstrap,finance_import,finance_reports,client_refund_reversal
    from subsystems.access.authentication_session import AdminPrincipal
    database=os.environ['SUBSIDY_PERIOD_TEST_DB']
    assert database.startswith('lu_test_') and mysql_adapter.DB_CONFIG['host'] in {'localhost','127.0.0.1'}
    app=FastAPI()
    for module in (government_subsidy_periods,government_subsidy,order_intake_terms_bootstrap,finance_import,finance_reports,client_refund_reversal):app.include_router(module.router)
    principal=AdminPrincipal(1,'synthetic-finance','Synthetic finance','system_admin')
    for guard in (admin_auth.require_admin,admin_auth.require_system_admin,admin_auth.require_persisted_admin):app.dependency_overrides[guard]=lambda:principal
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG,'database',database)
        with TestClient(app,headers={'X-Correlation-ID':'subsidy-period-test'}) as client:yield client


def rows(sql,params=()):
    connection=mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:cursor.execute(sql,params);return tuple(cursor.fetchall())
    finally:connection.close()


def write(sql,params=()):
    connection=mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:cursor.execute(sql,params);identity=cursor.lastrowid
        connection.commit();return identity
    finally:connection.close()


def checked(response):
    assert response.status_code==200,response.text
    return response.json()['data']


def seed_case(http,year,month,*,identity='補助市民',days=30):
    case='116'+str(rows('SELECT COUNT(*) n FROM orders')[0]['n']+1).zfill(6)
    start=date(year,month,1)
    client=write("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic subsidy',%s,'連續服務','2026-10-01')",(case,identity))
    write("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,%s,%s,8,0,'08:00:00','17:00:00',0)",(case,client,start,days))
    url=f'/api/v1/orders/{case}/intake-completion'
    preview=checked(http.post(url+'/preview',json={}))
    checked(http.post(url+'/apply',json={'expected_lifecycle_version':preview['lifecycle_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':''},headers={'Idempotency-Key':case+':init'}))
    # Established-status source fixture; receipt behavior itself is separately exercised through Finance Import.
    write("UPDATE orders SET status='訂單成立',end_date=%s WHERE case_no=%s",(start+timedelta(days=days-1),case))
    return case


def bank(amount,paid_on=date(2060,6,15),*,classification='government_subsidy'):
    return write("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,direction,credit,debit,currency,bank_references,warnings,raw_payload,classification_type) "
        "VALUES (%s,'legacy',%s,%s,%s,%s,'TWD',JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),%s)",
        (uuid4().hex+uuid4().hex,paid_on,'incoming' if amount>0 else 'outgoing',max(0,amount),max(0,-amount),classification))


def query(http,unit,year,index=1):return checked(http.get('/api/v1/government-subsidy/periods',params={'unit':unit,'year':year,'index':index}))


def reconcile(http,view,bank_row,key=None):
    return http.post('/api/v1/government-subsidy/periods/reconcile',json={**view['period'],'expected_version':view['version'],
        'bank_row_id':bank_row,'idempotency_key':key or uuid4().hex})


def test_intake_immediately_creates_refund_without_completion_or_customer_receipts(http):
    case=seed_case(http,2060,1)
    assert rows("SELECT amount_due_ntd,due_date FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))==({'amount_due_ntd':12000,'due_date':date(2060,3,15)},)
    assert rows('SELECT COUNT(*) n FROM client_ledger_entries WHERE case_no=%s',(case,))[0]['n']==0
    data=checked(http.get('/api/v1/finance-reports/client-subsidy-returns',params={'case_no':case}))
    assert data['rows'][0]['amount_ntd']==12000 and data['rows'][0]['is_estimate'] is False
    cash=checked(http.get('/api/v1/finance-reports/accounts-payable/cash-requirements',params={'page_size':200}))
    actual=next(row for row in cash['rows'] if row['case_no']==case and row['payment_type']=='client_subsidy_return')
    assert actual['certainty']=='confirmed' and actual['source_amount_ntd']==12000


def test_real_query_totals_are_consistent_and_quarter_covers_months_without_split_receipts(http):
    year=2061
    cases=[seed_case(http,year,month,days=20) for month in range(1,13)]
    months=[query(http,'month',year,month) for month in range(1,13)]
    quarters=[query(http,'quarter',year,q) for q in range(1,5)]
    annual=query(http,'year',year)
    assert [m['total_ntd'] for m in months]==[12000]*12
    assert [q['total_ntd'] for q in quarters]==[36000]*4
    assert annual['total_ntd']==144000==sum(q['total_ntd'] for q in quarters)==sum(m['total_ntd'] for m in months)
    before=rows('SELECT COUNT(*) n FROM government_subsidy_period_entries')[0]['n']
    assert reconcile(http,quarters[0],bank(35999)).status_code==409
    assert rows('SELECT COUNT(*) n FROM government_subsidy_period_entries')[0]['n']==before
    source=bank(36000)
    receipt=checked(reconcile(http,quarters[0],source,'same-quarter-key'))
    assert checked(reconcile(http,quarters[0],source,'same-quarter-key'))==receipt
    assert reconcile(http,quarters[1],source,'same-quarter-key').status_code==409
    month=query(http,'month',year,2)
    assert not month['can_reconcile'] and month['coverage'][0]['period']['unit']=='quarter'
    assert month['coverage'][0]['amount_ntd']==36000
    assert reconcile(http,month,bank(12000)).status_code==409
    assert reconcile(http,query(http,'year',year),bank(144000)).status_code==409
    assert rows('SELECT COUNT(*) n FROM government_subsidy_period_entries')[0]['n']==before+1
    assert checked(http.get('/api/v1/government-subsidy/periods/cases/'+cases[0]))['coverage'][0]['receipt_id']==receipt['receipt_id']


def test_stale_and_changed_case_membership_do_not_allow_double_receipt(http):
    year=2062
    case=seed_case(http,year,1)
    old=query(http,'month',year)
    checked(reconcile(http,old,bank(12000)))
    other=seed_case(http,year,4)
    assert reconcile(http,query(http,'month',year,4)|{'version':old['version']},bank(12000)).status_code==409
    write('UPDATE orders SET end_date=%s WHERE case_no=%s',(date(year+1,4,30),case))
    shifted=query(http,'month',year+1,4)
    assert case in shifted['blocked_cases'] and not shifted['can_reconcile']
    assert reconcile(http,shifted,bank(12000)).status_code==409
    original=query(http,'month',year,1)
    assert case in original['changed_cases'] and original['recorded_lines'][0]['amount_ntd']==12000


def test_whole_reversal_keeps_evidence_and_reopens_coverage(http):
    year=2064
    seed_case(http,year,1)
    receipt=checked(reconcile(http,query(http,'quarter',year),bank(12000)))['receipt_id']
    url='/api/v1/government-subsidy/periods/reverse'
    assert http.post(url,json={'receipt_id':receipt,'bank_row_id':bank(-11999),'idempotency_key':uuid4().hex}).status_code==409
    body={'receipt_id':receipt,'bank_row_id':bank(-12000),'idempotency_key':uuid4().hex}
    reversed_receipt=checked(http.post(url,json=body))
    assert checked(http.post(url,json=body))==reversed_receipt
    assert query(http,'month',year)['can_reconcile']
    assert rows('SELECT COUNT(*) n FROM government_subsidy_period_members WHERE receipt_id=%s',(receipt,))[0]['n']==1
    checked(reconcile(http,query(http,'month',year),bank(12000)))


def test_social_welfare_has_subsidy_but_no_customer_advance_refund(http):
    case=seed_case(http,2065,1,identity='社福',days=15)
    assert not rows("SELECT obligation_identity FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))
    view=query(http,'month',2065)
    assert view['lines'][0]['case_no']==case and view['total_ntd']==42000


def test_expired_claim_submission_and_approval_endpoints_cannot_write(http):
    for path in ('claim-batches/preview','claim-batches/apply','receipts/preview'):
        assert http.post('/api/v1/government-subsidy/'+path,json={}).status_code==410


def payout(http,case,paid_on):
    obligation=rows("SELECT obligation_identity,amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))[0]
    # Synthetic recipient snapshot and immutable source bank fact; actual reconciliation uses the public owner API.
    account='synthetic-'+case
    write("INSERT IGNORE INTO client_refund_recipient_snapshots(refund_obligation_identity,case_no,bank_code,bank_account,source_kind) VALUES (%s,%s,'synthetic',%s,'synthetic')",(obligation['obligation_identity'],case,account))
    bank_row=bank(-int(obligation['amount_due_ntd']),paid_on,classification='client_subsidy_return')
    write('UPDATE finance_import_rows SET counterparty_account=%s WHERE id=%s',(account,bank_row))
    body={'finance_import_row_ids':[bank_row],'obligation_identities':[obligation['obligation_identity']]}
    url=f'/api/v1/orders/{case}/client-finance/subsidy-return'
    preview=checked(http.post(url+'/preview',json=body))
    result=checked(http.post(url+'/apply',json={**body,'expected_account_version':preview['account_version'],
        'preview_fingerprint':preview['preview_fingerprint'],'reason':''},headers={'Idempotency-Key':uuid4().hex}))
    return rows('SELECT id,entry_type,amount_ntd FROM client_ledger_entries WHERE finance_import_row_id=%s',(bank_row,))[0]


def test_each_month_can_advance_and_whole_period_receipt_recovers_without_second_payout(http):
    year=2070
    cases=[seed_case(http,year,month,days=20) for month in (1,2,3)]
    for month,case in enumerate(cases,1):
        payment=payout(http,case,date(year,month+2,15))
        assert payment['entry_type']=='subsidy_advance' and payment['amount_ntd']==12000
    view=query(http,'quarter',year)
    result=checked(reconcile(http,view,bank(36000,date(year,6,15))))
    assert query(http,'quarter',year)['coverage'][0]['recovered_advance_ntd']==36000
    for case in cases:
        assert rows('SELECT COUNT(*) n FROM client_ledger_entries WHERE case_no=%s',(case,))[0]['n']==1
        assert not checked(http.get('/api/v1/finance-reports/client-subsidy-returns',params={'case_no':case}))['rows']
    cash=checked(http.get('/api/v1/finance-reports/accounts-payable/cash-requirements',params={'page_size':200}))
    for case in cases:
        actual=next(row for row in cash['rows'] if row['case_no']==case and row['payment_type']=='client_subsidy_return')
        assert actual['payment_status']=='paid' and actual['source_amount_ntd']==12000 and actual['unpaid_amount_ntd']==0


def test_government_received_first_never_creates_an_advance_or_second_payment(http):
    year=2071
    case=seed_case(http,year,2,days=20)
    checked(reconcile(http,query(http,'month',year,2),bank(12000,date(year,3,1))))
    payment=payout(http,case,date(year,4,15))
    assert payment['entry_type']=='subsidy_return'
    assert query(http,'month',year,2)['coverage'][0]['recovered_advance_ntd']==0


def test_backdated_customer_payout_posted_after_government_receipt_updates_recovery(http):
    year=2072
    case=seed_case(http,year,2,days=20)
    checked(reconcile(http,query(http,'month',year,2),bank(12000,date(year,5,1))))
    assert query(http,'month',year,2)['coverage'][0]['recovered_advance_ntd']==0
    payment=payout(http,case,date(year,4,15))
    assert payment['entry_type']=='subsidy_advance'
    assert query(http,'month',year,2)['coverage'][0]['recovered_advance_ntd']==12000


def test_source_date_and_quantity_changes_update_refund_in_same_owner_transaction(http):
    from infrastructure.mysql.automatic_client_accounting import synchronize_client_charges
    from shared_kernel.identities import ActorContext,IdempotencyKey,CorrelationId
    case=seed_case(http,2073,2,days=20)
    # Exercise the adapter called by real Orders/Scheduling writers in their outer transaction.
    connection=mysql_adapter.get_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute('UPDATE orders SET service_days=3,start_date=%s,end_date=%s WHERE case_no=%s',(date(2073,3,1),date(2073,3,3),case))
            cursor.execute('UPDATE client_payment_terms SET deposit_service_days=3 WHERE case_no=%s',(case,))
            synchronize_client_charges(cursor,case,actor=ActorContext('synthetic'),key=IdempotencyKey(uuid4().hex),
                correlation_id=CorrelationId('source-date-change'),source_family='synthetic-owner-change',source_id=case)
        connection.commit()
    finally:connection.close()
    assert rows("SELECT amount_due_ntd,due_date FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))==({'amount_due_ntd':7200,'due_date':date(2073,5,15)},)


def test_real_bank_workbook_government_receipt_stays_pending_until_period_selected(http):
    from io import BytesIO
    import pandas as pd
    case=seed_case(http,2074,1,days=20)
    headers=['序號','交易日期','交易時間','帳務日期','摘要','支出金額','存入金額','帳戶餘額','備註']
    raw=[uuid4().hex,'2074/06/15','09:00:00','2074/06/15','轉帳',None,12000,12000,'新竹市政府']
    contents=BytesIO();pd.DataFrame([headers,raw]).to_excel(contents,index=False,header=False)
    result=checked(http.post('/api/v1/finance-import/workbooks/ingest',files={'workbook':('government.xlsx',contents.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},headers={'Idempotency-Key':uuid4().hex}))
    batch=result['batch_identity']
    preview=checked(http.post('/api/v1/finance-import/batches/preview',json={'batch_identity':batch}))
    assert preview['counts']['ready_dispatch']==0
    bank_row=int(preview['rows'][0]['row_identity'].split(':')[-1])
    assert any(row['id']==bank_row for row in checked(http.get('/api/v1/government-subsidy/periods/bank-rows'))['items'])
    checked(reconcile(http,query(http,'month',2074,1),bank_row))
    again=checked(http.post('/api/v1/finance-import/batches/preview',json={'batch_identity':batch}))
    assert again['rows'][0]['disposition']=='existing'
    assert not rows('SELECT allocation.id FROM government_subsidy_allocations allocation JOIN subsidy_claim_batch_items item '
                    'ON item.id=allocation.claim_item_id WHERE item.case_no=%s',(case,))


def test_concurrent_month_and_quarter_reconciliation_create_only_one_receipt(http):
    from concurrent.futures import ThreadPoolExecutor
    seed_case(http,2075,1,days=20)
    month=query(http,'month',2075,1);quarter=query(http,'quarter',2075,1)
    banks=[bank(12000),bank(12000)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(reconcile,http,view,source) for view,source in zip((month,quarter),banks)]
        statuses=sorted(future.result().status_code for future in futures)
    assert statuses==[200,409]
    assert rows('SELECT COUNT(*) n FROM government_subsidy_period_entries WHERE period_year=2075')[0]['n']==1


def test_refund_term_changes_preserve_cash_and_handle_returned_overrefund(http,monkeypatch):
    from infrastructure.mysql.automatic_client_accounting import synchronize_client_charges
    from shared_kernel.identities import ActorContext,IdempotencyKey,CorrelationId
    from io import BytesIO
    from openpyxl import load_workbook
    case=seed_case(http,2076,1,days=20)
    original=payout(http,case,date(2076,3,15))
    def change(days):
        connection=mysql_adapter.get_connection()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute('UPDATE orders SET service_days=%s,end_date=%s WHERE case_no=%s',(days,date(2076,1,1)+timedelta(days=days-1),case))
                cursor.execute('UPDATE client_payment_terms SET deposit_service_days=3 WHERE case_no=%s',(case,))
                synchronize_client_charges(cursor,case,actor=ActorContext('synthetic'),key=IdempotencyKey(uuid4().hex),
                    correlation_id=CorrelationId('refund-term-change'),source_family='synthetic-term-change',source_id=case+':'+str(days))
            connection.commit()
        finally:connection.close()
    change(3)
    refund=rows("SELECT obligation_identity,amount_due_ntd,status FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))[0]
    assert refund['amount_due_ntd']==0
    difference=refund['obligation_identity']+':difference'
    assert rows('SELECT amount_due_ntd FROM client_obligations WHERE obligation_identity=%s',(difference,))[0]['amount_due_ntd']==4800
    # A real bank workbook and the existing Finance Import writer collect the difference.
    original_workbook=support['bank'].__globals__['workbook']
    def workbook(*args,**kwargs):
        book=load_workbook(BytesIO(original_workbook(*args,**kwargs)))
        sheet=book.active
        sheet['B2']='2076/04/15 09:08:07';sheet['C2']='2076/04/15';sheet['D2']='2076/04/15'
        output=BytesIO();book.save(output);return output.getvalue()
    monkeypatch.setitem(support['bank'].__globals__,'workbook',workbook)
    support['bank'](http,case,4800,2)
    change(20)
    assert rows('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s',(difference,))==({'amount_due_ntd':0,'status':'settled'},)
    assert rows('SELECT amount_due_ntd FROM client_obligations WHERE obligation_identity=%s',(refund['obligation_identity'],))[0]['amount_due_ntd']==4800
    assert rows('SELECT id,entry_type,amount_ntd FROM client_ledger_entries WHERE id=%s',(original['id'],))[0]==original


def invalid_schedule(case,status='cancelled'):
    generation=write("INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason,cancelled_at) "
        "VALUES (%s,1,1,%s,NULL,'synthetic','Reproduce stale scheduling pointer',CASE WHEN %s='cancelled' THEN NOW() ELSE NULL END)",(case,status,status))
    write('UPDATE scheduling_aggregates SET effective_generation_id=%s,generation_counter=1,aggregate_version=1 WHERE case_no=%s',(generation,case))


@pytest.mark.parametrize('status,year',[('cancelled',2077),('preparing',2078)])
def test_invalid_schedule_blocks_all_period_units_and_fresh_apply_without_writes(http,status,year):
    case=seed_case(http,year,1,days=6)
    original=query(http,'month',year)
    assert original['can_reconcile'] and original['total_ntd']==12000
    source=bank(12000)
    before=rows('SELECT COUNT(*) n FROM government_subsidy_period_entries')[0]['n']
    invalid_schedule(case,status)
    for unit in ('month','quarter','year'):
        view=query(http,unit,year)
        assert view['total_ntd'] is None and not view['can_reconcile']
        assert view['lines'][0]['unavailable_reason']=='scheduling_effective_generation_invalid'
        assert reconcile(http,view,source).status_code==409
    assert reconcile(http,original,source).status_code==409
    assert checked(http.get('/api/v1/government-subsidy/periods/cases/'+case))['amount_ntd'] is None
    assert rows('SELECT COUNT(*) n FROM government_subsidy_period_entries')[0]['n']==before


def test_policy_replay_resynchronizes_repaired_cases_without_relabel_or_duplicate_events(http):
    from scripts.migrate_subsidy_period_policy import apply,plan
    case=seed_case(http,2080,1,days=6)
    invalid_schedule(case)
    connection=mysql_adapter.get_connection()
    try:
        assert plan(connection)==[]  # Fresh canonical identity marker already exists.
        pending=[]
        assert apply(connection,[],pending_cases=pending)['scheduling_effective_generation_invalid']>=1
        assert case in {item['case_no'] for item in pending}
        # Repair only this synthetic generation; the live HANDOVER cases stay untouched.
        write("UPDATE scheduling_generations g JOIN scheduling_aggregates a ON a.effective_generation_id=g.id "
              "SET g.status='effective',g.effective_marker=1,g.cancelled_at=NULL WHERE a.case_no=%s",(case,))
        write("UPDATE orders SET start_date='2080-02-01',end_date='2080-02-06' WHERE case_no=%s",(case,))
        pending=[]
        apply(connection,[],pending_cases=pending)
        assert case not in {item['case_no'] for item in pending}
        assert rows('SELECT identity_status FROM clients WHERE case_no=%s',(case,))[0]['identity_status']=='補助市民'
        refunds=rows("SELECT due_date,amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))
        assert refunds==({'due_date':date(2080,4,15),'amount_due_ntd':12000},)
        events=rows('SELECT COUNT(*) n FROM client_obligation_events WHERE case_no=%s',(case,))[0]['n']
        apply(connection,[])
        assert rows('SELECT COUNT(*) n FROM client_obligation_events WHERE case_no=%s',(case,))[0]['n']==events
    finally:connection.close()

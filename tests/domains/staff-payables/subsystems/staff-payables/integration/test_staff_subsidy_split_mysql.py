"""Scheme-one confirmation, absent Payroll schedules and payout share one MySQL UoW."""
import json
import os
from datetime import date
from uuid import uuid4

import pymysql
import pytest

from api.dependencies.staff_payout import build_staff_payout_application
from domains.staff_payables.reconciliation import StaffPayoutEventType, StaffPayoutDifferenceMode
from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState
from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.staff_payables.payout_reconciliation import StaffPayoutSelection, StaffPayoutApplyRequest, StaffPayoutReconciliationError

pytestmark = pytest.mark.skipif(os.getenv('STAFF_SUBSIDY_SPLIT_MYSQL') != '1', reason='explicit local isolated MySQL acceptance')


def test_split_flag_is_closed_to_payout_and_survives_the_original_job_payload():
    from pydantic import ValidationError
    from api.schemas.staff_payout import PayoutPreviewBody, PayoutDifferencePreviewBody
    from api.routes.staff_payout import _payout_selection, _staff_payout_payload
    from api.dependencies.durable_job_handlers import _staff_payout_request
    from shared_kernel.fingerprints import PreviewFingerprint
    fields = {'finance_import_row_ids':[1],'obligation_identities':['obligation:1'],'confirm_subsidy_split':True}
    selection = _payout_selection(PayoutPreviewBody(**fields))
    command = StaffPayoutApplyRequest(selection,ExpectedVersion(0),ExpectedVersion(0),PreviewFingerprint('a'*64),IdempotencyKey('split-contract'),ActorContext('synthetic'),'',CorrelationId('split-contract'))
    assert _staff_payout_request(_staff_payout_payload(command)) == command
    with pytest.raises(ValidationError): PayoutDifferencePreviewBody(**fields,mode='underpayment')
    with pytest.raises(ValidationError): PayoutPreviewBody(**{**fields,'confirm_subsidy_split':'true'})


@pytest.fixture
def connection():
    assert os.environ['APP_ENV'] == 'development'
    assert os.environ['DB_HOST'] in {'localhost', '127.0.0.1'}
    assert os.environ['DB_DATABASE'].startswith('lu_test_')
    c = pymysql.connect(host=os.environ['DB_HOST'], port=int(os.environ.get('DB_PORT', '3306')),
        user=os.environ['DB_USER'], password=os.environ.get('DB_PASSWORD'), database=os.environ['DB_DATABASE'],
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    yield c
    c.rollback()
    c.close()


def seed(c, *, installments=False, scheme=None, subsidy=12000):
    tag = uuid4().hex
    case = f'87{int(tag[:8], 16) % 10000000:07d}'
    identity = 'split-command-test:' + tag
    name = '合成方案月嫂' + tag[:8]
    account = str(int(tag[:12], 16) % 10**12).zfill(12)
    with c.cursor() as q:
        q.execute("INSERT INTO clients(case_no,name,identity_status) VALUES(%s,'Synthetic Split Client','一般市民')", (case,))
        q.execute("INSERT INTO orders(case_no,client_id,status,actual_start_date,actual_end_date,service_days,service_hours_per_day) VALUES(%s,%s,'訂單完成','2026-09-01','2026-09-10',10,10)", (case, q.lastrowid))
        q.execute('INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES(%s,0)', (case,))
        q.execute('INSERT INTO staff(name) VALUES(%s)', (name,)); staff = q.lastrowid
        q.execute('UPDATE orders SET staff_id=%s WHERE case_no=%s', (staff, case))
        q.execute("INSERT INTO staff_bank_accounts(staff_id,bank_code,account_no,is_primary) VALUES(%s,'000',%s,1)", (staff, account))
        q.execute("INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status) VALUES(%s,%s,1,'completed')", (case, staff)); assignment = q.lastrowid
        q.execute("INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,30000,'2026-10-15',%s,0,1,%s,'synthetic','split fixture')", (identity, assignment, case, staff, 'a'*64, identity)); event = q.lastrowid
        q.execute("INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,amount_due_ntd,due_date,status,current_event_id,payroll_version) VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff',30000,'2026-10-15','open',%s,1)", (identity, assignment, case, staff, event))
        if subsidy is not None:
            q.execute("INSERT INTO government_subsidy_amount_controls(case_no,period_year,amount_mode,computed_ntd,effective_ntd) VALUES(%s,2026,'manual',%s,%s)", (case, subsidy, subsidy))
        if installments:
            q.executemany('INSERT INTO staff_obligation_installments(obligation_identity,funding_kind,amount_ntd,due_date) VALUES(%s,%s,%s,%s)',
                ((identity, 'client', 30000-subsidy, date(2026,10,15)), (identity, 'subsidy', subsidy, date(2026,11,15))))
    if scheme:
        MySqlAccountingWorkspaceState(c).append_subsidy_plan(case, 1, scheme, 'synthetic', uuid4().hex)
    c.commit()
    return {'case': case, 'identity': identity, 'staff': staff, 'name': name, 'account': account}


def source(c, data, cash=17935, bank='sinopac'):
    with c.cursor() as q:
        q.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,debit,direction,currency,warnings,raw_payload,memo,bank_references,matched_identity_ids,classification_type,reconciliation_status) VALUES(%s,%s,%s,%s,'outgoing','TWD','[]','{}',%s,%s,%s,'staff_payout','pending')",
            (uuid4().hex+uuid4().hex, bank, '2026-10-15' if bank == 'sinopac' else '2026-11-15', cash,
             data['name'], json.dumps({'交易參考編號':data['account']}), json.dumps([f"staff:{data['staff']}"])))
        row = q.lastrowid
    c.commit()
    return str(row)


def selected(data, row, *, split=True, mode=None):
    return StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (row,), (data['identity'],),
        difference_mode=mode, confirm_subsidy_split=split)


def request(selection, preview, key=None):
    return StaffPayoutApplyRequest(selection, ExpectedVersion(preview.staff_payables_version), ExpectedVersion(preview.bank_facts_version),
        preview.fingerprint, IdempotencyKey(key or uuid4().hex), ActorContext('synthetic'), '確認方案一並核銷', CorrelationId('split-mysql'))


def counts(c, data):
    c.rollback()
    with c.cursor() as q:
        result = {}
        for table, clause, args in (
            ('finance_case_subsidy_plan_events','case_no=%s',(data['case'],)),
            ('staff_obligation_installments','obligation_identity=%s',(data['identity'],)),
            ('staff_payout_events','staff_id=%s',(data['staff'],)),
            ('staff_payables_apply_receipts','staff_id=%s',(data['staff'],)),
        ):
            q.execute(f'SELECT COUNT(*) n FROM {table} WHERE {clause}', args)
            result[table] = q.fetchone()['n']
    return result


@pytest.mark.parametrize('existing,prior', [(False,0), (True,0), (False,5000)])
def test_confirm_missing_plan_and_schedule_atomically_then_subsidy_settles_original(connection, existing, prior):
    c = connection
    data = seed(c, installments=existing)
    application = build_staff_payout_application(c)
    if prior:
        old = selected(data, source(c, data, prior), split=False, mode=StaffPayoutDifferenceMode.UNDERPAYMENT)
        checked = application.preview(old, CorrelationId('prior'))
        application.apply(request(old, checked))
    selection = selected(data, source(c, data, 17935-prior))
    before = counts(c, data)
    checked = application.preview(selection, CorrelationId('preview'))
    assert checked.subsidy_split.subsidy_ntd == 12000
    assert checked.candidate.obligation_total.amount == 18000-prior
    assert checked.candidate.transfer_fee.amount == 65
    assert counts(c, data) == before, 'Preview must not save plan, schedule or payout'
    command = request(selection, checked)
    receipt = application.apply(command)
    assert receipt.resulting_status.value == 'partially_paid'
    assert application.apply(command) == receipt
    from dataclasses import replace
    with pytest.raises(StaffPayoutReconciliationError) as changed:
        application.apply(replace(command, selection=replace(selection, confirm_subsidy_split=False)))
    assert changed.value.error.code == 'idempotency_conflict'
    after = counts(c, data)
    assert after['finance_case_subsidy_plan_events'] == 1
    assert after['staff_obligation_installments'] == 2
    assert after['staff_payout_events'] == (2 if prior else 1)
    query = application.query(data['staff'])['obligations'][0]
    assert (int(query['net_paid_ntd']), int(query['balance_ntd']), query['payout_status']) == (18000,12000,'partially_paid')
    assert {p['funding_kind']:p['remaining_ntd'] for p in query['funding_portions']} == {'client':0,'subsidy':12000}
    assert {p['funding_kind']:p['due_date'] for p in query['funding_portions']} == {'client':'2026-10-15','subsidy':'2026-11-15'}
    assert MySqlAccountingWorkspaceState(c).subsidy_plan(data['case']).selected_scheme == 'split'
    with c.cursor() as q:
        q.execute('SELECT amount_due_ntd,due_date FROM staff_obligations WHERE obligation_identity=%s',(data['identity'],))
        assert q.fetchone() == {'amount_due_ntd':30000,'due_date':date(2026,10,15)}
    tail = selected(data, source(c,data,11970,'taishin'), split=False)
    tail_preview = application.preview(tail, CorrelationId('subsidy'))
    assert tail_preview.candidate.transfer_fee.amount == 30
    assert application.apply(request(tail,tail_preview)).resulting_status.value == 'completed'
    final = application.query(data['staff'])['obligations'][0]
    assert int(final['balance_ntd']) == 0 and all(p['remaining_ntd']==0 for p in final['funding_portions'])
    item = query_case_staff_accounting(c,data['case'])[0][0]
    assert item.remaining_ntd == 0 and item.settled


def test_failure_after_plan_and_schedule_rolls_back_everything(connection, monkeypatch):
    c = connection; data = seed(c)
    application = build_staff_payout_application(c)
    selection = selected(data, source(c,data))
    checked = application.preview(selection,CorrelationId('rollback'))
    before = counts(c,data)
    monkeypatch.setattr(application.repository, 'append_events', lambda *_: (_ for _ in ()).throw(RuntimeError('synthetic failure')))
    with pytest.raises(StaffPayoutReconciliationError):
        application.apply(request(selection,checked))
    assert counts(c,data)==before


@pytest.mark.parametrize('subsidy_amount',[12000,22000])
def test_payable_export_uses_bank_funding_balance_when_subsidy_was_paid_first(connection,subsidy_amount):
    from infrastructure.mysql.accounts_payable_export_sources import MySqlStaffPayableExportSource
    c=connection;data=seed(c,installments=True,scheme='split',subsidy=subsidy_amount)
    application=build_staff_payout_application(c)
    subsidy=selected(data,source(c,data,subsidy_amount-30,'taishin'),split=False)
    checked=application.preview(subsidy,CorrelationId('subsidy-first-export'))
    application.apply(request(subsidy,checked))
    export=MySqlStaffPayableExportSource(c)
    client_rows=[r for r in export.load(date(2026,10,15)) if r.obligation_identity==data['identity']]
    subsidy_rows=[r for r in export.load(date(2026,11,15)) if r.obligation_identity==data['identity']]
    assert len(client_rows)==1 and client_rows[0].amount.amount==30000-subsidy_amount
    assert client_rows[0].status.value=='payable'
    assert subsidy_rows==[], 'paid subsidy must not be exported a second time'
    audit=export.load_case(data['case'],date(2026,10,15))
    assert {r.funding_kind:r.balance.amount for r in audit if r.obligation_identity==data['identity']} == {'client':30000-subsidy_amount,'subsidy':0}


@pytest.mark.parametrize('kind', ['other_plan','missing_subsidy','subsidy_changed','plan_changed','wrong_bank','customer_amount_conflict','refund_conflict'])
def test_unsafe_or_stale_split_cannot_partially_save(connection,kind):
    c=connection
    data=seed(c,scheme='advance' if kind=='other_plan' else None,subsidy=None if kind=='missing_subsidy' else 12000)
    if kind=='customer_amount_conflict':
        with c.cursor() as q:
            for stage in ('deposit','first','second'):
                identity=uuid4().hex
                q.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES(%s,%s,%s,'receivable_from_client','established',0,10000,'2026-10-15',%s,0,%s,'synthetic','conflict fixture')",(identity,data['case'],stage,identity,identity))
                event=q.lastrowid
                q.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES(%s,%s,%s,'receivable_from_client',10000,'2026-10-15','open',%s,0)",(identity,data['case'],stage,event))
        c.commit()
    if kind=='refund_conflict':
        with c.cursor() as q:
            identity=uuid4().hex
            q.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES(%s,%s,'subsidy_return','payable_to_client','established',0,12000,'2026-11-15',%s,0,%s,'synthetic','refund fixture')",(identity,data['case'],identity,identity))
            event=q.lastrowid
            q.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES(%s,%s,'subsidy_return','payable_to_client',12000,'2026-11-15','open',%s,0)",(identity,data['case'],event))
        c.commit()
    row=source(c,data,bank='taishin' if kind=='wrong_bank' else 'sinopac')
    application=build_staff_payout_application(c); selection=selected(data,row)
    before=counts(c,data)
    if kind in {'other_plan','missing_subsidy','wrong_bank','customer_amount_conflict','refund_conflict'}:
        with pytest.raises(StaffPayoutReconciliationError): application.preview(selection,CorrelationId('blocked'))
    else:
        checked=application.preview(selection,CorrelationId('stale'))
        if kind=='subsidy_changed':
            with c.cursor() as q:q.execute('UPDATE government_subsidy_amount_controls SET effective_ntd=13000 WHERE case_no=%s',(data['case'],))
        else:
            MySqlAccountingWorkspaceState(c).append_subsidy_plan(data['case'],1,'split','synthetic',uuid4().hex)
            before['finance_case_subsidy_plan_events']=1
        c.commit()
        with pytest.raises(StaffPayoutReconciliationError) as failure: application.apply(request(selection,checked))
        assert failure.value.error.category.value=='conflict'
    assert counts(c,data)==before

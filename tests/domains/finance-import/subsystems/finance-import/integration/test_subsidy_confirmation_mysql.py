"""SUBSIDY-FLOW: original ingestion, zero-write Preview, Apply and money owners."""
import os
from datetime import date
from uuid import uuid4

import pandas as pd
import pymysql
import pytest

from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey

pytestmark = pytest.mark.skipif(os.getenv('SUBSIDY_CONFIRMATION_MYSQL') != '1', reason='explicit isolated MySQL acceptance')


def application(connection):
    from api.dependencies.finance_import import build_finance_import_application
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    return build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))


@pytest.fixture
def connection(monkeypatch):
    from infrastructure.mysql import mysql_adapter
    config = dict(mysql_adapter.DB_CONFIG)
    assert os.getenv('APP_ENV') == 'development' and config['host'] in {'localhost','127.0.0.1'}
    assert config['database'].startswith('lu_test_subsidy_b_')
    c = pymysql.connect(**config, cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    yield c
    c.rollback()
    c.close()


def seed(c, historical, scheme, *, paid=True, subsidy=12000, completed=True, actual_end=date(2026, 9, 10), staff=None):
    name = '合成補助月嫂' + uuid4().hex[:8].translate(str.maketrans('0123456789','qrstuvwxyz'))
    with c.cursor() as q:
        while True:
            case = f'{800+int(uuid4().hex[:3],16)%100:03d}{int(uuid4().hex[:3],16)%1000:06d}'
            q.execute('SELECT case_no FROM orders WHERE case_no=%s',(case,))
            if q.fetchone() is None:
                break
        status = ('歷史訂單－服務完成' if historical else '訂單完成') if completed else ('歷史訂單－服務中' if historical else '服務中')
        q.execute("INSERT INTO clients(case_no,name,identity_status) VALUES(%s,'Synthetic Subsidy Client','一般市民')",(case,))
        q.execute("INSERT INTO orders(case_no,client_id,status,start_date,end_date,actual_start_date,actual_end_date,service_days,service_hours_per_day,floor_fee) "
                  "VALUES(%s,%s,%s,'2026-09-01','2026-09-10','2026-09-01',%s,10,10,0)",(case,q.lastrowid,status,actual_end))
        q.execute('INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES(%s,0)',(case,))
        if staff is None:
            q.execute('INSERT INTO staff(name) VALUES(%s)', (name,))
            staff = q.lastrowid
        else:
            q.execute('SELECT name FROM staff WHERE id=%s', (staff,))
            name = q.fetchone()['name']
        q.execute('UPDATE orders SET staff_id=%s WHERE case_no=%s',(staff,case))
        q.execute("INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status) VALUES(%s,%s,1,'completed')",(case,staff)); assignment=q.lastrowid
        identity='subsidy-fixture:'+uuid4().hex
        q.execute("INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) "
            "VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,30000,'2026-10-15',%s,0,1,%s,'synthetic','Evidenced original payable fixture')",(identity,assignment,case,staff,'a'*64,identity)); event=q.lastrowid
        q.execute("INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,amount_due_ntd,due_date,status,current_event_id,payroll_version) "
            "VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff',30000,'2026-10-15','open',%s,1)",(identity,assignment,case,staff,event))
        if subsidy is not None:
            q.execute("INSERT INTO government_subsidy_amount_controls(case_no,period_year,amount_mode,computed_ntd,effective_ntd) VALUES(%s,2026,'manual',%s,%s)",(case,subsidy,subsidy))
        amounts=(5000,7000,18000-(subsidy if subsidy is not None else 12000)) if scheme=='split' else (5000,10000,15000)
        for stage,amount in zip(('deposit','first','second'),amounts):
            target=f'{case}:{stage}'
            q.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) "
                "VALUES(%s,%s,%s,'receivable_from_client','established',0,%s,'2026-09-01',%s,0,%s,'synthetic','Evidenced original period fixture')",(target,case,stage,amount,target,target)); event=q.lastrowid
            q.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES(%s,%s,%s,'receivable_from_client',%s,'2026-09-01','open',%s,0)",(target,case,stage,amount,event))
            if paid:
                q.execute("INSERT INTO client_ledger_entries(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) VALUES(%s,'receipt',%s,'2026-09-01',%s,%s,'synthetic','Original allocated receipt fixture')",(case,amount,uuid4().hex,uuid4().hex)); entry=q.lastrowid
                q.execute('INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES(%s,%s,%s,1)',(entry,target,amount))
                q.execute("UPDATE client_obligations SET amount_due_ntd=0,status='settled' WHERE obligation_identity=%s",(target,))
        c.commit()
    return case,name,identity


def bank_source(c, tmp_path, case, name, scheme, *, cash=11970, bare_case=False, transaction_date=date(2026,11,15), memo_override=None):
    from api.dependencies.finance_import import get_finance_import_ingestion_service
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
    memo = name+'補助款' if scheme=='split' else 'HC'+build_client_virtual_account(case)[-6:]+'雇主補助款'
    if bare_case:
        memo = 'HC'+build_client_virtual_account(case)[-6:]
    if memo_override is not None:
        memo = memo_override
    path=tmp_path/(uuid4().hex+'.xlsx')
    pd.DataFrame([['說明'],['序號','交易日期','交易時間','帳務日期','摘要','支出金額','存入金額','帳戶餘額','備註'],
        ['0001',transaction_date.strftime('%Y/%m/%d'),'09:00:00',transaction_date.strftime('%Y/%m/%d'),'轉出',cash,'',90000,memo]]).to_excel(path,index=False,header=False)
    ingest = get_finance_import_ingestion_service()
    result = ingest(str(path), IdempotencyKey('ingest:' + uuid4().hex), ActorContext('synthetic'))
    assert result.canonical_created_count==1
    c.rollback()  # Refresh the read-only pre-ingest REPEATABLE READ snapshot.
    return result.batch_identity


def snapshot(c, case):
    with c.cursor() as q:
        result={}
        for table in ('finance_case_subsidy_plan_events','client_obligation_events','client_ledger_entries','staff_obligation_events'):
            q.execute(f'SELECT COUNT(*) n FROM {table} WHERE case_no=%s',(case,));result[table]=q.fetchone()['n']
        q.execute('SELECT COUNT(*) n FROM staff_obligation_installments i JOIN staff_obligations o ON o.obligation_identity=i.obligation_identity WHERE o.case_no=%s',(case,));result['installments']=q.fetchone()['n']
    return result


@pytest.mark.parametrize('same_month', [False, True])
def test_staff_subsidy_case_match_with_multiple_assignments(connection, tmp_path, same_month):
    from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest

    case, name, _ = seed(connection, False, 'split')
    with connection.cursor() as cursor:
        cursor.execute('SELECT staff_id FROM orders WHERE case_no=%s', (case,))
        staff = cursor.fetchone()['staff_id']
    other, _, _ = seed(connection, False, 'split', staff=staff,
                       actual_end=date(2026, 9 if same_month else 10, 20), subsidy=8000)
    batch = bank_source(connection, tmp_path, case, name, 'split', memo_override=name)
    app = application(connection)
    correlation = CorrelationId('staff-subsidy-candidates')
    plan = app.preview_batch(batch, correlation)
    row = plan.rows[0]
    assert {item.case_no for item in row.staff_subsidy_cases} == ({case, other} if same_month else {case})
    selections = ()
    if same_month:
        assert row.pending_reason == 'staff_subsidy_multiple_same_month_cases'
        assert not plan.dispatchable_rows
        assert {item.payable_amount_ntd for item in row.staff_subsidy_cases} == {8000, 12000}
        invalid = app.preview_batch(batch, correlation, ((row.row_identity, 'invalid-case'),))
        assert invalid.rows[0].pending_reason == 'staff_subsidy_case_selection_invalid'
        selections = ((row.row_identity, case),)
        plan = app.preview_batch(batch, correlation, selections)
    assert len(plan.dispatchable_rows) == 1, [item.pending_reason for item in plan.rows]
    assert plan.dispatchable_rows[0].subsidy_preflight.case_no == case
    receipt = app.apply_batch(FinanceImportApplyRequest(
        batch, ExpectedVersion(plan.batch_version), plan.fingerprint,
        IdempotencyKey('apply:' + uuid4().hex), ActorContext('synthetic'), '', correlation, selections,
    ))
    assert receipt.reconciled_count == 1
    state = MySqlAccountingWorkspaceState(connection)
    assert state.subsidy_plan(case).selected_scheme == 'split'
    assert state.subsidy_plan(other).selected_scheme is None


@pytest.mark.parametrize('scheme', ['split', 'advance'])
def test_pending_rematch_settles_existing_confirmed_subsidy(connection, tmp_path, scheme):
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from subsystems.finance_import.import_workflow import PendingReconciliationRequest

    case, name, _ = seed(connection, False, scheme)
    workspace = build_accounting_workspace(connection)
    preview = workspace.preview_subsidy_plan(case, scheme, 0)
    assert preview.blocker is None
    workspace.save_subsidy_plan(case, scheme, 0, 'manual:' + uuid4().hex, 'synthetic', preview.fingerprint.value)
    connection.commit()
    batch = bank_source(connection, tmp_path, case, name, scheme)
    app = application(connection)
    correlation = CorrelationId('staff-subsidy-rematch')
    plan = app.preview_batch(batch, correlation)
    assert len(plan.dispatchable_rows) == 1, [item.pending_reason for item in plan.rows]
    assert plan.dispatchable_rows[0].subsidy_preflight.existing_confirmed_payable
    receipt = app.reconcile_pending(PendingReconciliationRequest(
        IdempotencyKey('rematch:' + uuid4().hex), ActorContext('synthetic'), correlation,
    ))
    assert receipt.reconciled_count >= 1
    assert any(t.bank_amount_ntd == 11970 and t.transfer_fee_ntd == 30
               for t in workspace.query(case).transactions)


@pytest.mark.parametrize('suffix_text', ['雇主補助款', '服務人員薪資'])
def test_existing_six_digit_subsidy_memos_still_ingest(connection, tmp_path, suffix_text):
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account

    case, name, _ = seed(connection, False, 'advance')
    memo = 'HC' + build_client_virtual_account(case)[-6:] + suffix_text
    bank_source(connection, tmp_path, case, name, 'advance', memo_override=memo)


@pytest.mark.parametrize('historical',[False,True])
@pytest.mark.parametrize('scheme',['split','advance'])
def test_bank_preview_then_apply_confirms_builds_and_settles_once(connection,tmp_path,historical,scheme):
    from api.dependencies.finance_import import build_finance_import_application
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace, MySqlAccountingWorkspaceState
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    case,name,identity=seed(connection,historical,scheme)
    case_before=build_accounting_workspace(connection).query(case)
    assert case_before.subsidy_ntd==12000 and case_before.subsidy_plan.selected_scheme is None
    batch=bank_source(connection,tmp_path,case,name,scheme)
    before=snapshot(connection,case)
    app=application(connection)
    plan=app.preview_batch(batch,CorrelationId('subsidy-test'))
    assert snapshot(connection,case)==before
    assert len(plan.dispatchable_rows)==1,[(r.pending_reason,r.evidence,r.subsidy_preflight) for r in plan.rows]
    candidate=plan.dispatchable_rows[0]
    assert candidate.subsidy_preflight.scheme==scheme
    from api.routes.finance_import import _plan_payload
    from api.schemas.finance_import import FinanceImportBatchPreviewView
    displayed = FinanceImportBatchPreviewView.model_validate(_plan_payload(plan)).rows[0].subsidy_preflight
    assert displayed.subsidy_ntd == displayed.payable_amount_ntd == displayed.settlement_ntd == 12000
    assert displayed.bank_cash_ntd == 11970 and displayed.transfer_fee_ntd == 30 and displayed.remaining_ntd == 0
    if scheme=='advance':
        assert candidate.subsidy_preflight.proposed_refund.amount.amount==12000
    else:
        assert candidate.subsidy_preflight.staff_confirm_split
    command=FinanceImportApplyRequest(batch,ExpectedVersion(plan.batch_version),plan.fingerprint,IdempotencyKey('apply:'+uuid4().hex),ActorContext('synthetic'),'',CorrelationId('subsidy-test'))
    receipt=app.apply_batch(command)
    assert receipt.reconciled_count==1
    confirmed=MySqlAccountingWorkspaceState(connection).subsidy_plan(case)
    assert confirmed.selected_scheme==scheme and confirmed.confirmation_source=='bank'
    assert confirmed.events[-1].bank_row_identity==candidate.row_identity
    after=snapshot(connection,case)
    readback=build_accounting_workspace(connection).query(case)
    assert any(t.bank_amount_ntd==11970 and t.transfer_fee_ntd==30 and t.amount_ntd==12000
        for t in readback.transactions)
    assert app.apply_batch(command)==receipt and snapshot(connection,case)==after
    assert after['finance_case_subsidy_plan_events']==1
    with connection.cursor() as q:
        if scheme=='advance':
            q.execute("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case,))
            assert q.fetchone()['amount_due_ntd']==0
        else:
            q.execute('SELECT funding_kind,amount_ntd FROM staff_obligation_installments WHERE obligation_identity=%s ORDER BY funding_kind',(identity,))
            assert [(r['funding_kind'],int(r['amount_ntd'])) for r in q.fetchall()]==[('client',18000),('subsidy',12000)]


@pytest.mark.parametrize('historical',[False,True])
def test_missing_advance_cash_blocks_financial_action_before_apply(connection,tmp_path,historical):
    from api.dependencies.finance_import import build_finance_import_application
    case,name,_=seed(connection,historical,'advance',paid=False)
    batch=bank_source(connection,tmp_path,case,name,'advance')
    before=snapshot(connection,case)
    plan=application(connection).preview_batch(batch,CorrelationId('subsidy-blocked'))
    assert not plan.dispatchable_rows
    assert plan.rows[0].subsidy_preflight.scheme=='advance'
    assert plan.rows[0].pending_reason and snapshot(connection,case)==before


@pytest.mark.parametrize(('actual_end', 'expected_due'), [
    (None, date(2026, 11, 15)),
    (date(2026, 10, 1), date(2026, 12, 15)),
])
def test_historical_staff_subsidy_uses_same_due_date_in_both_previews(connection, tmp_path, actual_end, expected_due):
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest

    case, name, _ = seed(connection, True, 'split', actual_end=actual_end)
    batch = bank_source(connection, tmp_path, case, name, 'split', transaction_date=expected_due,
                        memo_override=name + ' 　GB,轉入0000000000000')
    before = snapshot(connection, case)
    assert before['installments'] == 0

    manual = build_accounting_workspace(connection).preview_subsidy_plan(case, 'split', 0)
    assert manual.blocker is None
    manual_due = next(item.due_date for item in manual.payables if item.recipient == 'staff:subsidy')
    app = application(connection)
    correlation = CorrelationId('historical-staff-subsidy-date')
    bank = app.preview_batch(batch, correlation)
    assert len(bank.dispatchable_rows) == 1, [row.pending_reason for row in bank.rows]
    preflight = bank.dispatchable_rows[0].subsidy_preflight
    assert preflight.payable_due_date == manual_due == expected_due.isoformat()
    assert preflight.payable_amount_ntd == 12000
    assert snapshot(connection, case) == before
    command = FinanceImportApplyRequest(
        batch, ExpectedVersion(bank.batch_version), bank.fingerprint,
        IdempotencyKey('historical-date:' + uuid4().hex), ActorContext('synthetic'), '', correlation,
    )
    assert app.apply_batch(command).reconciled_count == 1
    readback = build_accounting_workspace(connection).query(case)
    subsidy_portion = next(
        portion for item in readback.staff_items for portion in item.funding_portions
        if portion.funding_kind == 'subsidy'
    )
    assert (subsidy_portion.due_date, subsidy_portion.amount_ntd, subsidy_portion.remaining_ntd) == (
        expected_due, 12000, 0,
    )
    assert any(t.amount_ntd == 12000 and t.bank_amount_ntd == 11970 and t.transfer_fee_ntd == 30
               for t in readback.transactions)


@pytest.mark.parametrize('historical',[False,True])
@pytest.mark.parametrize('scheme',['split','advance','direct'])
def test_manual_confirmation_previews_and_establishes_without_payment(connection,historical,scheme):
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    case,_,_=seed(connection,historical,scheme)
    app=build_accounting_workspace(connection);before=snapshot(connection,case)
    preview=app.preview_subsidy_plan(case,scheme,0)
    assert preview.blocker is None and len(preview.payables)=={'advance':1,'split':2,'direct':0}[scheme]
    assert snapshot(connection,case)==before
    with pytest.raises(ValueError,match='subsidy_plan_command_invalid'):
        app.save_subsidy_plan(case,scheme,0,'bank-subsidy:1:forged','synthetic',preview.fingerprint.value)
    app.save_subsidy_plan(case,scheme,0,'manual:'+uuid4().hex,'synthetic',preview.fingerprint.value)
    after=snapshot(connection,case)
    assert after['client_obligation_events']==before['client_obligation_events']+int(scheme=='advance')
    assert after['installments']==before['installments']+(2 if scheme=='split' else 0)
    assert after['client_ledger_entries']==before['client_ledger_entries']


@pytest.mark.parametrize('historical',[False,True])
def test_confirmed_advance_with_lawful_refund_keeps_original_bare_case_bank_evidence(connection,tmp_path,historical):
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    case,name,_=seed(connection,historical,'advance')
    workspace=build_accounting_workspace(connection)
    preview=workspace.preview_subsidy_plan(case,'advance',0)
    workspace.save_subsidy_plan(case,'advance',0,'original:'+uuid4().hex,'synthetic',preview.fingerprint.value)
    batch=bank_source(connection,tmp_path,case,name,'advance',bare_case=True)
    app=application(connection)
    plan=app.preview_batch(batch,CorrelationId('original-evidence'))
    assert len(plan.dispatchable_rows)==1 and plan.rows[0].subsidy_preflight.proposed_refund is None
    receipt=app.apply_batch(FinanceImportApplyRequest(batch,ExpectedVersion(plan.batch_version),plan.fingerprint,
        IdempotencyKey('bare:'+uuid4().hex),ActorContext('synthetic'),'',CorrelationId('original-evidence')))
    assert receipt.reconciled_count==1 and snapshot(connection,case)['finance_case_subsidy_plan_events']==1


@pytest.mark.parametrize('historical',[False,True])
def test_bank_confirmation_can_precede_service_completion_without_financial_effect(connection,tmp_path,historical):
    from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    case,name,_=seed(connection,historical,'advance',completed=False)
    batch=bank_source(connection,tmp_path,case,name,'advance')
    app=application(connection);before=snapshot(connection,case)
    plan=app.preview_batch(batch,CorrelationId('early-bank'))
    assert plan.dispatchable_rows[0].subsidy_preflight.confirmation_only
    request=FinanceImportApplyRequest(batch,ExpectedVersion(plan.batch_version),plan.fingerprint,
        IdempotencyKey('early:'+uuid4().hex),ActorContext('synthetic'),'',CorrelationId('early-bank'))
    receipt=app.apply_batch(request)
    assert receipt.pending_count==1 and receipt.reconciled_count==0
    after=snapshot(connection,case)
    assert after['finance_case_subsidy_plan_events']==1
    assert all(after[k]==v for k,v in before.items() if k!='finance_case_subsidy_plan_events')
    assert MySqlAccountingWorkspaceState(connection).subsidy_plan(case).confirmation_source=='bank'


@pytest.mark.parametrize('historical',[False,True])
def test_apply_failure_rolls_back_confirmation_new_payable_and_settlement(connection,tmp_path,monkeypatch,historical):
    from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest,FinanceImportWorkflowError
    case,name,_=seed(connection,historical,'advance')
    batch=bank_source(connection,tmp_path,case,name,'advance')
    app=application(connection);before=snapshot(connection,case)
    plan=app.preview_batch(batch,CorrelationId('atomic-bank'))
    assert len(plan.dispatchable_rows)==1
    monkeypatch.setattr(MySqlClientRefundReversalRepository,'append_allocations',lambda *_:(_ for _ in ()).throw(RuntimeError('synthetic failure after ledger')))
    request=FinanceImportApplyRequest(batch,ExpectedVersion(plan.batch_version),plan.fingerprint,
        IdempotencyKey('atomic:'+uuid4().hex),ActorContext('synthetic'),'',CorrelationId('atomic-bank'))
    with pytest.raises(FinanceImportWorkflowError):
        app.apply_batch(request)
    assert snapshot(connection,case)==before


@pytest.mark.parametrize('historical',[False,True])
def test_changed_subsidy_source_requires_new_preview(connection,tmp_path,historical):
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest,FinanceImportWorkflowError
    case,name,_=seed(connection,historical,'advance')
    batch=bank_source(connection,tmp_path,case,name,'advance')
    app=application(connection)
    plan=app.preview_batch(batch,CorrelationId('changed-bank'))
    assert len(plan.dispatchable_rows)==1
    with connection.cursor() as q:
        q.execute('UPDATE government_subsidy_amount_controls SET effective_ntd=13000 WHERE case_no=%s',(case,))
    connection.commit();before=snapshot(connection,case)
    request=FinanceImportApplyRequest(batch,ExpectedVersion(plan.batch_version),plan.fingerprint,
        IdempotencyKey('changed:'+uuid4().hex),ActorContext('synthetic'),'',CorrelationId('changed-bank'))
    with pytest.raises(FinanceImportWorkflowError) as error:
        app.apply_batch(request)
    assert error.value.error.code=='stale_preview'
    assert snapshot(connection,case)==before


@pytest.mark.parametrize('status',['訂單完成','歷史訂單－服務完成'])
def test_original_service_volume_computes_subsidy_before_any_scheme(status):
    from subsystems.government_subsidy.reconciliation_register_query import project_receivable_estimate
    source={'order_status':status,'identity_status':'一般市民','service_days':2,'service_hours_per_day':8,
        'payroll_hourly_rate_ntd':300,'historical_actual_service_hours':None}
    assert project_receivable_estimate(source).amount_ntd==4800
    assert project_receivable_estimate({**source,'payroll_hourly_rate_ntd':None}).amount_ntd is None
    assert project_receivable_estimate({**source,'pricing_active':1,'pricing_rule':'non_citizen'}).amount_ntd==0


def test_adopted_history_computes_subsidy_from_original_rates_without_daily_schedule(connection):
    from tests.domains.orders.subsystems.orders.integration.historical_accounting_scenarios import create_historical_scenario
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    case=f'79{int(uuid4().hex[:7],16)%10000000:07d}'
    create_historical_scenario(connection,case,paid=0,waiting=1000)
    before=snapshot(connection,case)
    detail=build_accounting_workspace(connection).query(case)
    assert detail.subsidy_ntd==12000 and detail.subsidy_plan.selected_scheme is None
    assert snapshot(connection,case)==before
    with connection.cursor() as q:
        q.execute('SELECT COUNT(*) n FROM staff_schedule WHERE case_no=%s',(case,))
        assert q.fetchone()['n']==0


def test_adopted_history_single_original_period_can_preflight_and_refund_its_real_advance(connection,tmp_path):
    from tests.domains.orders.subsystems.orders.integration.historical_accounting_scenarios import create_historical_scenario
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    with connection.cursor() as q:
        while True:
            case=f'797000{1+int(uuid4().hex[:4],16)%998:03d}'
            q.execute('SELECT case_no FROM orders WHERE case_no=%s',(case,))
            if q.fetchone() is None:break
    original=create_historical_scenario(connection,case,paid=72000,waiting=1000)
    workspace=build_accounting_workspace(connection)
    detail=workspace.query(case)
    assert detail.customer_amount_ntd==detail.customer_paid_ntd==72000
    assert detail.customer_fully_received and detail.collection_progress.stage=='scheme'
    assert len([i for i in detail.client_items if i.payment_stage])==1
    assert detail.subsidy_plan.selected_scheme is None and detail.subsidy_ntd==12000
    projected=workspace.preview_subsidy_plan(case,'advance',0)
    assert projected.blocker is None and projected.payables[0].amount_ntd==12000
    with connection.cursor() as q:
        q.execute('SELECT name FROM staff WHERE id=%s',(original.staff_id,));name=q.fetchone()['name']
    batch=bank_source(connection,tmp_path,case,name,'advance',transaction_date=date.fromisoformat(projected.payables[0].due_date))
    app=application(connection);before=snapshot(connection,case)
    plan=app.preview_batch(batch,CorrelationId('historical-original-period'))
    assert len(plan.dispatchable_rows)==1 and snapshot(connection,case)==before
    receipt=app.apply_batch(FinanceImportApplyRequest(batch,ExpectedVersion(plan.batch_version),plan.fingerprint,
        IdempotencyKey('history-single:'+uuid4().hex),ActorContext('synthetic'),'',CorrelationId('historical-original-period')))
    assert receipt.reconciled_count==1
    readback=workspace.query(case)
    assert readback.subsidy_plan.confirmation_source=='bank' and readback.customer_paid_ntd==72000
    assert any(t.amount_ntd==12000 and t.bank_amount_ntd==11970 and t.transfer_fee_ntd==30 for t in readback.transactions)
    with connection.cursor() as q:
        q.execute('SELECT COUNT(*) n FROM staff_schedule WHERE case_no=%s',(case,));assert q.fetchone()['n']==0

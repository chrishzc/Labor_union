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


def seed(c, historical, scheme, *, paid=True, subsidy=12000, completed=True, actual_end=date(2026, 9, 10), staff=None,
         client_name='Synthetic Subsidy Client'):
    name = '合成月嫂' + uuid4().hex[:8].translate(str.maketrans('0123456789','qrstuvwxyz'))
    with c.cursor() as q:
        while True:
            case = f'{800+int(uuid4().hex[:3],16)%100:03d}{int(uuid4().hex[:3],16)%1000:06d}'
            q.execute('SELECT case_no FROM orders WHERE case_no=%s',(case,))
            if q.fetchone() is None:
                break
        status = ('歷史訂單－服務完成' if historical else '訂單完成') if completed else ('歷史訂單－服務中' if historical else '服務中')
        q.execute("INSERT INTO clients(case_no,name,identity_status) VALUES(%s,%s,'一般市民')",(case,client_name))
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
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
    memo = name+'補助款' if scheme=='split' else 'HC'+build_client_virtual_account(case)[-6:]+'雇主補助款'
    if bare_case:
        memo = 'HC'+build_client_virtual_account(case)[-6:]
    if memo_override is not None:
        memo = memo_override
    result = bank_workbook(c, tmp_path, [(transaction_date, cash, memo)])
    assert result.canonical_created_count == 1
    return result.batch_identity


def bank_workbook(c, tmp_path, transactions):
    from api.dependencies.finance_import import get_finance_import_ingestion_service

    path=tmp_path/(uuid4().hex+'.xlsx')
    rows = [['說明'], ['序號','交易日期','交易時間','帳務日期','摘要','支出金額','存入金額','帳戶餘額','備註']]
    for index, (transaction_date, cash, memo) in enumerate(transactions, start=1):
        date_text = transaction_date.strftime('%Y/%m/%d') if transaction_date else ''
        rows.append([f'{index:04d}', date_text, '09:00:00', date_text, '轉出', cash, '', 90000, memo])
    pd.DataFrame(rows).to_excel(path, index=False, header=False)
    ingest = get_finance_import_ingestion_service()
    result = ingest(str(path), IdempotencyKey('ingest:' + uuid4().hex), ActorContext('synthetic'))
    c.rollback()  # Refresh the read-only pre-ingest REPEATABLE READ snapshot.
    return result


def snapshot(c, case):
    with c.cursor() as q:
        result={}
        for table in ('finance_case_subsidy_plan_events','client_obligation_events','client_ledger_entries','staff_obligation_events'):
            q.execute(f'SELECT COUNT(*) n FROM {table} WHERE case_no=%s',(case,));result[table]=q.fetchone()['n']
        q.execute('SELECT COUNT(*) n FROM staff_obligation_installments i JOIN staff_obligations o ON o.obligation_identity=i.obligation_identity WHERE o.case_no=%s',(case,));result['installments']=q.fetchone()['n']
    return result


@pytest.mark.parametrize('scenario', ['unique_month', 'same_month', 'no_month', 'suffix', 'wrong_suffix', 'missing_date', 'rematch'])
def test_shared_client_name_refund_uses_the_unique_eligible_case(connection, tmp_path, scenario):
    from contextlib import closing
    from api.dependencies.finance_import import get_finance_import_query_service
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest, PendingReconciliationRequest

    name = '合成同名客戶' + uuid4().hex[:8].translate(str.maketrans('0123456789', 'qrstuvwxyz'))
    first, _, _ = seed(connection, False, 'advance', client_name=name)
    second, _, _ = seed(connection, True, 'advance', client_name=name, subsidy=8000,
                       actual_end=date(2026, 9 if scenario in {'same_month', 'suffix'} else 10, 20))
    date_on = date(2026, 10 if scenario == 'no_month' else 11, 15)
    memo = name + ' GB,轉入0000000000000003'
    if scenario in {'suffix', 'wrong_suffix'}:
        suffix_case = first
        if scenario == 'wrong_suffix':
            suffix_case, _, _ = seed(connection, False, 'advance')
        memo = name + ' HC' + build_client_virtual_account(suffix_case)[-6:]
    receipt = bank_workbook(connection, tmp_path, [(None if scenario == 'missing_date' else date_on, 11970, memo)])
    if scenario == 'missing_date':
        assert receipt.canonical_created_count == 0 and receipt.source_warning_count == 1
        return
    assert receipt.canonical_created_count == 1
    before = {case: snapshot(connection, case) for case in (first, second)}
    app = application(connection)
    correlation = CorrelationId('synthetic-shared-client-name')
    plan = app.preview_batch(receipt.batch_identity, correlation)
    row, = plan.rows
    reason = {
        'same_month': 'client_subsidy_multiple_same_month_cases',
        'no_month': 'outgoing_client_refund_month_no_match',
        'wrong_suffix': 'client_subsidy_memo_recipient_unconfirmed',
    }.get(scenario)
    with closing(get_finance_import_query_service()) as query:
        listed, = next(query).bank_transactions(bank='taishin', direction='outgoing', status='pending',
            start=None, end=None, search='', limit=1, before_row_id=None,
            row_id=int(row.row_identity.rsplit(':', 1)[-1]))['items']
    if reason:
        assert not plan.dispatchable_rows and row.pending_reason == reason
        assert listed['cases'] == [] and listed['reconciliation_target'] is None
    else:
        assert plan.dispatchable_rows == (row,) and row.subsidy_preflight.case_no == first
        assert listed['cases'] == [first]
    assert {case: snapshot(connection, case) for case in (first, second)} == before

    request = FinanceImportApplyRequest(receipt.batch_identity, ExpectedVersion(plan.batch_version), plan.fingerprint,
        IdempotencyKey('shared-client:' + uuid4().hex), ActorContext('synthetic'), '', correlation)
    if scenario == 'rematch':
        applied = app.reconcile_pending(PendingReconciliationRequest(request.idempotency_key, request.actor, correlation))
        assert applied.reconciled_count >= 1
        assert snapshot(connection, second) == before[second]
        assert snapshot(connection, first)['client_ledger_entries'] == before[first]['client_ledger_entries'] + 1
        return
    applied = app.apply_batch(request)
    assert applied.reconciled_count == (0 if reason else 1)
    assert snapshot(connection, second) == before[second]
    if reason:
        assert snapshot(connection, first) == before[first]
    else:
        assert snapshot(connection, first)['client_ledger_entries'] == before[first]['client_ledger_entries'] + 1
        assert app.apply_batch(request) == applied


def test_mixed_statement_continues_with_eligible_rows_and_corrected_workbook(connection, tmp_path):
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    from subsystems.finance_import.query import FinanceImportQueryService

    good, _, _ = seed(connection, True, 'advance')
    conflict, staff_name, _ = seed(connection, False, 'split', completed=False)
    wrong_month, _, _ = seed(connection, True, 'advance')
    short_paid, _, _ = seed(connection, False, 'advance')
    no_advance, _, _ = seed(connection, False, 'advance', paid=False)

    def memo(case, suffix='雇主補助款'):
        return 'HC' + build_client_virtual_account(case)[-6:] + suffix

    november = date(2026, 11, 15)
    good_row = (november, 11900, memo(good))
    imported = bank_workbook(connection, tmp_path, [
        good_row,
        (november, 12000, memo(conflict)),
        (november, 12000, memo(conflict, staff_name + '補助款')),
        (date(2026, 12, 15), 12000, memo(wrong_month)),
        (november, 11899, memo(short_paid)),
        (november, 12000, memo(no_advance)),
        (november, 12000, '無法辨識的合成備註'),
    ])
    assert imported.canonical_created_count == 6
    cases = (good, conflict, wrong_month, short_paid, no_advance)
    before = {case: snapshot(connection, case) for case in cases}
    app = application(connection)
    correlation = CorrelationId('synthetic-mixed-statement')
    plan = app.preview_batch(imported.batch_identity, correlation)
    assert {case: snapshot(connection, case) for case in cases} == before
    pending = {}
    for row in plan.rows:
        if row.pending_reason:
            pending.setdefault(row.subsidy_preflight.case_no, []).append(row.pending_reason)
    assert pending[conflict] == ['subsidy_confirmation_plan_conflict'] * 2
    assert pending[wrong_month] == ['outgoing_client_refund_month_no_match']
    assert pending[short_paid] == ['outgoing_client_refund_amount_mismatch']
    assert pending[no_advance] == ['客戶實際墊款依據不足，保留既有款項並待確認。']
    assert [row.subsidy_preflight.case_no for row in plan.dispatchable_rows] == [good]

    request = FinanceImportApplyRequest(imported.batch_identity, ExpectedVersion(plan.batch_version), plan.fingerprint,
        IdempotencyKey('mixed:' + uuid4().hex), ActorContext('synthetic'), '', correlation)
    receipt = app.apply_batch(request)
    assert receipt.reconciled_count == 1
    bank_query = FinanceImportQueryService(connection)
    for row in plan.rows:
        if row.pending_reason:
            saved, = bank_query.bank_transactions(bank='taishin', direction='outgoing', status='pending',
                start=None, end=None, search='', limit=1, before_row_id=None,
                row_id=int(row.row_identity.rsplit(':', 1)[-1]))['items']
            assert saved['recorded_pending_reason'] == row.pending_reason
    assert all(snapshot(connection, case) == before[case] for case in cases if case != good)
    assert app.apply_batch(request) == receipt

    corrected = bank_workbook(connection, tmp_path, [
        good_row, (november, 12000, memo(wrong_month)), (november, 11900, memo(short_paid)),
    ])
    assert (corrected.canonical_created_count, corrected.duplicate_occurrence_count) == (2, 1)
    plan = app.preview_batch(corrected.batch_identity, correlation)
    assert {row.subsidy_preflight.case_no for row in plan.dispatchable_rows} == {wrong_month, short_paid}
    receipt = app.apply_batch(FinanceImportApplyRequest(corrected.batch_identity, ExpectedVersion(plan.batch_version),
        plan.fingerprint, IdempotencyKey('corrected:' + uuid4().hex), ActorContext('synthetic'), '', correlation))
    assert receipt.reconciled_count == 2


def test_mixed_shared_name_statement_respects_order_and_refund_state(connection, tmp_path):
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest

    base = '合成退款' + uuid4().hex[:8].translate(str.maketrans('0123456789', 'qrstuvwxyz'))
    workspace = build_accounting_workspace(connection)
    app = application(connection)
    correlation = CorrelationId('synthetic-shared-name-status-matrix')
    november = date(2026, 11, 15)
    cases = []
    targets = set()
    transactions = []
    for suffix in ('進行', '未墊', '已退', '皆未墊'):
        name = base + suffix
        eligible, _, _ = seed(connection, False, 'advance', client_name=name, paid=suffix != '皆未墊')
        other, _, _ = seed(connection, True, 'advance', client_name=name, completed=suffix != '進行',
                           paid=suffix not in {'未墊', '皆未墊'})
        cases.extend((eligible, other))
        if suffix != '皆未墊':
            targets.add(eligible)
        if suffix == '已退':
            preview = workspace.preview_subsidy_plan(other, 'advance', 0)
            workspace.save_subsidy_plan(other, 'advance', 0, 'settled-fixture:' + uuid4().hex, 'synthetic', preview.fingerprint.value)
            connection.commit()
            original = bank_source(connection, tmp_path, other, name, 'advance')
            plan = app.preview_batch(original, correlation)
            assert app.apply_batch(FinanceImportApplyRequest(original, ExpectedVersion(plan.batch_version), plan.fingerprint,
                IdempotencyKey('settled-fixture:' + uuid4().hex), ActorContext('synthetic'), '', correlation)).reconciled_count == 1
        transactions.append((november, 11970, name + ' GB,轉入0000000000000003'))

    before = {case: snapshot(connection, case) for case in cases}
    imported = bank_workbook(connection, tmp_path, transactions)
    assert imported.canonical_created_count == 4
    plan = app.preview_batch(imported.batch_identity, correlation)
    assert {row.subsidy_preflight.case_no for row in plan.dispatchable_rows} == targets
    assert [row.pending_reason for row in plan.rows if row.pending_reason] == ['outgoing_client_refund_month_no_match']
    assert {case: snapshot(connection, case) for case in cases} == before
    request = FinanceImportApplyRequest(imported.batch_identity, ExpectedVersion(plan.batch_version), plan.fingerprint,
        IdempotencyKey('status-matrix:' + uuid4().hex), ActorContext('synthetic'), '', correlation)
    receipt = app.apply_batch(request)
    assert receipt.reconciled_count == 3
    for case in cases:
        after = snapshot(connection, case)
        if case in targets:
            assert after['client_ledger_entries'] == before[case]['client_ledger_entries'] + 1
        else:
            assert after == before[case]
    assert app.apply_batch(request) == receipt


def test_shared_name_with_suffix_cannot_manually_reconcile_another_month(connection, tmp_path):
    from contextlib import closing
    from api.dependencies.finance_import import get_finance_import_query_service
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
    from infrastructure.mysql.finance_import_owning_domain_composite import BorrowedTransactionUnitOfWork
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalError, ClientRefundReversalSelection, ClientRefundReversalWorkflow,
    )
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account

    name = '合成跨月' + uuid4().hex[:8].translate(str.maketrans('0123456789', 'qrstuvwxyz'))
    first, _, _ = seed(connection, False, 'advance', client_name=name)
    second, _, _ = seed(connection, True, 'advance', client_name=name, actual_end=date(2026, 10, 20))
    workspace = build_accounting_workspace(connection)
    payable = workspace.preview_subsidy_plan(first, 'advance', 0)
    workspace.save_subsidy_plan(first, 'advance', 0, 'wrong-month-fixture:' + uuid4().hex, 'synthetic', payable.fingerprint.value)
    connection.commit()
    memo = name + ' HC' + build_client_virtual_account(first)[-6:]
    original = bank_workbook(connection, tmp_path, [(date(2026, 12, 15), 11970, memo)])
    assert original.canonical_created_count == 1
    before = {case: snapshot(connection, case) for case in (first, second)}
    correlation = CorrelationId('shared-name-wrong-month')
    plan = application(connection).preview_batch(original.batch_identity, correlation)
    row, = plan.rows
    assert not plan.dispatchable_rows and row.pending_reason == 'outgoing_client_refund_month_no_match'
    row_id = row.row_identity.rsplit(':', 1)[-1]
    selection = ClientRefundReversalSelection(first, ClientFinanceCorrectionType.REFUND, ClientRefundPurpose.SUBSIDY_RETURN,
        bank_fact_identities=(row_id,), obligation_identities=(payable.refund_plan.obligation_identity,))
    refund_workflow = ClientRefundReversalWorkflow(MySqlClientRefundReversalRepository(connection), BorrowedTransactionUnitOfWork)
    with pytest.raises(ClientRefundReversalError) as error:
        refund_workflow.preview(selection, correlation)
    assert error.value.error.code == 'outgoing_client_refund_month_no_match'
    with closing(get_finance_import_query_service()) as query:
        listed, = next(query).bank_transactions(bank='taishin', direction='outgoing', status='pending',
            start=None, end=None, search='', limit=1, before_row_id=None, row_id=int(row_id))['items']
    assert listed['cases'] == [first] and listed['reconciliation_target'] is None
    assert {case: snapshot(connection, case) for case in (first, second)} == before

    corrected = bank_workbook(connection, tmp_path, [(date(2026, 11, 15), 11970, memo)])
    app = application(connection)
    fixed_plan = app.preview_batch(corrected.batch_identity, correlation)
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    receipt = app.apply_batch(FinanceImportApplyRequest(corrected.batch_identity, ExpectedVersion(fixed_plan.batch_version),
        fixed_plan.fingerprint, IdempotencyKey('corrected-month:' + uuid4().hex), ActorContext('synthetic'), '', correlation))
    assert receipt.reconciled_count == 1
    assert snapshot(connection, first)['client_ledger_entries'] == before[first]['client_ledger_entries'] + 1
    assert snapshot(connection, second) == before[second]


@pytest.mark.parametrize('other_status', ['different_month', 'same_month', 'in_service', 'paid', 'rematch'])
def test_staff_subsidy_case_match_with_multiple_assignments(connection, tmp_path, other_status):
    from dataclasses import replace
    from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest, PendingReconciliationRequest
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account

    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace

    case, name, _ = seed(connection, False, 'split', paid=False)
    with connection.cursor() as cursor:
        cursor.execute('SELECT staff_id FROM orders WHERE case_no=%s', (case,))
        staff = cursor.fetchone()['staff_id']
    same_month = other_status == 'same_month'
    other, _, _ = seed(connection, True, 'split', staff=staff, completed=other_status != 'in_service',
                       actual_end=date(2026, 10 if other_status in {'different_month', 'rematch'} else 9, 20), subsidy=8000, paid=False)
    app = application(connection)
    correlation = CorrelationId('staff-subsidy-candidates')
    if other_status == 'paid':
        paid_batch = bank_source(connection, tmp_path, other, name, 'split', cash=8000,
            memo_override=name + ' HC' + build_client_virtual_account(other)[-6:])
        paid_plan = app.preview_batch(paid_batch, correlation)
        assert app.apply_batch(FinanceImportApplyRequest(paid_batch, ExpectedVersion(paid_plan.batch_version),
            paid_plan.fingerprint, IdempotencyKey('paid-staff:' + uuid4().hex), ActorContext('synthetic'), '', correlation)).reconciled_count == 1
    before = build_accounting_workspace(connection).query(case)
    other_before = build_accounting_workspace(connection).query(other)
    assert before.scheme == 'waiting'
    assert before.subsidy_ntd == 12000 and not before.subsidy_payments
    batch = bank_source(connection, tmp_path, case, name, 'split',
                        memo_override=name + ' 　GB,轉入' + '0' * 15 + '3')
    plan = app.preview_batch(batch, correlation)
    row = plan.rows[0]
    from subsystems.finance_import.query import FinanceImportQueryService
    bank_row, = FinanceImportQueryService(connection).bank_transactions(
        bank='taishin', direction='outgoing', status='pending', start=None, end=None,
        search='', limit=1, before_row_id=None, row_id=int(row.row_identity.rsplit(':', 1)[-1]),
    )['items']
    assert bank_row['staff_subsidy_batch_identity'] == batch
    assert {item.case_no for item in row.staff_subsidy_cases} == ({case, other} if same_month else {case})
    selections = ()
    if same_month:
        assert row.pending_reason == 'staff_subsidy_multiple_same_month_cases'
        assert not plan.dispatchable_rows
        assert {item.payable_amount_ntd for item in row.staff_subsidy_cases} == {8000, 12000}
        app.reconcile_pending(PendingReconciliationRequest(IdempotencyKey('rematch-staff:' + uuid4().hex),
            ActorContext('synthetic'), correlation))
        assert app.preview_batch(batch, correlation).rows[0].pending_reason == 'staff_subsidy_multiple_same_month_cases'
        invalid = app.preview_batch(batch, correlation, ((row.row_identity, 'invalid-case'),))
        assert invalid.rows[0].pending_reason == 'staff_subsidy_case_selection_invalid'
        selections = ((row.row_identity, case),)
        plan = app.preview_batch(batch, correlation, selections)
    assert len(plan.dispatchable_rows) == 1, [item.pending_reason for item in plan.rows]
    assert plan.dispatchable_rows[0].subsidy_preflight.case_no == case
    if other_status == 'rematch':
        receipt = app.reconcile_pending(PendingReconciliationRequest(IdempotencyKey('unique-staff-rematch:' + uuid4().hex),
            ActorContext('synthetic'), correlation))
        assert receipt.reconciled_count >= 1
        assert app.preview_batch(batch, correlation).rows[0].disposition.value == 'existing'
    else:
        receipt = app.apply_batch(FinanceImportApplyRequest(
            batch, ExpectedVersion(plan.batch_version), plan.fingerprint,
            IdempotencyKey('apply:' + uuid4().hex), ActorContext('synthetic'), '', correlation, selections,
        ))
        assert receipt.reconciled_count == 1
    state = MySqlAccountingWorkspaceState(connection)
    assert state.subsidy_plan(case).selected_scheme == 'split'
    other_after = build_accounting_workspace(connection).query(other)
    assert other_after.subsidy_plan == other_before.subsidy_plan
    assert tuple(replace(item, version='') for item in other_after.staff_items) == tuple(
        replace(item, version='') for item in other_before.staff_items)


@pytest.mark.parametrize('existing_installment', [False, True])
def test_staff_subsidy_suffix_with_wrong_month_requires_manual_reconciliation(connection, tmp_path, existing_installment):
    from dataclasses import replace
    from api.dependencies.staff_payout import build_staff_payout_application
    from domains.staff_payables.reconciliation import StaffPayoutEventType
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
    from subsystems.finance_import.import_workflow import PendingReconciliationRequest
    from subsystems.finance_import.query import FinanceImportQueryService
    from subsystems.staff_payables.payout_reconciliation import (
        StaffPayoutApplyRequest, StaffPayoutReconciliationError, StaffPayoutSelection,
    )

    case, name, identity = seed(connection, False, 'split')
    with connection.cursor() as cursor:
        cursor.execute('SELECT staff_id FROM orders WHERE case_no=%s', (case,))
        staff = cursor.fetchone()['staff_id']
    other, _, other_identity = seed(connection, True, 'split', staff=staff, actual_end=date(2026, 10, 20))
    workspace = build_accounting_workspace(connection)
    if existing_installment:
        preview = workspace.preview_subsidy_plan(case, 'split', 0)
        workspace.save_subsidy_plan(case, 'split', 0, 'split-fixture:' + uuid4().hex, 'synthetic', preview.fingerprint.value)
        connection.commit()
    memo = name + ' HC' + build_client_virtual_account(case)[-6:]
    batch = bank_source(connection, tmp_path, case, name, 'split', transaction_date=date(2026, 12, 15), memo_override=memo)
    before = {case_no: workspace.query(case_no) for case_no in (case, other)}
    app = application(connection)
    correlation = CorrelationId('staff-subsidy-wrong-month')
    plan = app.preview_batch(batch, correlation)
    row, = plan.rows
    assert not plan.dispatchable_rows and row.pending_reason == 'outgoing_staff_payout_month_no_match'
    app.reconcile_pending(PendingReconciliationRequest(IdempotencyKey('rematch-wrong-month:' + uuid4().hex),
        ActorContext('synthetic'), correlation))
    assert app.preview_batch(batch, correlation).rows[0].pending_reason == 'outgoing_staff_payout_month_no_match'
    row_id = row.row_identity.rsplit(':', 1)[-1]
    listed, = FinanceImportQueryService(connection).bank_transactions(
        bank='taishin', direction='outgoing', status='pending', start=None, end=None,
        search='', limit=1, before_row_id=None, row_id=int(row_id),
    )['items']
    assert listed['reconciliation_target']['case_no'] == case
    assert listed['reconciliation_target']['obligation_identities'] == [identity]
    selection = StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (row_id,), (identity,))
    workflow = build_staff_payout_application(connection)
    with pytest.raises(StaffPayoutReconciliationError) as error:
        workflow.preview(replace(selection, obligation_identities=(other_identity,)), correlation)
    assert error.value.error.code == 'staff_memo_case_mismatch'
    checked = workflow.preview(selection, correlation)
    for case_no in (case, other):
        assert workspace.query(case_no).staff_items == before[case_no].staff_items

    request = StaffPayoutApplyRequest(selection, ExpectedVersion(checked.staff_payables_version),
        ExpectedVersion(checked.bank_facts_version), checked.fingerprint,
        IdempotencyKey('staff-manual-month:' + uuid4().hex), ActorContext('synthetic'), '人工確認跨月撥款', correlation)
    receipt = workflow.apply(request)
    assert workflow.apply(request) == receipt
    payment, = [item for item in workspace.query(case).staff_items if item.identity == identity]
    assert payment.actual_ntd == 12000
    assert app.preview_batch(batch, correlation).rows[0].disposition.value == 'existing'
    assert tuple(replace(item, version='') for item in workspace.query(other).staff_items) == tuple(
        replace(item, version='') for item in before[other].staff_items)


@pytest.mark.parametrize(('scheme', 'bare_case'), [('split', False), ('advance', False), ('advance', True)])
def test_pending_rematch_settles_existing_confirmed_subsidy(connection, tmp_path, scheme, bare_case):
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from subsystems.finance_import.import_workflow import PendingReconciliationRequest

    case, name, _ = seed(connection, False, scheme)
    workspace = build_accounting_workspace(connection)
    app = application(connection)
    correlation = CorrelationId('staff-subsidy-rematch')
    if bare_case:
        batch = bank_source(connection, tmp_path, case, name, scheme, bare_case=True)
        assert not app.preview_batch(batch, correlation).dispatchable_rows
        assert app.reconcile_pending(PendingReconciliationRequest(
            IdempotencyKey('rematch-before-scheme:' + uuid4().hex), ActorContext('synthetic'), correlation,
        )).reconciled_count == 0
    preview = workspace.preview_subsidy_plan(case, scheme, 0)
    assert preview.blocker is None
    workspace.save_subsidy_plan(case, scheme, 0, 'manual:' + uuid4().hex, 'synthetic', preview.fingerprint.value)
    connection.commit()
    if not bare_case:
        batch = bank_source(connection, tmp_path, case, name, scheme)
        plan = app.preview_batch(batch, correlation)
        assert len(plan.dispatchable_rows) == 1, [item.pending_reason for item in plan.rows]
        assert plan.dispatchable_rows[0].subsidy_preflight.existing_confirmed_payable
    receipt = app.reconcile_pending(PendingReconciliationRequest(
        IdempotencyKey('rematch:' + uuid4().hex), ActorContext('synthetic'), correlation,
    ))
    assert receipt.reconciled_count >= 1
    assert any(t.bank_amount_ntd == 11970 and t.transfer_fee_ntd == 30
               for t in workspace.query(case).transactions)
    if bare_case:
        row, = app.preview_batch(batch, correlation).rows
        assert row.classification_type.value == 'client_subsidy_return'
        assert row.disposition.value == 'existing'


@pytest.mark.parametrize('suffix_text', ['雇主補助款', '服務人員薪資'])
def test_existing_six_digit_subsidy_memos_still_ingest(connection, tmp_path, suffix_text):
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account

    case, name, _ = seed(connection, False, 'advance')
    memo = 'HC' + build_client_virtual_account(case)[-6:] + suffix_text
    bank_source(connection, tmp_path, case, name, 'advance', memo_override=memo)


@pytest.mark.parametrize('historical',[False,True])
@pytest.mark.parametrize(('scheme', 'customer_name_memo'), [('split', False), ('advance', False), ('advance', True)])
def test_bank_preview_then_apply_confirms_builds_and_settles_once(connection,tmp_path,historical,scheme,customer_name_memo):
    from api.dependencies.finance_import import build_finance_import_application
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace, MySqlAccountingWorkspaceState
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    client_name = '合成客戶' + uuid4().hex[:8].translate(str.maketrans('0123456789','qrstuvwxyz'))
    case,name,identity=seed(connection,historical,scheme,client_name=client_name)
    case_before=build_accounting_workspace(connection).query(case)
    assert case_before.subsidy_ntd==12000 and case_before.subsidy_plan.selected_scheme is None
    memo = client_name + ' 　GB,轉入0000000000000003' if customer_name_memo else None
    batch=bank_source(connection,tmp_path,case,name,scheme,memo_override=memo)
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
def test_reconfirm_advance_restores_cancelled_refund_for_bank_reconciliation(connection,tmp_path,historical):
    from dataclasses import replace
    from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
    from infrastructure.mysql.subsidy_confirmation_repository import persist_confirmed_refund
    from shared_kernel.money import MoneyNTD
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest

    case, name, _ = seed(connection, historical, 'advance', actual_end=date(2026, 8, 10))
    workspace = build_accounting_workspace(connection)
    initial = workspace.preview_subsidy_plan(case, 'advance', 0)
    workspace.save_subsidy_plan(case, 'advance', 0, 'original:'+uuid4().hex, 'synthetic', initial.fingerprint.value)
    persist_confirmed_refund(
        connection, case, replace(initial.refund_plan, amount=MoneyNTD(0)),
        ActorContext('synthetic'), IdempotencyKey('cancel:'+uuid4().hex),
        CorrelationId('cancelled-refund'), 'synthetic-cancellation',
    )
    connection.commit()
    assert not any(item.obligation_type == 'subsidy_return' for item in workspace.query(case).client_items)
    batch = bank_source(connection, tmp_path, case, name, 'advance', cash=12000, transaction_date=date(2026, 10, 15))
    app = application(connection)
    before_refund = app.preview_batch(batch, CorrelationId('missing-refund'))
    assert not before_refund.dispatchable_rows
    before = snapshot(connection, case)
    preview = workspace.preview_subsidy_plan(case, 'advance', 1)
    assert preview.blocker is None and snapshot(connection, case) == before
    payment, = preview.payables
    assert (payment.identity, payment.amount_ntd, payment.due_date) == (
        initial.refund_plan.obligation_identity, 12000, '2026-10-15',
    )
    workspace.save_subsidy_plan(case, 'advance', 1, 'reconfirm:'+uuid4().hex, 'synthetic', preview.fingerprint.value)
    refund, = [item for item in workspace.query(case).client_items if item.obligation_type == 'subsidy_return']
    assert refund.identity == payment.identity and refund.remaining_ntd == 12000
    assert snapshot(connection, case)['client_ledger_entries'] == before['client_ledger_entries']

    plan = app.preview_batch(batch, CorrelationId('restored-refund'))
    candidate, = plan.dispatchable_rows
    assert candidate.target_identities == (refund.identity,)
    receipt = app.apply_batch(FinanceImportApplyRequest(
        batch, ExpectedVersion(plan.batch_version), plan.fingerprint,
        IdempotencyKey('restored:'+uuid4().hex), ActorContext('synthetic'), '', CorrelationId('restored-refund'),
    ))
    assert receipt.reconciled_count == 1
    final, = [item for item in workspace.query(case).client_items if item.obligation_type == 'subsidy_return']
    assert final.identity == refund.identity and final.remaining_ntd == 0


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
    request=FinanceImportApplyRequest(batch,ExpectedVersion(plan.batch_version),plan.fingerprint,
        IdempotencyKey('atomic:'+uuid4().hex),ActorContext('synthetic'),'',CorrelationId('atomic-bank'))
    with monkeypatch.context() as fault:
        fault.setattr(MySqlClientRefundReversalRepository,'append_allocations',lambda *_:(_ for _ in ()).throw(RuntimeError('synthetic failure after ledger')))
        with pytest.raises(FinanceImportWorkflowError):
            app.apply_batch(request)
    assert snapshot(connection,case)==before
    receipt = app.apply_batch(request)
    assert receipt.reconciled_count == 1
    after = snapshot(connection, case)
    assert after['finance_case_subsidy_plan_events'] == before['finance_case_subsidy_plan_events'] + 1
    assert after['client_ledger_entries'] == before['client_ledger_entries'] + 1
    assert app.apply_batch(request) == receipt and snapshot(connection, case) == after


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

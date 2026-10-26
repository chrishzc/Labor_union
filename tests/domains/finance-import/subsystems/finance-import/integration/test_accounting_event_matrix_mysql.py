"""Real MySQL event matrix: accounting follows service and bank owner events.

Initial execution, recipient master data and the explicitly reviewed government
reversal classification are synthetic source fixtures.
All subsequent schedule changes, receipts, refunds, returns, period receipts and
reconciliation use public APIs. No provider worker or product lifespan runs.
"""
import os
import pytest
from argparse import Namespace
DATABASE = os.getenv('LABOR_UNION_TEST_MYSQL_DATABASE')
pytestmark = pytest.mark.skipif(not DATABASE, reason='requires disposable localhost MySQL')
from datetime import date, timedelta
from io import BytesIO
import json, runpy
import base64
from uuid import uuid4
import pandas as pd
from fastapi.testclient import TestClient
from infrastructure.mysql import mysql_adapter
h = runpy.run_path('tests/domains/scheduling/subsystems/scheduling/integration/test_complex_service_accounting_mysql.py')
http = None
rows = h['rows']
checked = h['checked']

def write(sql, args=()):
    c = mysql_adapter.get_connection()
    try:
        with c.cursor() as q:
            q.execute(sql, args)
            identity = q.lastrowid
        c.commit()
        return identity
    finally:
        c.close()

def snapshot(case):
    result = {}
    for key, sql in {'order': 'SELECT status,lifecycle_version,staff_payment_due_date,actual_start_date,actual_end_date FROM orders WHERE case_no=%s', 'client': 'SELECT obligation_identity,obligation_type,direction,amount_due_ntd,status,due_date FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity', 'ledger': 'SELECT id,entry_type,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id', 'payroll': 'SELECT obligation_identity,staff_id,obligation_kind,direction,amount_due_ntd,status,due_date FROM staff_obligations WHERE case_no=%s ORDER BY obligation_identity', 'recovery': 'SELECT recovery_identity,staff_id,remaining_amount_ntd,status FROM staff_overpayment_recoveries WHERE staff_id IN (SELECT staff_id FROM case_staff_assignments WHERE case_no=%s) ORDER BY recovery_identity', 'schedule': 'SELECT staff_id,work_date,is_double_pay FROM staff_schedule WHERE case_no=%s AND effective_marker=1 AND is_work_day=1 ORDER BY work_date,staff_id'}.items():
        result[key] = rows(sql, (case,))
    result['government_accounts'] = rows('SELECT a.* FROM government_subsidy_batch_accounts a WHERE a.batch_id IN (SELECT batch_id FROM subsidy_claim_batch_items WHERE case_no=%s) ORDER BY a.batch_id', (case,))
    result['government_transactions'] = rows('SELECT id,claim_batch_id,finance_import_row_id,transaction_type,amount FROM government_subsidy_transactions WHERE claim_batch_id IN (SELECT batch_id FROM subsidy_claim_batch_items WHERE case_no=%s) ORDER BY id', (case,))
    result['government_allocations'] = rows('SELECT a.id,a.transaction_id,a.allocation_type,a.allocated_amount FROM government_subsidy_allocations a JOIN subsidy_claim_batch_items i ON i.id=a.claim_item_id WHERE i.case_no=%s ORDER BY a.id', (case,))
    return result

def next_case():
    return f"116{rows('SELECT COUNT(*) AS n FROM orders')[0]['n'] + 1:06d}"

def new_case(*, service=False, identity='補助市民', days=30, hours=8, floor=0, survey=None):
    case = next_case()
    if service and identity == '補助市民' and (days == 30) and (hours == 8) and (floor == 0) and (survey is None):
        staff = h['seed_case'](http, case)
        return (case, staff)
    client = write("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic event acceptance',%s,'連續服務','2026-09-01')", (case, identity))
    write("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,'2026-10-01',%s,%s,%s,'08:00:00','17:00:00',0)", (case, client, days, hours, floor))
    if survey is not None:
        write('INSERT INTO beclass_records(query_no,bound_case_no,client_id,survey_details) VALUES (%s,%s,%s,%s)', (case, case, client, json.dumps(survey, ensure_ascii=False)))
    url = f'/api/v1/orders/{case}/intake-completion'
    before = snapshot(case)
    plan = checked(http.post(url + '/preview', json={}))
    assert snapshot(case) == before
    checked(http.post(url + '/apply', json={'expected_lifecycle_version': plan['lifecycle_version'], 'preview_fingerprint': plan['preview_fingerprint'], 'reason': ''}, headers={'Idempotency-Key': case + ':intake'}))
    return (case, [])

def bank(case, amount, sequence, account=None):
    return h['bank'](http, case, amount, sequence, account=account)

def stage(case, amount, sequence, *, account=None, incoming=False, government=False, refund_account=None, evidence=None):
    day = f'2026/11/{sequence:02d}'
    if government or refund_account:
        headers = ['序號', '交易日期', '交易時間', '帳務日期', '摘要', '支出金額', '存入金額', '帳戶餘額', '備註']
        row = [f'{int(case[3:]) * 100 + sequence}', day, '09:08:07', day, '轉帳', None if incoming else amount, amount if incoming else None, 300000 + int(case[3:]) * 100 + sequence, '新竹市政府' if government else '客戶退款 ' + refund_account]
    else:
        headers = ['帳號', '交易日', '計息日', '入帳日', '摘要', '幣別', '支出', '存入', '餘額', '銷帳編號', '交易參考編號', '', '更正註記', '存摺備註']
        virtual = f'99781699{int(case[:3]):03d}{int(case[3:]):03d}'
        row = ['1' * 12, day + ' 09:08:07', day, day, '轉帳', 'TWD', None if incoming else amount, amount if incoming else None, 300000 + int(case[3:]) * 100 + sequence, None if account else virtual, account or f'{case}:{sequence}', 'synthetic', None, 'fixture']
    out = BytesIO()
    pd.DataFrame([headers, row]).to_excel(out, sheet_name='來源', index=False, header=False)
    ingestion = http.post('/api/v1/finance-import/workbooks/ingest', headers={'Idempotency-Key': f'{case}:stage:{sequence}'}, files={'workbook': (f'synthetic-{case}-{sequence}.xlsx', out.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    batch = checked(ingestion)['batch_identity']
    preview = http.post('/api/v1/finance-import/batches/preview', json={'batch_identity': batch})
    plan = checked(preview)
    if evidence is not None:
        evidence.update(ingestion=ingestion.json(), preview=preview.json(), workbook_base64=base64.b64encode(out.getvalue()).decode('ascii'))
    assert len(plan['rows']) == 1, plan
    return (int(plan['rows'][0]['row_identity'].split(':')[-1]), plan)

def jobs(accepted):
    from api.dependencies.durable_job_handlers import default_job_handlers
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from subsystems.jobs.durable_job_worker import DurableJobWorker
    connection = mysql_adapter.get_connection()
    try:
        handlers = {name: handler for name, handler in default_job_handlers().items() if name in {'finance_import_batch_apply', 'finance_import_correction_apply', 'government_subsidy_apply', 'staff_payout_apply', 'payroll_rebuild_apply'}}
        worker = DurableJobWorker(BackgroundJobRepository(connection), connection, handlers, 'isolated-event-matrix')
        assert worker.recover_and_run_once()
    finally:
        connection.close()
    result = checked(http.get('/api/v1/jobs/' + accepted['job_id']))
    assert result['status'] == 'succeeded', result
    return result

def owner_apply(url, body, *, case, key, versions):
    before = snapshot(case)
    plan = checked(http.post(url + '/preview', json=body))
    assert snapshot(case) == before
    body = {**body, **{f'expected_{owner}_version': plan[field] for owner, field in versions.items()}, 'preview_fingerprint': plan['preview_fingerprint'], 'reason': ''}
    headers = {'Idempotency-Key': key}
    response = http.post(url + '/apply', json=body, headers=headers)
    if response.status_code == 202:
        jobs(checked(response, 202))
    else:
        checked(response)
    saved = snapshot(case)
    replay = http.post(url + '/apply', json=body, headers=headers)
    assert replay.status_code == response.status_code, replay.text
    assert snapshot(case) == saved
    return (plan, response.json()['data'])

def all_receipts(case):
    for index in range(1, 6):
        open_stages = rows("SELECT obligation_type,amount_due_ntd FROM client_obligations WHERE case_no=%s AND direction='receivable_from_client' AND obligation_type IN ('deposit','first','second') AND status='open' AND amount_due_ntd>0 ORDER BY FIELD(obligation_type,'deposit','first','second')", (case,))
        if not open_stages:
            return
        bank(case, int(open_stages[0]['amount_due_ntd']), index)
    raise AssertionError('unexpected stage loop')

def complete(case):
    url = f'/api/v1/orders/{case}/service-completion'
    before = snapshot(case)
    plan = checked(http.post(url + '/preview', json={'evaluation_at': '2026-12-01T00:00:00+08:00'}))
    assert snapshot(case) == before
    body = {'evaluation_at': plan['evaluation_at'], 'expected_order_version': plan['expected_order_version'], 'preview_fingerprint': plan['fingerprint'], 'reason': ''}
    headers = {'Idempotency-Key': case + ':complete'}
    checked(http.post(url + '/apply', json=body, headers=headers))
    after = snapshot(case)
    checked(http.post(url + '/apply', json=body, headers=headers))
    assert snapshot(case) == after

def seed_service(case, days=30, *, splits=None, double_days=()):
    policy = rows('SELECT policy_version,policy_kind,hourly_rate_ntd,source_identity_status FROM case_payroll_rate_policy_snapshots WHERE case_no=%s', (case,))[0]
    splits = splits or (days,)
    connection = mysql_adapter.get_connection()
    staff = []
    offset = 0
    try:
        with connection.cursor() as q:
            q.execute("INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) VALUES (%s,1,1,'effective',1,'synthetic','confirmed execution fixture')", (case,))
            generation = q.lastrowid
            q.execute('UPDATE scheduling_aggregates SET effective_generation_id=%s,generation_counter=1,aggregate_version=1 WHERE case_no=%s', (generation, case))
            for sequence, count in enumerate(splits, 1):
                q.execute("INSERT INTO staff(name,status) VALUES (%s,'active')", (f'Synthetic {case} segment {sequence}',))
                sid = q.lastrowid
                staff.append(sid)
                q.execute("INSERT INTO staff_bank_accounts(staff_id,is_primary,bank_code,account_no) VALUES (%s,1,'synthetic',%s)", (sid, h['staff_account'](sid)))
                start = date(2026, 10, 1) + timedelta(days=offset)
                end = start + timedelta(days=count - 1)
                q.execute("INSERT INTO case_staff_assignments(case_no,generation_id,candidate_key,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status) VALUES (%s,%s,%s,%s,%s,%s,%s,'active')", (case, generation, f'{case}:g1:a{sequence}', sid, sequence, start, end))
                assignment = q.lastrowid
                q.execute('INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) VALUES (%s,%s,%s,%s,%s)', (assignment, policy['policy_version'], policy['policy_kind'], policy['hourly_rate_ntd'], policy['source_identity_status']))
                for i in range(count):
                    day = start + timedelta(days=i)
                    double = day.isoformat() in double_days
                    q.execute('INSERT INTO staff_schedule(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,%s,1,%s,1)', (case, sid, assignment, generation, day, double))
                    q.execute("INSERT INTO scheduling_effective_occupancy(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) VALUES (%s,%s,%s,%s,'assignment_interval')", (sid, day, generation, assignment))
                    if double:
                        q.execute("INSERT INTO payroll_special_pay_events(assignment_id,service_date,event_type,source_event_identity,actor,reason,idempotency_key) VALUES (%s,%s,'double_pay',%s,'synthetic','confirmed special day',%s)", (assignment, day, f'{case}:special', f'{case}:special:{day}'))
                offset += count
            q.execute("UPDATE orders SET status='服務中',actual_start_date='2026-10-01',actual_end_date=%s WHERE case_no=%s", (date(2026, 10, 1) + timedelta(days=days - 1), case))
        connection.commit()
    finally:
        connection.close()
    return staff

def identities():
    matrix = [('補助市民', 30, 0, None, 72000), ('社福', 15, 0, None, 42000), ('社福', 16, 0, None, 44800), ('非市民', 30, 0, None, 76800), ('補助市民', 30, 0, {'特殊計費:胎數': '雙胞胎'}, 108000)]
    for identity, days, floor, survey, expected in matrix:
        case, _ = new_case(identity=identity, days=days, floor=floor, survey=survey)
        seed_service(case, days)
        all_receipts(case)
        complete(case)
        total = sum((int(r['amount_due_ntd']) for r in rows("SELECT amount_due_ntd FROM staff_obligations WHERE case_no=%s AND obligation_kind='service_pay' AND status<>'cancelled'", (case,))))
        assert total == expected, (case, identity, total, expected)
    case, _ = new_case(floor=1001)
    staff = seed_service(case, splits=(10, 20), double_days=('2026-10-02',))
    all_receipts(case)
    complete(case)
    amounts = rows("SELECT staff_id,amount_due_ntd FROM staff_obligations WHERE case_no=%s AND obligation_kind='service_pay' AND status<>'cancelled' ORDER BY staff_id", (case,))
    assert amounts == [{'staff_id': staff[0], 'amount_due_ntd': 26734}, {'staff_id': staff[1], 'amount_due_ntd': 48667}], amounts

def government():
    # Current whole-period owner oracle also proves real workbook bank consumption.
    current=runpy.run_path('tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_period_reconciliation_mysql.py')
    current['test_real_bank_workbook_government_receipt_stays_pending_until_period_selected'](http)

def cancel(case, days):
    url = f'/api/v1/orders/{case}/cancellation'
    body = {'confirmed_service_days': days}
    before = snapshot(case)
    plan = checked(http.post(url + '/preview', json=body))
    assert snapshot(case) == before
    body.update({f'expected_{key}_version': plan[f'{key}_version'] for key in ('order', 'scheduling', 'client_finance', 'payroll')})
    body.update(preview_fingerprint=plan['preview_fingerprint'], reason='')
    headers = {'Idempotency-Key': case + ':cancel'}
    checked(http.post(url + '/apply', json=body, headers=headers))
    after = snapshot(case)
    checked(http.post(url + '/apply', json=body, headers=headers))
    assert snapshot(case) == after
    return plan

def cancellation():
    case, _ = new_case()
    bank(case, 12000, 1)
    plan = cancel(case, [])
    assert rows('SELECT status FROM orders WHERE case_no=%s', (case,)) == [{'status': '訂單取消'}]
    assert sum(int(r['amount_due_ntd']) for r in snapshot(case)['client'] if r['obligation_type'] == 'refund') == 12000
    case, staff = new_case(service=True)
    all_receipts(case)
    days = [{'service_date': f'2026-10-{d:02d}', 'staff_id': staff[0], 'reason': 'synthetic confirmed service'} for d in range(1, 5)]
    plan = cancel(case, days)
    assert len(snapshot(case)['schedule']) == 4
    assert all(item['after_due_date'] is not None for item in plan['client_finance_impact']['actions'] if item['direction'] == 'refund_due')
    assert sum(int(r['amount_due_ntd']) for r in snapshot(case)['client'] if r['obligation_type'] == 'refund') == 62400
    assert sum(int(r['amount_due_ntd']) for r in snapshot(case)['client'] if r['obligation_type'] == 'subsidy_return') == 9600
    assert sum(int(r['amount_ntd']) for r in snapshot(case)['ledger'] if r['entry_type'] == 'receipt') == 72000
    assert sum((int(r['amount_due_ntd']) for r in rows("SELECT amount_due_ntd FROM staff_obligations WHERE case_no=%s AND direction='payable_to_staff' AND status<>'cancelled'", (case,)))) == 9600

def terms():
    for change in ({'service_days': 25}, {'service_hours_per_day': 7.5}, {'floor_fee_ntd': 1001}, {'planned_start_date': '2026-10-03'}):
        case, _ = new_case()
        bank(case, 12000, 1)
        url = f'/api/v1/orders/{case}/terms'
        query = checked(http.get(url))
        before = snapshot(case)
        proposed = {**query['terms'], **change}
        body = {'proposed_terms': proposed}
        plan = checked(http.post(url + '/preview', json=body))
        assert snapshot(case) == before
        body.update({f'expected_{key}_version': plan[f'{key}_version'] for key in ('order', 'scheduling', 'client_finance', 'payroll')})
        body.update(preview_fingerprint=plan['preview_fingerprint'], requires_formal_apply=plan['requires_formal_apply'], reason='synthetic change')
        headers = {'Idempotency-Key': case + ':terms'}
        checked(http.post(url + '/apply', json=body, headers=headers))
        saved = snapshot(case)
        checked(http.post(url + '/apply', json=body, headers=headers))
        assert snapshot(case) == saved
        assert saved['ledger'] == before['ledger']
        expected_total = 60000 if 'service_days' in change else 67500 if 'service_hours_per_day' in change else 73001 if 'floor_fee_ntd' in change else 72000
        receivable = sum(int(r['amount_due_ntd']) for r in saved['client'] if r['direction'] == 'receivable_from_client')
        refund = sum(int(r['amount_due_ntd']) for r in saved['client'] if r['obligation_type'] == 'refund')
        assert 12000 + receivable - refund == expected_total
        if 'planned_start_date' in change:
            stages = {r['obligation_type']: str(r['due_date']) for r in saved['client']}
            assert stages['first'] == '2026-10-03' and stages['second'] == '2026-10-18'


def handover(case, staff_id, new_staff, start, key):
    assignments = checked(http.get(f'/api/v1/orders/{case}/leave-substitution/assignments'))
    source = next((a for a in assignments if a['staff_id'] == staff_id and a['assigned_end_date'] >= start))
    body = {'original_assignment_id': source['assignment_id'], 'handover_date': start, 'items': [{'original_schedule_id': d['schedule_id'], 'work_date': d['work_date'], 'resolution_type': 'substitute', 'substitute_staff_id': new_staff, 'is_double_pay': d['is_double_pay']} for d in source['official_schedules'] if d['work_date'] >= start]}
    return leave(case, body, key)

def leave(case, body, key):
    url = f'/api/v1/orders/{case}/leave-substitution'
    before = snapshot(case)
    plan = checked(http.post(url + '/preview', json=body))
    assert snapshot(case) == before
    assert plan['apply_readiness']['status'] == 'ready', plan['apply_readiness']
    body.update({f'expected_{owner}_version': plan[f'{owner}_version'] for owner in ('order', 'scheduling', 'client_finance', 'payroll')})
    body.update(preview_fingerprint=plan['preview_fingerprint'], reason='')
    checked(http.post(url + '/apply', json=body, headers={'Idempotency-Key': key}))
    saved = snapshot(case)
    checked(http.post(url + '/apply', json=body, headers={'Idempotency-Key': key}))
    assert snapshot(case) == saved
    return plan

def prepare_recovery():
    case, staff = new_case(service=True)
    all_receipts(case)
    bank(case, 36000, 6, h['staff_account'](staff[1]))
    plan = handover(case, staff[1], staff[2], '2026-10-24', case + ':handover')
    return (case, staff)

def recovery():
    case, staff = prepare_recovery()
    recovery = rows('SELECT recovery_identity,remaining_amount_ntd FROM staff_overpayment_recoveries WHERE staff_id=%s', (staff[1],))[0]
    rid = recovery['recovery_identity']
    amount = int(recovery['remaining_amount_ntd'])
    bank_id, plan = stage(case, amount, 20, account=h['staff_account'](staff[1]), incoming=True)
    body = {'recovery_identity': rid, 'finance_import_row_id': bank_id, 'evidence_reference': 'synthetic return confirmation'}
    versions = {'recovery': 'recovery_version', 'staff_payables': 'staff_payables_version'}
    _, matching = owner_apply('/api/v1/staff-payables/overpayment-recoveries/matching', body, case=case, key=case + ':matching', versions=versions)
    body.update(matching_identity=matching['matching_identity'], matching_version=matching['matching_version'])
    owner_apply('/api/v1/staff-payables/overpayment-recoveries/matched', body, case=case, key=case + ':recovery', versions=versions)
    assert rows('SELECT remaining_amount_ntd,status FROM staff_overpayment_recoveries WHERE recovery_identity=%s', (rid,)) == [{'remaining_amount_ntd': 0, 'status': 'recovered'}]

def differences():
    case, staff = new_case(service=True)
    all_receipts(case)
    root = rows("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s AND staff_id=%s AND status<>'cancelled'", (case, staff[0]))[0]['obligation_identity']
    for sequence, amount in ((20, 12000), (21, 24000)):
        bank_id, staged = stage(case, amount, sequence, account=h['staff_account'](staff[0]))
        review_url = '/api/v1/finance-import/batches/' + staged['batch_identity'] + '/review-rows'
        if sequence == 20:
            assert any(row['row_id'] == bank_id for row in checked(http.get(review_url))['items'])
        else:
            assert staged['counts']['ready_dispatch'] == 1, staged
        body = {'finance_import_row_ids': [bank_id], 'obligation_identities': [root]}
        url = '/api/v1/staff-payables/payout'
        if sequence == 20:
            body['mode'] = 'underpayment'
            url += '-difference'
        if sequence == 20:
            owner_apply(url, body, case=case, key=f'{case}:partial:{sequence}', versions={'staff_payables': 'staff_payables_version', 'bank_facts': 'bank_facts_version'})
        else:
            request = {'batch_identity': staged['batch_identity'], 'expected_batch_version': staged['batch_version'], 'preview_fingerprint': staged['preview_fingerprint'], 'reason': ''}
            jobs(checked(http.post('/api/v1/finance-import/batches/apply', json=request, headers={'Idempotency-Key': case + ':automatic-supplement'}), 202))
        assert all(row['row_id'] != bank_id for row in checked(http.get(review_url))['items'])
        assert rows('SELECT COUNT(*) AS n FROM staff_payables_outbox WHERE staff_id=%s', (staff[0],))[0]['n'] == (1 if sequence == 20 else 2)
        assert rows('SELECT balance_ntd FROM staff_payable_projections WHERE obligation_identity=%s', (root,)) == [{'balance_ntd': 36000 - 12000 if sequence == 20 else 0}]
    assert rows('SELECT balance_ntd FROM staff_payable_projections WHERE obligation_identity=%s', (root,)) == [{'balance_ntd': 0}]
    case, staff = new_case(service=True)
    all_receipts(case)
    root = rows("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s AND staff_id=%s AND status<>'cancelled'", (case, staff[0]))[0]['obligation_identity']
    bank_id, _ = stage(case, 40000, 20, account=h['staff_account'](staff[0]))
    owner_apply('/api/v1/staff-payables/payout-difference', {'finance_import_row_ids': [bank_id], 'obligation_identities': [root], 'mode': 'overpayment'}, case=case, key=case + ':overpaid', versions={'staff_payables': 'staff_payables_version', 'bank_facts': 'bank_facts_version'})
    assert rows('SELECT remaining_amount_ntd FROM staff_overpayment_recoveries WHERE staff_id=%s', (staff[0],)) == [{'remaining_amount_ntd': 4000}]

def reversals():
    case, _ = new_case()
    bank(case, 12000, 1)
    entry = rows("SELECT id FROM client_ledger_entries WHERE case_no=%s AND entry_type='receipt'", (case,))[0]['id']
    owner_apply(f'/api/v1/orders/{case}/client-finance/reversal', {'ledger_entry_ids': [entry], 'occurred_on': '2026-11-02'}, case=case, key=case + ':receipt-reversal', versions={'account': 'account_version'})
    assert rows("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='deposit'", (case,)) == [{'amount_due_ntd': 12000}]
    case, staff = new_case(service=True)
    all_receipts(case)
    bank(case, 36000, 6, h['staff_account'](staff[0]))
    source = rows('SELECT event.id,link.obligation_identity FROM staff_payout_events event JOIN staff_payout_obligation_links link ON link.payout_event_id=event.id JOIN staff_obligations o ON o.obligation_identity=link.obligation_identity WHERE o.case_no=%s', (case,))[0]
    owner_apply('/api/v1/staff-payables/reversal', {'source_payout_event_id': source['id'], 'occurred_on': '2026-11-07', 'obligation_identities': [source['obligation_identity']]}, case=case, key=case + ':staff-reversal', versions={'staff_payables': 'staff_payables_version', 'bank_facts': 'bank_facts_version'})

def complex_scheduling():
    case, staff = new_case(service=True)
    all_receipts(case)
    handover(case, staff[1], staff[2], '2026-10-24', case + ':first-change')
    handover(case, staff[2], staff[1], '2026-10-27', case + ':returning')
    complete(case)
    assert len(snapshot(case)['schedule']) == 30
    assert sum((int(r['amount_due_ntd']) for r in rows("SELECT amount_due_ntd FROM staff_obligations WHERE case_no=%s AND obligation_kind='service_pay' AND status<>'cancelled'", (case,)))) == 72000

def current_period_oracles():
    return runpy.run_path('tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_period_reconciliation_mysql.py')

def government_extra():
    current=current_period_oracles()
    current['test_real_query_totals_are_consistent_and_quarter_covers_months_without_split_receipts'](http)
    current['test_each_month_can_advance_and_whole_period_receipt_recovers_without_second_payout'](http)

def bank_return():
    case, staff = new_case(service=True)
    all_receipts(case)
    root = rows("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s AND staff_id=%s AND status<>'cancelled'", (case, staff[0]))[0]['obligation_identity']
    for sequence, amount in ((24, 12000), (25, 24000)):
        bid, _ = stage(case, amount, sequence, account=h['staff_account'](staff[0]))
        body = {'finance_import_row_ids': [bid], 'obligation_identities': [root]}
        url = '/api/v1/staff-payables/payout'
        if sequence == 24:
            url += '-difference'
            body['mode'] = 'underpayment'
        owner_apply(url, body, case=case, key=case + f':paid:{sequence}', versions={'staff_payables': 'staff_payables_version', 'bank_facts': 'bank_facts_version'})
    source = rows('SELECT event.id FROM staff_payout_events event JOIN staff_payout_obligation_links link ON link.payout_event_id=event.id WHERE link.obligation_identity=%s AND event.amount_ntd=12000', (root,))[0]['id']
    bid, _ = stage(case, 12000, 26, account=h['staff_account'](staff[0]), incoming=True)
    owner_apply('/api/v1/staff-payables/return', {'return_finance_import_row_id': bid, 'source_payout_event_id': source, 'obligation_identities': [root]}, case=case, key=case + ':returned', versions={'staff_payables': 'staff_payables_version', 'bank_facts': 'bank_facts_version'})
    assert rows('SELECT balance_ntd,status FROM staff_payable_projections WHERE obligation_identity=%s', (root,)) == [{'balance_ntd': 12000, 'status': 'partially_paid'}]
    return (case, staff)

def compound():
    case, staff = new_case(service=True)
    all_receipts(case)
    bank(case, 36000, 6, h['staff_account'](staff[1]))
    handover(case, staff[1], staff[2], '2026-10-24', case + ':out')
    handover(case, staff[2], staff[1], '2026-10-27', case + ':back')
    for day, kind in [('2026-10-28', 'substitute'), ('2026-10-30', 'defer_following_assignments')]:
        assignments = checked(http.get(f'/api/v1/orders/{case}/leave-substitution/assignments'))
        source = next((a for a in assignments if a['staff_id'] == staff[1] and any((d['work_date'] == day for d in a['official_schedules']))))
        schedule = next((d for d in source['official_schedules'] if d['work_date'] == day))
        item = {'original_schedule_id': schedule['schedule_id'], 'work_date': day, 'resolution_type': kind, 'is_double_pay': False}
        if kind == 'substitute':
            item['substitute_staff_id'] = staff[2]
        else:
            item['replacement_work_date'] = '2026-11-02'
        if kind == 'substitute':
            before = snapshot(case)
            blocked = http.post(f'/api/v1/orders/{case}/leave-substitution/preview', json={'original_assignment_id': source['assignment_id'], 'items': [item]})
            assert blocked.status_code == 409 and 'assignment_limit_exceeded' in blocked.text and (snapshot(case) == before), blocked.text
            continue
        leave(case, {'original_assignment_id': source['assignment_id'], 'items': [item]}, case + ':' + kind)
    complete(case)
    assert len(snapshot(case)['schedule']) == 30
    assert max((str(r['work_date']) for r in snapshot(case)['schedule'])) == '2026-11-02'

def customer_refund():
    case, _ = new_case()
    bank(case, 12000, 1)
    cancel(case, [])
    root = rows("SELECT obligation_identity,amount_due_ntd FROM client_obligations WHERE case_no=%s AND direction='payable_to_client' AND obligation_type='refund' AND status='open'", (case,))[0]
    account = '7' * 12 + case[-4:]
    write("INSERT INTO client_refund_recipient_snapshots(refund_obligation_identity,case_no,bank_code,bank_account,source_kind) VALUES (%s,%s,'0040000',%s,'synthetic-acceptance')", (root['obligation_identity'], case, account))
    bid, _ = stage(case, int(root['amount_due_ntd']), 24, refund_account=account)
    owner_apply(f'/api/v1/orders/{case}/client-finance/refund', {'finance_import_row_ids': [bid], 'obligation_identities': [root['obligation_identity']]}, case=case, key=case + ':refund', versions={'account': 'account_version'})
    entry = rows("SELECT id FROM client_ledger_entries WHERE case_no=%s AND entry_type='refund'", (case,))[0]['id']
    assert rows('SELECT status FROM client_obligations WHERE obligation_identity=%s', (root['obligation_identity'],)) == [{'status': 'settled'}]
    bid, plan = stage(case, int(root['amount_due_ntd']), 25, refund_account=account, incoming=True)
    body = {'row_identity': plan['rows'][0]['row_identity'], 'classification_type': 'client_refund_return', 'target_obligation_identities': [root['obligation_identity']], 'refund_ledger_entry_identity': str(entry), 'allow_partial_refund_recovery': False, 'allow_refund_overage_recovery': False, 'allow_client_receipt_overage': False, 'reason': '', 'evidence': ['synthetic bank refund return']}
    url = '/api/v1/finance-import/corrections'
    before = snapshot(case)
    preview = checked(http.post(url + '/preview', json=body))
    assert snapshot(case) == before
    apply = {**body, **{f'expected_{k}_version': preview[k + '_version'] for k in ('batch', 'canonical_fact', 'alert')}, 'preview_fingerprint': preview['preview_fingerprint']}
    accepted = checked(http.post(url + '/apply', json=apply, headers={'Idempotency-Key': case + ':refund-return'}), 202)
    jobs(accepted)
    assert rows('SELECT status FROM client_obligations WHERE obligation_identity=%s', (root['obligation_identity'],)) == [{'status': 'open'}]

def partial_customer_refund(tmp_path):
    case, _ = new_case()
    bank(case, 12000, 1)
    cancel(case, [])
    # A repeat customer has another cancelled case awaiting refund. The account
    # identifies the customer, but the operator must select the correct case.
    other_case, _ = new_case()
    client_id = rows('SELECT client_id FROM orders WHERE case_no=%s', (case,))[0]['client_id']
    write('UPDATE orders SET client_id=%s WHERE case_no=%s', (client_id, other_case))
    bank(other_case, 12000, 1)
    cancel(other_case, [])
    other_before = snapshot(other_case)
    root = rows("SELECT obligation_identity,amount_due_ntd FROM client_obligations WHERE case_no=%s AND direction='payable_to_client' AND obligation_type='refund' AND status='open'", (case,))[0]
    account = '7' * 12 + case[-4:]
    write("INSERT INTO client_refund_recipient_snapshots(refund_obligation_identity,case_no,bank_code,bank_account,source_kind) VALUES (%s,%s,'0040000',%s,'synthetic-acceptance')", (root['obligation_identity'], case, account))
    partial, topup = {}, {}
    bid, bank_plan = stage(case, 4000, 26, refund_account=account, evidence=partial)

    def readback(batch):
        before = snapshot(case)
        result = {}
        for name, url in {
            'manifest': f'/api/v1/finance-import/batches/{batch}/manifest',
            'reviews': f'/api/v1/finance-import/batches/{batch}/review-rows',
            'settlement': f'/api/v1/orders/{case}/client-finance/settlement-remediation?include_not_due=true',
            'cash': '/api/v1/finance-reports/accounts-payable/cash-requirements?page_size=100',
            'payables': '/api/v1/finance-reports/accounts-payable?target_month=2026-10',
        }.items():
            response = http.get(url)
            checked(response)
            result[name] = response.json()
        assert snapshot(case) == before, 'review and balance queries must not mutate owner facts'
        assert result['manifest']['data']['review_count'] == len(result['reviews']['data']['items'])
        return result

    partial['before'] = readback(bank_plan['batch_identity'])
    pending = partial['before']['reviews']['data']['items']
    assert len(pending) == 1 and pending[0]['row_identity'] == f'finance-import-row:{bid}'
    assert pending[0]['classification_type'] == 'client_refund'
    assert set(pending[0]['available_actions']) & {'preview_manual_correction', 'resolve_owning_domain_target', 'review_suspected_duplicate_business_match'}
    assert partial['before']['settlement']['data']['refund_obligations'][0]['amount_due_ntd'] == 12000
    assert bank_plan['counts']['ready_dispatch'] == 0, 'ambiguous case targets require operator selection'
    selection = {'row_identity': f'finance-import-row:{bid}', 'classification_type': 'client_refund',
                 'target_obligation_identities': [root['obligation_identity']], 'refund_ledger_entry_identity': None,
                 'allow_partial_refund_recovery': True, 'allow_refund_overage_recovery': False,
                 'allow_client_receipt_overage': False, 'reason': '', 'evidence': ['來源#2']}
    before = snapshot(case)
    preview = http.post('/api/v1/finance-import/corrections/preview', json=selection)
    plan = checked(preview)
    assert snapshot(case) == before
    body = {**selection, **{f'expected_{key}_version': plan[f'{key}_version'] for key in ('batch', 'canonical_fact', 'alert')}, 'preview_fingerprint': plan['preview_fingerprint']}
    headers = {'Idempotency-Key': case + ':partial-refund-review'}
    accepted = http.post('/api/v1/finance-import/corrections/apply', json=body, headers=headers)
    jobs(checked(accepted, 202))
    outcome = http.get(f"/api/v1/finance-import/jobs/{accepted.json()['data']['job_id']}/correction-outcome")
    assert checked(outcome)['receipt']['row_identity'] == f'finance-import-row:{bid}'
    partial['correction'] = {'preview': preview.json(), 'accepted': accepted.json(), 'outcome': outcome.json()}
    after = snapshot(case)
    assert checked(http.post('/api/v1/finance-import/corrections/apply', json=body, headers=headers), 202)['replayed'] is True
    assert snapshot(case) == after, 'same-key partial refund must not pay twice'
    assert rows('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s', (root['obligation_identity'],)) == [{'amount_due_ntd': 8000, 'status': 'open'}]
    report = checked(http.get('/api/v1/finance-reports/accounts-payable?target_month=2026-10'))
    assert any(case in row['case_numbers'] and row['amount_ntd'] == 8000 for row in report['rows'])
    partial['after'] = readback(bank_plan['batch_identity'])
    assert partial['after']['reviews']['data']['items'] == []
    assert partial['after']['settlement']['data']['refund_obligations'][0]['obligation_identity'] == root['obligation_identity']
    assert sum(row['unpaid_amount_ntd'] for row in partial['after']['cash']['data']['rows'] if row['case_no'] == case and row['payment_type'] == 'client_refund') == 8000
    bid, topup_plan = stage(case, 8000, 27, refund_account=account, evidence=topup)
    topup['before'] = readback(topup_plan['batch_identity'])
    assert topup_plan['counts']['ready_dispatch'] == 0
    assert len(topup['before']['reviews']['data']['items']) == 1
    selection = {**selection, 'row_identity': f'finance-import-row:{bid}', 'allow_partial_refund_recovery': False}
    before = snapshot(case)
    preview = http.post('/api/v1/finance-import/corrections/preview', json=selection)
    plan = checked(preview)
    assert snapshot(case) == before
    body = {**selection, **{f'expected_{key}_version': plan[f'{key}_version'] for key in ('batch', 'canonical_fact', 'alert')}, 'preview_fingerprint': plan['preview_fingerprint']}
    headers = {'Idempotency-Key': case + ':refund-topup-review'}
    accepted = http.post('/api/v1/finance-import/corrections/apply', json=body, headers=headers)
    jobs(checked(accepted, 202))
    outcome = http.get(f"/api/v1/finance-import/jobs/{accepted.json()['data']['job_id']}/correction-outcome")
    assert checked(outcome)['receipt']['row_identity'] == f'finance-import-row:{bid}'
    topup['correction'] = {'preview': preview.json(), 'accepted': accepted.json(), 'outcome': outcome.json()}
    after = snapshot(case)
    assert checked(http.post('/api/v1/finance-import/corrections/apply', json=body, headers=headers), 202)['replayed'] is True
    assert snapshot(case) == after, 'same-key top-up must not pay twice'
    topup['after'] = readback(topup_plan['batch_identity'])
    assert topup['after']['reviews']['data']['items'] == []
    assert topup['after']['settlement']['data']['refund_obligations'] == []
    settled_rows = [row for row in topup['after']['cash']['data']['rows'] if row['case_no'] == case and row['payment_type'] == 'client_refund']
    assert settled_rows and all(row['unpaid_amount_ntd'] == 0 and row['payment_status'] == 'paid' for row in settled_rows)
    assert rows('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s', (root['obligation_identity'],)) == [{'amount_due_ntd': 0, 'status': 'settled'}]
    report = checked(http.get('/api/v1/finance-reports/accounts-payable?target_month=2026-10'))
    assert not any(case in row['case_numbers'] for row in report['rows'])
    assert sum(int(row['amount_ntd']) for row in rows("SELECT amount_ntd FROM client_ledger_entries WHERE case_no=%s AND entry_type='refund'", (case,))) == 12000
    assert rows('SELECT COUNT(*) AS n FROM line_delivery_tasks') == [{'n': 0}]
    assert snapshot(other_case) == other_before, 'selecting this refund must not change another case of the same customer'
    # Fresh backend envelopes exercise the real frontend decoders and list entry.
    from pathlib import Path
    import subprocess
    exchange = tmp_path / 'refund-review-exchange.json'
    exchange.write_text(json.dumps({'case_no': case, 'partial': partial, 'topup': topup}, default=str), encoding='utf-8')
    project = Path(__file__).resolve().parents[6]
    report_path = tmp_path / 'refund-review-ui-report.json'
    environment = {name: os.environ[name] for name in ('PATH', 'SystemRoot', 'TEMP', 'TMP') if name in os.environ}
    environment.update(CI='true', FI_REFUND_REVIEW_EXCHANGE=str(exchange))
    result = subprocess.run(['node', str(project / 'ui_react/node_modules/vitest/vitest.mjs'), 'run', 'src/tests/finance_source_review_list.test.tsx', '-t', 'same-run refund-review', '--reporter=json', '--outputFile', str(report_path)], cwd=project / 'ui_react', env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr[-5000:]
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert report['numPassedTests'] == 1 and report['numFailedTests'] == 0


def government_reversal():
    current_period_oracles()['test_whole_reversal_keeps_evidence_and_reopens_coverage'](http)

@pytest.fixture(scope='module', autouse=True)
def isolated_event_matrix():
    global http
    assert DATABASE.startswith('lu_test_') and os.environ['APP_ENV'] == 'development'
    assert os.environ['LABOR_UNION_TEST_MYSQL_HOST'] in {'localhost', '127.0.0.1'}
    from scripts.bootstrap_disposable_mysql_schema import bootstrap
    from infrastructure.mysql.nas_mutations import PROCEDURES
    from api.dependencies import admin_auth
    from subsystems.access.authentication_session import AdminPrincipal
    from fastapi import FastAPI
    from importlib import import_module
    target = DATABASE + '_event_matrix'
    bootstrap(Namespace(host=os.environ['LABOR_UNION_TEST_MYSQL_HOST'], port=int(os.environ['LABOR_UNION_TEST_MYSQL_PORT']), user=os.environ['LABOR_UNION_TEST_MYSQL_USER'], password=os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'], database=target, confirm_database=target))
    app = FastAPI()
    for name in ('finance_import', 'order_intake_terms_bootstrap', 'order_terms', 'order_cancellation', 'order_auto_completion', 'leave_substitution', 'staff_payout', 'client_refund_reversal', 'government_subsidy', 'government_subsidy_periods', 'jobs', 'finance_reports'):
        app.include_router(import_module('api.routes.' + name).router)
    principal = AdminPrincipal(1, 'event-matrix', 'Synthetic accounting verifier', 'system_admin')
    for name in ('require_admin', 'require_system_admin', 'require_persisted_admin'):
        app.dependency_overrides[getattr(admin_auth, name)] = lambda: principal
    for route in import_module('api.routes.government_subsidy').router.routes:
        for dependency in route.dependant.dependencies:
            if getattr(dependency.call, '__module__', '') == admin_auth.__name__ and getattr(dependency.call, '__name__', '') == 'dependency':
                app.dependency_overrides[dependency.call] = lambda: principal
    from api.dependencies.leave_substitution import get_leave_substitution_application
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from datetime import datetime
    def fixed_leave_application():
        for application in get_leave_substitution_application():
            clock = FixedBusinessClock(datetime(2026, 10, 22, 10, tzinfo=TAIPEI_TIME_ZONE))
            application.workflow._clock = clock
            application.workflow._orders_port._clock = clock
            yield application
    app.dependency_overrides[get_leave_substitution_application] = fixed_leave_application
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG, 'database', target)
        connection = mysql_adapter.get_connection()
        try:
            parameters, body, _ = PROCEDURES['lu_nas_cancel_occupancy_v1']
            with connection.cursor() as cursor:
                cursor.execute(f'CREATE PROCEDURE lu_nas_cancel_occupancy_v1 ({parameters}) SQL SECURITY INVOKER BEGIN {body} END')
            connection.commit()
        finally:
            connection.close()
        http = TestClient(app, headers={'X-Correlation-ID': 'accounting-event-matrix'})
        try:
            yield
        finally:
            http.close()

@pytest.mark.parametrize('event', [cancellation, terms, recovery, differences, reversals, complex_scheduling, identities, government, bank_return, compound, customer_refund, partial_customer_refund, government_extra, government_reversal], ids=lambda event: event.__name__)
def test_accounting_updates_after_each_real_event(event, tmp_path):
    if event is partial_customer_refund:
        event(tmp_path)
    else:
        event()

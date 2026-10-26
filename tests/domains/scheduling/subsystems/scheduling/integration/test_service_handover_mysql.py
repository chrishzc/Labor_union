"""Formal handover through the shared union workflow and actual local owner writers.

Only synthetic local DB identities and committed delivery tasks; no provider workers.
"""
import json
import os
import runpy
from datetime import timedelta
from uuid import uuid4

import pytest
from shared_kernel.clock import SystemBusinessClock

base = runpy.run_path('tests/domains/scheduling/subsystems/scheduling/modules/service-start/test_service_start_mysql.py')
http = base['http']
rows, write, checked = base['rows'], base['write'], base['checked']
action, willingness, joined = base['action'], base['willingness'], base['joined']
pytestmark = pytest.mark.skipif(not os.getenv('SERVICE_START_TEST_DB'), reason='explicit local synthetic DB required')
ROOT = '/api/v1/scheduling/service-start'
TODAY = SystemBusinessClock().today()


def setup(http, count=1):
    case,staff,segments = base['seed_case'](http,count=count)
    for index in range(count):
        checked(base['submit'](http,case,staff[index],segments[index],start=str(TODAY-timedelta(days=19)+timedelta(days=30*index)))[0])
    assignment=rows('SELECT a.id FROM case_staff_assignments a JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id WHERE a.case_no=%s AND a.staff_id=%s',(case,staff[0][0]))[0]['id']
    return case,staff,assignment


def context(http,case,assignment):
    return checked(http.get(ROOT+'/handover/context',params={'case_no':case,'assignment_id':assignment}))


def inquire(http,case,assignment,staff):
    facts=context(http,case,assignment)
    body={'case_no':case,'assignment_id':assignment,'staff_id':staff[0],
        'expected_order_version':facts['order_version'],'expected_scheduling_version':facts['scheduling_version'],
        'idempotency_key':uuid4().hex}
    return checked(http.post(ROOT+'/handover/inquire',json=body)),body


def detail(http,item):
    return checked(http.get(ROOT+f"/{item['request_id']}"))


def ready(http,case,assignment,staff):
    item,_=inquire(http,case,assignment,staff)
    willingness(item,staff,'willing')
    item,_=action(http,detail(http,item),'invite')
    joined(case,staff)
    return detail(http,item)


def schedule(case):
    return rows('SELECT a.staff_id,d.work_date,d.is_double_pay FROM staff_schedule d JOIN case_staff_assignments a ON a.id=d.assignment_id JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id WHERE a.case_no=%s AND d.effective_marker=1 AND d.is_work_day=1 ORDER BY d.work_date',(case,))


def money(case):
    return {name:rows('SELECT * FROM '+name+' WHERE case_no=%s ORDER BY '+order,(case,)) for name,order in [
        ('client_payment_terms','case_no'),('client_obligations','obligation_identity'),('client_ledger_entries','id'),
        ('staff_obligations','obligation_identity')]}


def save(http,item,day=None,key=None):
    body={'start_date':str(day or TODAY+timedelta(days=1)),'expected_version':item['version'],'idempotency_key':key or uuid4().hex}
    return http.post(ROOT+f"/{item['request_id']}/dates",json=body),body


def test_case_query_is_read_only_and_requires_exact_in_service_source(http):
    case,staff,assignment=setup(http,2)
    before=rows('SELECT COUNT(*) n FROM scheduling_service_start_requests WHERE case_no=%s',(case,))
    value=context(http,case,assignment)
    assert value['staff_id']==staff[0][0] and value['assignment_id']==assignment
    assert len(value['service_dates'])==11 and value['request'] is None
    assert http.get(ROOT+'/handover/context',params={'case_no':case}).status_code==409
    assert http.get(ROOT+'/handover/context',params={'case_no':case,'assignment_id':assignment+999999}).status_code==409
    assert rows('SELECT COUNT(*) n FROM scheduling_service_start_requests WHERE case_no=%s',(case,))==before


def test_full_handover_decline_reselect_invite_join_dates_and_idempotent_result(http):
    case,staff,assignment=setup(http)
    before=schedule(case);payments=money(case)['client_ledger_entries']
    source=rows('SELECT actual_start_date,actual_end_date,status FROM orders WHERE case_no=%s',(case,))
    due=rows('SELECT first_payment_due_date FROM client_payment_terms WHERE case_no=%s',(case,))
    item,body=inquire(http,case,assignment,staff[1])
    assert item['workflow_kind']=='handover' and item['handover_dates'][0]==str(TODAY)
    assert schedule(case)==before
    assert checked(http.post(ROOT+'/handover/inquire',json=body))['request_id']==item['request_id']
    assert context(http,case,assignment)['request']['request_id']==item['request_id']
    assert http.post(ROOT+f"/{item['request_id']}/invite",json={'expected_version':item['version'],'idempotency_key':uuid4().hex}).status_code==409
    willingness(item,staff[1],'unwilling');item=detail(http,item)
    item,_=action(http,item,'inquire',staff_id=staff[2][0],start_date=item['handover_dates'][0],end_date=item['handover_dates'][-1])
    willingness(item,staff[1],'willing');assert detail(http,item)['willingness']=='pending'
    willingness(item,staff[2],'willing');item=detail(http,item)
    item,_=action(http,item,'invite')
    invitations=rows("SELECT recipient_identity FROM line_delivery_tasks WHERE source_aggregate_type='service_start_invitation' AND source_aggregate_identity LIKE %s",(str(rows('SELECT selected_candidate_id id FROM scheduling_service_start_requests WHERE id=%s',(item['request_id'],))[0]['id'])+':%',))
    assert invitations==[{'recipient_identity':staff[2][1]}]
    assert save(http,item)[0].status_code==409
    joined(case,staff[2]);item=detail(http,item)
    response,save_body=save(http,item);result=checked(response)
    assert result['status']=='applied' and result['result']['group_record_queued']
    after=schedule(case);handover=TODAY+timedelta(days=1)
    assert [r for r in after if r['work_date']<handover]==[r for r in before if r['work_date']<handover]
    assert all(r['staff_id']==staff[2][0] for r in after if r['work_date']>=handover)
    assert len(after)==len(before)==30
    assert rows('SELECT actual_start_date,actual_end_date,status FROM orders WHERE case_no=%s',(case,))==source
    assert rows('SELECT first_payment_due_date FROM client_payment_terms WHERE case_no=%s',(case,))==due
    assert money(case)['client_ledger_entries']==payments
    final=money(case)
    assert checked(http.post(ROOT+f"/{item['request_id']}/dates",json=save_body))['status']=='applied'
    assert money(case)==final
    assert context(http,case,assignment)['request']['status']=='applied'
    assert checked(http.get(ROOT+'/todos',params={'case_no':case}))['total']==0
    task=rows("SELECT recipient_type,payload_snapshot FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(item['request_id']),))
    assert len(task)==1 and task[0]['recipient_type']=='group' and 'postback' not in task[0]['payload_snapshot']
    outcome=rows('SELECT request_snapshot FROM scheduling_leave_substitution_batches WHERE case_no=%s',(case,))
    assert str(handover) in str(outcome)


def test_handover_preserves_unrelated_caregiver_segment(http):
    case,staff,assignment=setup(http,2)
    before=schedule(case)
    item=ready(http,case,assignment,staff[2]);result=checked(save(http,item)[0])
    assert result['status']=='applied'
    assert [r for r in schedule(case) if r['staff_id']==staff[1][0]]==[r for r in before if r['staff_id']==staff[1][0]]
    assert len(schedule(case))==60
    # A handover envelope never replaces either original service-start peer result.
    assert len(rows("SELECT id FROM scheduling_service_start_requests WHERE case_no=%s AND confirmed_version_id IS NOT NULL",(case,)))==2


@pytest.mark.parametrize('day',[-1,50])
def test_invalid_handover_dates_preserve_schedule_and_all_money(http,day):
    case,staff,assignment=setup(http)
    item=ready(http,case,assignment,staff[1]);before=schedule(case);financial=money(case)
    response,_=save(http,item,TODAY+timedelta(days=day))
    assert response.status_code==409 and 'error' in response.json()['detail']
    assert schedule(case)==before and money(case)==financial
    assert detail(http,item)['status']=='substitute_required'


def test_conflict_retains_todo_all_original_facts_and_can_change_candidate(http):
    case,staff,assignment=setup(http)
    item=ready(http,case,assignment,staff[1]);before=schedule(case);financial=money(case)
    write("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,status,reason,created_by) VALUES (%s,'long_leave',%s,%s,'effective','synthetic','synthetic')",(staff[1][0],TODAY,TODAY+timedelta(days=30)))
    result=checked(save(http,item)[0])
    assert result['status']=='substitute_required' and result['conflict_message']
    assert schedule(case)==before and money(case)==financial
    item,_=action(http,result,'inquire',staff_id=staff[2][0],start_date=result['handover_dates'][0],end_date=result['handover_dates'][-1])
    willingness(item,staff[2],'willing');joined(case,staff[2]);item=detail(http,item)
    assert checked(save(http,item)[0])['status']=='applied'


def test_initial_selection_fresh_versions_and_command_content_are_guarded(http):
    case,staff,assignment=setup(http)
    facts=context(http,case,assignment)
    body={'case_no':case,'assignment_id':assignment,'staff_id':staff[1][0],'expected_order_version':facts['order_version']+1,
        'expected_scheduling_version':facts['scheduling_version'],'idempotency_key':uuid4().hex}
    assert http.post(ROOT+'/handover/inquire',json=body).status_code==409
    body.update(expected_order_version=facts['order_version'],staff_id=staff[0][0],idempotency_key=uuid4().hex)
    assert http.post(ROOT+'/handover/inquire',json=body).status_code==409
    assert context(http,case,assignment)['request'] is None
    item,body=inquire(http,case,assignment,staff[1]);body['staff_id']=staff[2][0]
    assert http.post(ROOT+'/handover/inquire',json=body).status_code==409
    facts=context(http,case,assignment)
    body.update(idempotency_key=uuid4().hex)
    assert http.post(ROOT+'/handover/inquire',json=body).status_code==409
    assert len(rows("SELECT id FROM scheduling_service_start_requests WHERE case_no=%s AND JSON_UNQUOTE(JSON_EXTRACT(execution_dates,'$.kind'))='handover-v1'",(case,)))==1


@pytest.mark.parametrize('paid',[0,12000,72000])
def test_handover_uses_payroll_correction_preserving_actual_payout_and_customer_receipts(http,paid):
    case,staff,assignment=setup(http)
    if paid:
        write("INSERT INTO staff_bank_accounts(staff_id,is_primary,bank_code,account_no) VALUES (%s,1,'synthetic',%s)",(staff[0][0],base['h']['staff_account'](staff[0][0])))
        contents=base['h']['workbook'](case,paid,4,account=base['h']['staff_account'](staff[0][0]))
        batch=checked(http.post('/api/v1/finance-import/workbooks/ingest',files={'workbook':(case+'.xlsx',contents,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},headers={'Idempotency-Key':case+':paid-fixture'}))['batch_identity']
        plan=checked(http.post('/api/v1/finance-import/batches/preview',json={'batch_identity':batch}))
        from api.dependencies.staff_payout import build_staff_payout_application
        from infrastructure.mysql import mysql_adapter
        from domains.staff_payables.reconciliation import StaffPayoutEventType,StaffPayoutDifferenceMode
        from subsystems.staff_payables.payout_reconciliation import StaffPayoutSelection,StaffPayoutApplyRequest
        from shared_kernel.identities import ActorContext,CorrelationId,ExpectedVersion,IdempotencyKey
        selection=StaffPayoutSelection(StaffPayoutEventType.PAYOUT,(plan['rows'][0]['row_identity'].split(':')[-1],),
            tuple(r['obligation_identity'] for r in base['h']['money_snapshot'](case)),
            difference_mode=StaffPayoutDifferenceMode.UNDERPAYMENT if paid==12000 else None)
        connection=mysql_adapter.get_connection()
        try:
            application=build_staff_payout_application(connection)
            preview=application.preview(selection,CorrelationId(case))
            application.apply(StaffPayoutApplyRequest(selection,ExpectedVersion(preview.staff_payables_version),
                ExpectedVersion(preview.bank_facts_version),preview.fingerprint,IdempotencyKey(case+':payout'),ActorContext('synthetic'),'',CorrelationId(case)))
        finally:connection.close()
    ledger=rows('SELECT * FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case,))
    payout=rows('SELECT link.* FROM staff_payout_obligation_links link JOIN staff_obligations o ON o.obligation_identity=link.obligation_identity WHERE o.case_no=%s ORDER BY link.payout_event_id,link.id',(case,))
    item=ready(http,case,assignment,staff[1]);assert checked(save(http,item)[0])['status']=='applied'
    assert rows('SELECT * FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case,))==ledger
    assert rows('SELECT link.* FROM staff_payout_obligation_links link JOIN staff_obligations o ON o.obligation_identity=link.obligation_identity WHERE o.case_no=%s ORDER BY link.payout_event_id,link.id',(case,))==payout
    obligations=base['h']['money_snapshot'](case)
    active={r['staff_id']:max(0,int(r['balance_ntd'])) for r in obligations if r['obligation_kind']=='service_pay' and r['status']!='cancelled' and r['projection_status']!='closed'}
    assert active=={staff[0][0]:max(0,48000-paid),staff[1][0]:24000},obligations
    assert sum(int(link['allocated_amount_ntd']) for link in payout)==paid
    if paid==72000:
        assert rows('SELECT remaining_amount_ntd FROM staff_overpayment_recoveries WHERE staff_id=%s',(staff[0][0],))[0]['remaining_amount_ntd']==24000


def test_handover_transaction_failure_rolls_back_all_owner_changes_and_can_replay(http,monkeypatch):
    from infrastructure.mysql.leave_substitution_impact_ports import MySqlPayrollLeaveImpactPort
    case,staff,assignment=setup(http)
    item=ready(http,case,assignment,staff[1]);before=schedule(case);financial=money(case)
    def fail(*args): raise RuntimeError('synthetic payroll persistence failure')
    with monkeypatch.context() as patch:
        patch.setattr(MySqlPayrollLeaveImpactPort,'persist_leave_substitution',fail)
        with pytest.raises(RuntimeError,match='synthetic payroll'):
            save(http,item,key=case+':atomic')
    assert schedule(case)==before and money(case)==financial
    assert not rows('SELECT batch_key FROM scheduling_leave_substitution_batches WHERE case_no=%s',(case,))
    assert detail(http,item)['status']=='substitute_required'
    assert checked(save(http,item,key=case+':atomic')[0])['status']=='applied'


def test_group_departure_and_changed_binding_block_formal_handover(http):
    case,staff,assignment=setup(http)
    item=ready(http,case,assignment,staff[1]);before=schedule(case)
    joined(case,staff[1],'member_left')
    assert save(http,item)[0].status_code==409 and schedule(case)==before
    joined(case,staff[1])
    write("UPDATE line_identity_role_bindings SET binding_status='revoked' WHERE line_user_id=%s",(staff[1][1],))
    assert save(http,item)[0].status_code==409 and schedule(case)==before


def test_union_role_can_complete_entire_handover_without_system_admin(http,monkeypatch):
    from api.dependencies import admin_auth
    from subsystems.access.authentication_session import AdminPrincipal
    case,staff,assignment=setup(http)
    with monkeypatch.context() as patch:
        patch.delitem(http.app.dependency_overrides,admin_auth.require_line_matching_override)
        patch.setitem(http.app.dependency_overrides,admin_auth.require_admin,
            lambda:AdminPrincipal(1,'synthetic-union','Synthetic union','line_manager'))
        item=ready(http,case,assignment,staff[1])
        assert checked(save(http,item)[0])['status']=='applied'
        patch.setitem(http.app.dependency_overrides,admin_auth.require_admin,
            lambda:AdminPrincipal(1,'synthetic-staff','Synthetic staff','staff'))
        assert http.get(ROOT+'/handover/context',params={'case_no':case,'assignment_id':assignment}).status_code==403


def test_concurrent_same_initial_command_creates_one_inquiry(http):
    from concurrent.futures import ThreadPoolExecutor
    case,staff,assignment=setup(http)
    facts=context(http,case,assignment)
    body={'case_no':case,'assignment_id':assignment,'staff_id':staff[1][0],
        'expected_order_version':facts['order_version'],'expected_scheduling_version':facts['scheduling_version'],
        'idempotency_key':uuid4().hex}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:http.post(ROOT+'/handover/inquire',json=body),range(2)))
    identities=[checked(response)['request_id'] for response in results]
    assert len(set(identities))==1
    assert len(rows('SELECT id FROM scheduling_service_start_candidates WHERE request_id=%s',(identities[0],)))==1


def test_original_assignment_change_blocks_old_candidate_delivery_and_date_save(http):
    from domains.line.identities import LineDeliveryTaskId
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from infrastructure.mysql import mysql_adapter
    from api.routes.staff_leave_intake import router
    if not getattr(http.app.state,'leave_results_registered',False):
        http.app.include_router(router);http.app.state.leave_results_registered=True
    case,staff,assignment=setup(http)
    item=ready(http,case,assignment,staff[1])
    invitation=rows("SELECT id FROM line_delivery_tasks WHERE source_aggregate_type='service_start_invitation' AND source_aggregate_identity LIKE %s",(str(rows('SELECT selected_candidate_id id FROM scheduling_service_start_requests WHERE id=%s',(item['request_id'],))[0]['id'])+':%',))[0]['id']
    def current():
        connection=mysql_adapter.get_connection()
        try:
            with LineMySqlUnitOfWork(connection) as unit:
                return unit.service_starts.delivery_is_current(unit.delivery_tasks.get(LineDeliveryTaskId(invitation)))
        finally:connection.close()
    assert current()
    options=checked(http.post('/api/v1/line/staff-self-service/leave-results/cases',json={'line_id_token':staff[0][1]}))['items']
    subject=next(o for o in options if o['case_no']==case)
    body={'line_id_token':staff[0][1],'case_no':case,'assignment_id':assignment,'decision':'defer',
        'dates':[{'original_date':str(TODAY+timedelta(days=1)),'new_date':str(TODAY+timedelta(days=20))}],
        'expected_order_version':subject['order_version'],'expected_scheduling_version':subject['scheduling_version'],'idempotency_key':uuid4().hex}
    assert checked(http.post('/api/v1/line/staff-self-service/leave-results/submit',json=body))['status']=='applied'
    assert not current()
    before=schedule(case);financial=money(case)
    assert save(http,item)[0].status_code==409
    assert schedule(case)==before and money(case)==financial


def test_concurrent_same_handover_save_preserves_one_result_and_one_group_record(http):
    from concurrent.futures import ThreadPoolExecutor
    case,staff,assignment=setup(http)
    item=ready(http,case,assignment,staff[1])
    body={'start_date':str(TODAY+timedelta(days=1)),'expected_version':item['version'],'idempotency_key':uuid4().hex}
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda _:http.post(ROOT+f"/{item['request_id']}/dates",json=body),range(2)))
    assert all(checked(response)['status']=='applied' for response in replies)
    assert len(rows('SELECT batch_key FROM scheduling_leave_substitution_batches WHERE case_no=%s',(case,)))==1
    assert len(rows("SELECT id FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(item['request_id']),)))==1

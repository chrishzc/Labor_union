"""Real local owner transactions for agreed leave results; no provider worker runs."""
import os
import runpy
from datetime import date, timedelta
from uuid import uuid4

import pytest

base = runpy.run_path('tests/domains/scheduling/subsystems/scheduling/modules/service-start/test_service_start_mysql.py')
http = base['http']
rows, write, checked = base['rows'], base['write'], base['checked']
action, willingness, joined = base['action'], base['willingness'], base['joined']
pytestmark = pytest.mark.skipif(not os.getenv('SERVICE_START_TEST_DB'), reason='explicit local synthetic DB required')


def setup(http, count=1):
    from api.routes.staff_leave_intake import router
    if not getattr(http.app.state,'leave_results_registered',False):
        http.app.include_router(router)
        http.app.state.leave_results_registered=True
    case, staff, segments = base['seed_case'](http, count=count)
    for index in range(count):
        checked(base['submit'](http,case,staff[index],segments[index],start=str(date(2027,1,5)+timedelta(days=30*index)))[0])
    return case, staff


def submit(http, case, staff, decision='defer', dates=None, **overrides):
    options = checked(http.post('/api/v1/line/staff-self-service/leave-results/cases',json={'line_id_token':staff[1]}))['items']
    item = next(o for o in options if o['case_no']==case)
    body = {'line_id_token':staff[1], 'case_no':case, 'assignment_id':item['assignment_id'],
        'expected_order_version':item['order_version'],'expected_scheduling_version':item['scheduling_version'],
        'decision':decision,'dates': dates or [{'original_date':'2027-01-05','new_date':'2027-02-10' if decision=='defer' else None}],
        'idempotency_key':uuid4().hex,**overrides}
    return http.post('/api/v1/line/staff-self-service/leave-results/submit',json=body),body


def schedule(case):
    return rows('SELECT a.staff_id,d.work_date,d.is_double_pay FROM staff_schedule d JOIN case_staff_assignments a ON a.id=d.assignment_id '
        'JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id '
        'WHERE a.case_no=%s AND d.effective_marker=1 AND d.is_work_day=1 ORDER BY d.work_date',(case,))


def test_agreed_defer_updates_dates_schedule_finance_and_only_original_group(http):
    case,staff=setup(http)
    before=schedule(case)
    payments=rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case,))
    result,body=submit(http,case,staff[0]);result=checked(result)
    assert result['workflow_kind']=='leave' and result['status']=='applied'
    assert result['result']['actual_start_date']=='2027-01-06'
    assert result['result']['actual_end_date']=='2027-02-10'
    assert result['result']['first_payment_due_date']=='2027-01-06'
    after=schedule(case)
    assert len(after)==len(before)==30
    assert str(after[-1]['work_date'])=='2027-02-10'
    assert rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case,))==payments
    assert checked(http.post('/api/v1/line/staff-self-service/leave-results/submit',json=body))['request_id']==result['request_id']
    tasks=rows("SELECT recipient_type,recipient_identity,payload_snapshot FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(result['request_id']),))
    assert len(tasks)==1 and tasks[0]['recipient_type']=='group' and 'postback' not in tasks[0]['payload_snapshot']
    assert not rows("SELECT id FROM line_delivery_tasks WHERE source_aggregate_type='staff_leave_customer_coordination' AND payload_snapshot LIKE %s",('%'+case+'%',))
    assert checked(http.get('/api/v1/scheduling/service-start/todos',params={'case_no':case}))['total']==0
    from domains.line.identities import LineDeliveryTaskId
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from infrastructure.mysql import mysql_adapter
    task_id=rows("SELECT id FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(result['request_id']),))[0]['id']
    connection=mysql_adapter.get_connection()
    try:
        with LineMySqlUnitOfWork(connection) as unit:
            task=unit.delivery_tasks.get(LineDeliveryTaskId(task_id))
            assert unit.service_starts.delivery_is_current(task)
        write('UPDATE line_order_group_bindings SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,))
        with LineMySqlUnitOfWork(connection) as unit:
            assert not unit.service_starts.delivery_is_current(task)
    finally:connection.close()
    body['dates'][0]['new_date']='2027-02-11'
    assert http.post('/api/v1/line/staff-self-service/leave-results/submit',json=body).status_code==409


def test_conflict_preserves_all_owner_facts_then_union_records_new_agreement(http):
    case,staff=setup(http)
    before=schedule(case)
    finance=rows('SELECT * FROM client_payment_terms WHERE case_no=%s',(case,))
    write("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,status,reason,created_by) VALUES (%s,'long_leave','2027-02-10','2027-02-10','effective','synthetic','synthetic')",(staff[0][0],))
    result=checked(submit(http,case,staff[0])[0])
    assert result['status']=='substitute_required' and result['conflict_message']
    assert schedule(case)==before
    assert rows('SELECT * FROM client_payment_terms WHERE case_no=%s',(case,))==finance
    assert checked(http.get('/api/v1/scheduling/service-start/todos',params={'case_no':case}))['total']==1
    assert submit(http,case,staff[0])[0].status_code==409
    body={'expected_version':result['version'],'idempotency_key':uuid4().hex,
          'dates':[{'original_date':'2027-01-05','new_date':'2027-02-11'}]}
    path=f"/api/v1/scheduling/service-start/{result['request_id']}/defer"
    updated=checked(http.post(path,json=body))
    assert updated['status']=='applied'
    assert checked(http.post(path,json=body))['status']=='applied'


def test_substitution_willingness_invitation_join_and_staff_entered_dates(http):
    case,staff=setup(http)
    before=schedule(case)
    item=checked(submit(http,case,staff[0],decision='substitute')[0])
    assert schedule(case)==before and item['status']=='substitute_required'
    item,_=action(http,item,'inquire',staff_id=staff[1][0],start_date='2027-01-05',end_date='2027-01-05')
    inquiry=rows("SELECT payload_snapshot FROM line_delivery_tasks WHERE source_aggregate_type='service_start_inquiry' AND source_aggregate_identity=(SELECT selected_candidate_id FROM scheduling_service_start_requests WHERE id=%s)",(item['request_id'],))[0]['payload_snapshot']
    assert '服務日期：2027-01-05' in inquiry
    assert http.post(f"/api/v1/scheduling/service-start/{item['request_id']}/invite",json={'expected_version':item['version'],'idempotency_key':uuid4().hex}).status_code==409
    willingness(item,staff[1],'unwilling')
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    item,_=action(http,item,'inquire',staff_id=staff[2][0],start_date='2027-01-05',end_date='2027-01-05')
    willingness(item,staff[1],'willing')
    assert checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))['willingness']=='pending'
    willingness(item,staff[2],'willing')
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    item,_=action(http,item,'invite')
    body={'expected_version':item['version'],'idempotency_key':uuid4().hex,'start_date':'2027-01-05',
          'date_changes':[{'original_date':'2027-01-05','new_date':'2027-01-05'}]}
    path=f"/api/v1/scheduling/service-start/{item['request_id']}/dates"
    assert http.post(path,json=body).status_code==409
    joined(case,staff[2])
    result=checked(http.post(path,json=body))
    assert result['status']=='applied' and result['result']['group_record_queued']
    after=schedule(case)
    assert len(after)==30 and after[0]['staff_id']==staff[2][0]
    assert all(row['staff_id']==staff[0][0] for row in after[1:])
    assert checked(http.post(path,json=body))['status']=='applied'


def test_submit_identity_stale_dates_and_rollback(http,monkeypatch):
    case,staff=setup(http)
    response,body=submit(http,case,staff[0],expected_scheduling_version=0)
    assert response.status_code==409
    body['line_id_token']=staff[1][1]
    assert http.post('/api/v1/line/staff-self-service/leave-results/submit',json=body).status_code==409
    assert submit(http,case,staff[0],dates=[{'original_date':'2027-01-04','new_date':'2027-02-10'}])[0].status_code==409
    before=schedule(case)
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
    def fail(*args,**kwargs):raise RuntimeError('synthetic failure after financial writes')
    with monkeypatch.context() as patch:
        patch.setattr(MySqlServiceStartRepository,'complete',fail)
        with pytest.raises(RuntimeError,match='synthetic failure'):
            submit(http,case,staff[0])
    assert schedule(case)==before
    assert rows('SELECT COUNT(*) n FROM scheduling_service_start_requests WHERE case_no=%s',(case,))[0]['n']==1


def test_same_case_date_collision_is_internal_todo_and_other_staff_days_are_unchanged(http):
    case,staff=setup(http,count=2)
    before=schedule(case)
    result=checked(submit(http,case,staff[1],dates=[{'original_date':'2027-02-04','new_date':'2027-02-05'}])[0])
    assert result['status']=='substitute_required'
    assert schedule(case)==before
    body={'expected_version':result['version'],'idempotency_key':uuid4().hex,
          'dates':[{'original_date':'2027-02-04','new_date':'2027-03-10'}]}
    result=checked(http.post(f"/api/v1/scheduling/service-start/{result['request_id']}/defer",json=body))
    assert result['status']=='applied'
    assert [r for r in schedule(case) if r['staff_id']==staff[0][0]]==[r for r in before if r['staff_id']==staff[0][0]]
    assert len(schedule(case))==len(before)


def test_substitute_may_record_actual_new_day_after_joining_and_conflict_stays_pending(http):
    case,staff=setup(http)
    item=checked(submit(http,case,staff[0],decision='substitute')[0])
    item,_=action(http,item,'inquire',staff_id=staff[1][0],start_date='2027-01-05',end_date='2027-01-05')
    willingness(item,staff[1],'willing');joined(case,staff[1])
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    before=schedule(case)
    write("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,status,reason,created_by) VALUES (%s,'long_leave','2027-02-10','2027-02-10','effective','synthetic','synthetic')",(staff[1][0],))
    body={'expected_version':item['version'],'idempotency_key':uuid4().hex,'start_date':'2027-02-10',
          'date_changes':[{'original_date':'2027-01-05','new_date':'2027-02-10'}]}
    path=f"/api/v1/scheduling/service-start/{item['request_id']}/dates"
    item=checked(http.post(path,json=body))
    assert item['status']=='substitute_required' and schedule(case)==before
    body.update(expected_version=item['version'],idempotency_key=uuid4().hex,start_date='2027-02-11',
                date_changes=[{'original_date':'2027-01-05','new_date':'2027-02-11'}])
    result=checked(http.post(path,json=body))
    assert result['status']=='applied'
    assert any(str(row['work_date'])=='2027-02-11' and row['staff_id']==staff[1][0] for row in schedule(case))


def test_in_service_defer_preserves_started_days_and_receipt_history(http):
    # Signed prerequisites are synthetic; the initial start uses the real owner.
    from api.routes.staff_leave_intake import router
    if not getattr(http.app.state,'leave_results_registered',False):
        http.app.include_router(router);http.app.state.leave_results_registered=True
    case,staff,segments=base['seed_case'](http)
    checked(base['submit'](http,case,staff[0],segments[0],start='2026-10-05')[0])
    before=schedule(case)
    paid=rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case,))
    result=checked(submit(http,case,staff[0],dates=[{'original_date':'2026-10-29','new_date':'2026-11-10'}])[0])
    assert result['status']=='applied'
    assert result['result']['actual_start_date']=='2026-10-05'
    assert result['result']['first_payment_due_date']=='2026-10-05'
    assert [r for r in schedule(case) if str(r['work_date'])<'2026-10-29']==[r for r in before if str(r['work_date'])<'2026-10-29']
    assert rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case,))==paid


def test_missing_group_never_falls_back_to_private_customer_or_original_staff(http):
    case,staff=setup(http)
    write("UPDATE line_order_group_bindings SET binding_status='unbound',group_id=NULL WHERE case_no=%s",(case,))
    result=checked(submit(http,case,staff[0])[0])
    assert result['status']=='applied' and not result['result']['group_record_queued']
    assert not rows("SELECT id FROM line_delivery_tasks WHERE source_aggregate_identity=%s AND source_aggregate_type='service_start_schedule'",(str(result['request_id']),))

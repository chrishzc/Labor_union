"""Real localhost MySQL/API service starts. Signed documents/group identities are synthetic prerequisites.

Every service result, candidate inquiry, willingness response, invitation and date save
uses its actual application/API. No provider or application lifespan worker is run.
"""
import json
import os
import runpy
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infrastructure.mysql import mysql_adapter

DATABASE=os.getenv('SERVICE_START_TEST_DB')
pytestmark=pytest.mark.skipif(not DATABASE,reason='requires explicit disposable localhost service-start DB')
h=runpy.run_path('tests/domains/scheduling/subsystems/scheduling/integration/test_complex_service_accounting_mysql.py')


@pytest.fixture(scope='module')
def http():
    assert DATABASE.startswith('lu_test_') and mysql_adapter.DB_CONFIG['host'] in ('127.0.0.1','localhost')
    from api.dependencies import admin_auth
    from api.routes import service_start,line_staff_self_service,line_mobile_admin,order_intake_terms_bootstrap,finance_import
    from api.dependencies import line_identity
    from domains.line.identities import LineUserId
    from subsystems.access.authentication_session import AdminPrincipal
    from infrastructure.mysql.nas_mutations import PROCEDURES
    app=FastAPI()
    for module in [service_start,line_staff_self_service,line_mobile_admin,order_intake_terms_bootstrap,finance_import]:app.include_router(module.router)
    principal=AdminPrincipal(1,'synthetic-union','測試工會人員','system_admin')
    for guard in [admin_auth.require_admin,admin_auth.require_system_admin,admin_auth.require_persisted_admin,admin_auth.require_line_matching_override]:
        app.dependency_overrides[guard]=lambda:principal
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG,'database',DATABASE)
        verifier=SimpleNamespace(verify=lambda token:SimpleNamespace(line_user_id=LineUserId(token)))
        patch.setattr(line_staff_self_service,'get_liff_token_verifier',lambda:verifier)
        patch.setattr(line_mobile_admin,'get_liff_token_verifier',lambda:verifier)
        c=mysql_adapter.get_connection()
        try:
            with c.cursor() as cursor:
                for name in ['lu_nas_cancel_occupancy_v1']:
                    cursor.execute('SELECT ROUTINE_NAME FROM information_schema.routines WHERE routine_schema=DATABASE() AND routine_name=%s',(name,))
                    if not cursor.fetchone():
                        args,body,_=PROCEDURES[name]
                        cursor.execute(f'CREATE PROCEDURE {name} ({args}) SQL SECURITY INVOKER BEGIN {body} END')
            c.commit()
        finally:c.close()
        with TestClient(app,headers={'X-Correlation-ID':'service-start-test'}) as client:yield client


def write(sql,params=()):
    c=mysql_adapter.get_connection()
    try:
        with c.cursor() as cursor:
            cursor.execute(sql,params);identity=cursor.lastrowid
        c.commit();return identity
    finally:c.close()


def rows(sql,params=()):
    return h['rows'](sql,params)


def checked(response):
    assert response.status_code==200,response.text
    return response.json()['data']


def seed_case(http,*,count=1):
    case='116'+str(rows('SELECT COUNT(*) n FROM orders')[0]['n']+1).zfill(6)
    client=write("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic service start','一般市民','連續服務','2026-10-01')",(case,))
    write("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,'2027-01-01',%s,8,0,'08:00:00','17:00:00',0)",(case,client,count*30))
    base=f'/api/v1/orders/{case}/intake-completion'
    p=checked(http.post(base+'/preview',json={}))
    checked(http.post(base+'/apply',json={'expected_lifecycle_version':p['lifecycle_version'],'preview_fingerprint':p['preview_fingerprint'],'reason':''},headers={'Idempotency-Key':case+':init'}))
    # Real Finance bank/receipt owner settles the prerequisite deposit.
    amount=rows("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='deposit'",(case,))[0]['amount_due_ntd']
    h['bank'](http,case,amount,1)
    staff=[]
    for index in range(count+2):
        line='U'+uuid4().hex
        identity=write("INSERT INTO staff(name,status,line_user_id) VALUES (%s,'active',%s)",(f'Synthetic {case} {index}',line))
        write("INSERT INTO line_platform_users(line_user_id,friend_status) VALUES (%s,'active')",(line,))
        write("INSERT INTO line_identity_role_bindings(line_user_id,subject_type,binding_status,subject_reference) VALUES (%s,'staff','bound',%s)",(line,str(identity)))
        staff.append((identity,line))
    plan=write("INSERT INTO caregiver_matching_plans(case_no,status,is_active,start_date,end_date,created_by) VALUES (%s,'proposed',1,'2027-01-01',%s,'synthetic signed prerequisite')",(case,date(2027,1,1)+timedelta(days=count*30-1)))
    commitment=write('INSERT INTO precontract_service_commitments(case_no,matching_plan_id,commitment_key,plan_snapshot_sha256,created_by) VALUES (%s,%s,%s,%s,%s)',(case,plan,case+':commitment','0'*64,'synthetic signed prerequisite'))
    segments=[]
    for index,(staff_id,line) in enumerate(staff[:count]):
        start=date(2027,1,1)+timedelta(days=index*30)
        segment=write('INSERT INTO caregiver_matching_plan_segments(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) VALUES (%s,%s,%s,%s,%s)',(plan,index+1,staff_id,start,start+timedelta(days=29)))
        segments.append(segment)
        for i in range(30):write('INSERT INTO precontract_service_commitment_days(commitment_id,matching_segment_id,staff_id,service_date) VALUES (%s,%s,%s,%s)',(commitment,segment,staff_id,start+timedelta(days=i)))
    write("INSERT INTO order_contract_flow_events(case_no,contract_identity,event_type,actor,reason,idempotency_key) VALUES (%s,%s,'contract_completed','synthetic','signed fixture',%s)",(case,case+':signed',case+':signed'))
    # Signed client contract qualifies the canonical waiting-lock writer.
    write("INSERT INTO matching_response_events(plan_id,response_type,response_value,response_source,actor_id,reason,idempotency_key,payload_fingerprint,occurred_at_utc) VALUES (%s,'customer_decision','accepted','admin','synthetic','prerequisite',%s,%s,UTC_TIMESTAMP(6))",(plan,case+':customer','0'*64))
    write("INSERT INTO line_order_group_bindings(case_no,group_id,binding_status,aggregate_version,invitation_url) VALUES (%s,%s,'bound',1,%s)",(case,'C'+uuid4().hex,'https://line.me/R/ti/g/synthetic-'+case))
    write("INSERT INTO line_order_group_binding_events(case_no,action,expected_version,resulting_version,actor_id,binding_fingerprint,idempotency_key,correlation_id) VALUES (%s,'bound',0,1,'synthetic',%s,%s,%s)",(case,'0'*64,case+':group',case))
    return case,staff,segments


def submit(http,case,staff,segment,decision='accepted',start='2027-01-05',key=None):
    version=rows('SELECT lifecycle_version FROM orders WHERE case_no=%s',(case,))[0]['lifecycle_version']
    body={'line_id_token':staff[1],'case_no':case,'segment_id':segment,'decision':decision,
        'start_date':start if decision=='accepted' else None,'expected_order_version':version,'idempotency_key':key or uuid4().hex}
    return http.post('/api/v1/line/staff-self-service/service-start/submit',json=body),body


def test_normal_start_atomic_dates_finance_group_result_and_replay(http):
    case,staff,segments=seed_case(http)
    response,body=submit(http,case,staff[0],segments[0])
    result=checked(response)
    assert result['status']=='applied'
    assert result['result']['actual_start_date']=='2027-01-05'
    assert result['result']['first_payment_due_date']=='2027-01-05'
    assert len(result['result']['assignments'][0]['service_dates'])==30
    assert rows("SELECT COUNT(*) n FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(result['request_id']),))[0]['n']==1
    assert checked(http.post('/api/v1/line/staff-self-service/service-start/submit',json=body))['request_id']==result['request_id']
    assert rows("SELECT COUNT(*) n FROM scheduling_service_start_requests WHERE case_no=%s",(case,))[0]['n']==1
    assert checked(http.get('/api/v1/scheduling/service-start/todos',params={'case_no':case}))['total']==0


def test_refusal_is_todo_and_does_not_change_official_dates(http):
    case,staff,segments=seed_case(http)
    before=rows('SELECT actual_start_date,lifecycle_version FROM orders WHERE case_no=%s',(case,))
    result=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    assert result['status']=='substitute_required'
    assert rows('SELECT actual_start_date,lifecycle_version FROM orders WHERE case_no=%s',(case,))==before
    assert checked(http.get('/api/v1/scheduling/service-start/todos',params={'case_no':case}))['total']==1


def action(http,item,kind,**fields):
    body={'expected_version':item['version'],'idempotency_key':uuid4().hex,**fields}
    return checked(http.post(f"/api/v1/scheduling/service-start/{item['request_id']}/{kind}",json=body)),body


def willingness(item,staff,decision):
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from subsystems.line.matching_postback_application import LineMatchingPostbackApplication
    from domains.line.identities import LineSourceType,LineUserId
    task=rows("SELECT payload_snapshot FROM line_delivery_tasks WHERE source_aggregate_type='service_start_inquiry' AND source_aggregate_identity=(SELECT selected_candidate_id FROM scheduling_service_start_requests WHERE id=%s) ORDER BY id DESC LIMIT 1",(item['request_id'],))[0]
    payload=json.loads(task['payload_snapshot'])
    data=next(button['action']['data'] for button in payload['contents']['footer']['contents'] if button['action']['data'].endswith(':'+decision))
    event=SimpleNamespace(source=SimpleNamespace(source_type=LineSourceType.USER,user_id=LineUserId(staff[1])),payload_json=json.dumps({'postback':{'data':data}}),event_id=SimpleNamespace(value=uuid4().hex))
    c=mysql_adapter.get_connection()
    try:
        with LineMySqlUnitOfWork(c) as unit:
            LineMatchingPostbackApplication(None).handle(SimpleNamespace(event=event),unit)
            unit.commit()
    finally:c.close()


def joined(case,staff,event_type='member_joined'):
    from infrastructure.mysql.line_media_order_group_repository import MySqlLineOrderGroupBindingRepository
    from domains.line.identities import LineUserId
    from shared_kernel.identities import IdempotencyKey
    c=mysql_adapter.get_connection()
    try:
        group=rows('SELECT group_id FROM line_order_group_bindings WHERE case_no=%s',(case,))[0]['group_id']
        MySqlLineOrderGroupBindingRepository(c).record_membership_event(group_id=group,line_user_id=LineUserId(staff[1]),event_type=event_type,idempotency_key=IdempotencyKey(uuid4().hex),occurred_at=datetime.now(timezone.utc))
        c.commit()
    finally:c.close()


def test_substitute_unwilling_reselect_single_invite_join_and_union_dates(http):
    case,staff,segments=seed_case(http)
    item=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    item,_=action(http,item,'inquire',staff_id=staff[1][0],start_date='2027-01-05',end_date='2027-02-03')
    willingness(item,staff[1],'unwilling')
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    assert item['willingness']=='unwilling'
    item,_=action(http,item,'inquire',staff_id=staff[2][0],start_date='2027-01-05',end_date='2027-02-03')
    willingness(item,staff[1],'willing')  # The previous nominee cannot approve the new selection.
    assert checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))['willingness']=='pending'
    willingness(item,staff[2],'willing')
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    item,invite_body=action(http,item,'invite')
    invitations=rows("SELECT recipient_identity FROM line_delivery_tasks WHERE source_aggregate_type='service_start_invitation' AND source_aggregate_identity LIKE %s",(str(rows('SELECT selected_candidate_id FROM scheduling_service_start_requests WHERE id=%s',(item['request_id'],))[0]['selected_candidate_id'])+':%',))
    assert [i['recipient_identity'] for i in invitations]==[staff[2][1]]
    assert http.post(f"/api/v1/scheduling/service-start/{item['request_id']}/dates",json={'expected_version':item['version'],'idempotency_key':uuid4().hex,'start_date':'2027-01-05'}).status_code==409
    joined(case,staff[2])
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    assert item['joined']
    item,body=action(http,item,'dates',start_date='2027-01-05')
    assert item['status']=='applied'
    assert [a['staff_id'] for a in item['result']['assignments']]==[staff[2][0]]
    assert item['result']['first_payment_due_date']=='2027-01-05'
    assert checked(http.post(f"/api/v1/scheduling/service-start/{item['request_id']}/dates",json=body))['status']=='applied'
    assert len(rows('SELECT * FROM scheduling_generations WHERE case_no=%s',(case,)))==1
    payload=rows("SELECT payload_snapshot FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(item['request_id']),))[0]['payload_snapshot']
    assert 'postback' not in payload and '確認' not in payload


def test_multiple_caregivers_wait_for_all_results_then_apply_once(http):
    case,staff,segments=seed_case(http,count=2)
    first=checked(submit(http,case,staff[0],segments[0])[0])
    assert first['status']=='awaiting_peers'
    assert rows('SELECT actual_start_date FROM orders WHERE case_no=%s',(case,))[0]['actual_start_date'] is None
    last=checked(submit(http,case,staff[1],segments[1],start='2027-02-04')[0])
    assert last['status']=='applied'
    assert len(last['result']['assignments'])==2
    assert checked(http.get(f"/api/v1/scheduling/service-start/{first['request_id']}"))['status']=='applied'
    assert len(rows("SELECT * FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(last['request_id']),)))==1


def test_occupancy_conflict_keeps_official_dates_unchanged_and_creates_todo(http):
    case,staff,segments=seed_case(http)
    write("INSERT INTO scheduling_staff_unavailability_blocks(staff_id,block_kind,start_date,end_date,status,reason,created_by) VALUES (%s,'long_leave','2027-01-05','2027-02-10','effective','synthetic private time','synthetic')",(staff[0][0],))
    before=rows('SELECT actual_start_date,lifecycle_version FROM orders WHERE case_no=%s',(case,))
    item=checked(submit(http,case,staff[0],segments[0])[0])
    assert item['status']=='substitute_required'
    assert rows('SELECT actual_start_date,lifecycle_version FROM orders WHERE case_no=%s',(case,))==before
    assert not rows('SELECT * FROM confirmed_service_date_versions WHERE case_no=%s',(case,))


def test_staff_object_scope_validation_and_stale_rollback(http):
    case,staff,segments=seed_case(http)
    response,body=submit(http,case,staff[1],segments[0])
    assert response.status_code==409
    response,body=submit(http,case,staff[0],segments[0],start=None)
    assert response.status_code==409
    body['start_date']='2027-01-05';body['expected_order_version']-=1
    assert http.post('/api/v1/line/staff-self-service/service-start/submit',json=body).status_code==409
    assert not rows('SELECT * FROM scheduling_service_start_requests WHERE case_no=%s',(case,))


def test_partial_in_service_substitution_preserves_case_dates_and_paid_history(http):
    case,staff,segments=seed_case(http)
    normal=checked(submit(http,case,staff[0],segments[0],start='2026-10-05')[0])
    assert rows('SELECT status FROM orders WHERE case_no=%s',(case,))[0]['status']=='服務中'
    before=rows('SELECT actual_start_date FROM orders WHERE case_no=%s',(case,))
    due=rows('SELECT first_payment_due_date FROM client_payment_terms WHERE case_no=%s',(case,))
    payments=rows("SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s AND entry_type='receipt' ORDER BY id",(case,))
    item=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    item,_=action(http,item,'inquire',staff_id=staff[1][0],start_date='2026-10-25',end_date='2026-10-27')
    willingness(item,staff[1],'willing');joined(case,staff[1])
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    item,_=action(http,item,'dates',start_date='2026-10-25')
    assert item['status']=='applied'
    assert rows('SELECT actual_start_date FROM orders WHERE case_no=%s',(case,))==before
    assert rows('SELECT first_payment_due_date FROM client_payment_terms WHERE case_no=%s',(case,))==due
    assert rows("SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s AND entry_type='receipt' ORDER BY id",(case,))==payments
    assigned={a['staff_id']:a['service_dates'] for a in item['result']['assignments']}
    assert assigned[staff[1][0]]==['2026-10-25','2026-10-26','2026-10-27']
    assert sum(len(days) for days in assigned.values())==30
    own=checked(http.post('/api/v1/line/staff-self-service/service-start/cases',json={'line_id_token':staff[0][1]}))['items']
    own=[item for item in own if item['case_no']==case]
    ids={item['assignment_id'] for item in own}
    current=rows('SELECT a.id FROM case_staff_assignments a JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id WHERE a.case_no=%s AND a.staff_id=%s',(case,staff[0][0]))
    assert len(own)==len(ids) and ids=={item['id'] for item in current}
    assert all(item['segment_start_date'] and item['segment_end_date'] for item in own)


def test_future_start_day_advances_only_orders_without_rescheduling_or_extra_message(http):
    from infrastructure.mysql.service_start_lifecycle_repository import MySqlServiceStartLifecycleRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.orders.service_start_lifecycle import ServiceStartLifecycleWorkflow
    from shared_kernel.clock import TAIPEI_TIME_ZONE
    case,staff,segments=seed_case(http)
    checked(submit(http,case,staff[0],segments[0])[0])
    assert rows('SELECT status FROM orders WHERE case_no=%s',(case,))[0]['status']=='訂單成立'
    before=rows('SELECT * FROM staff_schedule WHERE case_no=%s ORDER BY id',(case,))
    messages=rows('SELECT COUNT(*) n FROM line_delivery_tasks')[0]['n']
    c=mysql_adapter.get_connection()
    try:
        flow=ServiceStartLifecycleWorkflow(MySqlServiceStartLifecycleRepository(c),lambda:MySqlUnitOfWork(c))
        assert flow.advance_due(datetime(2027,1,4,tzinfo=TAIPEI_TIME_ZONE))==0
        assert flow.advance_due(datetime(2027,1,5,tzinfo=TAIPEI_TIME_ZONE))>=1
        assert not MySqlServiceStartLifecycleRepository(c).advance(case,datetime(2027,1,6,tzinfo=TAIPEI_TIME_ZONE))
        c.rollback()
    finally:c.close()
    assert rows('SELECT status FROM orders WHERE case_no=%s',(case,))[0]['status']=='服務中'
    assert rows('SELECT * FROM staff_schedule WHERE case_no=%s ORDER BY id',(case,))==before
    assert rows('SELECT COUNT(*) n FROM line_delivery_tasks')[0]['n']==messages


def test_concurrent_same_command_has_one_generation_and_one_group_result(http):
    from concurrent.futures import ThreadPoolExecutor
    case,staff,segments=seed_case(http)
    version=rows('SELECT lifecycle_version FROM orders WHERE case_no=%s',(case,))[0]['lifecycle_version']
    body={'line_id_token':staff[0][1],'case_no':case,'segment_id':segments[0],'decision':'accepted','start_date':'2027-01-05','expected_order_version':version,'idempotency_key':uuid4().hex}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:http.post('/api/v1/line/staff-self-service/service-start/submit',json=body),range(2)))
    values=[checked(r) for r in responses]
    assert values[0]['request_id']==values[1]['request_id']
    assert len(rows('SELECT * FROM scheduling_generations WHERE case_no=%s',(case,)))==1
    assert len(rows("SELECT * FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' AND source_aggregate_identity=%s",(str(values[0]['request_id']),)))==1


def test_infrastructure_failure_rolls_back_all_dates_finance_and_outbox(http,monkeypatch):
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
    case,staff,segments=seed_case(http)
    before=rows('SELECT * FROM orders WHERE case_no=%s',(case,))
    finance=rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))
    def fail(*_):raise RuntimeError('synthetic failure before commit')
    monkeypatch.setattr(MySqlServiceStartRepository,'complete',fail)
    with pytest.raises(RuntimeError,match='synthetic failure before commit'):
        submit(http,case,staff[0],segments[0])
    assert rows('SELECT * FROM orders WHERE case_no=%s',(case,))==before
    assert rows('SELECT * FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity',(case,))==finance
    assert not rows('SELECT * FROM scheduling_generations WHERE case_no=%s',(case,))
    assert not rows('SELECT * FROM scheduling_service_start_requests WHERE case_no=%s',(case,))


def test_pending_single_invitation_redacted_and_cancelled_if_group_url_changes(http):
    from domains.line.identities import LineDeliveryTaskId
    from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
    from subsystems.line.delivery_worker import service_start_delivery_is_current
    case,staff,segments=seed_case(http)
    item=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    item,_=action(http,item,'inquire',staff_id=staff[1][0],start_date='2027-01-05',end_date='2027-02-03')
    willingness(item,staff[1],'willing')
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    item,_=action(http,item,'invite')
    identity=rows('SELECT invitation_identity FROM scheduling_service_start_candidates WHERE id=(SELECT selected_candidate_id FROM scheduling_service_start_requests WHERE id=%s)',(item['request_id'],))[0]['invitation_identity']
    task_id=rows("SELECT id FROM line_delivery_tasks WHERE source_aggregate_type='service_start_invitation' AND source_aggregate_identity=%s",(identity,))[0]['id']
    c=mysql_adapter.get_connection()
    try:
        with LineMySqlUnitOfWork(c) as unit:
            task=unit.delivery_tasks.get(LineDeliveryTaskId(task_id))
            assert unit.service_starts.delivery_is_current(task)
            assert 'https://line.me/' not in str(unit.delivery_tasks.get_admin(LineDeliveryTaskId(task_id)))
            c.rollback()
        # Simulate the canonical group's URL changing after work was queued.
        write("UPDATE line_order_group_bindings SET invitation_url=%s,aggregate_version=aggregate_version+1 WHERE case_no=%s",('https://line.me/R/ti/g/changed-synthetic-'+case,case))
        with LineMySqlUnitOfWork(c) as unit:
            assert not service_start_delivery_is_current(unit,task)
        assert rows('SELECT processing_status FROM line_delivery_tasks WHERE id=%s',(task_id,))[0]['processing_status']=='cancelled'
    finally:c.close()
    assert not rows('SELECT * FROM scheduling_generations WHERE case_no=%s',(case,))


def test_old_request_no_longer_appears_in_todos_or_accepts_candidate_commands(http):
    case,staff,segments=seed_case(http)
    old=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    new=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    todo=checked(http.get('/api/v1/scheduling/service-start/todos',params={'case_no':case}))
    assert [r['request_id'] for r in todo['items']]==[new['request_id']]
    assert http.post(f"/api/v1/scheduling/service-start/{old['request_id']}/inquire",json={'expected_version':old['version'],'idempotency_key':uuid4().hex,'staff_id':staff[1][0],'start_date':'2027-01-05','end_date':'2027-02-03'}).status_code==409


def test_multisegment_substitute_saved_before_peer_response_applies_together(http):
    case,staff,segments=seed_case(http,count=2)
    item=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    item,_=action(http,item,'inquire',staff_id=staff[2][0],start_date='2027-01-05',end_date='2027-02-03')
    willingness(item,staff[2],'willing');joined(case,staff[2])
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    waiting,_=action(http,item,'dates',start_date='2027-01-05')
    assert waiting['status']=='awaiting_peers'
    assert not rows('SELECT * FROM scheduling_generations WHERE case_no=%s',(case,))
    result=checked(submit(http,case,staff[1],segments[1],start='2027-02-04')[0])
    assert result['status']=='applied'
    assert {a['staff_id'] for a in result['result']['assignments']}=={staff[2][0],staff[1][0]}
    assert result['result']['first_payment_due_date']=='2027-01-05'
    assert checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))['status']=='applied'


def test_pre_service_full_period_replacement_is_one_successor_assignment(http):
    case,staff,segments=seed_case(http)
    checked(submit(http,case,staff[0],segments[0])[0])
    item=checked(submit(http,case,staff[0],segments[0],decision='declined')[0])
    item,_=action(http,item,'inquire',staff_id=staff[1][0],start_date='2027-01-05',end_date='2027-02-03')
    willingness(item,staff[1],'willing');joined(case,staff[1])
    item=checked(http.get(f"/api/v1/scheduling/service-start/{item['request_id']}"))
    result,_=action(http,item,'dates',start_date='2027-01-05')
    assert result['status']=='applied'
    assert len(result['result']['assignments'])==1
    assert result['result']['assignments'][0]['staff_id']==staff[1][0]
    assert len(result['result']['assignments'][0]['service_dates'])==30
    assert result['result']['first_payment_due_date']=='2027-01-05'

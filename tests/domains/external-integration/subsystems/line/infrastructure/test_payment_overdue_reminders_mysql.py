"""Real local owner/API/queue transactions. Every provider is a task-scoped fake."""
from dataclasses import asdict
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
import json,os,runpy
import pytest
from fastapi import HTTPException
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from domains.line.identities import LineDeliveryTaskId,LineProviderMessageId
from subsystems.line.delivery_contracts import ClaimLineDeliveryTasksQuery,LineProviderOutcome,LineProviderOutcomeType
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.payment_overdue_reminders import PaymentOverdueReminderApplication,SOURCE_TYPE

support=runpy.run_path('tests/domains/external-integration/subsystems/line/infrastructure/test_service_start_day_mysql.py')
http=support['http'];rows,write,checked=support['rows'],support['write'],support['checked']
pytestmark=pytest.mark.skipif(not os.getenv('SERVICE_START_TEST_DB'),reason='explicit synthetic localhost DB required')
NOW=datetime(2032,5,10,16,tzinfo=timezone.utc)
DAY=date(2032,5,11)


@pytest.fixture(autouse=True)
def route(http):
    from api.routes import line_payment_overdue_reminders
    from api.dependencies.payment_overdue_reminders import get_payment_overdue_reminders
    if not getattr(http.app.state,'overdue_registered',False):
        http.app.include_router(line_payment_overdue_reminders.router);http.app.state.overdue_registered=True
    app=PaymentOverdueReminderApplication(open_line_unit_of_work,lambda:NOW)
    http.app.dependency_overrides[get_payment_overdue_reminders]=lambda:app
    yield
    http.app.dependency_overrides.pop(get_payment_overdue_reminders,None)


def prepare(http,*,days=30,bound=True,group=True):
    # Actual intake writer creates all stage amounts; only clock/binding fixtures are synthetic.
    case='116'+str(rows('SELECT COUNT(*) n FROM orders')[0]['n']+1).zfill(6)
    client=write("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic overdue','一般市民','連續服務','2032-05-01')",(case,))
    write("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,'2032-05-11',%s,8,0,'08:00:00','17:00:00',0)",(case,client,days))
    url=f'/api/v1/orders/{case}/intake-completion'
    plan=checked(http.post(url+'/preview',json={}))
    checked(http.post(url+'/apply',json={'expected_lifecycle_version':plan['lifecycle_version'],'preview_fingerprint':plan['preview_fingerprint'],'reason':''},headers={'Idempotency-Key':case+':init'}))
    user='U'+uuid4().hex
    if bound:
        write('UPDATE clients SET line_user_id=%s WHERE id=%s',(user,client))
        write("INSERT INTO line_platform_users(line_user_id,friend_status) VALUES (%s,'active')",(user,))
        write("INSERT INTO line_identity_role_bindings(line_user_id,subject_type,binding_status,subject_reference) VALUES (%s,'customer','bound',%s)",(user,str(client)))
    gid='C'+uuid4().hex
    if group:
        write("INSERT INTO line_order_group_bindings(case_no,group_id,binding_status,aggregate_version) VALUES (%s,%s,'active',1)",(case,gid))
    for stage,day in [('deposit',DAY-timedelta(days=1)),('first',DAY),('second',DAY+timedelta(days=15))]:
        write('UPDATE client_obligations SET due_date=%s WHERE case_no=%s AND obligation_type=%s',(day,case,stage))
    return case,user,gid


def listing(http,case):
    result=checked(http.get('/api/v1/line/payment-overdue-reminders',params={'page_size':100}))
    # Synthetic database may contain older tasks; use bounded pagination for exact case evidence.
    values=result['items']
    for page in range(2,(result['total']+99)//100+1):
        values+=checked(http.get('/api/v1/line/payment-overdue-reminders',params={'page':page,'page_size':100}))['items']
    return [item for item in values if item['payment']['case_no']==case]


def send(http,item,key=None):
    return http.post('/api/v1/line/payment-overdue-reminders/send',json={**item['payment'],'idempotency_key':key or uuid4().hex})


def tasks(case):
    return rows('SELECT t.* FROM line_delivery_tasks t JOIN client_obligations o ON o.obligation_identity=t.source_aggregate_identity '
        'WHERE t.source_aggregate_type=%s AND o.case_no=%s ORDER BY t.id',(SOURCE_TYPE,case))


def deliver(identity):
    calls=[]
    class Worker(LineDeliveryWorker):
        def _claim(self):
            with open_line_unit_of_work() as unit:
                task=unit.delivery_tasks.claim_specific(LineDeliveryTaskId(identity),ClaimLineDeliveryTasksQuery(self._worker_identity,self._now(),1));unit.commit()
            return (task,) if task else ()
    def fake(request):
        calls.append(request)
        return LineProviderOutcome(LineProviderOutcomeType.SUCCESS,provider_message_id=LineProviderMessageId('synthetic-overdue-'+uuid4().hex))
    Worker(open_line_unit_of_work,SimpleNamespace(send=fake),'synthetic-overdue',lambda:NOW,batch_size=1).run_once()
    return calls


def all_due(case):
    write("UPDATE client_obligations SET due_date=%s WHERE case_no=%s AND obligation_type IN ('deposit','first','second')",(DAY-timedelta(days=1),case))


def test_only_deposit_overdue_never_exposes_future_stage_amounts_and_queries_do_not_write(http):
    case,user,_=prepare(http)
    before=rows('SELECT COUNT(*) n FROM line_delivery_tasks')[0]['n']
    items=listing(http,case);assert [item['payment']['payment_stage'] for item in items]==['deposit']
    item=items[0];assert item['overdue_days']==1 and item['recipient_label']=='客戶私人聊天室'
    assert rows('SELECT COUNT(*) n FROM line_delivery_tasks')[0]['n']==before
    result=checked(send(http,item,'key-'+case));assert checked(send(http,item,'key-'+case))==result
    work=tasks(case);assert len(work)==1 and work[0]['recipient_identity']==user and work[0]['recipient_type']=='user'
    copy=json.loads(work[0]['payload_snapshot'])['text']
    assert '訂金' in copy and '第一期' not in copy and '第二期' not in copy
    assert f"{item['payment']['remaining_amount_ntd']:,}" in copy
    assert listing(http,case)[0]['last_reminder']['status']=='pending'
    assert len(deliver(result['task_id']))==1
    assert listing(http,case)[0]['last_reminder']['status']=='sent'


def test_all_stages_have_separate_tasks_amounts_and_recipients(http):
    case,user,group=prepare(http);all_due(case)
    items=listing(http,case);assert {x['payment']['payment_stage'] for x in items}=={'deposit','first','second'}
    for item in items:
        result=checked(send(http,item));calls=deliver(result['task_id']);assert len(calls)==1
        request=calls[0];stage=item['payment']['payment_stage']
        assert request.recipient.identity.value==(user if stage=='deposit' else group)
        assert request.recipient.recipient_type.value==('user' if stage=='deposit' else 'group')
        assert f"{item['payment']['remaining_amount_ntd']:,}" in json.loads(request.payload_json)['text']
    assert len(tasks(case))==3


@pytest.mark.parametrize('change',['amount','date','stage','binding','group'])
def test_provider_gate_never_sends_old_amount_date_stage_or_recipient(http,change):
    case,_,_=prepare(http);all_due(case)
    stage='first' if change=='group' else 'deposit'
    item=next(x for x in listing(http,case) if x['payment']['payment_stage']==stage)
    work=checked(send(http,item));identity=item['payment']['obligation_identity']
    if change=='amount':write('UPDATE client_obligations SET amount_due_ntd=amount_due_ntd-1 WHERE obligation_identity=%s',(identity,))
    elif change=='date':write('UPDATE client_obligations SET due_date=%s WHERE obligation_identity=%s',(DAY,identity))
    elif change=='stage':write("UPDATE client_obligations SET obligation_type='adjustment' WHERE obligation_identity=%s",(identity,))
    elif change=='binding':write("UPDATE line_identity_role_bindings SET binding_status='revoked' WHERE line_user_id=(SELECT line_user_id FROM clients WHERE id=(SELECT client_id FROM orders WHERE case_no=%s))",(case,))
    else:write('UPDATE line_order_group_bindings SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,))
    assert deliver(work['task_id'])==[]
    assert tasks(case)[0]['processing_status']=='cancelled'


def test_formal_bank_receipt_removes_only_deposit_todo_and_cancels_queued_notice(http):
    case,_,_=prepare(http);all_due(case)
    original=listing(http,case);item=next(x for x in original if x['payment']['payment_stage']=='deposit')
    work=checked(send(http,item))
    support['existing']['h']['bank'](http,case,item['payment']['remaining_amount_ntd'],1)
    remaining=listing(http,case)
    assert {x['payment']['payment_stage'] for x in remaining}=={'first','second'}
    assert {x['payment']['payment_stage']:x['payment']['remaining_amount_ntd'] for x in remaining}=={
        x['payment']['payment_stage']:x['payment']['remaining_amount_ntd'] for x in original if x['payment']['payment_stage']!='deposit'}
    assert send(http,item).status_code==409
    assert not deliver(work['task_id'])


def test_missing_customer_or_group_retains_todo_without_fallback(http):
    case,_,_=prepare(http,bound=False,group=False);all_due(case)
    items=listing(http,case);assert len(items)==3 and all(not x['can_send'] for x in items)
    assert {x['unavailable_reason'] for x in items}=={'尚未綁定客戶 LINE','尚無可用案件群組'}
    for item in items:assert send(http,item).status_code==409
    assert not tasks(case)


def test_formal_receipts_clear_first_then_second_without_mixing_balances(http):
    case,_,_=prepare(http);all_due(case)
    original={item['payment']['payment_stage']:item for item in listing(http,case)}
    bank=support['existing']['h']['bank']
    bank(http,case,original['deposit']['payment']['remaining_amount_ntd'],1)
    bank(http,case,original['first']['payment']['remaining_amount_ntd'],2)
    remaining=listing(http,case)
    assert len(remaining)==1 and remaining[0]['payment']['payment_stage']=='second'
    assert remaining[0]['payment']['remaining_amount_ntd']==original['second']['payment']['remaining_amount_ntd']
    queued=checked(send(http,remaining[0]))
    bank(http,case,remaining[0]['payment']['remaining_amount_ntd'],3)
    assert listing(http,case)==[]
    assert not deliver(queued['task_id'])


def test_forged_stage_and_amount_are_conflicts_and_authorization_is_required(http):
    from api.dependencies import admin_auth
    from subsystems.access.authentication_session import AdminPrincipal
    case,_,_=prepare(http);item=listing(http,case)[0]
    assert send(http,{**item,'payment':{**item['payment'],'payment_stage':'first'}}).status_code==409
    assert send(http,{**item,'payment':{**item['payment'],'remaining_amount_ntd':1}}).status_code==409
    original=http.app.dependency_overrides[admin_auth.require_admin]
    try:
        http.app.dependency_overrides[admin_auth.require_admin]=lambda:AdminPrincipal(1,'union','工會','line_manager')
        assert http.get('/api/v1/line/payment-overdue-reminders').status_code==200
        assert send(http,item).status_code==200
        http.app.dependency_overrides[admin_auth.require_admin]=lambda:AdminPrincipal(2,'viewer','檢視者','read_only')
        assert http.get('/api/v1/line/payment-overdue-reminders').status_code==403
        assert send(http,item).status_code==403
    finally:http.app.dependency_overrides[admin_auth.require_admin]=original


def test_no_second_payment_and_due_today_do_not_create_todo(http):
    case,_,_=prepare(http,days=10)
    write('UPDATE client_obligations SET due_date=%s WHERE case_no=%s',(DAY,case))
    assert not listing(http,case)
    all_due(case)
    assert 'second' not in {x['payment']['payment_stage'] for x in listing(http,case)}

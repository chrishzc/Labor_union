"""Shared notification read contract and thin command/auth boundaries."""
from datetime import UTC, datetime
from types import SimpleNamespace
from domains.line.delivery import LineDeliveryStatus
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from api.dependencies.admin_auth import require_admin, require_line_matching_sender
from api.routes import notification_tasks as query, notification_task_actions as actions, line_mobile_admin
from api.schemas.notification_tasks import NotificationSource, NotificationPage, NotificationItem
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.deposit_notifications import DepositNotificationConflict

PRINCIPAL=AdminPrincipal(1,'synthetic-notifications','Synthetic','system_admin')


def test_first_receipt_notification_is_a_stable_internal_todo_and_never_sends(monkeypatch):
    from subsystems.line.payment_receipt_notifications import PaymentReceiptSnapshot,PaymentReceiptTodo
    payment=PaymentReceiptSnapshot('CASE-FIRST','first','a'*64,12000,2,'source')
    sent=[False];calls=[]
    def pending(page,size):
        calls.append((page,size));return ((),0) if sent[0] else ((PaymentReceiptTodo(payment,True,None,None),),1)
    monkeypatch.setattr(query,'get_payment_receipt_notifications',lambda:SimpleNamespace(list=pending,send=lambda *_:pytest.fail('notification query must not send')))
    first=query.query_source(NotificationSource.RECEIPT,0,PRINCIPAL)
    again=query.query_source(NotificationSource.RECEIPT,0,PRINCIPAL)
    assert first.items[0].id==again.items[0].id
    assert first.items[0].title=='第一期款已入帳，待確認通知'
    assert first.items[0].receipt.payment_stage=='first'
    assert '官方帳號' in first.items[0].reason and '已於官方帳號發送／標記已通知' in first.items[0].reason and first.items[0].case_no=='CASE-FIRST'
    sent[0]=True
    assert query.query_source(NotificationSource.RECEIPT,0,PRINCIPAL).items==[]


def test_customer_service_notification_is_retired_on_desktop_and_mobile(monkeypatch):
    source = NotificationSource.CUSTOMER_SERVICE
    monkeypatch.setattr(query, 'has_required_capability', lambda principal, cap: True)
    monkeypatch.setattr(query, '_read_source', lambda *args: pytest.fail('retired source read an owner'))
    verified = []

    def mobile_context(token, capability):
        verified.append((token, capability))
        return PRINCIPAL, None

    monkeypatch.setattr(line_mobile_admin, '_mobile_admin_context', mobile_context)
    for is_mobile in (False, True):
        assert source not in {row.source for row in query._catalog(PRINCIPAL, mobile=is_mobile)}

    with pytest.raises(HTTPException) as desktop:
        query.source_page(source, 0, PRINCIPAL)
    with pytest.raises(HTTPException) as mobile:
        query.mobile_source_page(source, query.MobileNotificationQuery(line_id_token='synthetic'))

    assert desktop.value.status_code == mobile.value.status_code == 410
    assert desktop.value.detail['error']['code'] == 'customer_service_retired'
    assert mobile.value.detail['error']['code'] == 'customer_service_retired'
    assert verified == [('synthetic', query.Cap.CUSTOMER_SERVICE_READ)]


def test_notification_failures_reuse_bounded_cursor_and_fresh_owner_without_writes(monkeypatch):
    from contextlib import nullcontext
    from datetime import datetime, UTC
    from subsystems.line.notification_failure_current_fact import (
        LineNotificationFailedSourceFact, evaluate_line_notification_failure_current_fact,
    )
    calls=[];active=True;complete=True
    projections=tuple(SimpleNamespace(issue_key='ci_'+format(i,'064x'),
        candidate=SimpleNamespace(definition_code='LINE-006',subject_identity={'case_no':f'CASE-{i}','notification_reason':'recipient_unavailable'},blocking=False,severity='warning'),
        episode_started_at=datetime(2026,10,26,tzinfo=UTC),last_verified_at=datetime(2026,10,26,tzinfo=UTC)) for i in range(1,27))
    def owner(expected):
        from dataclasses import replace
        result=evaluate_line_notification_failure_current_fact(expected,
            (LineNotificationFailedSourceFact(11,active,True,()),),owner_version=1,authoritative_complete=complete)
        return replace(result,related_task_ids=(7,),source_task_ids=((11,(7,)),))
    def page(request,after,limit):
        calls.append((request,after,limit));return projections if after is None else ()
    unit=SimpleNamespace(anomaly_rechecks=SimpleNamespace(query_current_page=page),
        notification_rules=SimpleNamespace(current_failure_fact=owner,list_case_timeline=lambda _:({'source_event_id':11,'delivery_task_id':7,'recipient_identity':'must-not-leak'},)),
        commit=lambda:pytest.fail('query must not commit'))
    monkeypatch.setattr(query,'open_line_unit_of_work',lambda:nullcontext(unit))
    first=query.query_source(NotificationSource.NOTIFICATION_FAILURE,0,PRINCIPAL)
    assert len(first.items)==25 and isinstance(first.next_cursor,str) and calls[0][2]==26
    assert first.items[0].failure.related_task_ids==[7]
    assert 'must-not-leak' not in first.model_dump_json()
    query.query_source(NotificationSource.NOTIFICATION_FAILURE,first.next_cursor,PRINCIPAL)
    assert calls[-1][1][-1]==projections[24].issue_key
    active=False
    assert query.query_source(NotificationSource.NOTIFICATION_FAILURE,0,PRINCIPAL).items==[]
    active=True;complete=False
    with pytest.raises(HTTPException) as unavailable:query.query_source(NotificationSource.NOTIFICATION_FAILURE,0,PRINCIPAL)
    assert unavailable.value.status_code==503


def test_notification_failure_repair_keeps_todo_and_pending_replay_blocks_duplicate_send(monkeypatch):
    from contextlib import nullcontext
    from subsystems.line.notification_failure_current_fact import (
        LineNotificationFailedSourceFact, LineNotificationReplaySuccessorFact, evaluate_line_notification_failure_current_fact,
    )
    ready=False;pending=False;work_status=None
    projection=SimpleNamespace(candidate=SimpleNamespace(definition_code='LINE-006',subject_identity={'case_no':'CASE-1','notification_reason':'recipient_unavailable'}))
    def owner(expected):
        successors=(LineNotificationReplaySuccessorFact(22,True,True,('processing',)),) if pending else ()
        from dataclasses import replace
        result=evaluate_line_notification_failure_current_fact(expected,(LineNotificationFailedSourceFact(11,True,True,successors),),owner_version=1,authoritative_complete=True)
        return replace(result,related_task_ids=(99,) if work_status else (),source_task_ids=((11,(99,) if work_status else ()),))
    unit=SimpleNamespace(anomaly_rechecks=SimpleNamespace(query_current=lambda _:projection),notification_rules=SimpleNamespace(
        current_failure_fact=owner,list_case_timeline=lambda _:({'source_event_id':11,'event_code':'client.second_payment_due','recipient_identity':'must-not-leak'},),
        preview_manual_replay=lambda _: {'can_replay':ready,'unavailable_reason':None if ready else 'recipient_unavailable'}),
        delivery_tasks=SimpleNamespace(get=lambda _:SimpleNamespace(status=SimpleNamespace(value=work_status)), get_admin=lambda _:SimpleNamespace(status=LineDeliveryStatus(work_status),error_code=None)))
    monkeypatch.setattr(actions,'open_line_unit_of_work',lambda:nullcontext(unit))
    issue='ci_'+'1'*64
    assert not actions.notification_failure_detail(issue,PRINCIPAL).data['sources'][0]['can_replay']
    ready=True
    assert actions.notification_failure_detail(issue,PRINCIPAL).data['sources'][0]['can_replay']
    pending=True
    view=actions.notification_failure_detail(issue,PRINCIPAL).data
    assert not view['sources'][0]['can_replay'] and '尚未完成' in view['sources'][0]['unavailable_reason']
    assert 'must-not-leak' not in str(view)
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda *args:(PRINCIPAL,None))
    assert actions.mobile_notification_failure_detail(issue,actions.MobileAuth(line_id_token='synthetic')).data==view
    pending=False;work_status='failed'
    assert not actions.notification_failure_detail(issue,PRINCIPAL).data['sources'][0]['can_replay']
    work_status='cancelled'
    assert actions.notification_failure_detail(issue,PRINCIPAL).data['sources'][0]['can_replay']


def test_mobile_notification_replay_keeps_original_writer_and_requires_current_line_auth(monkeypatch):
    from api.routes import line_notification_rules
    seen=[]
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda token,cap:(seen.append(cap) or (PRINCIPAL,None)))
    monkeypatch.setattr(line_notification_rules,'apply_notification_manual_replay',lambda identity,body,request,principal:(identity,body.idempotency_key,principal.id))
    body=actions.MobileNotificationReplay(line_id_token='synthetic',reason='',idempotency_key='same-intent',correlation_id='same-intent')
    assert actions.mobile_notification_replay(11,body,None)==(11,'same-intent',1)
    assert seen==[actions.LineCapability.CONFIG_MANAGE]
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda *args:(_ for _ in ()).throw(HTTPException(403,'unbound')))
    with pytest.raises(HTTPException):actions.mobile_notification_replay(11,body,None)


def test_original_replay_preview_checks_eligibility_without_writing():
    from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository, LineNotificationManualReplayValidationError
    repository=MySqlLineNotificationRepository(None)
    repository._source_event=lambda _:SimpleNamespace(event_code='client.second_payment_due',historical_silent=False)
    repository._current_configuration=lambda _: (1,{'rules':[{'event_code':'client.second_payment_due'}]})
    repository._validate_manual_replay=lambda *args:(_ for _ in ()).throw(LineNotificationManualReplayValidationError('recipient_unavailable'))
    assert repository.preview_manual_replay(11)['can_replay'] is False
    repository._validate_manual_replay=lambda *args:None
    assert repository.preview_manual_replay(11)['can_replay'] is True


def test_replay_uses_original_notification_policy_and_keeps_immutable_replay_lineage(monkeypatch):
    from datetime import datetime, UTC
    from infrastructure.mysql import line_notification_repository as repository_module
    from subsystems.line.notification_policy import NotificationSourceEvent
    repo=repository_module.MySqlLineNotificationRepository(None)
    repo._source_closed=lambda _:False
    original=NotificationSourceEvent('original','order.service_completed',False,{'case_no':'CASE-1'},'orders','order','CASE-1',1,datetime.now(UTC))
    replay=NotificationSourceEvent('manual-replay:11:same-intent',original.event_code,False,original.facts,'manual_replay','order','CASE-1',1,datetime.now(UTC))
    checked=[];intents=[]
    repo._source_event=lambda identity:original if identity==11 else None
    repo._rule_source_currently_applicable=lambda event,rule,**kwargs:(checked.append(('policy',event.source_domain)) or event.source_domain=='orders')
    repo._resolve_recipient=lambda selector,facts,**kwargs:(checked.append(('recipient',kwargs['source_domain'])) or 'original-group')
    repo._record_decision=lambda *args:71
    repo._create_intent_if_absent=lambda *args:intents.append(args[-1])
    monkeypatch.setattr(repository_module,'render_message_template',lambda *args:SimpleNamespace(payload_json='{}'))
    monkeypatch.setattr(repository_module,'_template_variables',lambda *args:{})
    monkeypatch.setattr(repository_module,'schedule_notification_occurrences',lambda **kwargs:(SimpleNamespace(number=1,scheduled_at=datetime.now(UTC)),))
    repo._project_rule(42,replay,1,{'id':'current-rule','recipient_selector':'case_group','enabled':True,'predicates':[],'template_id':'current-template','schedule':{'kind':'immediate'}}, {},1)
    assert checked==[('policy','orders'),('recipient','orders')]
    assert intents==[replay] and intents[0].source_domain=='manual_replay'


def test_existing_public_replay_preview_preserves_its_closed_response(monkeypatch):
    from api.routes import line_notification_rules
    preview={'source_event_id':11,'event_code':'order.service_completed','historical_silent':False,'matching_rule_count':1,'will_create_new_immutable_source':True}
    monkeypatch.setattr(line_notification_rules,'get_line_notification_manual_replay_application',lambda:SimpleNamespace(preview=lambda *args:{**preview,'can_replay':True,'unavailable_reason':None}))
    result=line_notification_rules.preview_notification_manual_replay(11,PRINCIPAL)
    assert result.data.model_dump()==preview


def test_pending_manual_replay_is_a_typed_state_conflict(monkeypatch):
    from api.routes import line_notification_rules
    from infrastructure.mysql.line_notification_repository import LineNotificationManualReplayValidationError
    monkeypatch.setattr(line_notification_rules,'get_line_notification_manual_replay_application',lambda:SimpleNamespace(
        apply=lambda *args:(_ for _ in ()).throw(LineNotificationManualReplayValidationError('notification_replay_in_progress'))))
    body=line_notification_rules.ApplyLineNotificationManualReplayRequest(reason='',idempotency_key='same',correlation_id='same')
    with pytest.raises(HTTPException) as conflict:line_notification_rules.apply_notification_manual_replay(11,body,None,PRINCIPAL)
    assert conflict.value.status_code==409
    assert conflict.value.detail['error']['code']=='notification_replay_in_progress'


@pytest.mark.parametrize('source',[source for source in NotificationSource if source not in {
    NotificationSource.LEAVE, NotificationSource.LOG, NotificationSource.STAFF_PROFILE, NotificationSource.IMPORT_FIELDS,
    NotificationSource.CUSTOMER_SERVICE,
}])
def test_desktop_and_verified_liff_use_same_projection_and_cursor(monkeypatch,source):
    cursor='original-owner-cursor' if source == NotificationSource.NOTIFICATION_FAILURE else 1
    calls=[]
    expected=NotificationPage(items=[NotificationItem(id=f'{source}:1',source=source,group=query.SOURCES[source][1],
        title='Synthetic task',summary='Pending owner result',reason='Existing owner query')],total=51,next_cursor=2)
    def read(kind,cursor,principal):
        calls.append((kind,cursor,principal.id));return expected
    monkeypatch.setattr(query,'_read_source',read)
    verified=[]
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda token,cap=None:(verified.append((token,cap)) or (PRINCIPAL,None)))
    app=FastAPI();app.include_router(query.router);app.dependency_overrides[require_admin]=lambda:PRINCIPAL
    with TestClient(app) as client:
        desktop=client.get('/api/v1/line/notification-tasks/'+source,params={'cursor':cursor})
        mobile=client.post('/api/v1/line/mobile-admin/notification-tasks/'+source,json={'line_id_token':'synthetic-verified-token','cursor':cursor})
    assert desktop.status_code==mobile.status_code==200
    assert desktop.json()['data']==mobile.json()['data']
    assert calls==[(source,cursor,1),(source,cursor,1)]
    assert verified==[('synthetic-verified-token',query.SOURCES[source][2])]


def test_staff_profile_review_reminder_is_desktop_only(monkeypatch):
    monkeypatch.setattr(query, 'has_required_capability', lambda principal, cap: cap == 'data_browser.write')
    source = NotificationSource.STAFF_PROFILE
    assert source in {item.source for item in query._catalog(PRINCIPAL)}
    assert source not in {item.source for item in query._catalog(PRINCIPAL, mobile=True)}
    with pytest.raises(HTTPException) as failure:
        query.mobile_source_page(source, query.MobileNotificationQuery(line_id_token='synthetic'))
    assert failure.value.status_code == 404


def test_import_fields_projects_current_case_issues_and_preserves_empty_candidate_page(monkeypatch):
    from domains.case_import.import_field_issues import ImportFieldIssue
    from subsystems.case_import.current_import_field_issues import CurrentImportFieldIssuesQuery

    first = ImportFieldIssue('client_beclass', 'client_profile', 'email', 'Email',
                             'client_field_invalid:Email', 'Email來源資料有誤，請補正此欄位。')
    second = ImportFieldIssue('hcm', 'order_terms', 'service_days', '希望服務天數',
                              'field_invalid:希望服務天數', '希望服務天數尚未完成。')
    current = {'CASE-1': (first, second)}
    candidates = ('CASE-1', *(f'CASE-{index}' for index in range(2, query.SIZE + 1)), 'CASE-NEXT')
    current['CASE-NEXT'] = (second,)
    repository = SimpleNamespace(
        candidate_case_nos=lambda *, offset, limit, case_no: candidates[offset:offset + limit],
        query_case=lambda case_no: current.get(case_no, ()),
    )
    closed = []
    monkeypatch.setattr(query, 'get_connection', lambda: SimpleNamespace(close=lambda: closed.append(True)))
    monkeypatch.setattr(query, 'build_import_field_issues_query', lambda _: CurrentImportFieldIssuesQuery(repository))
    monkeypatch.setattr(query, 'has_required_capability', lambda _, cap: cap == 'data_browser.read')
    app = FastAPI()
    app.include_router(query.router)
    app.dependency_overrides[require_admin] = lambda: PRINCIPAL

    with TestClient(app) as client:
        source_path = '/api/v1/line/notification-tasks/import_fields'
        page = client.get(source_path).json()['data']
        assert len(page['items']) == 1
        todo = page['items'][0]
        assert (todo['id'], todo['case_no'], todo['group']) == ('import_fields:CASE-1', 'CASE-1', 'review')
        assert todo['import_field_issues'] == [first.as_dict(), second.as_dict()]
        assert todo['recipient'] is None and todo['message'] is None and todo['person'] == ''
        assert page['total'] is None and page['next_cursor'] == 1

        current['CASE-1'] = (second,)
        partial = client.get(source_path).json()['data']['items']
        assert len(partial) == 1 and partial[0]['id'] == todo['id']
        assert partial[0]['import_field_issues'] == [second.as_dict()]

        del current['CASE-1']
        assert client.get(source_path).json()['data'] == {'items': [], 'total': None, 'next_cursor': 1}
        next_page = client.get(source_path, params={'cursor': 1}).json()['data']
        assert [item['id'] for item in next_page['items']] == ['import_fields:CASE-NEXT']
        assert next_page['next_cursor'] is None
    assert len(closed) == 4


def test_import_fields_is_catalogued_for_desktop_roster_readers_only(monkeypatch):
    allowed = {'data_browser.read'}
    monkeypatch.setattr(query, 'has_required_capability', lambda _, cap: cap in allowed)
    monkeypatch.setattr(line_mobile_admin, '_mobile_admin_context', lambda *_: (PRINCIPAL, None))
    monkeypatch.setattr(query, 'get_connection', lambda: pytest.fail('inaccessible source opened a connection'))
    app = FastAPI()
    app.include_router(query.router)
    app.dependency_overrides[require_admin] = lambda: PRINCIPAL

    with TestClient(app) as client:
        desktop = '/api/v1/line/notification-tasks'
        mobile = '/api/v1/line/mobile-admin/notification-tasks'
        body = {'line_id_token': 'synthetic-token'}
        descriptor = {'source': 'import_fields', 'label': '進件資料待修正', 'group': 'review',
                      'category_id': 'applications', 'category_label': '申請與資料'}
        assert descriptor in client.get(desktop).json()['data']
        assert descriptor not in client.post(mobile, json=body).json()['data']
        assert client.post(f'{mobile}/import_fields', json=body).status_code == 404
        allowed.clear()
        assert descriptor not in client.get(desktop).json()['data']
        response = client.get(f'{desktop}/import_fields')
        assert response.status_code == 403
        assert response.json()['detail']['error']['code'] == 'notification_source_forbidden'


def test_import_fields_owner_error_closes_connection_and_returns_typed_unavailable(monkeypatch):
    closed = []
    monkeypatch.setattr(query, 'has_required_capability', lambda _, cap: cap == 'data_browser.read')
    monkeypatch.setattr(query, 'get_connection', lambda: SimpleNamespace(close=lambda: closed.append(True)))

    def fail(**_kwargs):
        raise RuntimeError('private raw owner error')

    monkeypatch.setattr(query, 'build_import_field_issues_query', lambda _: SimpleNamespace(query_page=fail))
    with pytest.raises(HTTPException) as failure:
        query.query_source(NotificationSource.IMPORT_FIELDS, 0, PRINCIPAL)
    assert failure.value.status_code == 503
    assert failure.value.detail['error']['code'] == 'notification_source_unavailable'
    assert failure.value.detail['error']['retryable'] is True
    assert 'private raw owner error' not in str(failure.value.detail)
    assert closed == [True]


def test_liff_unbound_admin_stops_before_any_pending_query(monkeypatch):
    def deny(*args):raise HTTPException(403,{'error':{'message':'此 LINE 尚未綁定目前有效的工會人員身分。'}})
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',deny)
    monkeypatch.setattr(query,'_read_source',lambda *args:pytest.fail('unbound identity reached query'))
    app=FastAPI();app.include_router(query.router)
    with TestClient(app,headers={'Authorization':'Bearer desktop-session-is-not-liff'}) as client:
        response=client.post('/api/v1/line/mobile-admin/notification-tasks/overdue',json={'line_id_token':'unbound'})
    assert response.status_code==403


def test_source_failure_is_closed_error_instead_of_zero_or_sql_leak(monkeypatch):
    def fail(*args):raise RuntimeError('SELECT secret FROM private_storage')
    monkeypatch.setattr(query,'_read_source',fail)
    with pytest.raises(HTTPException) as failure:query.query_source(NotificationSource.DEPOSIT,0,PRINCIPAL)
    assert failure.value.status_code==503
    assert 'SELECT' not in str(failure.value.detail)
    assert failure.value.detail['error']['retryable'] is True


def test_runtime_is_a_readonly_workbench_card_without_recipient_setup_todo(monkeypatch):
    monkeypatch.setattr(query,'get_connection',lambda:SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(query,'MySqlRuntimeMonitorRepository',lambda conn:SimpleNamespace(list_status=lambda:()))
    result=query._read_source(NotificationSource.RUNTIME,0,PRINCIPAL)
    assert result.total == 0 and result.items == []
    assert NotificationSource.RUNTIME not in [entry.source for entry in query._catalog(PRINCIPAL)]


def test_mobile_system_status_refresh_errors_and_late_responses_are_readonly():
    import subprocess
    script = r'''
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
import {Window} from './ui_react/node_modules/happy-dom/lib/index.js';
const html=fs.readFileSync('line/static/mobile_admin.html','utf8').replace(/\r\n/g,'\n');
const window=new Window();const document=window.document;
document.body.innerHTML=html.slice(html.indexOf('<body>')+6,html.indexOf('<script'));
const status=document.getElementById('systemStatus');
assert.equal(status.parentElement.id,'reviewPane');assert.equal(status.open,false);
assert(status.compareDocumentPosition(document.querySelector('.workbench-summary'))&4);
const requests=[];let resolve, reject;
const ctx=vm.createContext({document,Date,Object,Number,console,
 notificationText:(tag,value)=>{const element=document.createElement(tag);element.textContent=value;return element},
 postJson:(url,body)=>{requests.push([url,body]);return new Promise((ok,fail)=>{resolve=ok;reject=fail})}});
vm.runInContext("let target='staff_review';const studioPreview=false;",ctx);
vm.runInContext(html.slice(html.indexOf('const systemStatusNames ='),html.indexOf('\nfunction requireMatchingFollowupPage')),ctx);
const data={status:'healthy',worker_status:'healthy',pending_count:2,failed_count:0,last_checked_at:'2026-10-30T00:00:00Z',checks:[{label:'LINE 訊息發送服務',status:'healthy',checked_at:'2026-10-30T00:00:00Z'}]};
let loading=vm.runInContext('loadSystemStatus()',ctx);
assert.equal(document.getElementById('systemStatusLabel').textContent,'讀取中');
assert.equal(document.getElementById('refreshSystemStatus').disabled,true);
resolve(data);await loading;
assert.equal(status.dataset.status,'healthy');assert.equal(document.getElementById('systemPending').textContent,'2 件');
loading=vm.runInContext('loadSystemStatus()',ctx);reject(new Error('private SQL details'));await loading;
assert.equal(status.dataset.status,'unknown');assert.equal(document.getElementById('systemWorker').textContent,'—');
assert.equal(document.getElementById('systemStatusLabel').textContent,'無法讀取');
assert(!status.textContent.includes('private SQL'));
const old=vm.runInContext('loadSystemStatus()',ctx),oldResolve=resolve;
vm.runInContext("target='customer_service'",ctx);oldResolve(data);await old;
assert.notEqual(status.dataset.status,'healthy','late success changed a departed surface');
vm.runInContext("target='staff_review'",ctx);
loading=vm.runInContext('loadSystemStatus()',ctx);resolve({...data,checks:[{label:'invalid',status:'broken'}]});await loading;
assert.equal(document.getElementById('systemStatusLabel').textContent,'無法讀取');
assert(requests.every(([url,body])=>url.endsWith('/runtime/query')&&Object.keys(body).length===0));
assert.equal(document.getElementById('refreshSystemStatus').disabled,false);
await window.happyDOM.abort();
'''
    result = subprocess.run(['node','--input-type=module','-e',script], capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stderr


def test_recommendation_notifications_use_owner_page_and_plan_status_identity(monkeypatch):
    from contextlib import nullcontext
    from subsystems.scheduling.matching_notification_contracts import CustomerRecommendationFollowup

    records = (
        CustomerRecommendationFollowup('CASE-1', 1, 'response_failed', None, None, '回覆處理異常'),
        CustomerRecommendationFollowup('CASE-2', 2, 'awaiting_signing', None, None),
        CustomerRecommendationFollowup('CASE-3', 3, 'reply_reminder', None, None),
    )
    tail = tuple(CustomerRecommendationFollowup('CASE-4', plan, 'reply_reminder', None, None)
                 for plan in range(4, query.SIZE + 2))
    all_records = records + tail
    read_pages = []

    def followups(now, *, limit, offset):
        read_pages.append((limit, offset))
        return all_records[offset:offset + limit]

    owner = SimpleNamespace(customer_recommendation_followup_count=lambda now: len(all_records),
                            customer_recommendation_followups=followups)
    monkeypatch.setattr(query, 'open_line_unit_of_work', lambda: nullcontext(SimpleNamespace(matching_notifications=owner)))
    source = NotificationSource.RECOMMENDATION
    first = query.query_source(source, 0, PRINCIPAL)
    last = query.query_source(source, first.next_cursor, PRINCIPAL)

    assert read_pages == [(query.SIZE, 0), (query.SIZE, query.SIZE)]
    assert first.total == last.total == query.SIZE + 1
    assert first.next_cursor == 1 and last.next_cursor is None
    assert len(first.items) == query.SIZE and len(last.items) == 1
    assert [(item.id, item.case_no, item.tag) for item in first.items[:3]] == [
        ('recommendation:1:response_failed', 'CASE-1', '待跟進'),
        ('recommendation:2:awaiting_signing', 'CASE-2', '待簽約'),
        ('recommendation:3:reply_reminder', 'CASE-3', '待跟進'),
    ]
    assert first.items[0].summary == '回覆處理異常'
    assert all(item.source == source and item.reference_id is None for item in first.items + last.items)


def test_catalog_does_not_grant_inaccessible_source(monkeypatch):
    monkeypatch.setattr(query,'has_required_capability',lambda principal,cap:cap=='line.task.read')
    assert {r.source for r in query._catalog(PRINCIPAL)}=={NotificationSource.REGISTRATION,NotificationSource.DEPOSIT}
    with pytest.raises(HTTPException) as failure:query.query_source(NotificationSource.OVERDUE,0,PRINCIPAL)
    assert failure.value.status_code==403


def test_catalog_excludes_delivery_and_notification_failure_from_todo(monkeypatch):
    monkeypatch.setattr(query, 'has_required_capability', lambda principal, cap: True)
    desktop_sources = {r.source for r in query._catalog(PRINCIPAL)}
    mobile_sources = {r.source for r in query._catalog(PRINCIPAL, mobile=True)}
    for excluded in (NotificationSource.DELIVERY, NotificationSource.NOTIFICATION_FAILURE, NotificationSource.RUNTIME):
        assert excluded not in desktop_sources
        assert excluded not in mobile_sources


def test_work_categories_share_order_and_keep_legacy_groups(monkeypatch):
    monkeypatch.setattr(query, 'has_required_capability', lambda *_: True)
    expected = {
        'applications': ('申請與資料', 'review', ('registration', 'staff_profile', 'import_fields')),
        'identity': ('LINE 身分', 'review', ('identity', 'customer_binding', 'staff_binding')),
        'coordination': ('媒合、簽約與交接', 'review', ('followup', 'recommendation', 'service_start')),
        'payments': ('款項', 'reminder', ('deposit', 'payment_receipt', 'overdue')),
        'groups': ('案件群組', 'reminder', ('group',)),
    }
    desktop = [
        (source, category, label, group)
        for category, (label, group, sources) in expected.items()
        for source in sources
    ]
    for mobile in (False, True):
        catalog = query._catalog(PRINCIPAL, mobile=mobile)
        assert [(r.source.value, r.category_id, r.category_label, r.group) for r in catalog] == [
            row for row in desktop if not mobile or row[0] not in {'staff_profile', 'import_fields'}
        ]


def test_registration_todo_reads_pending_owner_page_without_personal_fields(monkeypatch):
    timestamp = datetime(2026, 11, 27, 3, 42, tzinfo=UTC)
    registrations = [
        (41, 'subsidy', 'pending'), (42, 'non_citizen', 'pending'),
        (43, 'non_citizen', 'approving'), (44, 'non_citizen', 'approved'),
        (45, 'non_citizen', 'rejected'), (46, 'non_citizen', 'expired'),
    ]
    calls = []

    def pending(*, after_id, limit):
        calls.append((after_id, limit))
        return tuple(
            SimpleNamespace(registration_id=number, registration_kind=kind, status=status, submitted_at_utc=timestamp)
            for number, kind, status in registrations if number > after_id
        )

    monkeypatch.setattr(query, 'SIZE', 6)
    monkeypatch.setattr(query, 'get_registration_review_query_application',
                        lambda: SimpleNamespace(pending_registrations=pending))
    result = query.query_source(NotificationSource.REGISTRATION, 40, PRINCIPAL)
    assert [(r.id, r.reference_id, r.title, r.time) for r in result.items] == [
        ('registration:41', 41, '服務登記待審核', timestamp.isoformat()),
        ('registration:42', 42, '非市民申請待審核', timestamp.isoformat()),
    ]
    assert all(not r.person and r.recipient is None and r.case_no is None and r.message is None
               for r in result.items)
    assert result.next_cursor == 46
    next_page = query.query_source(NotificationSource.REGISTRATION, result.next_cursor, PRINCIPAL)
    assert next_page.items == [] and next_page.next_cursor is None
    assert calls == [(40, 6), (46, 6)]


def test_registration_todo_unavailable_does_not_initialize_storage(monkeypatch):
    from api.dependencies import registration_applications
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError

    def unavailable(**_kwargs):
        raise ProvisionalRegistrationStorageError('registration_redis_initialization_required')

    staging = SimpleNamespace(
        pending=unavailable,
        ensure_initialized=unavailable,
        initialize=lambda *_args, **_kwargs: pytest.fail('notification query initialized staging'),
    )
    formal = SimpleNamespace(
        registration_id_high_water=lambda: pytest.fail('notification query read SQL high-water'),
    )
    monkeypatch.setattr(registration_applications, 'get_registration_staging_repository', lambda: staging)
    monkeypatch.setattr(registration_applications, 'get_line_identity_application', lambda: formal)
    getter = registration_applications.get_registration_review_query_application
    getter.cache_clear()
    try:
        with pytest.raises(HTTPException) as failure:
            query.query_source(NotificationSource.REGISTRATION, 0, PRINCIPAL)
    finally:
        getter.cache_clear()
    assert failure.value.status_code == 503
    assert failure.value.detail['error']['code'] == 'notification_source_unavailable'
    assert failure.value.detail['error']['retryable'] is True


@pytest.mark.parametrize('source,role,label', [
    (NotificationSource.CUSTOMER_BINDING,'customer','客戶'),
    (NotificationSource.STAFF_BINDING,'staff','月嫂'),
])
@pytest.mark.parametrize('can_manage', [True, False])
def test_binding_reminder_projection_keeps_owner_page_and_limits_dismissal(monkeypatch,source,role,label,can_manage):
    from api.routes import line_identity_management
    from subsystems.line.identity_management_contracts import LineIdentityBindingReminder,LineIdentityBindingReminderPage
    calls=[]
    def read(request):
        calls.append(request)
        cases = ('115000001', '115000002', None) if role == 'customer' else (None,)
        return LineIdentityBindingReminderPage(tuple(
            LineIdentityBindingReminder('7', '合成姓名', '0987654321', case) for case in cases
        ), 51)
    monkeypatch.setattr(line_identity_management,'_application',lambda:SimpleNamespace(binding_reminders=read))
    monkeypatch.setattr(query, 'has_required_capability', lambda _, cap: can_manage and cap == 'line.identity.binding.manage')
    result=query._read_source(source,1,PRINCIPAL)
    assert result.total==51 and result.next_cursor==2
    assert calls[0].subject_type.value==role and calls[0].page==2 and calls[0].page_size==25
    item=result.items[0]
    assert item.title==f'人工提醒{label}綁定 LINE' and item.person=='合成姓名'
    assert item.tag=='待人工提醒'
    if role == 'customer':
        assert item.recipient is None and item.message is None
        assert [r.id for r in result.items[:2]] == ['customer_binding:7:115000001', 'customer_binding:7:115000002']
        assert [r.can_dismiss for r in result.items] == [can_manage, can_manage, False]
    else:
        assert item.can_dismiss is False
        assert item.recipient == '0987654321' and '身分證字號與生日' in item.message
    assert query.SOURCES[source][2].value=='line.identity.binding.read'


def test_mobile_binding_dismiss_checks_capability_and_reuses_case_command(monkeypatch):
    from api.dependencies import line_identity
    from subsystems.line.capabilities import LineCapability

    calls = []

    def mobile_context(token, capability):
        assert capability is LineCapability.IDENTITY_BINDING_MANAGE
        if token != 'synthetic-mobile':
            raise HTTPException(403, 'not an authorized LINE manager')
        return PRINCIPAL, None

    def dismiss(subject_reference, case_no, reason, key, actor):
        calls.append((subject_reference, case_no, reason, key.value, actor.actor_id))
        if case_no == 'stale-case':
            raise LookupError('binding_reminder_subject_changed')
        return len(calls) > 1

    monkeypatch.setattr(line_mobile_admin, '_mobile_admin_context', mobile_context)
    monkeypatch.setattr(line_identity, 'get_line_identity_management_application',
                        lambda: SimpleNamespace(dismiss_customer_binding_reminder=dismiss))
    app = FastAPI()
    app.include_router(actions.mobile_router)
    path = '/api/v1/line/mobile-admin/notification-task-actions/customer-binding-reminder/dismiss'
    body = {'line_id_token': 'synthetic-mobile', 'subject_reference': 7, 'case_no': '115000001',
            'reason': '使用者移除提醒', 'idempotency_key': 'same-intent'}
    with TestClient(app) as client:
        assert client.post(path, json={**body, 'line_id_token': 'unbound'}).status_code == 403
        assert calls == []
        first = client.post(path, json=body)
        replay = client.post(path, json=body)
        stale = client.post(path, json={**body, 'case_no': 'stale-case'})
    assert first.status_code == replay.status_code == 200
    assert first.json()['data'] == {'dismissed': True, 'replayed': False}
    assert replay.json()['data'] == {'dismissed': True, 'replayed': True}
    assert calls[:2] == [(7, '115000001', '使用者移除提醒', 'same-intent', 'admin:1')] * 2
    assert stale.status_code == 409
    assert stale.json()['detail']['error']['code'] == 'binding_reminder_subject_changed'


@pytest.mark.parametrize('code,message',[('deposit_customer_not_bound','尚未綁定 LINE'),('deposit_payment_details_incomplete','繳費資訊尚未完整'),('deposit_liff_not_configured','LIFF')])
def test_deposit_failures_are_actionable_without_enqueue(monkeypatch,code,message):
    captured=[]
    def send(*args):captured.append(args);raise DepositNotificationConflict(code)
    monkeypatch.setattr(actions,'get_deposit_notifications',lambda:SimpleNamespace(send_reminder=send))
    with pytest.raises(HTTPException) as failure:
        actions.deposit_reminder(actions.DepositReminder(case_no='116000001',expected_version=7,idempotency_key='same-intent'),PRINCIPAL)
    assert failure.value.status_code==409
    assert message in failure.value.detail['error']['message']
    assert captured[0][0:2]==('116000001',7)
    assert captured[0][2].value=='same-intent'


def test_mobile_registration_uses_binding_auth_and_original_approval(monkeypatch):
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda *args:(_ for _ in ()).throw(HTTPException(403,'unbound')))
    monkeypatch.setattr(actions,'get_registration_review_application',lambda:pytest.fail('must not create writer'))
    with pytest.raises(HTTPException):
        actions.mobile_registration_approve(3,actions.MobileRegistrationApproval(line_id_token='unbound',expected_version=2))


def test_invalid_source_cursor_and_unknown_command_fields_are_rejected():
    app=FastAPI();app.include_router(query.router);app.include_router(actions.router)
    app.dependency_overrides[require_admin]=lambda:PRINCIPAL
    with TestClient(app) as client:
        assert client.get('/api/v1/line/notification-tasks/not-a-source').status_code==422
        assert client.get('/api/v1/line/notification-tasks/profile').status_code == 422
        assert client.post('/api/v1/line/mobile-admin/notification-tasks/profile',
                           json={'line_id_token': 'synthetic'}).status_code == 422
        assert client.get('/api/v1/line/notification-tasks/deposit?cursor=-1').status_code==422
        response=client.post('/api/v1/line/notification-task-actions/information/3/send',json={
            'recipient':'customer','message_text':'text','idempotency_key':'key','line_id_token':'cannot-change-auth-boundary'})
        assert response.status_code==404


def test_mobile_legacy_customer_service_target_opens_staff_review_without_ticket_actions():
    import subprocess

    script = r'''
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const html=fs.readFileSync('line/static/mobile_admin.html','utf8');
const ctx=vm.createContext({URLSearchParams,location:{search:''},document:{getElementById:id=>({id})}});
const start=html.indexOf('const panes =');
const end=html.indexOf('function targetForIdentityRedirect(',start);
assert(start>=0 && end>start);
vm.runInContext(html.slice(start,end),ctx);
for (const search of ['?target=customer_service','?liff.state=%3Ftarget%3Dcustomer_service']) {
  ctx.location.search=search;
  assert.equal(vm.runInContext('panes[targetFromUrl()].id',ctx),'reviewPane');
}
assert(!vm.runInContext('supportedTargets.includes("customer_service")',ctx));
assert.doesNotMatch(html,/loadTicketDetail|ticket_q|\/customer-service(?:\/|['"])/);
'''
    result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stderr


def test_legacy_leave_is_not_a_current_source_and_both_queries_are_retired(monkeypatch):
    assert NotificationSource.LEAVE not in {row.source for row in query._catalog(PRINCIPAL)}
    monkeypatch.setattr(query,'_read_source',lambda *args:pytest.fail('retired source must not read owners'))
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda *args:(PRINCIPAL,None))
    with pytest.raises(HTTPException) as desktop:
        query.source_page(NotificationSource.LEAVE,0,PRINCIPAL)
    with pytest.raises(HTTPException) as mobile:
        query.mobile_source_page(NotificationSource.LEAVE,query.MobileNotificationQuery(line_id_token='synthetic'))
    assert desktop.value.status_code==mobile.value.status_code==410
    from api.routes import staff_leave_management
    with pytest.raises(HTTPException) as review:
        staff_leave_management.review_staff_leave_request(7,staff_leave_management.ReviewBody(expected_version=1,action='accept',reason=''), 'synthetic',PRINCIPAL)
    assert review.value.status_code==410


def test_service_day_log_reminder_is_not_a_current_source_and_both_queries_are_retired(monkeypatch):
    assert NotificationSource.LOG not in {row.source for row in query._catalog(PRINCIPAL)}
    monkeypatch.setattr(query,'_read_source',lambda *args:pytest.fail('retired source must not read owners'))
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda *args:(PRINCIPAL,None))
    with pytest.raises(HTTPException) as desktop:
        query.source_page(NotificationSource.LOG,0,PRINCIPAL)
    with pytest.raises(HTTPException) as mobile:
        query.mobile_source_page(NotificationSource.LOG,query.MobileNotificationQuery(line_id_token='synthetic'))
    assert desktop.value.status_code==mobile.value.status_code==410
    assert desktop.value.detail['error']['code']=='service_day_log_reminder_retired'
    assert mobile.value.detail['error']['code']=='service_day_log_reminder_retired'


def test_mobile_identity_focus_uses_original_single_item_reader_and_current_auth(monkeypatch):
    from api.dependencies import line_identity
    calls=[];owner=object()
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda token,cap:(calls.append(cap.value) or (PRINCIPAL,None)))
    monkeypatch.setattr(line_identity,'get_line_identity_review_application',lambda:SimpleNamespace(get=lambda identity:(calls.append(identity.value) or owner)))
    monkeypatch.setattr(line_mobile_admin,'_review_view',lambda item:({'request_id':999,'status':'pending'} if item is owner else pytest.fail('wrong item')))
    result=actions.mobile_identity_query(999,actions.MobileAuth(line_id_token='synthetic'))
    assert result.data['request_id']==999 and calls==['line.review.read',999]
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda *args:(_ for _ in ()).throw(HTTPException(403,'unbound')))
    with pytest.raises(HTTPException) as failure:actions.mobile_identity_query(999,actions.MobileAuth(line_id_token='unbound'))
    assert failure.value.status_code==403 and len(calls)==2


def test_mobile_notification_focus_and_return_ignore_late_content_and_errors():
    import subprocess
    script=r'''
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
import {Window} from './ui_react/node_modules/happy-dom/lib/index.js';
const text=fs.readFileSync('line/static/mobile_admin.html','utf8').replace(/\r\n/g,'\n');
const extract=h=>{const i=text.indexOf(h);assert(i>=0,h);return text.slice(i,text.indexOf('\n}',i)+2)};
const window=new Window();const document=window.document;window.HTMLElement.prototype.scrollIntoView=()=>{};
document.body.innerHTML='<select id="depositStatus"></select><div id="notificationSources"></div><div id="notificationOperations"></div><div id="reauthenticate" class="hidden"></div><input id="orderStatusSearch">';
const calls=[];let finish;let returned=0;
const ctx=vm.createContext({document,console,navigator:{clipboard:{writeText:async value=>calls.push(['copy',value])}},
 notificationText:(tag,value)=>{const node=document.createElement(tag);node.textContent=value;return node},
 notificationButton:(label,action)=>{const button=document.createElement('button');button.textContent=label;button.action=action;return button},
 reviewCard:review=>{const node=document.createElement('article');node.dataset.review=String(review.request_id);return node},
 switchPane:name=>calls.push(['pane',name]),
 postJson:async(url,body)=>{calls.push([url,body]);if(url.includes('/identity/999/query'))return {request_id:999,status:'pending'};
  if(url.includes('/notification-tasks/followup'))return {items:[{id:'followup:8',source:'followup',reference_id:8,case_no:'PUBLIC',summary:'待跟進'}]};
  return new Promise(resolve=>{finish=resolve})},
 });
vm.runInContext("let notificationSequence=0,notificationSelection=null;const notificationParents=new Map();let target='staff_review';",ctx);
for(const header of ['function restoreNotificationPanels(','function focusNotificationItems(','async function openNotificationItem('])vm.runInContext(extract(header),ctx);
ctx.loadReviewWorkbench=async()=>{returned++;vm.runInContext('++notificationSequence;restoreNotificationPanels()',ctx)};
const opening=vm.runInContext("openNotificationItem({source:'identity',reference_id:7,title:'身分重綁',reason:''},0)",ctx);
await document.querySelector('button').action();assert.equal(returned,1);
finish({request_id:7,status:'pending'});await opening;
assert.equal(document.querySelectorAll('[data-review]').length,0,'late identity detail reappeared after return');
await vm.runInContext("openNotificationItem({source:'identity',reference_id:999,title:'指定審核',reason:''},3)",ctx);
assert(document.querySelector('[data-review="999"]'));
assert(calls.some(([url])=>url==='/api/v1/line/mobile-admin/notification-task-actions/identity/999/query'));
assert(!calls.some(([url])=>String(url).endsWith('/identity-reviews')),'list page must not determine identity detail');
await vm.runInContext("openNotificationItem({id:'followup:8',source:'followup',reference_id:8,case_no:'PUBLIC',title:'回覆待跟進',reason:''},0)",ctx);
const buttons=[...document.querySelectorAll('button')];
await buttons.find(b=>b.textContent==='複製案件編號').action();
await buttons.find(b=>b.textContent==='查看本案狀態').action();
assert(calls.some(([type,value])=>type==='copy'&&value==='PUBLIC'));
assert(calls.some(([type,value])=>type==='pane'&&value==='order_tracking'));
assert.equal(document.getElementById('orderStatusSearch').value,'PUBLIC');
assert(!calls.some(([url])=>String(url).includes('/send')||String(url).includes('/apply')));
vm.runInContext("notificationSelection={item:{source:'service_start',reference_id:77},matched:false}",ctx);
const focused=vm.runInContext("focusNotificationItems('service_start',[{request_id:76},{request_id:77},{request_id:78}])",ctx);
assert.equal(focused.length,1);assert.equal(focused[0].request_id,77);
vm.runInContext("const studioPreview=false,idToken='synthetic';",ctx);
ctx.safeErrorCode=()=> 'liff_expired';ctx.safeErrorMessage=()=> 'expired';
ctx.fetch=()=>new Promise(resolve=>{finish=resolve});vm.runInContext(extract('async function postJson('),ctx);
const lateError=vm.runInContext("postJson('/synthetic',{})",ctx);
await ctx.loadReviewWorkbench();finish({ok:false,status:403,json:async()=>({})});
await assert.rejects(lateError,/expired/);
assert(document.getElementById('reauthenticate').classList.contains('hidden'),'late auth error changed current screen');
document.body.insertAdjacentHTML('beforeend','<div id="groupTodos">current group content</div>');
vm.runInContext('let groupTodoQuerySequence=0,groupTodoPage=1;',ctx);
ctx.postJson=()=>new Promise(resolve=>{finish=resolve});
vm.runInContext(extract('async function loadGroupTodos('),ctx);
const oldGroup=vm.runInContext('loadGroupTodos()',ctx);
await ctx.loadReviewWorkbench();finish({items:[],total:0,total_pages:1,page:1});await oldGroup;
assert.equal(document.getElementById('groupTodos').textContent,'current group content','old group query altered the restored panel');
window.happyDOM.abort();
'''
    result=subprocess.run(['node','--input-type=module','-e',script],check=False,capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stderr


def test_mobile_opening_greeting_history_is_visible_even_without_paid_group_todos():
    import subprocess

    script = r'''
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
import {Window} from './ui_react/node_modules/happy-dom/lib/index.js';
const source=fs.readFileSync('line/static/mobile_admin.html','utf8').replace(/\r\n/g,'\n');
const extract=h=>{const i=source.indexOf(h);assert(i>=0,h);return source.slice(i,source.indexOf('\n}',i)+2)};
const window=new Window();const document=window.document;
document.body.innerHTML='<div id="reviewPane"><strong id="reviewTotal">—</strong><div class="workstream-list"></div></div><div id="notificationSources"></div>';
const calls=[];
const ctx=vm.createContext({document,notificationSequence:0,notificationSelection:null,target:'staff_review',
  notificationGroups:{all:'全部',reminder:'提醒'},restoreNotificationPanels(){},updateNotificationCards(){},showStatus(){},
  postJson:async(url,body)=>{
    calls.push([url,body]);
    if(url.endsWith('/notification-tasks'))return [{group:'reminder',source:'group',label:'訂金已付尚未建群'}];
    if(url.endsWith('/notification-tasks/group'))return {items:[],total:0,next_cursor:null};
    assert.equal(url,'/api/v1/line/mobile-admin/order-group-todos');
    assert.equal(body.view,'opening_greeting_skips');
    return {items:[{case_no:body.page===1?'CASE-A':'CASE-B',occurred_at:'2026-11-15T01:00:00Z'}],
      page:body.page,page_size:25,total:26};
  },
});
for(const header of ['function notificationText(', 'function notificationButton(', 'function showEmpty(',
  'function renderPagination(', 'function requireTodoPage(', 'function openingGreetingSkipRecords(',
  'async function loadReviewWorkbench(']){
  // Helpers with a one-line body end before the next newline.
  const index=source.indexOf(header);
  const line=source.slice(index,source.indexOf('\n',index));
  vm.runInContext(line.endsWith(' }')?line:extract(header),ctx);
}
await vm.runInContext('loadReviewWorkbench()',ctx);
const group=document.querySelector('[data-notification-source="group"]');
assert(group.textContent.includes('目前沒有此類待辦。'));
const history=group.querySelector('details');
assert.equal(history.querySelector('summary').textContent,'開工問候未送出紀錄');
assert.equal(calls.length,2);
history.open=true;
history.dispatchEvent(new window.Event('toggle'));
await new Promise(resolve=>setTimeout(resolve,0));
assert(history.textContent.includes('案件 CASE-A'));
assert(history.textContent.includes('未綁定有效的案件服務群組'));
[...history.querySelectorAll('button')].find(button=>button.textContent==='下一頁').click();
await new Promise(resolve=>setTimeout(resolve,0));
assert(history.textContent.includes('案件 CASE-B'));
assert(!history.textContent.includes('案件 CASE-A'));
assert(!calls.some(([url])=>url.includes('/send')||url.includes('/apply')));
window.happyDOM.abort();
'''
    result = subprocess.run(['node', '--input-type=module', '-e', script], check=False, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stderr


def test_mobile_identity_decision_refreshes_todos_and_ignores_late_operations():
    import subprocess
    script=r'''
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
import {Window} from './ui_react/node_modules/happy-dom/lib/index.js';
const source=fs.readFileSync('line/static/mobile_admin.html','utf8').replace(/\r\n/g,'\n');
const extract=h=>{const i=source.indexOf(h);assert(i>=0,h);return source.slice(i,source.indexOf('\n}',i)+2)};
const window=new Window();const document=window.document;
document.body.innerHTML='<textarea id="reason-1"></textarea>';
const calls=[];const statuses=[];let currentReads=0;let deferPreview=null;let deferIdentity=false;
const ctx=vm.createContext({document,crypto,showStatus:text=>statuses.push(text),
 postJson:async(url,body)=>{calls.push([url,body]);
  if(url.endsWith('/preview')) {
    if(deferIdentity)return new Promise((resolve,reject)=>{deferPreview={resolve,reject}});
    return {request_id:1,decision:body.decision,expected_version:1,resulting_version:2,before_status:'pending',after_status:'rejected',preview_fingerprint:'a'.repeat(64)};
  }
  assert(url.endsWith('/apply'));
  return {request_id:1,status:'rejected',version:2,outcome:'created',receipt_identity:'owner-receipt'};
 },loadReviewWorkbench:async()=>{currentReads++;vm.runInContext('++notificationSequence',ctx)},
 });
vm.runInContext("let notificationSequence=0,notificationSelection={item:{source:'identity'}};const reviewPreviews=new Map();const target='staff_review';",ctx);
for(const header of ['function notificationViewCurrent(','function requireReviewPreview(','async function previewReviewDecision(','async function applyReviewDecision('])vm.runInContext(extract(header),ctx);
await vm.runInContext("previewReviewDecision({request_id:1,version:1},'reject')",ctx);
assert.equal(calls.filter(([u])=>u.includes('/identity-reviews/')).length,2);
assert.equal(currentReads,1);assert.equal(calls[0][1].reason,'工會退回身分審核');
assert(!document.querySelector('button'),'no second confirmation button may be added');
deferIdentity=true;
const old=vm.runInContext("previewReviewDecision({request_id:1,version:1},'reject')",ctx);
vm.runInContext('++notificationSequence',ctx);statuses.push('new screen');deferPreview.reject(Error('late failure'));await old;
assert.equal(statuses.at(-1),'new screen','old failure must not overwrite new screen');
const oldSuccess=vm.runInContext("previewReviewDecision({request_id:1,version:1},'reject')",ctx);
vm.runInContext('++notificationSequence',ctx);deferPreview.resolve({request_id:1,decision:'reject',expected_version:1,resulting_version:2,before_status:'pending',after_status:'rejected',preview_fingerprint:'c'.repeat(64)});await oldSuccess;
assert.equal(calls.filter(([u])=>u.endsWith('/apply')).length,1,'leaving before preview completes must not submit another Apply');
window.happyDOM.abort();
'''
    result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('task_status,expected_a,expected_b', [('failed',False,True),('pending',False,True),('cancelled',True,True)])
def test_original_task_blocks_only_its_own_source_on_desktop_and_liff(monkeypatch,task_status,expected_a,expected_b):
    from contextlib import nullcontext
    from dataclasses import replace
    from subsystems.line.notification_failure_current_fact import LineNotificationFailedSourceFact, evaluate_line_notification_failure_current_fact
    projection=SimpleNamespace(candidate=SimpleNamespace(definition_code='LINE-006',subject_identity={'case_no':'CASE-1','notification_reason':'recipient_unavailable'}))
    def owner(expected):
        readback=evaluate_line_notification_failure_current_fact(expected,
            (LineNotificationFailedSourceFact(11,True,True,()),LineNotificationFailedSourceFact(12,True,True,())),owner_version=12,authoritative_complete=True)
        return replace(readback,related_task_ids=(99,),source_task_ids=((11,(99,)),(12,())))
    unit=SimpleNamespace(anomaly_rechecks=SimpleNamespace(query_current=lambda _:projection),notification_rules=SimpleNamespace(
        current_failure_fact=owner,list_case_timeline=lambda _:({'source_event_id':11,'event_code':'order.service_start_day'},{'source_event_id':12,'event_code':'order.service_completed'}),
        preview_manual_replay=lambda _: {'can_replay':True,'unavailable_reason':None}),
        delivery_tasks=SimpleNamespace(get=lambda _:SimpleNamespace(status=SimpleNamespace(value=task_status)), get_admin=lambda _:SimpleNamespace(status=LineDeliveryStatus(task_status),error_code=None)))
    monkeypatch.setattr(actions,'open_line_unit_of_work',lambda:nullcontext(unit))
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda *args:(PRINCIPAL,None))
    issue='ci_'+'1'*64
    desktop=actions.notification_failure_detail(issue,PRINCIPAL).data
    mobile=actions.mobile_notification_failure_detail(issue,actions.MobileAuth(line_id_token='synthetic')).data
    assert desktop==mobile
    assert [source['can_replay'] for source in desktop['sources']]==[expected_a,expected_b]


@pytest.mark.parametrize('allowed', [(),(99,)])
def test_delivery_fresh_filter_preserves_candidate_cursor_and_does_not_claim_raw_total(monkeypatch,allowed):
    from contextlib import nullcontext
    from datetime import datetime,UTC
    from domains.line.delivery import LineDeliveryStatus
    calls=[]
    task=SimpleNamespace(task_id=SimpleNamespace(value=99),status=LineDeliveryStatus.FAILED,updated_at=datetime(2026,10,26,tzinfo=UTC))
    monkeypatch.setattr(query,'get_line_delivery_task_admin_application',lambda:SimpleNamespace(list=lambda request,actor:SimpleNamespace(items=(task,),total=51)))
    unit=SimpleNamespace(notification_rules=SimpleNamespace(unresolved_delivery_task_ids=lambda ids:(calls.append(ids) or allowed)))
    monkeypatch.setattr(query,'open_line_unit_of_work',lambda:nullcontext(unit))
    result=query.query_source(NotificationSource.DELIVERY,1,PRINCIPAL)
    assert result.total is None and result.next_cursor==2
    assert [item.id for item in result.items]==(['delivery:99'] if allowed else [])
    assert calls==[(99,)]


def test_delivery_incomplete_source_is_typed_unavailable_instead_of_silent_removal(monkeypatch):
    from contextlib import nullcontext
    def incomplete(_):raise RuntimeError('line_failure_task_readback_incomplete')
    monkeypatch.setattr(query,'get_line_delivery_task_admin_application',lambda:SimpleNamespace(list=lambda *args:SimpleNamespace(items=(),total=0)))
    monkeypatch.setattr(query,'open_line_unit_of_work',lambda:nullcontext(SimpleNamespace(notification_rules=SimpleNamespace(unresolved_delivery_task_ids=incomplete))))
    with pytest.raises(HTTPException) as failure:query.query_source(NotificationSource.DELIVERY,0,PRINCIPAL)
    assert failure.value.status_code==503 and failure.value.detail['error']['retryable']


def test_deposit_missing_details_share_exact_readonly_reason_between_desktop_and_liff(monkeypatch):
    from contextlib import nullcontext
    from subsystems.client_finance.deposit_payment_query import DepositPayment
    from subsystems.line.deposit_notifications import DepositNotificationApplication,DepositNotificationTodo,DepositNotificationTodoPage
    from api.routes import line_deposit_payment as deposit
    payment=DepositPayment('SYNTHETIC','synthetic-deposit',1,3000,None,None,None,None)
    app=DepositNotificationApplication(lambda:pytest.fail('query must not enter writer'),lambda:None,liff_id='',bank_code='')
    result=DepositNotificationTodoPage((DepositNotificationTodo(payment,False,None),),1,1,0,1,False)
    unit=SimpleNamespace(deposit_notifications=SimpleNamespace(followups=lambda **kwargs:result))
    monkeypatch.setattr(query,'get_deposit_notifications',lambda:app)
    monkeypatch.setattr(deposit,'get_deposit_notifications',lambda:app)
    monkeypatch.setattr(query,'open_line_unit_of_work',lambda:nullcontext(unit))
    monkeypatch.setattr(deposit,'open_line_unit_of_work',lambda:nullcontext(unit))
    monkeypatch.setattr(deposit,'_mobile_admin_context',lambda *args:(PRINCIPAL,None))
    desktop=query.query_source(NotificationSource.DEPOSIT,0,PRINCIPAL).items[0]
    mobile=deposit.deposit_staff_followups(deposit.DepositStaffQuery(line_id_token='synthetic')).data.items[0]
    assert desktop.unavailable_reason==mobile.unavailable_reason
    for label in ('客戶尚未綁定 LINE','繳費到期日','案件虛擬帳號','銀行代碼','LINE 繳費頁面設定'):
        assert label in desktop.unavailable_reason
    assert mobile.ready is False

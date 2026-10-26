"""Committed completion -> one original-group notice, using only synthetic local identities.

No real LINE sender, menu publisher, application lifespan or broad worker is run.
"""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import os
import runpy
import pytest

from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.order_pre_start_notification_source_worker import MySqlOrderPreStartNotificationSourceWorker
from infrastructure.mysql.orders_terminal_closure_source import MySqlOrdersTerminalClosureSource, _event_from_payload
from subsystems.line.service_completion_notifications import SOURCE_TYPE, EVENT_CODE
from subsystems.line.terminal_closure_application import consume_terminal_closure
from subsystems.line.terminal_closure_contracts import TerminalClosureDecision

support=runpy.run_path('tests/domains/external-integration/subsystems/line/infrastructure/test_service_start_day_mysql.py')
http=support['http'];configurations=support['configurations']
rows,write,checked,units=support['rows'],support['write'],support['checked'],support['units']
existing=support['existing']
pytestmark=pytest.mark.skipif(not os.getenv('SERVICE_START_TEST_DB'),reason='explicit local synthetic database required')
NOW=datetime(2034,5,30,3,tzinfo=timezone.utc)
COPY='本案服務已完成，感謝您的配合。請填寫服務滿意度問卷，讓我們了解您的服務體驗。'


def prepared(http):
    from api.routes.order_auto_completion import router
    if not getattr(http.app.state,'completion_registered',False):
        http.app.include_router(router);http.app.state.completion_registered=True
    case,staff,segments=existing['seed_case'](http)
    user='U'+uuid4().hex
    client=rows('SELECT client_id FROM orders WHERE case_no=%s',(case,))[0]['client_id']
    write('UPDATE clients SET line_user_id=%s WHERE id=%s',(user,client))
    write("INSERT INTO line_platform_users(line_user_id,friend_status) VALUES (%s,'active')",(user,))
    write("INSERT INTO line_identity_role_bindings(line_user_id,subject_type,binding_status,subject_reference) VALUES (%s,'customer','bound',%s)",(user,str(client)))
    checked(existing['submit'](http,case,staff[0],segments[0],start='2026-10-05')[0])
    return case,user


def complete(http,case,key=None):
    url=f'/api/v1/orders/{case}/service-completion'
    plan=checked(http.post(url+'/preview',json={'evaluation_at':NOW.isoformat()}))
    body={'evaluation_at':NOW.isoformat(),'expected_order_version':plan['expected_order_version'],'preview_fingerprint':plan['fingerprint'],'reason':''}
    key=key or uuid4().hex
    receipt=checked(http.post(url+'/apply',json=body,headers={'Idempotency-Key':key}))
    return receipt,body,key


def tasks(case):
    return rows('SELECT * FROM line_delivery_tasks WHERE source_aggregate_type=%s AND source_aggregate_identity=%s ORDER BY id',(SOURCE_TYPE,case))


def scan():
    return MySqlOrderPreStartNotificationSourceWorker(mysql_adapter.get_connection,lambda:NOW).run_once()


def deliver(task_id):
    worker=support['TaskScopedWorker'](task_id,now=NOW)
    worker.run_once();return worker.calls


def source_row(case):
    return rows("SELECT * FROM orders_domain_outbox WHERE case_no=%s AND JSON_EXTRACT(payload_snapshot,'$.line_service_completion_notification')=TRUE",(case,))[0]


def test_no_notice_until_actual_completion_then_original_group_once_with_survey_copy(http):
    case,_=prepared(http)
    scan();assert not tasks(case)
    receipt,body,key=complete(http,case)
    marker=source_row(case)
    assert json.loads(marker['payload_snapshot'])['terminal_kind']=='completion'
    scan();scan();work=tasks(case);assert len(work)==1
    assert work[0]['recipient_type']=='group'
    assert work[0]['recipient_identity']==rows('SELECT group_id FROM line_order_group_bindings WHERE case_no=%s',(case,))[0]['group_id']
    assert json.loads(work[0]['payload_snapshot'])=={'type':'text','text':COPY}
    assert '帳務' not in work[0]['payload_snapshot'] and 'http' not in work[0]['payload_snapshot']
    assert checked(http.post(f'/api/v1/orders/{case}/service-completion/apply',json=body,headers={'Idempotency-Key':key}))['lifecycle_event_id']==receipt['lifecycle_event_id']
    assert len(deliver(work[0]['id']))==1
    scan();assert len(tasks(case))==1
    assert rows('SELECT status FROM orders_domain_outbox WHERE id=%s',(marker['id'],))[0]['status']==marker['status']


def test_ordinary_customer_menu_noop_is_independent_from_group_completion_notice(http):
    case,user=prepared(http);complete(http,case)
    marker=source_row(case);payload=json.loads(marker['payload_snapshot'])
    event=_event_from_payload(payload,case_no=case)
    connection=mysql_adapter.get_connection()
    try:
        source=MySqlOrdersTerminalClosureSource(connection)
        assert marker['id'] in {identity for identity,_ in source.list_pending(limit=100000)}
    finally:connection.close()
    result=consume_terminal_closure(units,event)
    assert result.decision is TerminalClosureDecision.NOOP_NOT_STAFF
    assert consume_terminal_closure(units,event).decision is TerminalClosureDecision.NOOP_REPLAY
    assert not rows("SELECT id FROM line_domain_outbox WHERE idempotency_identity=%s",('staff-default-restore:'+event.source_event_identity,))
    connection=mysql_adapter.get_connection()
    try:
        assert marker['id'] not in {identity for identity,_ in MySqlOrdersTerminalClosureSource(connection).list_pending(limit=100000)}
    finally:connection.close()
    scan();assert len(tasks(case))==1 and tasks(case)[0]['recipient_identity']!=user


@pytest.mark.parametrize('source_kind',['historical_unmarked','cancellation'])
def test_historical_or_cancellation_source_does_not_create_completion_notice(http,source_kind):
    case,_=prepared(http);complete(http,case)
    marker=source_row(case)
    payload=json.loads(marker['payload_snapshot'])
    if source_kind=='historical_unmarked':
        payload.pop('line_service_completion_notification')
    else:
        payload['terminal_kind']='cancellation'
    # Deliberate synthetic source fixtures; never rewrite a live Orders event.
    write('UPDATE orders_domain_outbox SET payload_snapshot=%s WHERE id=%s',(json.dumps(payload),marker['id']))
    scan();assert not tasks(case)


@pytest.mark.parametrize('change',['different_group','same_group_version','released'])
def test_provider_gate_cancels_changed_group_without_private_fallback(http,change):
    case,_=prepared(http);complete(http,case);scan();old=tasks(case)[0]
    if change=='different_group':
        write('UPDATE line_order_group_bindings SET group_id=%s,aggregate_version=aggregate_version+1 WHERE case_no=%s',('C'+uuid4().hex,case))
    elif change=='same_group_version':
        write('UPDATE line_order_group_bindings SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,))
    else:
        write("UPDATE line_order_group_bindings SET binding_status='released',aggregate_version=aggregate_version+1 WHERE case_no=%s",(case,))
    assert not deliver(old['id'])
    assert tasks(case)[0]['processing_status']=='cancelled'
    scan()
    assert len(tasks(case))==(1 if change=='released' else 2)
    assert all(t['recipient_type']=='group' for t in tasks(case))


def test_already_sent_notice_does_not_repeat_after_group_rebind(http):
    case,_=prepared(http);complete(http,case);scan();old=tasks(case)[0]
    assert len(deliver(old['id']))==1
    write('UPDATE line_order_group_bindings SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,))
    scan();assert len(tasks(case))==1


def test_missing_group_is_internal_line_todo_without_private_notice(http):
    case,_=prepared(http);complete(http,case)
    write("UPDATE line_order_group_bindings SET binding_status='released',aggregate_version=aggregate_version+1 WHERE case_no=%s",(case,))
    scan();assert not tasks(case)
    decisions=rows('SELECT d.reason_code FROM line_notification_source_events s JOIN line_notification_decisions d ON d.source_event_id=s.id WHERE s.event_code=%s AND s.source_aggregate_identity=%s',(EVENT_CODE,case))
    assert decisions and decisions[0]['reason_code']=='recipient_unavailable'
    with units() as unit:
        assert any(item.case_no==case for item in unit.notification_rules.list_line006_recheck_targets(limit=100))


def test_completion_failure_rolls_back_notice_source_with_owner_transaction(http,monkeypatch):
    from subsystems.payroll.rebuild_workflow import PayrollRebuildWorkflow
    case,_=prepared(http)
    def fail(*args,**kwargs):raise RuntimeError('synthetic completion accounting failure')
    with monkeypatch.context() as patch:
        patch.setattr(PayrollRebuildWorkflow,'synchronize_in_unit_of_work',fail)
        with pytest.raises(RuntimeError,match='synthetic completion'):
            complete(http,case)
    assert rows('SELECT status FROM orders WHERE case_no=%s',(case,))[0]['status']=='服務中'
    assert not rows('SELECT lifecycle_event_id FROM order_service_data_locks WHERE case_no=%s',(case,))
    assert not rows("SELECT id FROM orders_domain_outbox WHERE case_no=%s AND JSON_EXTRACT(payload_snapshot,'$.line_service_completion_notification')=TRUE",(case,))
    scan();assert not tasks(case)


def test_configuration_text_edit_applies_to_next_notice_preserving_queued_snapshot(http):
    from domains.line.configuration import LineConfigurationKind,build_configuration_candidate
    from shared_kernel.identities import ActorContext,CorrelationId,IdempotencyKey
    from subsystems.line.configuration_contracts import ApplyLineConfigurationCommand
    case,_=prepared(http);complete(http,case);scan();old=tasks(case)[0]
    original=json.loads(Path('config/message_templates.json').read_text(encoding='utf-8'))
    changed=json.loads(json.dumps(original))
    template=next(t for t in changed['templates'] if t['id']=='LINE-SERVICE-COMPLETION-TEXT-V1')
    template['content']=COPY+'\nhttps://example.invalid/satisfaction'
    def apply(definition):
        with units() as unit:
            current=unit.configurations.get(LineConfigurationKind.MESSAGE_TEMPLATES)
            candidate=build_configuration_candidate(kind=LineConfigurationKind.MESSAGE_TEMPLATES,current_revision=current.revision,
                expected_revision=current.revision,definition=definition)
            unit.configurations.apply(ApplyLineConfigurationCommand(candidate,ActorContext('synthetic'),'',IdempotencyKey(uuid4().hex),CorrelationId(uuid4().hex)))
            unit.commit()
    try:
        apply(changed)
        second,_=prepared(http);complete(http,second);scan()
        assert json.loads(tasks(second)[0]['payload_snapshot'])['text']==template['content']
        assert tasks(case)[0]['payload_snapshot']==old['payload_snapshot']
    finally:apply(original)

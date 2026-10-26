"""Real MySQL start-day chain, with a task-scoped fake provider only.

Uses the existing disposable service-start fixture/writers. No application
lifespan, canonical runtime, real provider or menu publication is started.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import os
import runpy
import pytest

from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from infrastructure.mysql.service_start_day_repository import MySqlServiceStartDayRepository
from infrastructure.mysql.order_pre_start_notification_source_worker import MySqlOrderPreStartNotificationSourceWorker
from domains.line.configuration import LineConfigurationKind, build_configuration_candidate
from domains.line.identities import LineSourceType, LineUserId, LineGroupId, LineDeliveryTaskId
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.configuration_contracts import ApplyLineConfigurationCommand
from subsystems.line.delivery_contracts import ClaimLineDeliveryTasksQuery, LineProviderOutcome, LineProviderOutcomeType
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.service_start_day import ServiceStartDayPostbackApplication

DATABASE=os.getenv('SERVICE_START_TEST_DB')
pytestmark=pytest.mark.skipif(not DATABASE,reason='requires explicit localhost lu_test_ DB')
existing=runpy.run_path('tests/domains/scheduling/subsystems/scheduling/modules/service-start/test_service_start_mysql.py')
http=existing['http']
rows,write,checked=existing['rows'],existing['write'],existing['checked']
DAY=date(2031,3,12)
NOW=datetime(2031,3,12,3,tzinfo=timezone.utc)


def units(): return LineMySqlUnitOfWork(mysql_adapter.get_connection())


@pytest.fixture(scope='module',autouse=True)
def configurations(http):
    assert os.getenv('APP_ENV')=='development'
    assert mysql_adapter.DB_CONFIG['host'] in ('localhost','127.0.0.1')
    assert DATABASE.startswith('lu_test_') and mysql_adapter.DB_CONFIG['database']==DATABASE
    # Formal configuration writer, isolated database only; no Rich Menu kind.
    with units() as unit:
        for kind in (LineConfigurationKind.MESSAGE_TEMPLATES,LineConfigurationKind.NOTIFICATION_RULES):
            definition=json.loads(Path(f'config/{kind.value}.json').read_text(encoding='utf-8'))
            if kind is LineConfigurationKind.NOTIFICATION_RULES:
                from domains.line.notification_rules import validate_notification_rules
                validate_notification_rules(definition)
            current=unit.configurations.get(kind)
            candidate=build_configuration_candidate(kind=kind,current_revision=current.revision,
                expected_revision=current.revision,definition=definition)
            unit.configurations.apply(ApplyLineConfigurationCommand(candidate,ActorContext('synthetic-start-day'),
                'start-day isolated verification',IdempotencyKey(uuid4().hex),CorrelationId(uuid4().hex)))
        unit.commit()


def prepared(http):
    case,staff,segments=existing['seed_case'](http)
    checked(existing['submit'](http,case,staff[0],segments[0],start=DAY.isoformat())[0])
    group=rows('SELECT group_id FROM line_order_group_bindings WHERE case_no=%s',(case,))[0]['group_id']
    return case,staff,segments,group


def candidate(case):
    with units() as unit:return unit.service_start_days.current(case,DAY)


def tasks(case,source='order_service_start_day'):
    return rows('SELECT * FROM line_delivery_tasks WHERE source_aggregate_type=%s AND source_aggregate_identity=%s ORDER BY id',(source,case))


def scan():
    return MySqlOrderPreStartNotificationSourceWorker(mysql_adapter.get_connection,lambda:NOW).run_once()


def click(token,user,group,decision='normal',*,rollback=False):
    event=SimpleNamespace(event_id=SimpleNamespace(value=uuid4().hex),occurred_at=NOW,
        source=SimpleNamespace(source_type=LineSourceType.GROUP,user_id=LineUserId(user),group_id=LineGroupId(group)),
        payload_json=json.dumps({'postback':{'data':f'start-day:{token}:{decision}'}}))
    with units() as unit:
        assert ServiceStartDayPostbackApplication().handle(SimpleNamespace(event=event),unit)
        if not rollback:unit.commit()


class TaskScopedWorker(LineDeliveryWorker):
    def __init__(self,task_id,now=NOW):
        self.target=LineDeliveryTaskId(task_id);self.calls=[]
        provider=SimpleNamespace(send=lambda request:self.send(request))
        super().__init__(units,provider,'synthetic-start-day',lambda:now,batch_size=1)
    def send(self,request):
        self.calls.append(request)
        return LineProviderOutcome(LineProviderOutcomeType.SUCCESS)
    def _claim(self):
        with units() as unit:
            task=unit.delivery_tasks.claim_specific(self.target,ClaimLineDeliveryTasksQuery(self._worker_identity,self._now(),1))
            unit.commit()
        return (task,) if task else ()


def test_real_scan_group_card_replay_and_fake_delivery(http):
    case,staff,_,group=prepared(http)
    before=rows('SELECT lifecycle_version,actual_start_date FROM orders WHERE case_no=%s',(case,))
    scan();scan()
    notices=tasks(case);assert len(notices)==1
    notice=notices[0]
    assert notice['recipient_type']=='group' and notice['recipient_identity']==group
    payload=json.loads(notice['payload_snapshot'])
    assert [b['action']['label'] for b in payload['contents']['footer']['contents']]==['服務正常','需要協助']
    assert '第一期款尚待繳納' in payload['contents']['body']['contents'][0]['text']
    worker=TaskScopedWorker(notice['id']);assert worker.run_once()==1
    assert len(worker.calls)==1 and worker.calls[0].recipient.identity.value==group
    scan();assert len(tasks(case))==1
    assert rows('SELECT lifecycle_version,actual_start_date FROM orders WHERE case_no=%s',(case,))==before


def test_paid_first_stage_omits_payment_paragraph_with_real_bank_owner(http):
    case,staff,_,group=prepared(http)
    amount=rows("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='first' AND status='open'",(case,))[0]['amount_due_ntd']
    existing['h']['bank'](http,case,amount,2)
    scan()
    payload=json.loads(tasks(case)[0]['payload_snapshot'])
    text=payload['contents']['body']['contents'][0]['text']
    assert '第一期款尚待繳納' not in text and '請問今天的服務是否順利' in text
    assert candidate(case).first_payment_amount==0


def test_group_actor_normal_help_idempotency_and_rollback(http):
    case,staff,_,group=prepared(http);scan();context=candidate(case)
    before=rows('SELECT lifecycle_version,actual_start_date FROM orders WHERE case_no=%s',(case,))
    for user,where in [(staff[1][1],group),(staff[0][1],'C_OTHER_GROUP')]:click(context.token,user,where,'help')
    assert not rows('SELECT id FROM customer_service_tickets WHERE case_no=%s',(case,))
    click(context.token,staff[0][1],group,'help',rollback=True)
    assert not rows('SELECT id FROM customer_service_tickets WHERE case_no=%s',(case,))
    click(context.token,staff[0][1],group)
    click(context.token,staff[0][1],group)
    click(context.token,staff[0][1],group,'help');click(context.token,staff[0][1],group,'help')
    assert len(rows('SELECT id,status FROM customer_service_tickets WHERE case_no=%s',(case,)))==1
    acks=tasks(context.token,'order_service_start_day_response')
    assert len(acks)==2 and all(item['recipient_identity']==group for item in acks)
    assert rows('SELECT lifecycle_version,actual_start_date FROM orders WHERE case_no=%s',(case,))==before
    # The actual customer-service read model exposes the service-progress need.
    with units() as unit:
        ticket=unit.customer_service.get(rows('SELECT id FROM customer_service_tickets WHERE case_no=%s',(case,))[0]['id'])
        assert ticket.status.value in ('waiting','handling') and ticket.case_no==case
        from subsystems.customer_service.contracts import CustomerServiceReminderQuery, CustomerServiceReminderSource
        page=unit.customer_service.list_reminders(CustomerServiceReminderQuery(source=CustomerServiceReminderSource.SERVICE,search=case))
        assert page.total==1 and page.items[0].case_no==case


@pytest.mark.parametrize('change',['date','group','schedule','binding','payment'])
def test_fresh_provider_or_actor_guard_rejects_stale_context(http,change):
    case,staff,_,group=prepared(http);scan();context=candidate(case);notice=tasks(case)[0]
    if change=='date':
        # Use the existing formal date writer, not a replacement Orders fact.
        checked(existing['submit'](http,case,staff[0],existing['rows']('SELECT segment_id FROM scheduling_service_start_requests WHERE case_no=%s ORDER BY id DESC LIMIT 1',(case,))[0]['segment_id'],start=(DAY+timedelta(days=1)).isoformat())[0])
    elif change=='group':
        write("UPDATE line_order_group_bindings SET binding_status='released',aggregate_version=aggregate_version+1 WHERE case_no=%s",(case,))
    elif change=='schedule':
        write('UPDATE staff_schedule SET effective_marker=NULL WHERE assignment_id IN (SELECT id FROM case_staff_assignments WHERE case_no=%s)',(case,))
    elif change=='binding':
        write("UPDATE line_identity_role_bindings SET binding_status='revoked' WHERE line_user_id=%s AND subject_type='staff'",(staff[0][1],))
    else:
        amount=rows("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='first' AND status='open'",(case,))[0]['amount_due_ntd']
        existing['h']['bank'](http,case,amount,2)
    if change!='binding':
        worker=TaskScopedWorker(notice['id']);worker.run_once()
        assert not worker.calls
        assert tasks(case)[0]['processing_status']=='cancelled'
    if change!='payment':
        click(context.token,staff[0][1],group,'help')
        assert not rows('SELECT id FROM customer_service_tickets WHERE case_no=%s',(case,))
    else:
        scan();assert len(tasks(case))==2
        assert '第一期款尚待繳納' not in json.loads(tasks(case)[1]['payload_snapshot'])['contents']['body']['contents'][0]['text']


def test_no_group_or_planned_date_only_never_falls_back_to_private(http):
    case,staff,_,group=prepared(http)
    write("UPDATE line_order_group_bindings SET binding_status='released',aggregate_version=aggregate_version+1 WHERE case_no=%s",(case,))
    assert candidate(case) is None
    scan();assert not tasks(case)
    case2,staff2,_=existing['seed_case'](http)
    with units() as unit:
        assert unit.service_start_days.current(case2,date(2027,1,1)) is None


def test_all_live_group_binding_states_and_today_only(http):
    case,staff,_,group=prepared(http)
    for status in ('bound','inviting','active','attention'):
        write('UPDATE line_order_group_bindings SET binding_status=%s WHERE case_no=%s',(status,case))
        assert candidate(case).group_id==group
        with units() as unit:
            recipient=unit.notification_rules._resolve_recipient('case_group',candidate(case).facts(),
                source_domain='orders',event_code='order.service_start_day')
            assert recipient.identity.value==group
            assert unit.service_start_days.current(case,DAY+timedelta(days=1)) is None
    scan();assert len(tasks(case))==1


def test_multi_caregiver_only_first_day_assignee_can_respond(http):
    case,staff,segments=existing['seed_case'](http,count=2)
    checked(existing['submit'](http,case,staff[0],segments[0],start=DAY.isoformat())[0])
    checked(existing['submit'](http,case,staff[1],segments[1],start=(DAY+timedelta(days=30)).isoformat())[0])
    scan();context=candidate(case)
    assert [item.staff_id for item in context.caregivers]==[staff[0][0]]
    click(context.token,staff[1][1],context.group_id,'help')
    assert not rows('SELECT id FROM customer_service_tickets WHERE case_no=%s',(case,))
    click(context.token,staff[0][1],context.group_id)
    assert len(tasks(context.token,'order_service_start_day_response'))==1


def test_concurrent_help_clicks_create_one_todo_and_group_ack(http):
    from concurrent.futures import ThreadPoolExecutor
    case,staff,_,group=prepared(http);scan();context=candidate(case)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures=[executor.submit(click,context.token,staff[0][1],group,'help') for _ in range(2)]
        for future in futures:future.result(timeout=20)
    assert len(rows('SELECT id FROM customer_service_tickets WHERE case_no=%s',(case,)))==1
    assert len(tasks(context.token,'order_service_start_day_response'))==1

"""Opt-in real MySQL verification, using only a newly created lu_test_* database.

Copies schema metadata (never data) from the localhost development database.
The canonical configuration, queue, receipt, and webhook repositories are real;
the sole outbound provider is an in-process fake. The owned database is dropped
in fixture teardown; the application database is never written.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date,datetime,timedelta,timezone
from itertools import count
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4
import os,re

import pytest

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import LineDeliveryTaskId,LineDestinationId,LineSourceIdentity,LineSourceType,LineUserId,LineWebhookEventId,LineProviderMessageId
from domains.line.webhook import CanonicalLineWebhookEvent
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.line.delivery_contracts import ClaimLineDeliveryTasksQuery,LineProviderOutcome,LineProviderOutcomeType,CancelLineDeliveryTaskCommand
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.deposit_notifications import DepositNotificationApplication
from subsystems.line.payment_reminder_notifications import PaymentReminderNotificationWorker,FOLLOWUP
from subsystems.line.payment_overdue_reminders import PaymentOverdueReminderApplication,PaymentOverdueReminderConflict
from shared_kernel.identities import ActorContext
from shared_kernel.identities import IdempotencyKey,CorrelationId
from domains.line.configuration import LineConfigurationKind,LineConfigurationRevisionConflict
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.capabilities import LineCapability
from subsystems.line.payment_reminder_schedule import PaymentReminderSchedule
from dataclasses import asdict
import json

pytestmark=pytest.mark.skipif(os.getenv('RUN_PAYMENT_REMINDER_MYSQL')!='1',reason='explicit opt-in disposable localhost MySQL verification')
NOW=datetime(2026,11,5,1,tzinfo=timezone.utc)
TABLES=('clients','orders','order_contract_flow_events','client_finance_accounts','client_obligations','client_obligation_events',
    'client_payment_terms','line_platform_users','line_identity_role_bindings','line_delivery_tasks','line_delivery_attempt_events',
    'line_domain_audit_events','line_inbox_events','line_command_receipts','line_configuration_current','line_configuration_revisions',
    'client_deposit_settlement_projection','client_ledger_entries','client_legacy_virtual_accounts')


@pytest.fixture(scope='module')
def isolated_database():
    assert os.getenv('APP_ENV')=='development'
    assert mysql_adapter.DB_CONFIG['host'] in ('localhost','127.0.0.1')
    origin=mysql_adapter.DB_CONFIG['database']
    assert origin=='union_db' or origin.startswith('lu_test_')
    assert re.fullmatch(r'[A-Za-z0-9_]+',origin)
    owned='lu_test_payment_reminders_'+uuid4().hex[:12]
    admin=mysql_adapter.get_connection()
    created=False
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{owned}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            created=True
            for table in TABLES:
                cursor.execute(f'CREATE TABLE `{owned}`.`{table}` LIKE `{origin}`.`{table}`')
        with pytest.MonkeyPatch.context() as patch:
            patch.setitem(mysql_adapter.DB_CONFIG,'database',owned)
            yield owned
    finally:
        if created:
            assert re.fullmatch(r'lu_test_payment_reminders_[0-9a-f]{12}',owned) and owned!=origin
            with admin.cursor() as cursor:cursor.execute(f'DROP DATABASE `{owned}`')
        admin.close()


@pytest.fixture
def runtime(isolated_database):
    clock=[NOW]
    def units():
        unit=LineMySqlUnitOfWork(mysql_adapter.get_connection())
        # This workflow creates no notification-rule intents. Their optional
        # anomaly projection is outside the queue/Finance/reply transaction oracle.
        unit.notification_rules=SimpleNamespace()
        return unit
    def execute(sql,params=()):
        connection=mysql_adapter.get_connection()
        try:
            with connection.cursor() as cursor:cursor.execute(sql,params);identity=cursor.lastrowid
            connection.commit();return identity
        finally:connection.close()
    def rows(sql,params=()):
        connection=mysql_adapter.get_connection()
        try:
            with connection.cursor() as cursor:cursor.execute(sql,params);return tuple(cursor.fetchall())
        finally:connection.close()
    deposit=DepositNotificationApplication(units,lambda:clock[0],liff_id='synthetic-liff',bank_code='807')
    return SimpleNamespace(units=units,execute=execute,rows=rows,clock=clock,worker=PaymentReminderNotificationWorker(units,lambda:clock[0],deposit))


identities=count(1)
def seed(rt,stage='first',amount=24000):
    case='116'+str(next(identities)).zfill(6);user='U'+uuid4().hex;obligation=case+':'+stage
    client=rt.execute("INSERT INTO clients(case_no,name,identity_status,service_type,created_at,line_user_id) VALUES (%s,'Synthetic reminder','一般市民','連續服務','2026-11-01',%s)",(case,user))
    first_due='2026-10-21' if stage=='second' else '2026-11-05'
    second_due='2026-11-05' if stage=='second' else '2026-11-20'
    rt.execute("INSERT INTO orders(case_no,client_id,status,actual_start_date,contract_identity) VALUES (%s,%s,'服務中',%s,%s)",(case,client,first_due,case+':signed'))
    rt.execute("INSERT INTO order_contract_flow_events(case_no,contract_identity,event_type,actor,reason,idempotency_key) VALUES (%s,%s,'contract_completed','synthetic','both parties signed',%s)",(case,case+':signed',case+':signed'))
    rt.execute('INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,1)',(case,))
    event=rt.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,'receivable_from_client','established',0,%s,%s,0,%s,'synthetic','fixture')",(obligation,case,stage,amount,case+':source',case+':event'))
    rt.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,%s,'receivable_from_client',%s,'2026-11-05',%s,%s,1)",(obligation,case,stage,amount,'open' if amount else 'settled',event))
    rt.execute("INSERT INTO client_payment_terms(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) VALUES (%s,'synthetic',350,3,'2026-11-05',%s,%s,%s)",(case,first_due,second_due,event))
    rt.execute("INSERT INTO line_platform_users(line_user_id,friend_status) VALUES (%s,'active')",(user,))
    rt.execute("INSERT INTO line_identity_role_bindings(line_user_id,subject_type,subject_reference,binding_status) VALUES (%s,'customer',%s,'bound')",(user,str(client)))
    return case,obligation,user


def tasks(rt,identity):return rt.rows('SELECT id,processing_status,source_aggregate_type,recipient_type,recipient_identity FROM line_delivery_tasks WHERE source_aggregate_identity=%s ORDER BY id',(identity,))


def deliver(rt,identity):
    calls=[]
    class Worker(LineDeliveryWorker):
        def _claim(self):
            with rt.units() as unit:
                task=unit.delivery_tasks.claim_specific(LineDeliveryTaskId(identity),ClaimLineDeliveryTasksQuery('synthetic-payment-reminders',rt.clock[0],1))
                unit.commit()
            return (task,) if task else ()
    def fake(request):
        calls.append(request)
        return LineProviderOutcome(LineProviderOutcomeType.SUCCESS,provider_message_id=LineProviderMessageId('synthetic-'+uuid4().hex))
    Worker(rt.units,SimpleNamespace(send=fake),'synthetic-payment-reminders',lambda:rt.clock[0],batch_size=1).run_once()
    return calls


def reply(rt,user,kind='message',source='user',at=None):
    value={'type':kind,'source':{'type':source,'userId':user},'message':{'type':'text','text':'synthetic reply'}}
    event=CanonicalLineWebhookEvent(LineWebhookEventId('synthetic-'+uuid4().hex),LineDestinationId('synthetic'),kind,
        LineSourceIdentity(LineSourceType.USER if source=='user' else LineSourceType.GROUP,user if source=='user' else 'C-synthetic',LineUserId(user)),
        at or rt.clock[0],fingerprint_payload(value),payload_json=canonical_line_payload_json(value))
    with rt.units() as unit:unit.webhook_inbox.register(event);unit.commit()


@pytest.mark.parametrize('stage',['deposit','first','second'])
def test_real_queue_success_followup_and_unpaid_todo_remain_private(runtime,stage):
    rt=runtime;_,identity,user=seed(rt,stage)
    assert rt.worker._queue(identity)==1 and rt.worker._queue(identity)==0
    first=tasks(rt,identity)[0]
    assert first['recipient_type']=='user' and first['recipient_identity']==user
    assert len(deliver(rt,first['id']))==1
    assert tasks(rt,identity)[0]['processing_status']=='sent'
    rt.clock[0]=NOW+timedelta(days=1,hours=1)
    assert rt.worker._queue(identity)==1 and rt.worker._queue(identity)==0
    second=tasks(rt,identity)[1]
    assert second['source_aggregate_type']==FOLLOWUP and len(deliver(rt,second['id']))==1
    rt.clock[0]+=timedelta(days=7)
    assert rt.worker._queue(identity)==0 and len(tasks(rt,identity))==2
    with rt.units() as unit:
        todos,total=unit.payment_overdue_reminders.list(rt.clock[0].date(),1,100)
    assert any(todo.payment.obligation_identity==identity and todo.recipient_label=='客戶私人聊天室' for todo in todos)


@pytest.mark.parametrize('kind',['message','postback'])
def test_any_verified_private_reply_cancels_pending_followup_before_fake_provider(runtime,kind):
    rt=runtime;_,identity,user=seed(rt)
    rt.worker._queue(identity);deliver(rt,tasks(rt,identity)[0]['id'])
    rt.clock[0]=NOW+timedelta(days=1,hours=1)
    rt.worker._queue(identity)
    pending=tasks(rt,identity)[1]
    reply(rt,user,kind)
    before=rt.rows('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s',(identity,))
    assert deliver(rt,pending['id'])==[]
    assert tasks(rt,identity)[1]['processing_status']=='cancelled'
    assert rt.rows('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s',(identity,))==before
    rt.execute('DELETE FROM line_inbox_events WHERE source_user_id=%s',(user,))
    assert rt.worker._queue(identity)==0  # Existing handoff receipt survives inbox lifecycle.
    # Automatic stop does not block the existing human command.
    with rt.units() as unit:payment=unit.payment_overdue_reminders.payment(identity)
    result=PaymentOverdueReminderApplication(rt.units,lambda:rt.clock[0]).send(payment,uuid4().hex,ActorContext('synthetic-union'))
    assert len(deliver(rt,result[0]))==1


@pytest.mark.parametrize('noise',['group','other_user','follow'])
def test_only_current_customer_private_replies_after_original_send_suppress_followup(runtime,noise):
    rt=runtime;_,identity,user=seed(rt)
    reply(rt,user,at=NOW-timedelta(seconds=1))
    rt.worker._queue(identity);deliver(rt,tasks(rt,identity)[0]['id'])
    rt.clock[0]=NOW+timedelta(days=1,hours=1)
    if noise=='group':reply(rt,user,source='group')
    elif noise=='other_user':reply(rt,'U'+uuid4().hex)
    else:reply(rt,user,kind='follow')
    assert rt.worker._queue(identity)==1


def test_native_zero_first_greets_but_zero_or_ambiguous_second_never_queues(runtime):
    rt=runtime;_,first,_=seed(rt,'first',0)
    assert rt.worker._queue(first)==1
    payload=rt.rows('SELECT payload_snapshot FROM line_delivery_tasks WHERE source_aggregate_identity=%s',(first,))[0]['payload_snapshot']
    assert '祝服務順利' in str(payload) and '未確認入帳' not in str(payload)
    _,zero,_=seed(rt,'second',0)
    assert rt.worker._queue(zero)==0
    case,second,_=seed(rt,'second')
    rt.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) SELECT %s,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version FROM client_obligations WHERE obligation_identity=%s",(case+':other-second',second))
    assert rt.worker._queue(second)==0 and not tasks(rt,second)


def test_concurrent_scans_create_one_work_and_manual_different_key_is_conflict(runtime):
    rt=runtime;_,identity,_=seed(rt);start=Barrier(2)
    def queue(_):start.wait(timeout=10);return rt.worker._queue(identity)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(queue,range(2)))
    assert sorted(results)==[0,1] and len(tasks(rt,identity))==1
    with rt.units() as unit:payment=unit.payment_overdue_reminders.payment(identity)
    rt.clock[0]+=timedelta(days=1)
    with pytest.raises(PaymentOverdueReminderConflict,match='in_flight'):
        PaymentOverdueReminderApplication(rt.units,lambda:rt.clock[0]).send(payment,uuid4().hex,ActorContext('synthetic-union'))


def test_cancelled_unchanged_initial_is_not_requeued_or_false_idempotency_conflict(runtime):
    rt=runtime;_,identity,_=seed(rt)
    rt.worker._queue(identity);work=tasks(rt,identity)[0]
    with rt.units() as unit:
        task=unit.delivery_tasks.get(LineDeliveryTaskId(work['id']))
        unit.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(task.task_id,ActorContext('synthetic-union'),IdempotencyKey(uuid4().hex),task.request.correlation_id))
        unit.commit()
    rt.clock[0]+=timedelta(minutes=1)
    assert rt.worker._queue(identity)==0
    assert len(tasks(rt,identity))==1 and tasks(rt,identity)[0]['processing_status']=='cancelled'


def test_schedule_is_persisted_by_real_configuration_writer_and_stale_revision_conflicts(runtime):
    rt=runtime;app=LineConfigurationApplication(rt.units)
    actor=ActorContext('synthetic-schedule',tuple(sorted((LineCapability.CONFIG_READ.value,LineCapability.CONFIG_MANAGE.value))))
    current=app.get(LineConfigurationKind.MESSAGE_SCHEDULES,actor)
    definition={'timezone':'Asia/Taipei','schedules':[],'retained_setting':{'value':'preserved'},
        'payment_reminders':{**asdict(PaymentReminderSchedule()),'first_time':'11:30'}}
    key=IdempotencyKey(uuid4().hex)
    result=app.apply(kind=LineConfigurationKind.MESSAGE_SCHEDULES,expected_revision=current.revision,
        definition=definition,actor=actor,reason='synthetic schedule verification',
        idempotency_key=key,correlation_id=CorrelationId(uuid4().hex))
    readback=app.get(LineConfigurationKind.MESSAGE_SCHEDULES,actor)
    assert readback.revision==result.snapshot.revision
    assert json.loads(readback.definition_json)==definition
    assert app.get_applied(LineConfigurationKind.MESSAGE_SCHEDULES,key,actor)==readback
    with pytest.raises(LineConfigurationRevisionConflict):
        app.apply(kind=LineConfigurationKind.MESSAGE_SCHEDULES,expected_revision=current.revision,
            definition=definition,actor=actor,reason='stale verification',
            idempotency_key=IdempotencyKey(uuid4().hex),correlation_id=CorrelationId(uuid4().hex))

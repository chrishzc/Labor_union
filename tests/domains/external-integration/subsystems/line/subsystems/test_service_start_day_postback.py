"""Group actor authorization, repeated clicks and committed-work boundaries."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest

from domains.line.delivery import LineMessageKind
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from domains.line.identities import LineSourceIdentity, LineSourceType, LineUserId
from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
from subsystems.line.service_start_day import (
    GREETING_SOURCE, ServiceStartDayCandidate, StartDayCaregiver, ServiceStartDayGreetingWorker,
    ServiceStartDayPaymentReply, greeting_reference, start_day_delivery_is_current,
)

CANDIDATE = ServiceStartDayCandidate('CASE-001', date(2026,10,23), 'C_ORIGINAL', 7, 12000,
                                      (StartDayCaregiver(1, '測試月嫂'),))


def inbox(text, user='U_STAFF'):
    return SimpleNamespace(event=SimpleNamespace(
        event_id=SimpleNamespace(value=uuid4().hex), occurred_at=datetime(2026,10,23,tzinfo=timezone.utc),
        source=LineSourceIdentity(LineSourceType.GROUP, 'C_ORIGINAL', LineUserId(user)),
        payload_json=json.dumps({'message':{'type':'text','text':text}})))


class Unit:
    def __init__(self):
        self.recorded={};self.tasks=[];self.commits=0
        self.receipts=SimpleNamespace(get=lambda key,**_:self.recorded.get(key.value),
                                     append=lambda receipt:self.recorded.setdefault(receipt.key.value,receipt))
        self.delivery_tasks=SimpleNamespace(enqueue=self.tasks.append)
        self.service_start_days=SimpleNamespace()
    def commit(self): self.commits+=1


@pytest.mark.parametrize('retired,current,expected',[(True,True,False),(False,False,False),(False,True,False)])
def test_provider_guard_cancels_retired_or_stale_work(retired,current,expected):
    unit=Unit();cancelled=[]
    unit.delivery_tasks.cancel=cancelled.append
    unit.service_start_days.delivery_is_current=lambda *_:current
    task=SimpleNamespace(task_id=SimpleNamespace(value=10),request=SimpleNamespace(
        source_aggregate_type='order_service_start_day',
        correlation_id=SimpleNamespace(value=('line-notification:order-pre-start-reminder:case:date' if retired else 'current'))))
    assert start_day_delivery_is_current(unit,task,datetime.now(timezone.utc)) is expected
    assert len(cancelled)==(0 if expected else 1)
    assert unit.commits==(0 if expected else 1)


class GreetingUnit(Unit):
    def __init__(self, amount):
        super().__init__()
        self.now = datetime(2026,10,23,1,tzinfo=timezone.utc)
        self.payment = None if amount is None else OverdueClientPayment('CASE-001','first','payment-1',1,1,CANDIDATE.service_date,amount)
        self.service_start_days = SimpleNamespace(
            due_cases=lambda day, after: (CANDIDATE.case_no,) if day == CANDIDATE.service_date else (),
            current=lambda case_no, day, **_: CANDIDATE,
            first_payment=lambda case_no: self.payment if self.payment and self.payment.remaining_amount_ntd else None,
            has_greeting=lambda case_no, day: any(row.status != 'cancelled' for row in self.tasks),
            delivery_is_current=lambda task, now: task.request.correlation_id.value == greeting_reference(CANDIDATE,self.service_start_days.first_payment(CANDIDATE.case_no)),
        )
        self.delivery_tasks = SimpleNamespace(
            enqueue=self.enqueue,
            exists_for_key=lambda key: any(row.request.idempotency_key == key for row in self.tasks),
            cancel=lambda command: setattr(self.tasks[command.task_id.value-1], 'status', 'cancelled'),
        )
        self.configurations = SimpleNamespace(get=lambda kind: SimpleNamespace(revision=SimpleNamespace(value=1),definition_json='{}'))
        self.audit = SimpleNamespace(append=lambda _:None)
        self.worker = ServiceStartDayGreetingWorker(lambda:self,lambda:self.now)

    def __enter__(self):
        return self

    def __exit__(self,*_):
        return False

    def enqueue(self, request):
        task = SimpleNamespace(task_id=SimpleNamespace(value=len(self.tasks)+1),request=request,status='pending')
        self.tasks.append(task)
        return task


@pytest.mark.parametrize('amount',[None,0,12000])
def test_opening_sends_one_plain_group_message_any_first_payment_state(amount):
    unit=GreetingUnit(amount)
    assert unit.worker.run_once()==1
    assert unit.worker.run_once()==0
    request=unit.tasks[0].request
    payload=json.loads(request.payload_json)
    assert request.source_aggregate_type==GREETING_SOURCE
    assert request.recipient.identity.value=='C_ORIGINAL'
    assert request.message_kind is LineMessageKind.TEXT
    assert set(payload)=={'type','text'} and payload['type']=='text'
    assert '祝服務順利' in payload['text']
    assert '正常服務' not in payload['text'] and '需要協助' not in payload['text']
    assert ('已經匯款' in payload['text']) is bool(amount)
    assert ('第一期款' in payload['text']) is bool(amount)
    assert ('12,000' in payload['text']) is bool(amount)


def test_stale_unsent_opening_is_replaced_with_greeting_after_settlement():
    unit=GreetingUnit(12000)
    assert unit.worker.run_once()==1
    unit.payment=None
    assert not start_day_delivery_is_current(unit, unit.tasks[0], unit.now)
    assert unit.worker.run_once()==1
    assert '第一期款' not in json.loads(unit.tasks[1].request.payload_json)['text']
    assert unit.worker.run_once()==0


def test_opening_schedule_never_backfills_past_days():
    unit=GreetingUnit(None)
    unit.now+=timedelta(days=1)
    assert unit.worker.run_once()==0
    assert not unit.tasks


def test_provider_guard_reuses_claim_for_same_task_and_blocks_replacement_if_payment_changes():
    unit=GreetingUnit(12000)
    assert unit.worker.run_once()==1
    assert start_day_delivery_is_current(unit,unit.tasks[0],unit.now)
    assert start_day_delivery_is_current(unit,unit.tasks[0],unit.now)
    assert len(unit.recorded)==1
    unit.payment=None
    assert not start_day_delivery_is_current(unit,unit.tasks[0],unit.now)
    assert unit.worker.run_once()==0


def test_prior_flex_configuration_renders_a_plain_opening_with_fixed_text_commands():
    from subsystems.line.message_copy_catalog import render_copy_payload

    prior={'templates':[{'id':'LINE-COPY-payment-first-reminder','message_type':'text',
        'content':'{"contents/header/contents/0/text":"舊卡片標題"}', 'copy_fields':[], 'variables':[]}]}
    values={'case_no':'CASE-001','amount_ntd':'12,000','due_date':'2026-10-23'}
    payload=render_copy_payload(prior,'payment-first-reminder',{'type':'text','text':''},values)
    assert set(payload)=={'type','text'} and '12,000' in payload['text'] and '舊卡片標題' not in payload['text']
    draft=render_copy_payload(prior,'payment-first-reminder',payload,values,'測試 {case_no}\n未付款 {amount_ntd}，請在 {due_date} 前繳款。')
    assert draft['text'].startswith('測試 CASE-001\n')
    assert '12,000' in draft['text'] and '2026-10-23' in draft['text']
    assert '正常服務' not in draft['text'] and '需要協助' not in draft['text']
    assert draft['text'].count('已經匯款')==1


@pytest.mark.parametrize('command', ['正常服務', '需要協助'])
def test_retired_service_commands_have_no_effect(command):
    unit = Unit()
    assert not ServiceStartDayPaymentReply().handle_message(inbox(command), unit)
    assert not unit.tasks and not unit.recorded


def test_opening_payment_command_keeps_payment_reply_and_handoff(monkeypatch):
    unit = Unit()
    unit.service_start_days.payment_reply_context = lambda group, day, user: (CANDIDATE, 1) if user == 'U_CUSTOMER' else None
    calls = []
    monkeypatch.setattr('subsystems.line.deposit_notifications.handle_payment_reminder_postback',
                        lambda data, event, unit: calls.append(data) or True)
    application = ServiceStartDayPaymentReply()
    assert not application.handle_message(inbox('已經匯款'), unit)
    assert application.handle_message(inbox('已經匯款', 'U_CUSTOMER'), unit)
    assert calls == ['payment-ack:first:CASE-001']
    assert 'payment-reminder-replied:1' in unit.recorded


def test_old_opening_payment_help_replies_in_group_and_stops_private_followup(monkeypatch):
    unit = Unit()
    unit.service_start_days.payment_reply_context = lambda *_: (CANDIDATE, 1)
    calls = []
    monkeypatch.setattr('subsystems.line.deposit_notifications.handle_payment_reminder_postback',
                        lambda data, event, unit, *, reply_only: calls.append((data, reply_only)) or True)

    assert ServiceStartDayPaymentReply().handle_message(inbox('有疑問需要解決', 'U_CUSTOMER'), unit)
    assert calls == [('payment-assistance:first:CASE-001', True)]
    assert 'payment-reminder-replied:1' in unit.recorded


@pytest.mark.parametrize('key', ['ack:start-day-response:old', 'ack:opening-greeting-response:old'])
def test_pending_service_status_replies_cancel_before_delivery(key):
    unit = Unit()
    cancelled = []
    unit.delivery_tasks.cancel = cancelled.append
    task = SimpleNamespace(task_id=SimpleNamespace(value=10), request=SimpleNamespace(
        source_aggregate_type=REPLY_ONLY_WEBHOOK_SOURCE,
        idempotency_key=SimpleNamespace(value=key),
        correlation_id=SimpleNamespace(value='line-event:old')))
    assert not start_day_delivery_is_current(unit, task, datetime.now(timezone.utc))
    assert len(cancelled) == 1


def test_pending_greeting_with_retired_report_is_replaced_before_delivery(monkeypatch):
    from dataclasses import replace
    from domains.line.canonical_payload import canonical_line_payload_json
    from shared_kernel.fingerprints import fingerprint_payload
    from subsystems.line import service_start_day

    unit = GreetingUnit(None)
    original = service_start_day.greeting_reference
    monkeypatch.setattr(service_start_day, 'greeting_reference', lambda ctx, payment: (
        service_start_day.greeting_correlation_prefix(ctx.service_date, None)
        + fingerprint_payload(ctx.facts()).value))
    assert unit.worker.run_once() == 1
    task = unit.tasks[0]
    task.request = replace(task.request, payload_json=canonical_line_payload_json({
        'type': 'text', 'text': '祝服務順利！請在群組輸入「正常服務」或「需要協助」。',
    }))
    monkeypatch.setattr(service_start_day, 'greeting_reference', original)
    assert not start_day_delivery_is_current(unit, task, unit.now)
    assert unit.worker.run_once() == 1
    assert '正常服務' not in json.loads(unit.tasks[1].request.payload_json)['text']

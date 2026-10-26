"""Group actor authorization, repeated clicks and committed-work boundaries."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest

from domains.line.identities import LineSourceType, LineUserId, LineGroupId
from subsystems.line.service_start_day import (
    ServiceStartDayCandidate, StartDayCaregiver, ServiceStartDayPostbackApplication,
    start_day_delivery_is_current,
)

CANDIDATE = ServiceStartDayCandidate('CASE-001', date(2026,10,23), 'C_ORIGINAL', 7, 12000,
                                      (StartDayCaregiver(1, '測試月嫂'),))


def inbox(decision='normal', *, group='C_ORIGINAL', user='U_STAFF', source=LineSourceType.GROUP):
    return SimpleNamespace(event=SimpleNamespace(
        event_id=SimpleNamespace(value=uuid4().hex), occurred_at=datetime(2026,10,23,tzinfo=timezone.utc),
        source=SimpleNamespace(source_type=source, user_id=LineUserId(user) if user else None,
                               group_id=LineGroupId(group) if group else None),
        payload_json=json.dumps({'postback':{'data':f'start-day:{CANDIDATE.token}:{decision}'}})))


class Unit:
    def __init__(self):
        self.recorded={};self.tasks=[];self.tickets=[];self.commits=0
        self.receipts=SimpleNamespace(get=lambda key,**_:self.recorded.get(key.value),
                                     append=lambda receipt:self.recorded.setdefault(receipt.key.value,receipt))
        self.delivery_tasks=SimpleNamespace(enqueue=self.tasks.append)
        self.service_start_days=SimpleNamespace(response_context=lambda token,group,user:
            CANDIDATE if group=='C_ORIGINAL' and user=='U_STAFF' else None)
        self.customer_service=SimpleNamespace(create_or_append=self.create_ticket)
    def create_ticket(self,command):
        self.tickets.append(command);return SimpleNamespace(ticket_id=1)
    def commit(self): self.commits+=1


@pytest.mark.parametrize('decision',['normal','help'])
def test_authorized_response_and_repeated_event_ids_have_one_effect(decision):
    unit=Unit();app=ServiceStartDayPostbackApplication()
    assert app.handle(inbox(decision),unit)
    assert app.handle(inbox(decision),unit)
    assert len(unit.tasks)==len(unit.recorded)==1
    assert len(unit.tickets)==(1 if decision=='help' else 0)
    assert unit.tasks[0].recipient.recipient_type.value=='group'
    assert unit.tasks[0].recipient.identity.value=='C_ORIGINAL'
    expected='已收到，祝您服務順利。' if decision=='normal' else '已收到您的協助需求，請留下遇到的狀況。'
    assert json.loads(unit.tasks[0].payload_json)['text']==expected
    assert unit.commits==0  # caller owns atomic commit
    if decision=='help':
        assert unit.tickets[0].case_no=='CASE-001'
        assert '服務開始日協助需求' in unit.tickets[0].message


def test_normal_reply_does_not_prevent_later_assistance():
    unit=Unit();app=ServiceStartDayPostbackApplication()
    app.handle(inbox('normal'),unit);app.handle(inbox('help'),unit)
    assert len(unit.tasks)==2 and len(unit.tickets)==1


@pytest.mark.parametrize('options',[
    {'user':'U_CUSTOMER'}, {'user':'U_OTHER_STAFF'}, {'user':'U_ADMIN'},
    {'group':'C_OTHER'}, {'user':None}, {'group':None}, {'source':LineSourceType.USER},
])
def test_unqualified_or_forwarded_click_has_no_effect(options):
    unit=Unit()
    assert ServiceStartDayPostbackApplication().handle(inbox('help',**options),unit)
    assert not unit.recorded and not unit.tickets and not unit.tasks


def test_stale_context_cannot_create_need_or_success_ack():
    unit=Unit();unit.service_start_days.response_context=lambda *_:None
    assert ServiceStartDayPostbackApplication().handle(inbox('help'),unit)
    assert not unit.recorded and not unit.tickets and not unit.tasks


def test_unrelated_or_malformed_postback_cannot_mutate():
    unit=Unit();app=ServiceStartDayPostbackApplication()
    event=inbox();event.event.payload_json=json.dumps({'postback':{'data':'unrelated'}})
    assert not app.handle(event,unit)
    event.event.payload_json=json.dumps({'postback':{'data':'start-day:bad:help'}})
    assert app.handle(event,unit)
    assert not unit.tasks


@pytest.mark.parametrize('retired,current,expected',[(True,True,False),(False,False,False),(False,True,True)])
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

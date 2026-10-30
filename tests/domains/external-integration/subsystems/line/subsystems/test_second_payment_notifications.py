"""Second-stage eligibility, short group copy, source replacement and egress guards."""
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from domains.line.notification_rules import validate_notification_rules, LineNotificationRuleError
from subsystems.line.second_payment_notifications import (
    SecondPaymentNotification, DUE_EVENT, SETTLED_EVENT, REMINDER, SETTLED, second_payment_delivery_is_current,
)
from subsystems.line.message_configuration import render_message_template

NOW=datetime(2026,10,23,3,tzinfo=timezone.utc)
PAYMENT=SecondPaymentNotification('CASE-SECOND','second:1',4,8,date(2026,10,23),12000,12000,'C_ORIGINAL')


@pytest.mark.parametrize('paid',[False,True])
def test_current_rules_short_copy_and_group_only(paid):
    value=replace(PAYMENT,remaining_amount=0,settled=True,settlement_identity='a'*64,settled_amount=12000) if paid else PAYMENT
    event=value.event(NOW)
    assert event.event_code==(SETTLED_EVENT if paid else DUE_EVENT)
    rules=json.loads(Path('config/notification_rules.json').read_text(encoding='utf-8'))
    rule=next(r for r in rules['rules'] if r['event_code']==event.event_code)
    assert rule['recipient_selector']=='case_group' and rule['schedule']=={'kind':'immediate'} and rule['frequency']=={'kind':'once'}
    templates=json.loads(Path('config/message_templates.json').read_text(encoding='utf-8'))
    message=json.loads(render_message_template(templates,rule['template_id'],{
        'case_no':value.case_no,'second_payment_amount':event.facts['second_payment_amount'],
    }).payload_json)
    assert message=={'type':'text','text':('案件 CASE-SECOND 第二期款 12,000 元已確認入帳，謝謝。' if paid else
        '案件 CASE-SECOND 第二期款尚待繳納 12,000 元，請於今天完成繳款。若已匯款，請勿重複繳納，待工會核對入帳。')}
    assert 'line_user_id' not in event.facts


@pytest.mark.parametrize('change',[{'required_amount':0},{'remaining_amount':0},{'remaining_amount':-1},
    {'required_amount':0,'remaining_amount':0,'settled':True,'settlement_identity':'a'*64,'settled_amount':12000}])
def test_no_second_stage_or_no_balance_cannot_create_a_source_event(change):
    with pytest.raises(ValueError):replace(PAYMENT,**change).event(NOW)


@pytest.mark.parametrize('changes',[{'remaining_amount':11000},{'due_date':date(2026,10,24)},{'group_id':'C_UPDATED'},{'group_version':2}])
def test_changed_snapshot_has_a_new_identity_without_mutating_the_old_event(changes):
    original=PAYMENT.event(NOW);replacement=replace(PAYMENT,**changes).event(NOW)
    assert original.identity!=replacement.identity
    assert original.facts==PAYMENT.event(NOW).facts


@pytest.mark.parametrize('event_code',[DUE_EVENT,SETTLED_EVENT])
def test_rules_cannot_switch_second_payment_to_a_private_or_repeated_notice(event_code):
    rules=json.loads(Path('config/notification_rules.json').read_text(encoding='utf-8'))
    rule=next(r for r in rules['rules'] if r['event_code']==event_code)
    rule['recipient_selector']='client.bound_case'
    with pytest.raises(LineNotificationRuleError):validate_notification_rules(rules)


@pytest.mark.parametrize('kind,retired,current,expected',[
    (REMINDER,False,True,False),(REMINDER,False,False,False),(SETTLED,False,False,False),
    ('order',True,True,False),('unrelated',False,False,True),
])
def test_provider_guard_cancels_stale_and_retired_work(kind,retired,current,expected):
    cancelled=[];committed=[]
    unit=SimpleNamespace(delivery_tasks=SimpleNamespace(cancel=cancelled.append),commit=lambda:committed.append(True),
        second_payment_notifications=SimpleNamespace(delivery_is_current=lambda *_:current))
    task=SimpleNamespace(task_id=SimpleNamespace(value=7),request=SimpleNamespace(source_aggregate_type=kind,
        correlation_id=SimpleNamespace(value='line-notification:order-second-payment-reminder:case:date' if retired else 'current')))
    assert second_payment_delivery_is_current(unit,task,NOW) is expected
    assert len(cancelled)==len(committed)==(0 if expected else 1)


def test_retired_group_due_source_cannot_be_revived_by_manual_rule_replay():
    from infrastructure.mysql.second_payment_notification_repository import MySqlSecondPaymentNotificationRepository
    assert not MySqlSecondPaymentNotificationRepository(None).source_is_current(PAYMENT.facts(),DUE_EVENT,lock=True)

"""Current group start-day card and unchanged second-payment reminder contracts."""
import json
from datetime import date, datetime, timezone
from pathlib import Path
import pytest
from subsystems.line.message_configuration import render_message_template
from subsystems.line.notification_policy import evaluate_notification_rules
from subsystems.line.notification_source_adapters import from_order_service_start_day
from subsystems.line.service_start_day import ServiceStartDayCandidate, StartDayCaregiver


@pytest.mark.parametrize('amount',[24000,0])
def test_start_day_group_rule_and_full_card(amount):
    rules=json.loads(Path('config/notification_rules.json').read_text(encoding='utf-8'))
    templates=json.loads(Path('config/message_templates.json').read_text(encoding='utf-8'))
    candidate=ServiceStartDayCandidate('CASE-001',date(2026,8,20),'C_SERVICE',7,amount,(StartDayCaregiver(1,'測試月嫂'),))
    event=from_order_service_start_day(candidate,occurred_at=datetime(2026,8,20,tzinfo=timezone.utc))
    rule=next(r for r in rules['rules'] if r['event_code']==event.event_code)
    assert rule['recipient_selector']=='case_group'
    assert evaluate_notification_rules(event,rules)[0].status=='intent_created'
    variables={v['name']:event.facts[v['name']] for v in next(t for t in templates['templates'] if t['id']==rule['template_id'])['variables']}
    payload=json.loads(render_message_template(templates,rule['template_id'],variables).payload_json)
    assert payload['type']=='flex'
    text=payload['contents']['body']['contents'][0]['text']
    assert '今天是本案的服務開始日' in text and '測試月嫂，請問今天的服務是否順利？' in text
    assert '第一期款尚待繳納' not in text
    assert '3 天後' not in text and '留言聯繫專員' not in text
    buttons=payload['contents']['footer']['contents']
    assert [b['action']['label'] for b in buttons]==['服務正常','需要協助']
    assert [b['action']['data'] for b in buttons]==[f'start-day:{candidate.token}:normal',f'start-day:{candidate.token}:help']


@pytest.mark.parametrize('override',[
    {'recipient_selector':'client.bound_case'},
    {'frequency':{'kind':'recurring_bounded','maximum_occurrences':2,'interval_days':1}},
    {'schedule':{'kind':'relative_service_time','offset_seconds':60}},
    {'event_code':'order.pre_start_reminder'},
])
def test_rule_writer_cannot_restore_private_early_or_repeated_reminders(override):
    from domains.line.notification_rules import validate_notification_rules, LineNotificationRuleError
    rules=json.loads(Path('config/notification_rules.json').read_text(encoding='utf-8'))
    rule=next(r for r in rules['rules'] if r['event_code']=='order.service_start_day')
    rule.update(override)
    with pytest.raises(LineNotificationRuleError):validate_notification_rules(rules)


def test_historical_config_is_readable_but_retired_template_cannot_send():
    from api.schemas.line_notification_rules import LineNotificationRulesDefinition
    from subsystems.line.message_configuration import LineMessageConfigurationError
    rules=json.loads(Path('config/notification_rules.json').read_text(encoding='utf-8'))
    rule=next(r for r in rules['rules'] if r['event_code']=='order.service_start_day')
    rule['event_code']='order.pre_start_reminder'
    assert LineNotificationRulesDefinition.model_validate(rules)
    templates={'templates':[{'id':'LU96-ORDER-PRE-START-REMINDER-CARD-V1','message_type':'text','content':'舊提醒'},
                             {'id':'unrelated','message_type':'text','content':'其他現行通知'}]}
    assert json.loads(render_message_template(templates,'unrelated').payload_json)['text']=='其他現行通知'
    with pytest.raises(LineMessageConfigurationError):
        render_message_template(templates,'LU96-ORDER-PRE-START-REMINDER-CARD-V1')

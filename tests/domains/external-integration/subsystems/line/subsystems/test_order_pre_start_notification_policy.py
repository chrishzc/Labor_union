"""Retired group notifications: start-day, service-completion and second-payment rules cannot be saved."""
import json
from pathlib import Path
import pytest
from subsystems.line.message_configuration import render_message_template


def _rule(event_code):
    return {'id': 'R1', 'event_code': event_code, 'recipient_selector': 'case_group', 'template_id': 'T1',
            'enabled': True, 'schedule': {'kind': 'immediate'}, 'frequency': {'kind': 'once'}, 'predicates': []}


@pytest.mark.parametrize('event_code', [
    'order.service_start_day', 'order.service_completed',
    'order.pre_start_reminder', 'order.second_payment_reminder',
])
def test_rule_writer_cannot_restore_retired_group_or_private_reminders(event_code):
    from domains.line.notification_rules import validate_notification_rules, LineNotificationRuleError
    with pytest.raises(LineNotificationRuleError):
        validate_notification_rules({'rules': [_rule(event_code)]})


def test_second_payment_rules_are_not_blocked_by_writer():
    from domains.line.notification_rules import validate_notification_rules
    for code in ('client.second_payment_due', 'client.second_payment_settled'):
        validate_notification_rules({'rules': [{**_rule(code), 'recipient_selector': 'client.bound_case'}]})


def test_default_rules_contain_no_retired_group_push():
    rules = json.loads(Path('config/notification_rules.json').read_text(encoding='utf-8'))
    retired = {'order.service_start_day', 'order.service_completed',
               'client.second_payment_due', 'client.second_payment_settled'}  # 第二期款走私訊排程，不再有預設群組規則
    assert not retired & {r['event_code'] for r in rules['rules']}
    assert all(r['recipient_selector'] != 'case_group' for r in rules['rules'])


def test_historical_config_is_readable_but_retired_template_cannot_send():
    from api.schemas.line_notification_rules import LineNotificationRulesDefinition
    from subsystems.line.message_configuration import LineMessageConfigurationError
    assert LineNotificationRulesDefinition.model_validate({'rules': [_rule('order.pre_start_reminder')]})
    templates={'templates':[{'id':'LU96-ORDER-PRE-START-REMINDER-CARD-V1','message_type':'text','content':'舊提醒'},
                             {'id':'unrelated','message_type':'text','content':'其他現行通知'}]}
    assert json.loads(render_message_template(templates,'unrelated').payload_json)['text']=='其他現行通知'
    with pytest.raises(LineMessageConfigurationError):
        render_message_template(templates,'LU96-ORDER-PRE-START-REMINDER-CARD-V1')

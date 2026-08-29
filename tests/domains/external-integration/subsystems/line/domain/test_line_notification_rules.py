"""
File: test_line_notification_rules.py
Description: 驗證 LINE 通知規則僅接受已登錄的事件與條件。
"""

import pytest

from domains.line.notification_rules import (
    LineNotificationRuleError,
    validate_notification_rules,
)


def test_rule_accepts_registered_service_end_predicate() -> None:
    validate_notification_rules(
        {
            "rules": [
                {
                    "id": "baby_log_reminder",
                    "event_code": "service_time_checkpoint",
                    "recipient_selector": "assigned_caregiver",
                    "template_id": "baby_log_reminder",
                    "schedule": {"kind": "service_end"},
                    "frequency": {"kind": "once"},
                    "predicates": ["baby_log_missing"],
                }
            ]
        }
    )


def test_rule_rejects_arbitrary_expression() -> None:
    with pytest.raises(LineNotificationRuleError, match="predicate"):
        validate_notification_rules(
            {
                "rules": [
                    {
                        "id": "unsafe_rule",
                        "event_code": "service_time_checkpoint",
                        "recipient_selector": "assigned_caregiver",
                        "template_id": "baby_log_reminder",
                        "schedule": {"kind": "service_end"},
                        "predicates": ["SELECT * FROM orders"],
                    }
                ]
            }
        )


def test_recurring_rule_requires_explicit_daily_interval() -> None:
    with pytest.raises(LineNotificationRuleError, match="recurring"):
        validate_notification_rules(
            {
                "rules": [{
                    "id": "daily_baby_log_reminder",
                    "event_code": "service_time_checkpoint",
                    "recipient_selector": "assigned_caregiver",
                    "template_id": "baby_log_reminder",
                    "schedule": {"kind": "service_end"},
                    "frequency": {"kind": "recurring_bounded", "maximum_occurrences": 3},
                    "predicates": ["baby_log_missing"],
                }]
            }
        )


def test_rule_rejects_non_boolean_enablement_state() -> None:
    with pytest.raises(LineNotificationRuleError, match="enabled"):
        validate_notification_rules(
            {
                "rules": [{
                    "id": "baby_log_reminder",
                    "event_code": "service_time_checkpoint",
                    "recipient_selector": "case_group",
                    "template_id": "baby_log_reminder",
                    "enabled": "yes",
                    "schedule": {"kind": "service_end"},
                    "predicates": ["baby_log_missing"],
                }]
            }
        )


def test_unknown_event_is_allowed_only_for_disabled_shadow_rule() -> None:
    definition = {
        "rules": [{
            "id": "future_shadow",
            "event_code": "future_owner_event",
            "recipient_selector": "case_group",
            "template_id": "future_shadow",
            "enabled": False,
            "schedule": {"kind": "immediate"},
            "frequency": {"kind": "once"},
            "predicates": [],
        }]
    }
    validate_notification_rules(definition)
    definition["rules"][0]["enabled"] = True
    with pytest.raises(LineNotificationRuleError, match="not registered"):
        validate_notification_rules(definition)


def test_rule_grammar_rejects_unknown_nested_fields() -> None:
    definition = {
        "rules": [{
            "id": "deposit_notice",
            "event_code": "deposit_confirmed",
            "recipient_selector": "case_group",
            "template_id": "deposit_notice",
            "enabled": True,
            "schedule": {"kind": "immediate", "sql": "SELECT 1"},
            "frequency": {"kind": "once"},
            "predicates": [],
        }]
    }
    with pytest.raises(LineNotificationRuleError, match="fields"):
        validate_notification_rules(definition)

"""
File: test_line_notification_policy.py
Description: 驗證規則未明確啟用時只產生 shadow decision，永不建立投遞意圖。
"""

from subsystems.line.notification_policy import (
    NotificationSourceEvent,
    evaluate_notification_rules,
)


def test_unenabled_rule_is_shadow_suppressed() -> None:
    decisions = evaluate_notification_rules(
        NotificationSourceEvent("event-1", "service_time_checkpoint", False, {"baby_log_completed": False}),
        {"rules": [{"id": "baby_log", "event_code": "service_time_checkpoint", "predicates": ["baby_log_missing"]}]},
    )

    assert [(item.status, item.reason_code) for item in decisions] == [
        ("suppressed", "rule_shadow_mode")
    ]

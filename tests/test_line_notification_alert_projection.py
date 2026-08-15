"""
File: test_line_notification_alert_projection.py
Description: 驗證僅安全投遞阻塞會建立 LINE-006 異常投影，不將正常抑制誤報為故障。
"""

from subsystems.anomalies.line_notification_alert import (
    LineNotificationFailure,
    build_line_notification_alert_request,
)


def _failure(reason: str) -> LineNotificationFailure:
    return LineNotificationFailure(7, "checkpoint:9", "CASE-1", reason, 1)


def test_missing_group_creates_line_notification_alert() -> None:
    request = build_line_notification_alert_request(_failure("recipient_unavailable"))

    assert request is not None
    assert request.desired.definition_code == "LINE-006"
    assert request.desired.fingerprint_values == {
        "case_no": "CASE-1",
        "notification_reason": "recipient_unavailable",
    }
    assert request.display_snapshot == request.desired.fingerprint_values


def test_normal_rule_shadow_is_not_a_line_notification_anomaly() -> None:
    assert build_line_notification_alert_request(_failure("rule_shadow_mode")) is None

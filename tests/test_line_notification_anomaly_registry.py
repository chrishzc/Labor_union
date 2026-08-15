"""
File: test_line_notification_anomaly_registry.py
Description: 驗證 LINE 通知無法安全投遞時使用專屬異常代號與唯讀時間軸跳轉。
"""

from domains.anomalies.registry import default_anomaly_registry


def test_line_notification_delivery_failure_has_its_own_anomaly_contract() -> None:
    definition = default_anomaly_registry().require("LINE-006")

    assert definition.source_domain == "line_notification"
    assert definition.fingerprint_fields == ("case_no", "notification_reason")
    action = definition.available_actions[0]
    assert action.owning_domain == "line_notification"
    assert action.preview_operation == "QueryLineNotificationTimeline"
    assert action.requires_preview is False

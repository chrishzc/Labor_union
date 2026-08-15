"""
File: test_line_notification_anomaly_projector.py
Description: 驗證 LINE notification decision 僅於安全投遞阻塞時投影 LINE-006。
"""

from subsystems.anomalies.line_notification_anomaly_projector import (
    LineNotificationAnomalyProjector,
    NotificationDecisionSource,
)


class _Anomalies:
    def __init__(self) -> None:
        self.requests = []

    def project(self, request) -> None:
        self.requests.append(request)


def test_actionable_notification_decision_projects_once() -> None:
    anomalies = _Anomalies()
    projected = LineNotificationAnomalyProjector(anomalies).project(
        NotificationDecisionSource(9, "checkpoint:4", "CASE-1", "recipient_unavailable", 1)
    )

    assert projected is True
    assert len(anomalies.requests) == 1
    assert anomalies.requests[0].desired.definition_code == "LINE-006"


def test_non_actionable_decision_does_not_project() -> None:
    anomalies = _Anomalies()
    projected = LineNotificationAnomalyProjector(anomalies).project(
        NotificationDecisionSource(9, "checkpoint:4", "CASE-1", "rule_shadow_mode", 1)
    )

    assert projected is False
    assert anomalies.requests == []

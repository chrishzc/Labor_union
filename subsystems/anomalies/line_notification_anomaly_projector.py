"""
File: line_notification_anomaly_projector.py
Description: 將 immutable LINE 通知 decision 逐筆投影為 LINE-006，重跑交由異常 checkpoint 冪等處理。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from subsystems.anomalies.line_notification_alert import (
    LineNotificationFailure,
    build_line_notification_alert_request,
)


@dataclass(frozen=True, slots=True)
class NotificationDecisionSource:
    decision_id: int
    source_event_identity: str
    case_no: str
    reason: str
    source_version: int


class AnomalyProjectorPort(Protocol):
    def project(self, request): ...


class LineNotificationAnomalyProjector:
    def __init__(self, anomalies: AnomalyProjectorPort) -> None:
        self._anomalies = anomalies

    def project(self, source: NotificationDecisionSource) -> bool:
        request = build_line_notification_alert_request(
            LineNotificationFailure(
                source.decision_id,
                source.source_event_identity,
                source.case_no,
                source.reason,
                source.source_version,
            )
        )
        if request is None:
            return False
        self._anomalies.project(request)
        return True


__all__ = ["LineNotificationAnomalyProjector", "NotificationDecisionSource"]

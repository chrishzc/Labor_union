"""
File: line_notification_alert.py
Description: 將 LINE 通知的安全投遞阻塞原因歸約為可跳轉的 LINE-006 異常投影請求。
"""

from __future__ import annotations

from dataclasses import dataclass

from domains.anomalies.registry import DesiredAlertState
from subsystems.anomalies.alert_workflow import ProjectAlertRequest


_ACTIONABLE_REASONS = frozenset({"recipient_unavailable", "template_or_schedule_invalid"})


@dataclass(frozen=True, slots=True)
class LineNotificationFailure:
    decision_id: int
    source_event_identity: str
    case_no: str
    reason: str
    source_version: int


def build_line_notification_alert_request(
    failure: LineNotificationFailure,
) -> ProjectAlertRequest | None:
    if failure.reason not in _ACTIONABLE_REASONS:
        return None
    if failure.decision_id <= 0 or not failure.case_no or failure.source_version < 0:
        raise ValueError("line notification anomaly source is invalid")
    desired = DesiredAlertState(
        definition_code="LINE-006",
        source_identity=f"line-notification-decision:{failure.decision_id}",
        source_version=failure.source_version,
        active=True,
        fingerprint_values={
            "case_no": failure.case_no,
            "notification_reason": failure.reason,
        },
    )
    return ProjectAlertRequest(
        desired=desired,
        source_event_identity=failure.source_event_identity,
        consumer_identity="line-notification-anomaly-projector",
        partition_identity=f"line-notification:{failure.decision_id}",
        display_snapshot={
            "case_no": failure.case_no,
            "notification_reason": failure.reason,
        },
    )


__all__ = ["LineNotificationFailure", "build_line_notification_alert_request"]

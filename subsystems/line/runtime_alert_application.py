"""Project persisted health transitions into canonical LINE delivery tasks."""

from __future__ import annotations

from datetime import datetime

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId, LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey


class RuntimeLineAlertProjector:
    def __init__(self, now) -> None:
        self._now = now

    def project(self, event_id: int, repository, delivery_tasks) -> int:
        queued = 0
        for target in repository.pending_alert_targets(event_id):
            resolved_type, resolved_id = _resolve_target(target)
            if not resolved_id or not _meets_threshold(str(target["resulting_status"]), str(target["minimum_status"])):
                repository.append_alert_intent(event_id, int(target["id"]), None, "skipped", resolved_type, resolved_id, "target_unavailable_or_below_threshold")
                continue
            identity = LineGroupId(resolved_id) if resolved_type == "group" else LineUserId(resolved_id)
            result = delivery_tasks.enqueue(LineDeliveryRequest(
                LineRecipient(LineRecipientType(resolved_type), identity),
                LineMessageKind.TEXT,
                canonical_line_payload_json({"type": "text", "text": _message(target)}),
                self._now(),
                IdempotencyKey(f"runtime-alert:{event_id}:{target['id']}"),
                CorrelationId(f"runtime-health-event:{event_id}"),
                "runtime_health_event",
                str(event_id),
            ))
            repository.append_alert_intent(event_id, int(target["id"]), result.task_id.value, "queued", resolved_type, resolved_id)
            queued += 1
        return queued


def register_group_alert_target(inbox, unit_of_work, actor) -> bool:
    return unit_of_work.runtime_monitor.upsert_group_target(
        inbox.event.source.source_id,
        "LINE 工會異常通知群組",
        actor.actor_id,
    )


def _resolve_target(target):
    if str(target["target_type"]) == "group":
        return "group", str(target["group_id"] or "")
    return "user", str(target["linked_line_user_id"] or "")


def _meets_threshold(status, threshold):
    weights = {"healthy": 0, "unknown": 0, "maintenance": 0, "warning": 1, "critical": 2}
    return weights.get(status, 0) >= weights.get(threshold, 1) or status == "healthy"


def _message(target):
    status = str(target["resulting_status"])
    heading = "系統已恢復" if status == "healthy" else "系統異常通知"
    occurred = target["occurred_at_utc"]
    stamp = occurred.isoformat(sep=" ", timespec="seconds") if isinstance(occurred, datetime) else str(occurred)
    return f"【{heading}】\n元件：{target['check_name']}\n狀態：{status}\n說明：{target['message']}\n時間：{stamp} UTC"


__all__ = ["RuntimeLineAlertProjector", "register_group_alert_target"]

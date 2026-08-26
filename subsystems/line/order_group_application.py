"""
File: order_group_application.py
Description: 協調 LINE 訂單群組綁定、邀請、事件與唯讀 numbered query。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Callable

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineGroupId, LineSourceType, LineUserId
from domains.line.order_group import LineGroupInvitationRelay
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.capabilities import (
    LineCapability,
    line_capabilities_for_role,
    require_line_capability,
)
from subsystems.line.order_group_contracts import BindLineOrderGroupCommand
from subsystems.line.ports import LineAuditIntent

_BIND_COMMAND = re.compile(r"^綁定訂單\s+([A-Za-z0-9_-]{1,50})$")
_INVITE_COMMAND = re.compile(r"^發送邀請連結\s+(\S+)$")
_ALERT_TARGET_COMMAND = "設定異常通知群組"


class LineOrderGroupCommandRejected(ValueError):
    """A safe business rejection that can be returned to the source group."""


class LineOrderGroupApplication:
    def __init__(
        self,
        now: Callable[[], datetime],
        alert_group_registrar: Callable[[object, object, object], bool] | None = None,
    ) -> None:
        self._now = now
        self._alert_group_registrar = alert_group_registrar

    def handle_message(self, inbox, unit_of_work) -> bool:
        event = inbox.event
        if event.source.source_type is not LineSourceType.GROUP:
            return False
        text = _message_text(inbox)
        if text is None:
            return False
        bind_match = _BIND_COMMAND.fullmatch(text)
        invite_match = _INVITE_COMMAND.fullmatch(text)
        is_alert_command = text == _ALERT_TARGET_COMMAND
        if bind_match is None and invite_match is None and not is_alert_command:
            return False
        try:
            if bind_match is not None:
                self._bind(inbox, unit_of_work, bind_match.group(1))
            elif invite_match is not None:
                self._relay(inbox, unit_of_work, invite_match.group(1))
            else:
                self._register_alert_group(inbox, unit_of_work)
        except (LookupError, PermissionError, RuntimeError, ValueError) as error:
            self._reply_to_group(inbox, unit_of_work, _safe_error_message(error), "error")
        return True

    def handle_membership(self, inbox, unit_of_work) -> bool:
        event_type = inbox.event.event_type
        if event_type not in {"memberJoined", "memberLeft"}:
            return False
        if inbox.event.source.source_type is not LineSourceType.GROUP:
            return False
        payload = json.loads(inbox.event.payload_json)
        collection_name = "joined" if event_type == "memberJoined" else "left"
        members = payload.get(collection_name, {}).get("members", [])
        normalized_event = "member_joined" if event_type == "memberJoined" else "member_left"
        for item in members if isinstance(members, list) else []:
            user_id = str(item.get("userId") or "").strip() if isinstance(item, dict) else ""
            if not user_id:
                continue
            unit_of_work.order_groups.record_membership_event(
                group_id=inbox.event.source.source_id,
                line_user_id=LineUserId(user_id),
                event_type=normalized_event,
                idempotency_key=IdempotencyKey(
                    f"group-member:{inbox.event.event_id.value}:{user_id}"
                ),
                occurred_at=inbox.event.occurred_at,
            )
        return True

    def _bind(self, inbox, unit_of_work, case_no: str) -> None:
        actor = _linked_actor(inbox, unit_of_work, LineCapability.ORDER_GROUP_BIND)
        audience = unit_of_work.order_audiences.get(case_no)
        if audience is None:
            raise LookupError("order_not_found")
        current = unit_of_work.order_groups.get(case_no)
        expected_version = current.version if current else ExpectedVersion(0)
        before_group_id = current.group_id.value if current and current.group_id else None
        group_id = LineGroupId(inbox.event.source.source_id)
        if before_group_id != group_id.value:
            unit_of_work.order_groups.bind(
                BindLineOrderGroupCommand(
                    case_no,
                    group_id,
                    expected_version,
                    actor,
                    IdempotencyKey(f"group-bind:{inbox.event.event_id.value}"),
                    CorrelationId(f"line-event:{inbox.event.event_id.value}"),
                )
            )
            unit_of_work.order_audiences.set_group_projection(
                case_no,
                group_id.value,
                before_group_id,
            )
        unit_of_work.order_groups.sync_participants(audience)
        unit_of_work.audit.append(
            LineAuditIntent("order_group.bind", actor.actor_id, "order", case_no)
        )
        self._reply_to_group(
            inbox,
            unit_of_work,
            f"已將本群組綁定訂單 {case_no}。請再輸入「發送邀請連結 LINE群組網址」。",
            "bound",
        )

    def _relay(self, inbox, unit_of_work, invitation_url: str) -> None:
        actor = _linked_actor(inbox, unit_of_work, LineCapability.ORDER_GROUP_BIND)
        binding = unit_of_work.order_groups.get_by_group(inbox.event.source.source_id)
        if binding is None or binding.group_id is None:
            raise LookupError("group_not_bound")
        audience = unit_of_work.order_audiences.get(binding.case_no)
        if audience is None:
            raise LookupError("order_not_found")
        recipients = tuple(
            sorted(
                {audience.customer_line_user_id, *audience.staff_line_user_ids},
                key=lambda item: item.value,
            )
        )
        event_identity = inbox.event.event_id.value
        correlation_id = CorrelationId(f"line-event:{event_identity}")
        relay = LineGroupInvitationRelay(
            binding.case_no,
            binding.group_id,
            invitation_url,
            recipients,
            actor,
            correlation_id,
        )
        relay_key = IdempotencyKey(f"group-invite:{event_identity}")
        unit_of_work.order_groups.sync_participants(audience)
        unit_of_work.order_groups.record_invitation_relay(relay, relay_key)
        for recipient in relay.recipients:
            unit_of_work.delivery_tasks.enqueue(
                _invitation_delivery(
                    relay,
                    recipient,
                    event_identity,
                    self._now(),
                    "媽媽" if recipient == audience.customer_line_user_id else "月嫂",
                )
            )
        unit_of_work.audit.append(
            LineAuditIntent(
                "order_group.invitation_relay",
                actor.actor_id,
                "order_group_invitation",
                relay.invitation_fingerprint.value,
            )
        )
        self._reply_to_group(
            inbox,
            unit_of_work,
            f"訂單 {binding.case_no} 的邀請已排入發送，共 {len(recipients)} 位。",
            "invite-queued",
        )

    def _register_alert_group(self, inbox, unit_of_work) -> None:
        actor = _linked_actor(inbox, unit_of_work, LineCapability.ALERT_MANAGE)
        if self._alert_group_registrar is None:
            raise RuntimeError("alert_group_registration_unavailable")
        created = self._alert_group_registrar(inbox, unit_of_work, actor)
        message = "已設定本群組接收系統異常通知。" if created else "本群組已是異常通知目標。"
        self._reply_to_group(inbox, unit_of_work, message, "alert-target")

    def _reply_to_group(self, inbox, unit_of_work, text: str, suffix: str) -> None:
        event_identity = inbox.event.event_id.value
        unit_of_work.delivery_tasks.enqueue(
            LineDeliveryRequest(
                LineRecipient(
                    LineRecipientType.GROUP,
                    LineGroupId(inbox.event.source.source_id),
                ),
                LineMessageKind.TEXT,
                canonical_line_payload_json({"type": "text", "text": text}),
                self._now(),
                IdempotencyKey(f"group-reply:{event_identity}:{suffix}"),
                CorrelationId(f"line-event:{event_identity}"),
                "line_webhook_event",
                event_identity,
            )
        )


class LineOrderGroupQueryApplication:
    def __init__(self, unit_of_work_factory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def list(self, actor: ActorContext, *, status: str | None, limit: int):
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            page = unit_of_work.order_groups.list(status=status, limit=limit)
            unit_of_work.commit()
        return page

    def list_numbered(
        self,
        actor: ActorContext,
        *,
        status: str | None,
        page: int,
        page_size: int,
    ):
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.order_groups.list_numbered(
                status=status,
                page=page,
                page_size=page_size,
            )

    def get(self, actor: ActorContext, case_no: str):
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.order_groups.get(case_no)
            unit_of_work.commit()
        return result

    def events(self, actor: ActorContext, case_no: str, *, limit: int):
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.order_groups.events(case_no, limit=limit)
            unit_of_work.commit()
        return result

    def events_numbered(
        self,
        actor: ActorContext,
        case_no: str,
        *,
        page: int,
        page_size: int,
    ):
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.order_groups.events_numbered(
                case_no,
                page=page,
                page_size=page_size,
            )


def _linked_actor(inbox, unit_of_work, capability: LineCapability) -> ActorContext:
    line_user_id = inbox.event.source.user_id
    if line_user_id is None:
        raise PermissionError("linked_admin_required")
    admin = unit_of_work.admins.get_linked_admin(line_user_id)
    if admin is None:
        raise PermissionError("linked_admin_required")
    actor = ActorContext(
        f"admin:{admin.admin_user_id}",
        line_capabilities_for_role(admin.role),
    )
    require_line_capability(actor, capability)
    return actor


def _message_text(inbox) -> str | None:
    payload = json.loads(inbox.event.payload_json)
    message = payload.get("message")
    if not isinstance(message, dict) or message.get("type") != "text":
        return None
    text = message.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _invitation_delivery(relay, recipient, event_identity, scheduled_at, label):
    payload = {
        "type": "flex",
        "altText": f"訂單 {relay.case_no} 服務群組邀請",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {"type": "text", "text": "服務群組邀請", "weight": "bold", "size": "xl"},
                    {"type": "text", "text": f"案件編號：{relay.case_no}", "size": "sm"},
                    {"type": "text", "text": f"{label}您好，請點下方按鈕加入本案服務群組。", "wrap": True},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#06C755",
                        "action": {
                            "type": "uri",
                            "label": "加入服務群組",
                            "uri": relay.invitation_url,
                        },
                    }
                ],
            },
        },
    }
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, recipient),
        LineMessageKind.FLEX,
        canonical_line_payload_json(payload),
        scheduled_at,
        IdempotencyKey(f"group-invite-delivery:{event_identity}:{recipient.value}"),
        relay.correlation_id,
        "line_order_group_invitation",
        f"{relay.case_no}:{relay.invitation_fingerprint.value}",
    )


def _safe_error_message(error: Exception) -> str:
    messages = {
        "linked_admin_required": "此操作只允許已綁定 LINE 的工會人員使用。",
        "order_not_found": "找不到指定訂單。",
        "group_not_bound": "本群組尚未綁定訂單，請先輸入「綁定訂單 案件編號」。",
        "order_line_audience_not_ready": "訂單的媽媽或月嫂尚未完成 LINE 綁定。",
        "cancelled_order_cannot_bind_line_group": "已取消的訂單不能綁定服務群組。",
        "line_group_already_bound_to_another_order": "此群組已綁定其他訂單。",
    }
    return messages.get(str(error), "操作無法完成，請至 LINE 管理中心查看。")


__all__ = [
    "LineOrderGroupApplication",
    "LineOrderGroupCommandRejected",
    "LineOrderGroupQueryApplication",
]

"""
File: order_group_application.py
Description: 協調 LINE 訂單群組綁定、邀請、事件與唯讀 numbered query。
"""

from __future__ import annotations

from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE

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
from domains.line.order_group import (
    LineGroupInvitationRelay, LineOrderGroupBindingConflict, validate_invitation_url,
)
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
from subsystems.line.order_group_contracts import (
    PaidOrderGroupTodoPage,
    BindLineOrderGroupCommand,
    GetLineOrderGroupQuery,
    LineOrderGroupWorkspacePage,
    LineOrderGroupWorkspaceRecord,
    LineOrderGroupWorkspaceEventPage,
)
from subsystems.line.ports import LineAuditIntent
from subsystems.line.delivery_contracts import CancelLineDeliveryTaskCommand
from subsystems.line.message_copy_catalog import configured_payload

_BIND_FORMAT = "格式：綁定訂單 案件編號 邀請網址\n例如：綁定訂單 115000157 https://line.me/R/ti/g/xxxxx\n各項之間可用空白或換行，網址請完整貼上。"
_INVITE_COMMAND_FORMAT = "邀請指令只需輸入「發送邀請」。\n首次設定或更新網址請使用：\n" + _BIND_FORMAT
_INVITATION_URL_REQUIRED = "請先設定本群組邀請網址。\n" + _BIND_FORMAT
_SAFE_RUNTIME_ERRORS = {
    "order_line_audience_not_ready", "cancelled_order_cannot_bind_line_group",
    "settled_deposit_required_for_line_group",
    "alert_group_registration_unavailable",
}
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
        is_bind_command = text.startswith("綁定訂單")
        is_invite_command = text.startswith("發送邀請")
        if text == _ALERT_TARGET_COMMAND:
            return True  # Retired command: no registration, reply or delivery intent.
        if not (is_bind_command or is_invite_command):
            return False
        try:
            if is_bind_command:
                case_no, invitation_url = _parse_binding(text)
                self._bind(inbox, unit_of_work, case_no, invitation_url)
            elif is_invite_command:
                if text != "發送邀請":
                    raise LineOrderGroupCommandRejected(_INVITE_COMMAND_FORMAT)
                self._relay(inbox, unit_of_work)
        except (LookupError, PermissionError, RuntimeError, ValueError) as error:
            # Persistence failures must reach the outer consumer and roll back.
            if isinstance(error, LineOrderGroupBindingConflict):
                raise
            if isinstance(error, ValueError) and not isinstance(error, LineOrderGroupCommandRejected):
                raise
            if isinstance(error, RuntimeError) and str(error) not in _SAFE_RUNTIME_ERRORS:
                raise
            message = _safe_error_message(error)
            self._reply_to_group(inbox, unit_of_work, message, "error")
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

    def _bind(self, inbox, unit_of_work, case_no: str, invitation_url: str) -> None:
        actor = _linked_actor(inbox, unit_of_work, LineCapability.ORDER_GROUP_BIND)
        audience = unit_of_work.order_audiences.get(case_no)
        if audience is None:
            raise LookupError("order_not_found")
        current = unit_of_work.order_groups.get(case_no)
        expected_version = current.version if current else ExpectedVersion(0)
        before_group_id = current.group_id.value if current and current.group_id else None
        group_id = LineGroupId(inbox.event.source.source_id)
        occupied = unit_of_work.order_groups.get_by_group(group_id.value)
        if occupied is not None and occupied.case_no != case_no:
            raise LineOrderGroupCommandRejected("此群組已綁定其他訂單。")
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
        binding = unit_of_work.order_groups.get(case_no)
        unit_of_work.order_groups.save_invitation_url(binding, invitation_url)
        unit_of_work.order_groups.sync_participants(audience)
        unit_of_work.audit.append(
            LineAuditIntent("order_group.bind", actor.actor_id, "order", case_no)
        )
        self._reply_to_group(
            inbox,
            unit_of_work,
            group_binding_acknowledgement(case_no),
            "bound",
        )

    def _relay(self, inbox, unit_of_work) -> None:
        actor = _linked_actor(inbox, unit_of_work, LineCapability.ORDER_GROUP_BIND)
        binding = unit_of_work.order_groups.get_by_group(inbox.event.source.source_id)
        if binding is None or binding.group_id is None:
            raise LookupError("group_not_bound")
        audience = unit_of_work.order_audiences.get(binding.case_no)
        if audience is None:
            raise LookupError("order_not_found")
        settings = unit_of_work.order_groups.get_invitation(binding.case_no, lock=True)
        if settings is None or settings.binding.group_id != binding.group_id:
            raise LineOrderGroupBindingConflict("line_order_group_binding_conflict")
        if settings.invitation_url is None:
            raise LineOrderGroupCommandRejected(_INVITATION_URL_REQUIRED)
        binding = settings.binding
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
            settings.invitation_url,
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
                    inbox.event.occurred_at,
                    "媽媽" if recipient == audience.customer_line_user_id else "月嫂",
                    binding.version.value,
                    unit_of_work,
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
            group_invitation_acknowledgement(binding.case_no, len(recipients)),
            "invite-queued",
        )

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
                inbox.event.occurred_at,
                IdempotencyKey(f"group-reply:{event_identity}:{suffix}"),
                CorrelationId(f"line-event:{event_identity}"),
                REPLY_ONLY_WEBHOOK_SOURCE,
                event_identity,
            )
        )


class LineOrderGroupQueryApplication:
    def __init__(self, unit_of_work_factory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def paid_uncreated_todos(self, actor: ActorContext, *, page: int, page_size: int) -> PaidOrderGroupTodoPage:
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.order_groups.paid_uncreated_todos(page=page, page_size=page_size)

    def workspace_list(
        self, actor: ActorContext, *, search: str | None, status: str | None,
        page: int, page_size: int,
    ) -> LineOrderGroupWorkspacePage:
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.order_groups.workspace_list(
                search=search, status=status, page=page, page_size=page_size,
            )

    def workspace_get(self, actor: ActorContext, case_no: str) -> LineOrderGroupWorkspaceRecord | None:
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        GetLineOrderGroupQuery(case_no)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.order_groups.workspace_get(case_no)

    def workspace_events(
        self, actor: ActorContext, case_no: str, *, page: int, page_size: int,
    ) -> LineOrderGroupWorkspaceEventPage | None:
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        GetLineOrderGroupQuery(case_no)
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.order_groups.get(case_no) is None:
                return None
            return unit_of_work.order_groups.workspace_events(case_no, page=page, page_size=page_size)

    def list(self, actor: ActorContext, *, status: str | None, limit: int):
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.order_groups.list(status=status, limit=limit)

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
            return unit_of_work.order_groups.get(case_no)

    def events(self, actor: ActorContext, case_no: str, *, limit: int):
        require_line_capability(actor, LineCapability.ORDER_GROUP_READ)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.order_groups.events(case_no, limit=limit)

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


def _invitation_delivery(relay, recipient, event_identity, scheduled_at, label, binding_version, unit=None):
    payload = group_invitation_payload(relay.case_no, label, relay.invitation_url)
    if unit is not None:
        payload = configured_payload(unit, "group-invitation-customer" if label == "媽媽" else "group-invitation-staff", payload, {"case_no": relay.case_no})
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, recipient),
        LineMessageKind.FLEX,
        canonical_line_payload_json(payload),
        scheduled_at,
        IdempotencyKey(f"group-invite-delivery:{event_identity}:{recipient.value}"),
        relay.correlation_id,
        "line_order_group_invitation",
        f"{relay.case_no}:{binding_version}:{relay.invitation_fingerprint.value}",
    )


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, LineOrderGroupCommandRejected):
        return str(error)
    messages = {
        "linked_admin_required": "此操作只允許已綁定 LINE 的工會人員使用。",
        "order_not_found": "找不到指定訂單。",
        "group_not_bound": "本群組尚未設定。\n" + _BIND_FORMAT,
        "order_line_audience_not_ready": "訂單的媽媽或月嫂尚未完成 LINE 綁定。",
        "cancelled_order_cannot_bind_line_group": "已取消的訂單不能綁定服務群組。",
        "settled_deposit_required_for_line_group": "客戶訂金尚未確認入帳，不能建立或邀請第三方服務群組。",
        "line_group_already_bound_to_another_order": "此群組已綁定其他訂單。",
    }
    return messages.get(str(error), "操作無法完成，請至 LINE 管理中心查看。")


def _parse_binding(text: str) -> tuple[str, str]:
    parts = text.split()
    reason = None
    if parts[0] != "綁定訂單":
        reason = "請在指令、案件編號與網址之間加空白或換行。"
    elif len(parts) == 1:
        reason = "請填寫案件編號與邀請網址。"
    elif len(parts) == 2:
        reason = ("請填寫案件編號。" if parts[1].startswith("http")
                  else "請在案件編號與網址之間加空白或換行。" if "https://" in parts[1]
                  else "請貼上本群組邀請網址。")
    elif len(parts) > 3:
        reason = "請只填寫案件編號與一個完整邀請網址；網址中間不要換行或加空白。"
    elif not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", parts[1]):
        reason = "案件編號格式不正確。"
    else:
        try:
            validate_invitation_url(parts[2])
        except ValueError:
            reason = "邀請網址格式不正確，請從本群組複製完整的 LINE 群組邀請連結。"
    if reason is not None:
        raise LineOrderGroupCommandRejected(reason + "\n" + _BIND_FORMAT)
    return parts[1], parts[2]


def group_invitation_delivery_is_current(unit_of_work, task) -> bool:
    """Suppress queued invitations after URL, group, payment or audience changes."""
    request = task.request
    if request.source_aggregate_type != "line_order_group_invitation":
        return True
    case_no, separator, _ = request.source_aggregate_identity.partition(":")
    valid = False
    if separator:
        try:
            audience = unit_of_work.order_audiences.get(case_no)
        except RuntimeError as error:
            if str(error) not in _SAFE_RUNTIME_ERRORS:
                raise
            audience = None
        settings = unit_of_work.order_groups.get_invitation(case_no, lock=True)
        if audience is not None and settings is not None and settings.binding.group_id and settings.invitation_url:
            recipients = tuple(sorted({audience.customer_line_user_id, *audience.staff_line_user_ids}, key=lambda item: item.value))
            relay = LineGroupInvitationRelay(case_no, settings.binding.group_id, settings.invitation_url, recipients,
                                            ActorContext("line-group-worker"), request.correlation_id)
            identity = f"{case_no}:{settings.binding.version.value}:{relay.invitation_fingerprint.value}"
            valid = (identity == request.source_aggregate_identity
                     and request.recipient.recipient_type is LineRecipientType.USER
                     and request.recipient.identity in recipients)
    if not valid:
        unit_of_work.delivery_tasks.cancel(CancelLineDeliveryTaskCommand(
            task.task_id, ActorContext("line-group-worker"),
            IdempotencyKey(f"group-invitation-stale:{task.task_id.value}"), request.correlation_id,
        ))
        unit_of_work.commit()
    return valid


__all__ = [
    "LineOrderGroupApplication",
    "LineOrderGroupCommandRejected",
    "LineOrderGroupQueryApplication",
]


def group_invitation_payload(case_no, label, invitation_url):
    payload = {
        "type": "flex",
        "altText": f"訂單 {case_no} 服務群組邀請",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {"type": "text", "text": "服務群組邀請", "weight": "bold", "size": "xl"},
                    {"type": "text", "text": f"案件編號：{case_no}", "size": "sm"},
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
                            "uri": invitation_url,
                        },
                    }
                ],
            },
        },
    }
    return payload


def group_binding_acknowledgement(case_no):
    return f"已設定案件 {case_no} 的服務群組。"


def group_invitation_acknowledgement(case_no, recipient_count):
    return f"訂單 {case_no} 的邀請已排入發送，共 {recipient_count} 位。"

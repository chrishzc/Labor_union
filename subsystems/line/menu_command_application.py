"""Canonical message intents for per-user LINE Rich Menu selection."""

from __future__ import annotations

import json

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.ports import OutboxIntent
from subsystems.line.ports import LineAuditIntent
from subsystems.line.rich_menu_binding import RICH_MENU_BINDING_INTENT


_CUSTOMER_MENU_COMMANDS = {"一般選單", "一般用戶選單", "切換一般", "切換客戶"}
_STAFF_MENU_COMMANDS = {"月嫂選單", "月嫂專區", "切換月嫂"}
_UNION_MENU_COMMANDS = {"工會選單", "工會客服", "切換工會", "開啟客服系統", "月嫂驗證管理"}
_MENU_HELP_COMMANDS = {"切換選單", "選單切換", "管理者選單"}


class LineMenuCommandApplication:
    def handle(self, inbox, unit_of_work, line_user_id, text: str) -> bool:
        command = text.strip()
        if command in _MENU_HELP_COMMANDS:
            return self._queue_switch_help(inbox, unit_of_work, line_user_id)
        if command in _CUSTOMER_MENU_COMMANDS:
            return self._queue_scoped_menu(
                inbox,
                unit_of_work,
                line_user_id,
                "default_menu",
                "customer-menu",
                allow_subject=LineBindingSubjectType.CUSTOMER,
            )
        if command in _STAFF_MENU_COMMANDS:
            return self._queue_scoped_menu(
                inbox,
                unit_of_work,
                line_user_id,
                "staff_menu",
                "staff-menu",
                allow_subject=LineBindingSubjectType.STAFF,
            )
        if command in _UNION_MENU_COMMANDS:
            return self._queue_scoped_menu(
                inbox,
                unit_of_work,
                line_user_id,
                "union_staff_menu",
                "union-menu",
                allow_subject=LineBindingSubjectType.ADMIN,
            )
        if command.lower() == "esc":
            self._queue_menu(inbox, unit_of_work, line_user_id, "default_menu", "esc")
            return True
        return False

    def _queue_scoped_menu(
        self,
        inbox,
        unit_of_work,
        line_user_id,
        menu_definition_id,
        command,
        *,
        allow_subject,
    ) -> bool:
        binding = unit_of_work.identities.get(line_user_id)
        if binding is None or binding.status is not LineIdentityBindingStatus.BOUND:
            return False
        if binding.subject_type not in {LineBindingSubjectType.ADMIN, allow_subject}:
            return False
        self._queue_menu(inbox, unit_of_work, line_user_id, menu_definition_id, command)
        return True

    def _queue_switch_help(self, inbox, unit_of_work, line_user_id) -> bool:
        binding = unit_of_work.identities.get(line_user_id)
        if (
            binding is None
            or binding.status is not LineIdentityBindingStatus.BOUND
            or binding.subject_type is not LineBindingSubjectType.ADMIN
        ):
            return False
        event_id = inbox.event.event_id.value
        unit_of_work.delivery_tasks.enqueue(
            LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                LineMessageKind.TEXT,
                canonical_line_payload_json(
                    {
                        "type": "text",
                        "text": (
                            "管理者可切換以下操作視角：\n"
                            "・切換一般：一般用戶選單\n"
                            "・切換月嫂：月嫂專區選單\n"
                            "・切換工會：工會客服選單\n\n"
                            "此功能只切換下方圖文選單，不會降低您的管理者權限。"
                        ),
                    }
                ),
                getattr(inbox, "received_at", None) or inbox.event.occurred_at,
                IdempotencyKey(f"line-menu-help:{event_id}"),
                CorrelationId(f"line-event:{event_id}"),
                "line_webhook_event",
                event_id,
            )
        )
        unit_of_work.audit.append(
            LineAuditIntent("line.rich_menu.command", f"line:{line_user_id.value}", "line_menu", "menu-help")
        )
        return True

    def _queue_menu(self, inbox, unit_of_work, line_user_id, menu_definition_id, command):
        event_id = inbox.event.event_id.value
        unit_of_work.outbox.append(
            OutboxIntent(
                "line_identity",
                line_user_id.value,
                RICH_MENU_BINDING_INTENT,
                json.dumps(
                    {"line_user_id": line_user_id.value, "menu_definition_id": menu_definition_id},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                f"line-menu-command:{command}:{event_id}",
            )
        )
        unit_of_work.audit.append(
            LineAuditIntent("line.rich_menu.command", f"line:{line_user_id.value}", "line_menu", command)
        )


__all__ = ["LineMenuCommandApplication"]

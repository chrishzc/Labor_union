"""Canonical message intents for per-user LINE Rich Menu selection."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from domains.line.identities import LineSourceType
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.identity_management_application import LineIdentityManagementApplication
from subsystems.line.identity_management_contracts import SelectLineIdentityRoleCommand
from shared_kernel.ports import OutboxIntent
from subsystems.line.ports import LineAuditIntent
from subsystems.line.rich_menu_binding import RICH_MENU_BINDING_INTENT
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE


_CUSTOMER_MENU_COMMANDS = {"客戶選單", "客戶專區", "切換客戶"}
_VISITOR_MENU_COMMANDS = {"訪客選單", "切換訪客", "一般選單", "一般用戶選單", "切換一般"}
_STAFF_MENU_COMMANDS = {"月嫂選單", "月嫂專區", "切換月嫂"}
_UNION_MENU_COMMANDS = {"工會選單", "工會客服", "切換工會"}
_MENU_HELP_COMMANDS = {"切換選單", "選單切換", "管理者選單"}


class LineMenuCommandApplication:
    def handle(self, inbox, unit_of_work, line_user_id, text: str) -> bool:
        source_type = getattr(getattr(inbox.event, 'source', None), 'source_type', None)
        if source_type is not None and source_type.value != 'user':
            return False
        command = text.strip()
        if command in _MENU_HELP_COMMANDS:
            return self._queue_switch_help(inbox, unit_of_work, line_user_id)
        if command in _CUSTOMER_MENU_COMMANDS:
            return self._queue_scoped_menu(
                inbox,
                unit_of_work,
                line_user_id,
                "customer_menu",
                "customer-menu",
                allow_subject=LineBindingSubjectType.CUSTOMER,
            )
        if command in _VISITOR_MENU_COMMANDS:
            self._queue_menu(inbox, unit_of_work, line_user_id, "default_menu", "visitor-menu")
            return True
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
        bindings = tuple(binding for binding in unit_of_work.identities.list_by_user(line_user_id)
                         if binding.status is LineIdentityBindingStatus.BOUND)
        admin = next((binding for binding in bindings if binding.subject_type is LineBindingSubjectType.ADMIN), None)
        if not bindings:
            return False
        if admin is not None:
            if len(bindings) != 1:
                raise RuntimeError('line_identity_admin_role_exclusive')
            self._queue_menu(inbox, unit_of_work, line_user_id, menu_definition_id, command)
            return True
        if not any(binding.subject_type is allow_subject for binding in bindings):
            return False
        if len(bindings) > 1:
            # The verified user command is the explicit choice; the webhook owns commit.
            application = LineIdentityManagementApplication(lambda: unit_of_work, lambda: datetime.now(timezone.utc))
            event_id = inbox.event.event_id.value
            key = IdempotencyKey(f'line-menu-role:{event_id}')
            existing = unit_of_work.receipts.get(key)
            if existing is not None:
                if not existing.result_reference.startswith(f'line-identity-role:{line_user_id.value}:{allow_subject.value}:'):
                    raise RuntimeError('line_identity_role_selection_idempotency_conflict')
                return True
            preview = application.preview_role_selection_in_unit_of_work(unit_of_work, line_user_id, allow_subject)
            application.select_role_in_unit_of_work(unit_of_work, SelectLineIdentityRoleCommand(
                line_user_id, allow_subject, preview.readback.context_version, preview.preview_fingerprint,
                ActorContext(f'line-user:{line_user_id.value}'),
                key, CorrelationId(f'line-event:{event_id}'),
            ))
            return True
        self._queue_menu(inbox, unit_of_work, line_user_id, menu_definition_id, command)
        return True

    def _queue_switch_help(self, inbox, unit_of_work, line_user_id) -> bool:
        bindings = tuple(binding for binding in unit_of_work.identities.list_by_user(line_user_id)
                         if binding.status is LineIdentityBindingStatus.BOUND)
        binding = next((item for item in bindings if item.subject_type is LineBindingSubjectType.ADMIN), None)
        dual_role = {item.subject_type for item in bindings} == {LineBindingSubjectType.CUSTOMER, LineBindingSubjectType.STAFF}
        if binding is not None and len(bindings) != 1:
            raise RuntimeError('line_identity_admin_role_exclusive')
        if (
            not dual_role and binding is None
        ):
            return False
        event_id = inbox.event.event_id.value
        source = getattr(inbox.event, "source", None)
        same_private_chat = (
            getattr(source, "source_type", None) is LineSourceType.USER
            and getattr(source, "user_id", None) == line_user_id
        )
        unit_of_work.delivery_tasks.enqueue(
            LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                LineMessageKind.TEXT,
                canonical_line_payload_json(
                    {
                        "type": "text",
                        "text": ("您同時具有客戶與月嫂身分，請輸入「切換客戶」或「切換月嫂」選擇目前使用的身分。" if dual_role else (
                            "管理者可切換以下操作視角：\n"
                            "・切換訪客：訪客初始選單\n"
                            "・切換客戶：客戶專屬選單\n"
                            "・切換月嫂：月嫂專區選單\n"
                            "・切換工會：工會客服選單\n\n"
                            "此功能只切換下方圖文選單，不會降低您的管理者權限。"
                        )),
                    }
                ),
                getattr(inbox, "received_at", None) or inbox.event.occurred_at,
                IdempotencyKey(f"line-menu-help:{event_id}"),
                CorrelationId(f"line-event:{event_id}"),
                REPLY_ONLY_WEBHOOK_SOURCE if same_private_chat else "line_webhook_event",
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

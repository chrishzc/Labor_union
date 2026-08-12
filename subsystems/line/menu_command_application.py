"""Canonical message intents for per-user LINE Rich Menu selection."""

from __future__ import annotations

import json

from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
from shared_kernel.ports import OutboxIntent
from subsystems.line.ports import LineAuditIntent
from subsystems.line.rich_menu_binding import RICH_MENU_BINDING_INTENT


_UNION_MENU_COMMANDS = {"工會選單", "開啟客服系統", "月嫂驗證管理"}


class LineMenuCommandApplication:
    def handle(self, inbox, unit_of_work, line_user_id, text: str) -> bool:
        command = text.strip()
        if command in _UNION_MENU_COMMANDS:
            return self._queue_union_menu(inbox, unit_of_work, line_user_id)
        if command.lower() == "esc":
            self._queue_menu(inbox, unit_of_work, line_user_id, "default_menu", "esc")
            return True
        return False

    def _queue_union_menu(self, inbox, unit_of_work, line_user_id) -> bool:
        binding = unit_of_work.identities.get(line_user_id)
        if binding is None or binding.status is not LineIdentityBindingStatus.BOUND:
            return False
        if binding.subject_type is not LineBindingSubjectType.ADMIN:
            return False
        self._queue_menu(inbox, unit_of_work, line_user_id, "union_staff_menu", "union-menu")
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

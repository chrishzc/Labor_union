import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from domains.line.identities import LineSourceType, LineUserId, LineWebhookEventId
from subsystems.line.service_help_application import LineServiceHelpApplication
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers


@pytest.mark.parametrize("text", [
    "切換選單", "選單切換", "管理者選單",
    "客戶選單", "客戶專區", "切換客戶",
    "訪客選單", "服務選單", "切換訪客", "一般選單", "一般用戶選單", "切換一般", "esc", "ESC",
    "月嫂選單", "月嫂專區", "切換月嫂",
    "工會選單", "工會客服", "切換工會",
])
def test_retired_private_menu_text_does_not_send_a_reply_or_change_the_menu(text: str) -> None:
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    inbox = SimpleNamespace(event=SimpleNamespace(
        event_id=LineWebhookEventId("synthetic-menu-command"),
        source=SimpleNamespace(source_type=LineSourceType.USER, user_id=LineUserId("U-synthetic")),
        occurred_at=now,
        payload_json=json.dumps({"message": {"type": "text", "text": text}}),
    ))
    unit_of_work = Mock()
    handlers = LineWebhookIdentityHandlers(
        lambda: now,
        lambda purpose, flow: "https://example.test/identity",
        service_help_application=LineServiceHelpApplication(lambda: now),
    )

    assert not handlers.handle_reply_message(inbox, unit_of_work)
    handlers.handle_message(inbox, unit_of_work)

    unit_of_work.delivery_tasks.enqueue.assert_not_called()
    unit_of_work.outbox.append.assert_not_called()
    unit_of_work.identities.select_role.assert_not_called()
    unit_of_work.identity_flows.open.assert_not_called()

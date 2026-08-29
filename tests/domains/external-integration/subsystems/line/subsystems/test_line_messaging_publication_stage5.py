"""Stage 5 task control, media outbox, and Rich Menu reliability contracts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
    transition_delivery_status,
)
from domains.line.identities import (
    LineDeliveryTaskId,
    LineDestinationId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
)
from domains.line.webhook import (
    LineWebhookInboxSnapshot,
    LineWebhookProcessingStatus,
    build_line_webhook_event,
)
from infrastructure.line.rich_menu_image_store import FileSystemRichMenuImageStore
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.delivery_admin_application import LineDeliveryTaskAdminApplication
from subsystems.line.delivery_admin_contracts import ControlLineDeliveryTaskCommand
from subsystems.line.media_application import schedule_line_media_archive
from subsystems.line.rich_menu_definition import rich_menu_provider_definition

NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


class FakeUow:
    def __init__(self, **items):
        self.__dict__.update(items)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class Receipts:
    def __init__(self):
        self.items = {}

    def get(self, key):
        return self.items.get(key.value)

    def append(self, receipt):
        self.items[receipt.key.value] = receipt


class Recording:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


class DeliveryTasks:
    def __init__(self, task):
        self.task = task
        self.retry_calls = 0

    def get(self, _task_id):
        return self.task

    def retry_failed(self, _task_id, _now):
        self.retry_calls += 1
        self.task = LineDeliveryTaskSnapshot(
            self.task.task_id,
            self.task.request,
            LineDeliveryStatus.PENDING,
            0,
        )
        return self.task


def test_manual_failed_delivery_retry_is_idempotent_and_audited() -> None:
    repository = DeliveryTasks(_failed_task())
    uow = FakeUow(delivery_tasks=repository, receipts=Receipts(), audit=Recording())
    application = LineDeliveryTaskAdminApplication(lambda: uow, clock=lambda: NOW)
    command = ControlLineDeliveryTaskCommand(
        LineDeliveryTaskId(1),
        ActorContext("admin:1", ("line.task.control",)),
        "人工確認後重送",
        IdempotencyKey("retry-delivery:1"),
        CorrelationId("retry-delivery:1"),
    )

    first = application.retry(command)
    second = application.retry(command)

    assert first.status is LineDeliveryStatus.PENDING
    assert second.status is LineDeliveryStatus.PENDING
    assert repository.retry_calls == 1
    assert uow.audit.items[0].action == "line.delivery.retry"
    assert transition_delivery_status(LineDeliveryStatus.FAILED, LineDeliveryStatus.PENDING)


def test_image_message_creates_durable_media_outbox_intent() -> None:
    outbox = Recording()
    event = build_line_webhook_event(
        provider_event_id="event-media-1",
        destination_id=LineDestinationId("destination-1"),
        event_type="message",
        source=LineSourceIdentity(LineSourceType.USER, "U-media", LineUserId("U-media")),
        occurred_at=NOW,
        canonical_payload={
            "type": "message",
            "message": {"id": "media-1", "type": "image"},
            "source": {"type": "user", "userId": "U-media"},
            "timestamp": 1,
        },
    )
    inbox = LineWebhookInboxSnapshot(
        event,
        LineWebhookProcessingStatus.PROCESSING,
        ExpectedVersion(1),
    )

    assert schedule_line_media_archive(inbox, FakeUow(outbox=outbox)) is True
    assert outbox.items[0].intent_type == "line.media.archive"
    assert json.loads(outbox.items[0].payload_json)["provider_media_id"] == "media-1"


def test_rich_menu_definition_and_image_are_deterministic(tmp_path) -> None:
    menu = {
        "id": "menu-1",
        "name": "測試選單",
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "chat_bar_text": "開啟選單",
        "appearance": {"image_mode": "generated", "background_color": "#FFFFFF"},
        "buttons": [
            {
                "label": "開始",
                "bounds": {"x": 0, "y": 0, "width": 2500, "height": 843},
                "action": {"type": "message", "text": "開始"},
            }
        ],
    }
    provider = json.loads(rich_menu_provider_definition(menu))
    store = FileSystemRichMenuImageStore(tmp_path)
    definition = canonical_line_payload_json(menu)

    first = store.materialize(definition)
    second = store.materialize(definition)

    assert provider["chatBarText"] == "開啟選單"
    assert first == second
    assert store.load(first)[1] == "image/jpeg"


def _failed_task():
    request = LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId("U-task")),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "測試"}),
        NOW + timedelta(minutes=1),
        IdempotencyKey("delivery:1"),
        CorrelationId("delivery:1"),
        "test",
        "1",
    )
    return LineDeliveryTaskSnapshot(
        LineDeliveryTaskId(1),
        request,
        LineDeliveryStatus.FAILED,
        3,
    )

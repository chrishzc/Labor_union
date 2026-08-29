"""
File: test_line_delivery_notification_intent_state.py
Description: 驗證 provider 成功後同步標記通知意圖，避免後續完成事件誤取消已送達訊息。
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryLease,
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineDeliveryTaskId, LineUserId, LineProviderMessageId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.delivery_contracts import LineProviderOutcome, LineProviderOutcomeType
from subsystems.line.delivery_worker import LineDeliveryWorker


def test_successful_delivery_marks_linked_notification_intent_provider_accepted() -> None:
    now = datetime(2026, 8, 16, 10, tzinfo=UTC)
    task = LineDeliveryTaskSnapshot(
        LineDeliveryTaskId(5),
        LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId("U-caregiver")),
            LineMessageKind.TEXT, canonical_line_payload_json({"text": "提醒"}), now,
            IdempotencyKey("delivery-5"), CorrelationId("delivery-5"),
            "case_staff_assignment", "8",
        ),
        LineDeliveryStatus.PROCESSING, 0,
        LineDeliveryLease(LineDeliveryTaskId(5), "worker-1", now, now + timedelta(minutes=1)),
    )
    recorded: list[object] = []

    class Uow:
        def __init__(self):
            self.delivery_tasks = SimpleNamespace(record_attempt=recorded.append)
            self.notification_rules = SimpleNamespace(
                mark_delivery_task_provider_accepted=lambda task_id: recorded.append(("accepted", task_id))
            )

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            recorded.append("commit")

    worker = LineDeliveryWorker(lambda: Uow(), SimpleNamespace(), "worker-1", lambda: now)
    worker._record(task, LineProviderOutcome(LineProviderOutcomeType.SUCCESS, LineProviderMessageId("msg-5")))

    assert recorded[1:] == [("accepted", 5), "commit"]

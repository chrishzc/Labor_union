import pytest

from subsystems.scheduling.matching_schedule_confirmation import (
    MatchingScheduleConfirmationWorkflow,
)
from infrastructure.mysql.matching_schedule_confirmation_repository import (
    MySqlMatchingScheduleConfirmationRepository,
    _delivery_status,
)
from domains.line.delivery import LineMessageKind


class _Cursor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))


class _DeliveryTasks:
    def __init__(self) -> None:
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)


class _Repository:
    def __init__(self):
        self.rolled_back = False

    def confirm(self, *args):
        return {"gate_passed": True}

    def commit(self):
        return None

    def rollback(self):
        self.rolled_back = True


def test_schedule_rejection_requires_a_reason():
    workflow = MatchingScheduleConfirmationWorkflow(_Repository())

    with pytest.raises(ValueError, match="rejection_reason_required"):
        workflow.confirm(1, "rejected", "admin", "", "key-68")


def test_schedule_send_requires_every_recipient_to_have_line_binding():
    payloads = (
        {"key": "customer", "line_user_id": "U-customer"},
        {"key": "caregiver:7", "line_user_id": None},
    )

    with pytest.raises(ValueError, match="recipient_line_binding_required:caregiver:7"):
        MySqlMatchingScheduleConfirmationRepository._require_line_binding(payloads)


def test_schedule_recipient_enqueue_uses_a_canonical_flex_delivery_request():
    repository = MySqlMatchingScheduleConfirmationRepository(object())
    deliveries = _DeliveryTasks()
    repository.deliveries = deliveries
    cursor = _Cursor()
    payload = {
        "audience": "customer",
        "key": "customer",
        "segment_id": None,
        "line_user_id": "U-customer",
        "dates": ["2026-08-01"],
    }

    repository._enqueue(cursor, 9, 7, payload, "send-key")

    assert deliveries.requests[0].message_kind is LineMessageKind.FLEX
    assert deliveries.requests[0].idempotency_key.value == "schedule:send-key:9"
    assert deliveries.requests[0].source_aggregate_type == "matching_schedule_recipient"
    assert deliveries.requests[0].source_aggregate_identity == "9"
    assert "matching_schedule_line_interactions" in cursor.calls[0][0]


def test_schedule_delivery_status_projects_the_canonical_task_outcome():
    assert _delivery_status({"delivery_status": "queued", "processing_status": "sent"}) == "sent"
    assert _delivery_status({"delivery_status": "queued", "processing_status": "failed"}) == "failed"
    assert _delivery_status({"delivery_status": "queued", "processing_status": "pending"}) == "queued"

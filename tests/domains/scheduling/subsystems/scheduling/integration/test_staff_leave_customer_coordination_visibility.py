from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from domains.line.identities import LineUserId
from subsystems.line import staff_leave_customer_coordination as coordination
from subsystems.scheduling.staff_leave_intake_workflow import (
    StaffLeaveIntakeWorkflowError,
)


NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)


class _Delivery:
    def __init__(self):
        self.requests = []

    def enqueue(self, request):
        self.requests.append(request)


class _UnitOfWork:
    def __init__(self):
        self._connection = object()
        self.delivery_tasks = _Delivery()
        self.customer_service = SimpleNamespace()


def _application():
    return coordination.StaffLeaveCustomerCoordinationApplication(
        lambda: None,
        lambda: None,
        lambda: NOW,
    )


def _context(*, recipient="U-customer"):
    return {
        "request_id": 17,
        "request_version": 4,
        "leave_start_date": date(2026, 9, 20),
        "leave_end_date": date(2026, 9, 21),
        "targets": [
            {"case_no": "CASE-1", "client_line_user_id": recipient},
        ],
    }


def _inbox(*, event_id="event-1"):
    return SimpleNamespace(
        event=SimpleNamespace(
            source=SimpleNamespace(
                user_id=LineUserId("U-customer"),
                source_type=SimpleNamespace(value="user"),
            ),
            event_id=SimpleNamespace(value=event_id),
            occurred_at=NOW,
            payload_json=json.dumps(
                {
                    "postback": {
                        "data": coordination._postback_value(
                            17, 4, "CASE-1", "agree_defer"
                        )
                    }
                }
            ),
        )
    )


def test_missing_current_recipient_does_not_invent_a_delivery_target():
    application = _application()
    unit = _UnitOfWork()

    application._enqueue_inquiries(_context(recipient=None), unit)

    assert unit.delivery_tasks.requests == []


def test_inquiry_card_identifies_the_exact_leave_period():
    application = _application()
    unit = _UnitOfWork()

    application._enqueue_inquiries(_context(), unit)

    assert len(unit.delivery_tasks.requests) == 1
    payload = json.loads(unit.delivery_tasks.requests[0].payload_json)
    texts = [
        item["text"]
        for item in payload["contents"]["body"]["contents"]
        if item.get("type") == "text"
    ]
    assert "案件：CASE-1" in texts
    assert "請假期間：2026-09-20～2026-09-21" in texts
    assert "2026-09-20～2026-09-21" in payload["altText"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("leave_request_stale", "這個確認已失效"),
        (
            "leave_customer_decision_idempotency_conflict",
            "這個確認目前無法更改",
        ),
        ("leave_customer_recipient_mismatch", "這個確認目前無法使用"),
    ],
)
def test_terminal_customer_choice_errors_create_safe_visible_result(
    monkeypatch, code, expected
):
    class _Workflow:
        def __init__(self, _repository):
            pass

        def record_customer_decision(self, _command):
            raise StaffLeaveIntakeWorkflowError(code)

    monkeypatch.setattr(coordination, "StaffLeaveIntakeWorkflow", _Workflow)
    unit = _UnitOfWork()

    assert _application().handle_postback(_inbox(), unit) is True

    assert len(unit.delivery_tasks.requests) == 1
    request = unit.delivery_tasks.requests[0]
    text = json.loads(request.payload_json)["text"]
    assert expected in text
    assert "CASE-1" not in text
    assert request.idempotency_key.value == "leave-customer-decision-rejected:event-1"


def test_terminal_error_ack_is_stable_for_exact_webhook_replay(monkeypatch):
    class _Workflow:
        def __init__(self, _repository):
            pass

        def record_customer_decision(self, _command):
            raise StaffLeaveIntakeWorkflowError("leave_request_stale")

    monkeypatch.setattr(coordination, "StaffLeaveIntakeWorkflow", _Workflow)
    first = _UnitOfWork()
    second = _UnitOfWork()
    inbox = _inbox(event_id="event-replay")

    assert _application().handle_postback(inbox, first) is True
    assert _application().handle_postback(inbox, second) is True

    first_request = first.delivery_tasks.requests[0]
    second_request = second.delivery_tasks.requests[0]
    assert first_request.idempotency_key == second_request.idempotency_key
    assert first_request.fingerprint == second_request.fingerprint

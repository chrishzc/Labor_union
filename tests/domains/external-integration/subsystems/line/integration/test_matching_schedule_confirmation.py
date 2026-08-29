"""
File: test_matching_schedule_confirmation.py
Description: 驗證日期表 LINE／人工快照、確認原因與版本失效契約。
"""

import json
from datetime import date

import pytest

from subsystems.scheduling.matching_schedule_confirmation import (
    MatchingScheduleConfirmationWorkflow,
)
from infrastructure.mysql.matching_schedule_confirmation_repository import (
    MySqlMatchingScheduleConfirmationRepository,
    _delivery_status,
    _schedule_confirmation_card,
    _schedule_payload,
    _snapshot_status,
)
from domains.line.delivery import LineMessageKind


class _Cursor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))


class _QueryCursor:
    def __init__(self, one_rows, many_rows):
        self._one_rows = iter(one_rows)
        self._many_rows = iter(many_rows)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return None

    def fetchone(self):
        return next(self._one_rows)

    def fetchall(self):
        return next(self._many_rows)


class _QueryConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


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

    def prepare_manual(self, *args):
        return {"snapshot_status": "manual_ready"}


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


@pytest.mark.parametrize("value", ["rejected", "manually_confirmed", "manually_revoked"])
def test_manual_schedule_updates_require_a_reason(value):
    workflow = MatchingScheduleConfirmationWorkflow(_Repository(), _UnitOfWork)

    with pytest.raises(ValueError, match="confirmation_reason_required"):
        workflow.confirm(1, value, "admin", "", "key-68")


def test_manual_schedule_preparation_requires_a_reason():
    workflow = MatchingScheduleConfirmationWorkflow(_Repository(), _UnitOfWork)

    with pytest.raises(ValueError, match="manual_schedule_confirmation_reason_required"):
        workflow.prepare_manual("CASE-68", 18, "admin", " ", 1, "f" * 64, "key-68")


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
    payload = _schedule_payload("customer", "customer", None, "U-customer", ["2026-08-08", "2026-08-09"])

    repository._enqueue(cursor, 9, 7, payload, "send-key")

    assert deliveries.requests[0].message_kind is LineMessageKind.FLEX
    assert deliveries.requests[0].idempotency_key.value == "schedule:send-key:9"
    assert deliveries.requests[0].source_aggregate_type == "matching_schedule_recipient"
    assert deliveries.requests[0].source_aggregate_identity == "9"
    assert "matching_schedule_line_interactions" in cursor.calls[0][0]


def test_schedule_card_includes_sunday_to_saturday_weekly_counts():
    payload = _schedule_payload("customer", "customer", None, "U-customer", ["2026-08-08", "2026-08-09"])

    card = json.loads(_schedule_confirmation_card(payload, "token-68"))

    contents = card["contents"]["body"]["contents"]
    assert contents[2]["text"] == "共 2 個服務日／2 週"
    assert "第1週 2026-08-02～2026-08-08（1日）：2026-08-08" in contents[3]["text"]
    assert "第2週 2026-08-09～2026-08-15（1日）：2026-08-09" in contents[3]["text"]


def test_schedule_delivery_status_projects_the_canonical_task_outcome():
    assert _delivery_status({"delivery_status": "queued", "processing_status": "sent"}) == "sent"
    assert _delivery_status({"delivery_status": "queued", "processing_status": "failed"}) == "failed"
    assert _delivery_status({"delivery_status": "queued", "processing_status": "pending"}) == "queued"


def test_schedule_snapshot_with_old_confirmed_date_version_is_sent_outdated():
    snapshot = {
        "id": 9,
        "confirmed_version_id": 3,
        "status": "invalidated",
        "current_marker": None,
    }

    assert _snapshot_status(4, snapshot) == "sent_outdated"


def test_schedule_snapshot_for_current_version_without_current_marker_is_not_sent():
    snapshot = {
        "id": 9,
        "confirmed_version_id": 4,
        "status": "invalidated",
        "current_marker": None,
    }

    assert _snapshot_status(4, snapshot) == "not_sent"


def test_current_draft_snapshot_is_projected_as_manual_ready():
    snapshot = {
        "id": 9,
        "confirmed_version_id": 4,
        "status": "draft",
        "current_marker": 1,
    }

    assert _snapshot_status(4, snapshot) == "manual_ready"


def test_schedule_query_projects_old_sent_snapshot_as_outdated_without_reusing_confirmations():
    cursor = _QueryCursor(
        one_rows=[
            {"id": 4, "version": 2},
            {"line_user_id": "U-client"},
            {"id": 9, "confirmed_version_id": 3, "status": "invalidated", "current_marker": None},
            {"line_user_id": "U-client"},
        ],
        many_rows=[
            [{"service_date": date(2026, 8, 4)}], [],
            [{"service_date": date(2026, 8, 3)}], [],
        ],
    )
    repository = MySqlMatchingScheduleConfirmationRepository(_QueryConnection(cursor))

    result = repository.query("CASE-68", 18)

    assert result["snapshot_status"] == "sent_outdated"
    assert result["recipients"] == []
    assert result["gate_passed"] is False
    assert result["schedule_preview"]["weeks"][0]["service_dates"] == ["2026-08-04"]
    assert result["outdated_schedule_preview"]["weeks"][0]["service_dates"] == ["2026-08-03"]

"""File: test_scheduling_checkpoint_notification_source.py
Description: 驗證服務結束 checkpoint 僅投影一次為 LINE source event，未知資料依 retry policy 留在 owner outbox。"""

from datetime import datetime, timezone

from subsystems.line.scheduling_checkpoint_notification_source import (
    SchedulingCheckpointNotificationSourceProjector,
    SchedulingCheckpointOutboxItem,
)


def _item(payload=None) -> SchedulingCheckpointOutboxItem:
    return SchedulingCheckpointOutboxItem(
        31,
        12,
        payload or {
            "assignment_id": 8,
            "baby_log_completed": False,
            "case_no": "CASE-8",
            "requires_cooking": True,
            "service_date": "2026-08-16",
            "staff_id": 4,
        },
        datetime(2026, 8, 16, 10, tzinfo=timezone.utc),
    )


def test_projects_checkpoint_as_service_time_source_event() -> None:
    recorded = {"published": [], "retried": []}

    class Outbox:
        def claim_due(self, _now, _limit):
            return (_item(),)

        def mark_published(self, outbox_id):
            recorded["published"].append(outbox_id)

        def mark_retry_or_failed(self, outbox_id, _now, error):
            recorded["retried"].append((outbox_id, error))

    class Registry:
        def register_source_event(self, event):
            recorded["event"] = event
            return 99

    result = SchedulingCheckpointNotificationSourceProjector(Outbox(), Registry()).run_once(
        datetime(2026, 8, 16, 10, tzinfo=timezone.utc)
    )

    assert result == 1
    assert recorded["event"].event_code == "service_time_checkpoint"
    assert recorded["event"].facts["baby_log_completed"] is False
    assert recorded["published"] == [31]
    assert recorded["retried"] == []


def test_invalid_checkpoint_payload_is_not_published_and_is_retried() -> None:
    recorded = []

    class Outbox:
        def claim_due(self, _now, _limit):
            return (_item({"case_no": "CASE-8"}),)

        def mark_published(self, _outbox_id):
            raise AssertionError("invalid checkpoint cannot publish")

        def mark_retry_or_failed(self, outbox_id, _now, error):
            recorded.append((outbox_id, str(error)))

    class Registry:
        def register_source_event(self, _event):
            raise AssertionError("invalid checkpoint cannot register")

    SchedulingCheckpointNotificationSourceProjector(Outbox(), Registry()).run_once(
        datetime(2026, 8, 16, 10, tzinfo=timezone.utc)
    )

    assert recorded == [(31, "assignment ID is invalid")]


def test_projects_and_evaluates_source_in_the_same_owner_outbox_attempt() -> None:
    recorded = []

    class Outbox:
        def claim_due(self, _now, _limit):
            return (_item(),)

        def mark_published(self, outbox_id):
            recorded.append(("published", outbox_id))

        def mark_retry_or_failed(self, *_args):
            raise AssertionError("valid source cannot retry")

    class Registry:
        def register_and_project(self, event):
            recorded.append(("projected", event.event_code))
            return 99

        def register_source_event(self, _event):
            raise AssertionError("production registry must project immediately")

    SchedulingCheckpointNotificationSourceProjector(Outbox(), Registry()).run_once(
        datetime(2026, 8, 16, 10, tzinfo=timezone.utc)
    )

    assert recorded == [("projected", "service_time_checkpoint"), ("published", 31)]

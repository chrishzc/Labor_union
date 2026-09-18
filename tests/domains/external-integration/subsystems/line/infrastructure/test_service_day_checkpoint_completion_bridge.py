"""Issue #311: committed service-day logs must reach checkpoint completion facts."""

import json
from datetime import UTC, datetime

from infrastructure.mysql.service_day_checkpoint_repository import (
    MySqlServiceDayCheckpointRepository,
)
from subsystems.scheduling.service_day_checkpoint_workflow import (
    ServiceDayCheckpointCandidate,
)


class _Cursor:
    def __init__(self, *, log_exists: bool, calls: list[tuple[str, tuple]]):
        self._log_exists = log_exists
        self._calls = calls
        self.lastrowid = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self._calls.append((sql, params))
        if "SELECT id FROM scheduling_service_day_logs" in sql:
            return
        if "INSERT INTO scheduling_service_day_checkpoints" in sql:
            self.lastrowid = 101
            return
        if "INSERT INTO scheduling_service_day_checkpoint_events" in sql:
            self.lastrowid = 201
            return
        if "INSERT INTO scheduling_service_day_checkpoint_outbox" in sql:
            return
        raise AssertionError("unexpected SQL")

    def fetchone(self):
        return {"id": 91} if self._log_exists else None


class _Connection:
    def __init__(self, *, log_exists: bool):
        self.log_exists = log_exists
        self.calls: list[tuple[str, tuple]] = []

    def cursor(self):
        return _Cursor(log_exists=self.log_exists, calls=self.calls)


def _candidate(*, requires_cooking: bool):
    return ServiceDayCheckpointCandidate(
        assignment_id=8,
        schedule_id=18,
        case_no="CASE-311",
        staff_id=4,
        service_date="2026-09-18",
        service_ends_at_utc=datetime(2026, 9, 18, 10, tzinfo=UTC),
        requires_cooking=requires_cooking,
    )


def _outbox_payload(connection: _Connection):
    outbox_calls = [
        params
        for sql, params in connection.calls
        if "INSERT INTO scheduling_service_day_checkpoint_outbox" in sql
    ]
    assert len(outbox_calls) == 1
    return json.loads(outbox_calls[0][2])


def test_non_cooking_completed_log_projects_completed_checkpoint_fact():
    connection = _Connection(log_exists=True)

    created = MySqlServiceDayCheckpointRepository(connection).append_checkpoint(
        _candidate(requires_cooking=False)
    )

    assert created is True
    payload = _outbox_payload(connection)
    assert payload["assignment_id"] == 8
    assert payload["service_date"] == "2026-09-18"
    assert payload["requires_cooking"] is False
    assert payload["baby_log_completed"] is True


def test_cooking_completed_log_projects_completed_checkpoint_fact_after_media_owned_apply():
    connection = _Connection(log_exists=True)

    created = MySqlServiceDayCheckpointRepository(connection).append_checkpoint(
        _candidate(requires_cooking=True)
    )

    assert created is True
    payload = _outbox_payload(connection)
    assert payload["requires_cooking"] is True
    assert payload["baby_log_completed"] is True


def test_missing_log_projects_incomplete_checkpoint_fact_for_reminder_evaluation():
    connection = _Connection(log_exists=False)

    created = MySqlServiceDayCheckpointRepository(connection).append_checkpoint(
        _candidate(requires_cooking=True)
    )

    assert created is True
    payload = _outbox_payload(connection)
    assert payload["requires_cooking"] is True
    assert payload["baby_log_completed"] is False

"""Focused contract for concurrent order-reminder source registration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from infrastructure.mysql import order_pre_start_notification_source_worker as worker_module
from subsystems.line.notification_policy import NotificationSourceEvent


NOW = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
EVENT = NotificationSourceEvent(
    identity="order-pre-start:CASE-CONCURRENT:2026-09-20",
    event_code="order.pre_start_reminder",
    historical_silent=False,
    facts={"case_no": "CASE-CONCURRENT", "planned_start_date": "2026-09-20"},
    source_domain="orders",
    source_aggregate_type="order",
    source_aggregate_identity="CASE-CONCURRENT",
    source_version=1,
    occurred_at=NOW,
)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0
        self.lastrowid = 0
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters=()):
        self.connection.statements.append((sql, tuple(parameters)))
        self.rowcount = 0
        self._one = None
        if sql == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED":
            assert not self.connection.in_transaction
            self.connection.next_transaction_isolation = "READ COMMITTED"
            return
        if sql.startswith("INSERT IGNORE INTO line_notification_source_events"):
            assert self.connection.in_transaction
            # Model the losing scanner after the unique-key wait: the winner's
            # row is committed, so INSERT IGNORE affects zero rows.
            self.rowcount = 0
            return
        if (
            "FROM line_notification_source_events" in sql
            and "source_event_identity=%s" in sql
        ):
            # A repeatable-read snapshot established by the earlier source scan
            # would hide this row.  READ COMMITTED must make the post-wait read
            # observe the winner's committed immutable source.
            assert self.connection.transaction_isolation == "READ COMMITTED"
            self._one = dict(self.connection.existing_source)
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        value = self._one
        self._one = None
        return value


class _Connection:
    def __init__(self, existing_source):
        self.existing_source = existing_source
        self.statements = []
        self.next_transaction_isolation = None
        self.transaction_isolation = None
        self.in_transaction = False
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return _Cursor(self)

    def begin(self):
        assert self.next_transaction_isolation == "READ COMMITTED"
        self.transaction_isolation = self.next_transaction_isolation
        self.next_transaction_isolation = None
        self.in_transaction = True

    def commit(self):
        assert self.in_transaction
        self.commits += 1
        self.in_transaction = False

    def rollback(self):
        if self.in_transaction:
            self.rollbacks += 1
            self.in_transaction = False

    def close(self):
        self.closed = True


class _Projector:
    def __init__(self, _source_repository, notification_repository):
        self.notification_repository = notification_repository

    def run_once(self, _now, *, target_date=None):
        del target_date
        assert self.notification_repository.register_source_event(EVENT) == 41
        return 1


def _existing_source(**changes):
    row = {
        "id": 41,
        "source_aggregate_type": EVENT.source_aggregate_type,
        "source_aggregate_identity": EVENT.source_aggregate_identity,
        "source_version": EVENT.source_version,
        "historical_silent": EVENT.historical_silent,
        "facts_snapshot": dict(EVENT.facts),
    }
    row.update(changes)
    return row


def test_losing_scanner_reads_winner_after_unique_key_wait(monkeypatch):
    connection = _Connection(_existing_source())
    monkeypatch.setattr(
        worker_module, "MySqlOrderPreStartNotificationSourceRepository", lambda _connection: object()
    )
    monkeypatch.setattr(worker_module, "OrderPreStartNotificationSourceProjector", _Projector)

    processed = worker_module.MySqlOrderPreStartNotificationSourceWorker(
        lambda: connection,
        lambda: NOW,
    ).run_once()

    assert processed == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed is True
    assert connection.statements[0][0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"
    assert connection.statements[1][0].startswith("INSERT IGNORE INTO line_notification_source_events")
    assert "source_event_identity=%s" in connection.statements[2][0]


def test_same_identity_with_different_immutable_facts_still_conflicts(monkeypatch):
    connection = _Connection(_existing_source(source_version=2))
    monkeypatch.setattr(
        worker_module, "MySqlOrderPreStartNotificationSourceRepository", lambda _connection: object()
    )
    monkeypatch.setattr(worker_module, "OrderPreStartNotificationSourceProjector", _Projector)

    with pytest.raises(RuntimeError, match="line_notification_source_event_conflict"):
        worker_module.MySqlOrderPreStartNotificationSourceWorker(
            lambda: connection,
            lambda: NOW,
        ).run_once()

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True

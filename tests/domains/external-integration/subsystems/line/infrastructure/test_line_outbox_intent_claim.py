"""Infrastructure coverage for intent-scoped LINE outbox leases."""

from datetime import datetime, timedelta, timezone

import pytest

from infrastructure.mysql.line_receipt_outbox_audit import MySqlLineOutboxWriter
from domains.line.identities import LineUserId
from subsystems.line.outbox_contracts import (
    ClaimLineOutboxQuery,
    CompleteLineOutboxCommand,
    LineOutboxWorkItem,
)

NOW = datetime(2026, 8, 11, 4, tzinfo=timezone.utc)


class RecordingCursor:
    def __init__(self) -> None:
        self.calls = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return ()

    def fetchone(self):
        return {"next_due_at_utc": None}


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()

    def cursor(self):
        return self.cursor_instance


def test_menu_provider_lock_releases_on_error(monkeypatch):
    connection = RecordingConnection()
    cursor = connection.cursor_instance
    monkeypatch.setattr(cursor, "fetchone", lambda: {"acquired": 1})
    monkeypatch.setattr(connection, "rollback", lambda: None, raising=False)
    repository = MySqlLineOutboxWriter(connection)
    with pytest.raises(ValueError, match="fixture failure"):
        with repository.menu_provider_lock(LineUserId("U-fixture")) as acquired:
            assert acquired
            raise ValueError("fixture failure")
    acquire, release = cursor.calls
    assert "GET_LOCK" in acquire[0] and "RELEASE_LOCK" in release[0]
    assert acquire[1] == release[1]
    assert len(acquire[1][0]) == 64


def test_latest_menu_intent_compares_request_id_with_outbox_column_collation(monkeypatch):
    connection = RecordingConnection()
    cursor = connection.cursor_instance
    monkeypatch.setattr(cursor, "fetchone", lambda: {"id": 9})
    assert MySqlLineOutboxWriter(connection).latest_menu_intent_id(LineUserId("U-fixture")) == 9
    sql, _ = cursor.calls[-1]
    assert "CAST(request.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci" in sql


def test_claim_and_due_query_are_scoped_to_requested_intent() -> None:
    connection = RecordingConnection()
    repository = MySqlLineOutboxWriter(connection)
    query = ClaimLineOutboxQuery(
        "worker-1", NOW, intent_type="line.rich_menu.bind"
    )

    assert repository.claim(query) == ()
    assert repository.next_due_at("line.rich_menu.bind") is None

    claim_parameters = connection.cursor_instance.calls[0][1]
    due_parameters = connection.cursor_instance.calls[-1][1]
    assert claim_parameters[0] == "line.rich_menu.bind"
    assert due_parameters == ("line.rich_menu.bind",)


def test_non_retryable_failure_moves_outbox_item_to_dead() -> None:
    connection = RecordingConnection()
    repository = MySqlLineOutboxWriter(connection)
    item = LineOutboxWorkItem(
        7, "line_identity", "U-1", "line.rich_menu.bind", "{}",
        0, 3, "worker-1", NOW,
    )

    repository.complete(
        CompleteLineOutboxCommand(
            item,
            NOW,
            "line_rich_menu_rejected",
            "rejected",
            retryable=False,
        )
    )

    completion_parameters = connection.cursor_instance.calls[0][1]
    assert completion_parameters[0] == "dead"
    assert completion_parameters[1] == 1


class MenuLeaseCursor(RecordingCursor):
    def __init__(self, attempts, created_at):
        super().__init__()
        self.row = {
            "id": 7, "aggregate_type": "line_identity", "aggregate_identity": "U-1",
            "intent_type": "line.rich_menu.bind", "payload_snapshot": "{}",
            "idempotency_identity": "test-menu-work", "attempt_count": attempts,
            "max_attempts": 5, "created_at_utc": created_at,
        }

    def execute(self, statement, parameters=None):
        super().execute(statement, parameters)
        self.statement = statement
        self.parameters = parameters
        if "attempt_count=attempt_count+1" in statement:
            self.row["attempt_count"] += 1
        if "processing_status='dead'" in statement:
            self.row = None

    def fetchall(self):
        if "max_attempts=3" in self.statement:
            return ()
        if "SELECT id,created_at_utc" in self.statement:
            exhausted = self.row and (
                self.row["attempt_count"] >= self.row["max_attempts"]
                or self.row["created_at_utc"] <= self.parameters[-1]
            )
            return (self.row,) if exhausted else ()
        return (self.row,) if self.row else ()


def test_expired_leases_consume_the_same_persisted_attempt_budget():
    connection = RecordingConnection()
    cursor = connection.cursor_instance = MenuLeaseCursor(0, NOW.replace(tzinfo=None))
    for index in range(5):
        # Each cycle constructs a new repository, with no completion from the previous process.
        repository = MySqlLineOutboxWriter(connection)
        now = NOW + timedelta(seconds=90 * index)
        item, = repository.claim(ClaimLineOutboxQuery("worker", now, 1, "line.rich_menu.bind"))
        assert item.attempt_count == index + 1
        assert item.deadline == NOW + timedelta(minutes=10)
        assert item.lease_expires_at == now + timedelta(seconds=90)
    repository = MySqlLineOutboxWriter(connection)
    query = ClaimLineOutboxQuery("worker", NOW + timedelta(seconds=450), 1, "line.rich_menu.bind")
    assert repository.claim(query) == ()
    assert cursor.calls[-2][1][0] == "rich_menu_binding_attempts_exhausted"
    assert repository.claim(query) == ()


def test_deadline_applies_before_reserving_an_attempt():
    connection = RecordingConnection()
    cursor = connection.cursor_instance = MenuLeaseCursor(0, NOW.replace(tzinfo=None) - timedelta(minutes=10))
    repository = MySqlLineOutboxWriter(connection)
    assert repository.claim(ClaimLineOutboxQuery("worker", NOW, 1, "line.rich_menu.bind")) == ()
    assert cursor.calls[-2][1][0] == "rich_menu_binding_deadline_exhausted"


def test_reserved_attempt_completion_uses_exact_lease_and_does_not_count_twice():
    connection = RecordingConnection()
    cursor = connection.cursor_instance
    item = LineOutboxWorkItem(
        7, "line_identity", "U-1", "line.rich_menu.bind", "{}",
        2, 5, "worker", NOW + timedelta(seconds=90), NOW + timedelta(minutes=10), True,
    )
    repository = MySqlLineOutboxWriter(connection)
    repository.complete(CompleteLineOutboxCommand(item, NOW, "line_http_429", "rate limited", 35))
    sql, params = cursor.calls[-1]
    assert params[:3] == ("pending", 2, NOW.replace(tzinfo=None) + timedelta(seconds=35))
    assert "lease_expires_at_utc=%s" in sql
    assert params[-1] == item.lease_expires_at.replace(tzinfo=None)
    cursor.rowcount = 0
    with pytest.raises(RuntimeError, match="line_outbox_lease_lost"):
        repository.complete(CompleteLineOutboxCommand(item, NOW))

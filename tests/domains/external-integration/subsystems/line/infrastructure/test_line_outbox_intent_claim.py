"""Infrastructure coverage for intent-scoped LINE outbox leases."""

from datetime import datetime, timezone

from infrastructure.mysql.line_receipt_outbox_audit import MySqlLineOutboxWriter
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


def test_claim_and_due_query_are_scoped_to_requested_intent() -> None:
    connection = RecordingConnection()
    repository = MySqlLineOutboxWriter(connection)
    query = ClaimLineOutboxQuery(
        "worker-1", NOW, intent_type="line.rich_menu.bind"
    )

    assert repository.claim(query) == ()
    assert repository.next_due_at("line.rich_menu.bind") is None

    claim_parameters = connection.cursor_instance.calls[0][1]
    due_parameters = connection.cursor_instance.calls[1][1]
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

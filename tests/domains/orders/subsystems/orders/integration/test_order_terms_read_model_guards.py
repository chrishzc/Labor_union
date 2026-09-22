from types import SimpleNamespace

import pytest

from infrastructure.mysql.order_terms_read_model import (
    _historical_precision_restarted,
    lock_staff_mutexes,
)


def test_empty_impacted_staff_set_requires_no_mutex_query():
    cursor = SimpleNamespace(execute=lambda *_args: pytest.fail("unexpected SQL"))

    lock_staff_mutexes(cursor, ())


class _RestartCursor:
    def __init__(self, row):
        self.row = row
        self.statement = None
        self.parameters = None

    def execute(self, statement, parameters):
        self.statement = " ".join(statement.split())
        self.parameters = parameters

    def fetchone(self):
        return self.row


def test_historical_precision_restart_provenance_uses_the_immutable_lifecycle_event():
    cursor = _RestartCursor({"id": 17})

    assert _historical_precision_restarted(cursor, "CASE-HISTORY", lock=True) is True
    assert "trigger_event='orders_historical_precision_restart'" in cursor.statement
    assert "ORDER BY id DESC LIMIT 1 FOR UPDATE" in cursor.statement
    assert cursor.parameters == ("CASE-HISTORY", "訂單成立")


def test_missing_historical_precision_restart_event_does_not_enable_the_exception():
    cursor = _RestartCursor(None)

    assert _historical_precision_restarted(cursor, "CASE-NORMAL", lock=False) is False

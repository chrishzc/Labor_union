"""File: test_customer_service_escalation_ticket_adapter.py
Description: 驗證 M4 只解析既有客服 ticket event，並以 CAS 轉移 ticket 狀態。
"""

from __future__ import annotations

import pytest

from infrastructure.mysql.customer_service_repository import (
    CustomerServiceTicketNotFoundError,
    MySqlCustomerServiceRepository,
)


class _Cursor:
    def __init__(self, row=None, *, rowcount=1):
        self.row = row
        self.rowcount = rowcount
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, *cursors):
        self.cursors = list(cursors)

    def cursor(self):
        return self.cursors.pop(0) if self.cursors else _Cursor()


def test_escalation_source_missing_ticket_fails_closed():
    repository = MySqlCustomerServiceRepository(_Connection(_Cursor(None)))
    with pytest.raises(CustomerServiceTicketNotFoundError):
        repository.create_or_append_escalation_ticket(
            type("Command", (), {"source_event_identity": "line-event:missing"})()
        )


def test_start_handling_uses_ticket_root_cas_and_management_event():
    cursor = _Cursor()
    repository = MySqlCustomerServiceRepository(_Connection(cursor))
    repository.get = lambda ticket_id, lock=False: {"ticket_id": ticket_id}  # type: ignore[method-assign]
    result = repository.start_handling_for_escalation(7, 2, "admin:11")
    assert result["ticket_id"] == 7
    assert len(cursor.calls) == 2
    assert "version=%s" in cursor.calls[0][0]
    assert cursor.calls[0][1] == (11, 7, 2)
    assert "customer_service_ticket_events" in cursor.calls[1][0]


def test_resolve_uses_handling_state_guard():
    cursor = _Cursor()
    repository = MySqlCustomerServiceRepository(_Connection(cursor))
    repository.get = lambda ticket_id, lock=False: {"ticket_id": ticket_id}  # type: ignore[method-assign]
    repository.resolve_for_escalation(7, 3, "admin:11", "handled")
    assert "status='handling'" in cursor.calls[0][0]
    assert cursor.calls[0][1] == (7, 3)

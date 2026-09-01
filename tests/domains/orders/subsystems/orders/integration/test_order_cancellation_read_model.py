"""Unit coverage for the cancellation read model's staff-lock boundary."""

from __future__ import annotations

import pytest

from infrastructure.mysql import order_cancellation_read_model as read_model


class StaffLockCursor:
    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return self._result_sets.pop(0)


def test_cancellation_locks_canonical_mutex_before_active_staff_validation():
    cursor = StaffLockCursor([[{"id": 1}, {"id": 2}], [{"id": 1}, {"id": 2}]])

    read_model._lock_staff(cursor, (1, 2))

    mutex_statement, mutex_parameters = cursor.calls[0]
    active_statement, active_parameters = cursor.calls[1]
    assert "ORDER BY id FOR UPDATE" in mutex_statement
    assert mutex_parameters == (1, 2)
    assert "status='active'" in active_statement
    assert "FOR UPDATE" not in active_statement
    assert active_parameters == (1, 2)


def test_cancellation_rejects_inactive_staff_after_mutex_lock():
    cursor = StaffLockCursor([[{"id": 1}, {"id": 2}], [{"id": 1}]])

    with pytest.raises(ValueError, match="scheduling_staff_not_found"):
        read_model._lock_staff(cursor, (1, 2))


def test_cancellation_without_impacted_staff_skips_staff_mutex():
    cursor = StaffLockCursor([])

    read_model._lock_staff(cursor, ())

    assert cursor.calls == []

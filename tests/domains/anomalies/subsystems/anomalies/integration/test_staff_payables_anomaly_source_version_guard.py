"""
File: test_staff_payables_anomaly_source_version_guard.py
Description: 驗證 PAYOUT-001 鎖定根事實與 legacy 版號遷移。
"""

from datetime import date

import pytest

from subsystems.anomalies.source_version import daily_root_source_version
from subsystems.anomalies.staff_payables_anomaly_source import (
    _OVERDUE_PAYABLES_SQL,
    _overdue_request,
    consume_staff_payables_anomaly_sources,
    scan_overdue_staff_payables,
)


_AS_OF = date(2026, 8, 27)


def _row(
    *,
    root_version=3,
    amount_due_ntd=1200,
    balance_ntd=1200,
    due_date=date(2026, 8, 1),
    obligation_status="open",
    projection_status="payable",
):
    return {
        "obligation_identity": "obligation:1",
        "staff_id": 7,
        "amount_due_ntd": amount_due_ntd,
        "balance_ntd": balance_ntd,
        "due_date": due_date,
        "obligation_status": obligation_status,
        "projection_status": projection_status,
        "root_version": root_version,
    }


def test_overdue_scan_locks_canonical_obligation_and_projection() -> None:
    cursor = _Cursor([_row()])

    page = scan_overdue_staff_payables(cursor, as_of=_AS_OF)

    assert page.requests[0].desired.definition_code == "PAYOUT-001"
    assert _OVERDUE_PAYABLES_SQL.rstrip().endswith("FOR UPDATE")
    assert cursor.calls[0][0].rstrip().endswith("FOR UPDATE")


def test_legacy_date_version_is_superseded_by_daily_root_version() -> None:
    request = _overdue_request(_row(root_version=3), _AS_OF)

    expected = daily_root_source_version(as_of=_AS_OF, root_version=3)
    assert request.desired.source_version == expected
    assert request.desired.source_version > _AS_OF.toordinal()


def test_same_day_root_version_advances_source_version() -> None:
    first = _overdue_request(_row(root_version=3), _AS_OF)
    second = _overdue_request(_row(root_version=4), _AS_OF)

    assert second.desired.source_version == first.desired.source_version + 1


@pytest.mark.parametrize(
    "row_overrides",
    (
        {"balance_ntd": 0},
        {"due_date": None},
        {"due_date": _AS_OF},
        {"obligation_status": "cancelled"},
        {"projection_status": "cancelled"},
    ),
)
def test_overdue_predicate_is_inactive_when_balance_is_not_due_or_obligation_is_cancelled(
    row_overrides,
) -> None:
    request = _overdue_request(_row(**row_overrides), _AS_OF)

    assert request.desired.active is False


@pytest.mark.parametrize("root_version", (None, -1, True, 1_000_000_000))
def test_invalid_root_version_fails_closed(root_version) -> None:
    with pytest.raises((TypeError, ValueError)):
        _overdue_request(_row(root_version=root_version), _AS_OF)


def test_scan_lock_failure_rolls_back_without_projecting() -> None:
    connection = _FailingConnection()

    class _Runtime:
        class _UnitOfWork:
            def __init__(self, connection):
                self.connection = connection

            def __enter__(self):
                self.connection.begin()
                return self

            def __exit__(self, exception_type, *_args):
                if exception_type is not None:
                    self.connection.rollback()
                return False

            def commit(self):
                self.connection.commit()

        def failure_unit_of_work(self, connection):
            return self._UnitOfWork(connection)

    result = consume_staff_payables_anomaly_sources(
        connection, as_of=_AS_OF, maximum_items=1, runtime=_Runtime()
    )

    assert result.projected_count == 0
    assert result.active_count == 0
    assert result.error is not None
    assert result.error.code == "transaction_failed"
    assert connection.begin_calls == 1
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


class _FailingCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        raise RuntimeError("root readback unavailable")


class _FailingConnection:
    def __init__(self):
        self.begin_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def begin(self):
        self.begin_calls += 1

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def cursor(self):
        return _FailingCursor()

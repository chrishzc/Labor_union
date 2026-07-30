import ast
import inspect
from datetime import datetime
from datetime import date
from decimal import Decimal

import pytest

from services import caregiver_availability_lock_conversion_service as service


def terms(count=1, *, floor_fee="0.00"):
    return [
        {"segment_id": 10 + index, "hourly_rate": Decimal("300.00"), "floor_fee_allocated": Decimal(floor_fee if index == 0 else "0.00")}
        for index in range(count)
    ]


@pytest.mark.parametrize("value", [0, -1, True, "1", 1.5])
def test_rejects_invalid_lock_id_before_connecting(monkeypatch, value):
    monkeypatch.setattr(service, "get_connection", lambda: pytest.fail("connection must not be opened"))
    with pytest.raises(ValueError):
        service.convert_availability_lock_to_assignments("C-1", value, "event-1", "admin", "paid", terms())


@pytest.mark.parametrize("bad_value", [1.0, "300.00", Decimal("NaN"), Decimal("-1.00")])
def test_rejects_non_decimal_or_invalid_terms_before_connecting(monkeypatch, bad_value):
    monkeypatch.setattr(service, "get_connection", lambda: pytest.fail("connection must not be opened"))
    invalid = [{"segment_id": 10, "hourly_rate": bad_value, "floor_fee_allocated": Decimal("0.00")}]
    with pytest.raises(ValueError):
        service.convert_availability_lock_to_assignments("C-1", 7, "event-1", "admin", "paid", invalid)


def test_terms_require_exactly_one_entry_per_segment():
    with pytest.raises(ValueError, match="duplicate"):
        service._normalize_terms([
            {"segment_id": 10, "hourly_rate": Decimal("1"), "floor_fee_allocated": Decimal("0")},
            {"segment_id": 10, "hourly_rate": Decimal("1"), "floor_fee_allocated": Decimal("0")},
        ])


def test_payload_is_stable_and_decimal_safe():
    request = service._normalize_request("C-1", 7, "event-1", "admin", "paid", terms(floor_fee="50.00"))
    payload = service._payload(request, {"plan_id": 3}, [])
    assert payload == {
        "case_no": "C-1", "lock_id": 7, "plan_id": 3, "assignments": [],
        "terms": [{"segment_id": 10, "hourly_rate": "300.00", "floor_fee_allocated": "50.00"}],
    }


def test_database_decimal_accepts_integral_values_but_never_float():
    assert service._database_decimal(9, "hours", positive=True) == Decimal("9.00")
    with pytest.raises(ValueError):
        service._database_decimal(9.0, "hours", positive=True)


def test_source_uses_transaction_schedule_generator_and_no_payment_writes():
    source = inspect.getsource(service)
    tree = ast.parse(source)
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert "generate_assignment_schedule_in_transaction" in calls
    assert "lock_staff_occupancy_mutex" in calls
    upper = source.upper()
    assert "INSERT INTO CLIENT_PAYMENTS" not in upper
    assert "INSERT INTO STAFF_PAYMENTS" not in upper
    assert "UPDATE STAFF_SCHEDULE" not in upper
    assert "DELETE FROM" not in upper


def test_rejects_current_or_historical_lock_days():
    class Cursor:
        def __init__(self):
            self.rowcount = 1
            self.lastrowid = 101

        def execute(self, sql, params=()):
            self.sql = sql

        def fetchone(self):
            if "CURRENT_DATE" in self.sql:
                return {"current_date": date(2026, 8, 2)}
            if "FROM orders" in self.sql:
                return {
                    "case_no": "C-1", "status": "洽談中", "start_date": date(2026, 8, 2),
                    "end_date": date(2026, 8, 2), "service_days": 1,
                    "service_hours_per_day": Decimal("8"),
                    "floor_fee": Decimal("0"),
                }
            if "FROM client_payments" in self.sql:
                return {"case_no": "C-1", "deposit_receivable": Decimal("1"), "deposit_received": Decimal("1")}
            if "FROM caregiver_availability_locks" in self.sql:
                return {"id": 7, "plan_id": 3, "status": "active", "is_active": 1, "released_by": None, "released_at": None}
            if "FROM caregiver_matching_plans" in self.sql:
                return {
                    "id": 3, "case_no": "C-1", "status": "accepted", "is_active": 1,
                    "start_date": date(2026, 8, 2), "end_date": date(2026, 8, 2),
                }
            raise AssertionError(self.sql)

        def fetchall(self):
            if "client_payment_transactions" in self.sql:
                return [{
                    "transaction_type": "receipt", "transaction_status": "succeeded", "stage": "deposit",
                    "amount": Decimal("1"), "reversal_of_transaction_id": None,
                }]
            if "caregiver_matching_plan_segments" in self.sql:
                return [{
                    "id": 10, "plan_id": 3, "segment_order": 1, "staff_id": 20,
                    "assigned_start_date": date(2026, 8, 2), "assigned_end_date": date(2026, 8, 2),
                }]
            if "caregiver_availability_lock_days" in self.sql:
                return [{
                    "id": 30, "segment_id": 10, "staff_id": 20, "lock_date": date(2026, 8, 2),
                    "active_marker": 1, "released_by": None, "released_at": None,
                }]
            if "case_staff_assignments" in self.sql:
                return []
            raise AssertionError(self.sql)

    monkeypatch = pytest.MonkeyPatch()
    cursor = Cursor()
    monkeypatch.setattr(
        service,
        "normalize_plan_snapshot",
        lambda *_: {
            "start_date": date(2026, 8, 2), "end_date": date(2026, 8, 2),
            "segments": [{
                "segment_id": 10, "segment_order": 1, "staff_id": 20,
                "assigned_start_date": date(2026, 8, 2), "assigned_end_date": date(2026, 8, 2),
            }],
            "lock_rows": [{"segment_id": 10, "staff_id": 20, "lock_date": "2026-08-02"}],
        },
    )
    try:
        with pytest.raises(ValueError, match="historical"):
            service._load_state(
                cursor,
                service._normalize_request("C-1", 7, "event-1", "admin", "paid", terms()),
            )
    finally:
        monkeypatch.undo()


def test_deposit_refund_requires_explicit_reversal_link():
    rows = [{
        "transaction_type": "refund", "transaction_status": "succeeded", "stage": "deposit",
        "amount": Decimal("1.00"), "reversal_of_transaction_id": None,
    }]
    with pytest.raises(ValueError, match="reversal_of_transaction_id"):
        service._validate_deposit_transactions(rows, Decimal("-1.00"))


class TransactionCursor:
    def __init__(self, *, insert_rowcount=1):
        self._insert_rowcount = insert_rowcount
        self.lock_day_count = 1
        self.rowcount = insert_rowcount
        self.lastrowid = 101
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        self.rowcount = (
            self.lock_day_count
            if "UPDATE caregiver_availability_lock_days" in sql
            else self._insert_rowcount
        )

    def close(self):
        self.calls.append(("CURSOR_CLOSE", ()))


class TransactionConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _install_conversion_path(
    monkeypatch,
    cursor,
    connection,
    *,
    actual_hours=Decimal("8.00"),
    calendar_days=1,
    target_hours=Decimal("8.00"),
):
    segment_end = date(2026, 8, 2 + calendar_days)
    lock_days = [
        {
            "id": 30 + offset,
            "segment_id": 10,
            "staff_id": 20,
            "lock_date": date(2026, 8, 3 + offset),
            "active_marker": 1,
            "released_by": None,
            "released_at": None,
        }
        for offset in range(calendar_days)
    ]
    lock_calls = []
    cursor.lock_day_count = calendar_days

    def load_days(passed_cursor, lock_id, *, active_only=True, for_update=True):
        lock_calls.append((passed_cursor, lock_id, active_only, for_update))
        return [dict(row) for row in lock_days]

    monkeypatch.setattr(service, "get_connection", lambda: connection)
    monkeypatch.setattr(service, "_load_preflight_lock_days", load_days)
    monkeypatch.setattr(service, "lock_staff_occupancy_mutex", lambda passed_cursor, ids: list(ids))
    monkeypatch.setattr(service, "_existing_result", lambda *_: None)
    monkeypatch.setattr(
        service,
        "_load_state",
        lambda *_: {
            "current_date": date(2026, 8, 1),
            "order": {
                "start_date": date(2026, 8, 3),
                "end_date": segment_end,
                "service_days": int(target_hours / Decimal("8.00")),
                "daily_hours": Decimal("8.00"),
                "target_hours": target_hours,
                "floor_fee": Decimal("0.00"),
            },
            "plan_id": 3,
            "lock_days": lock_days,
            "snapshot": {"segments": [{
                "segment_id": 10, "segment_order": 1, "staff_id": 20,
                "assigned_start_date": date(2026, 8, 3),
                "assigned_end_date": segment_end,
            }]},
        },
    )
    monkeypatch.setattr(service, "validate_assignment_plan_transition", lambda **_: None)
    monkeypatch.setattr(
        service,
        "generate_assignment_schedule_in_transaction",
        lambda *_: {
            "assignment_schedule": [{
                "work_date": "2026-08-03", "is_work_day": 1, "is_double_pay": 0, "notes": None,
            }],
            "actual_hours": actual_hours,
        },
    )
    return lock_calls


def test_public_service_acquires_mutex_before_for_update_and_commits_once(monkeypatch):
    cursor = TransactionCursor()
    connection = TransactionConnection(cursor)
    lock_calls = _install_conversion_path(monkeypatch, cursor, connection)

    result = service.convert_availability_lock_to_assignments(
        "C-1", 7, "event-1", "admin", "paid", terms(),
    )

    assert result["result"] == "created"
    assert [call[3] for call in lock_calls[:2]] == [False, True]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert any(
        "UPDATE orders SET status = '訂單成立'" in statement
        for statement, _ in cursor.calls
    )


def test_public_service_rolls_back_when_actual_hours_do_not_reconcile(monkeypatch):
    cursor = TransactionCursor()
    connection = TransactionConnection(cursor)
    _install_conversion_path(monkeypatch, cursor, connection, actual_hours=Decimal("7.00"))

    with pytest.raises(ValueError, match="accounting totals"):
        service.convert_availability_lock_to_assignments(
            "C-1", 7, "event-1", "admin", "paid", terms(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_conversion_conserves_order_target_without_copying_planned_hours(monkeypatch):
    cursor = TransactionCursor()
    connection = TransactionConnection(cursor)
    _install_conversion_path(
        monkeypatch,
        cursor,
        connection,
        actual_hours=Decimal("8.00"),
        calendar_days=2,
        target_hours=Decimal("8.00"),
    )

    result = service.convert_availability_lock_to_assignments(
        "C-1", 7, "event-1", "admin", "paid", terms(),
    )

    assert result["planned_hours"] == Decimal("16.00")
    assert result["actual_hours"] == Decimal("8.00")
    assert connection.commits == 1


def test_public_service_rolls_back_on_assignment_insert_rowcount(monkeypatch):
    cursor = TransactionCursor(insert_rowcount=0)
    connection = TransactionConnection(cursor)
    _install_conversion_path(monkeypatch, cursor, connection)

    with pytest.raises(ValueError, match="assignment insert rowcount"):
        service.convert_availability_lock_to_assignments(
            "C-1", 7, "event-1", "admin", "paid", terms(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_existing_conversion_rejects_incomplete_lifecycle_before_returning():
    class ReplayCursor:
        def execute(self, sql, params=()):
            self.sql = sql

        def fetchone(self):
            if "FROM orders" in self.sql:
                return {"status": "訂單成立"}
            return {
                "id": 7, "plan_id": 3, "status": "converted", "is_active": None,
                "released_by": "admin", "released_at": None,
            }

    request = service._normalize_request("C-1", 7, "event-1", "admin", "paid", terms())
    payload = {
        "case_no": "C-1", "lock_id": 7, "plan_id": 3,
        "terms": [{"segment_id": 10, "hourly_rate": "300.00", "floor_fee_allocated": "0.00"}],
        "assignments": [{"not": "trusted"}],
    }
    with pytest.raises(ValueError, match="lifecycle"):
        service._validate_existing_conversion(ReplayCursor(), request, payload)

"""
File: test_historical_baseline_obligation_sync.py
Description: 驗證歷史完成訂單自動同步月嫂薪資基準應付義務之計算、到期日與等冪性。
"""

from datetime import date
from decimal import Decimal
import pytest

from subsystems.payroll.historical_baseline_obligation_sync import (
    sync_historical_staff_baseline_obligations,
)


class _MockCursor:
    def __init__(self, orders=(), assignments=(), existing_obligations=()):
        self.orders = list(orders)
        self.assignments = list(assignments)
        self.existing_obligations = list(existing_obligations)
        self.executed = []
        self.lastrowid = 101
        self._next_fetch = None

    def execute(self, sql, params=()):
        norm = " ".join(sql.split())
        self.executed.append((norm, params))

        if "FROM orders o" in norm:
            self._next_fetch = self.orders
        elif "FROM case_staff_assignments" in norm:
            self._next_fetch = self.assignments
        elif "FROM historical_service_day_items" in norm:
            self._next_fetch = []
        elif "FROM staff_obligations" in norm:
            self._next_fetch = self.existing_obligations
        elif "SELECT aggregate_version" in norm:
            self._next_fetch = [{"aggregate_version": 1}]
        elif "INSERT INTO" in norm:
            self.lastrowid += 1
            self._next_fetch = None
        else:
            self._next_fetch = None

    def fetchone(self):
        if self._next_fetch and isinstance(self._next_fetch, list):
            return self._next_fetch[0] if self._next_fetch else None
        return self._next_fetch

    def fetchall(self):
        if self._next_fetch and isinstance(self._next_fetch, list):
            res = list(self._next_fetch)
            self._next_fetch = None
            return res
        return ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def close(self):
        pass


class _MockConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_sync_creates_baseline_obligation_for_completed_historical_order():
    order = {
        "case_no": "115000088",
        "client_id": 1,
        "staff_id": 99,
        "status": "歷史訂單－服務完成",
        "lifecycle_version": 1,
        "service_days": 20,
        "service_hours_per_day": Decimal("9.0"),
        "floor_fee": Decimal("0"),
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 20),
        "actual_start_date": date(2026, 9, 1),
        "actual_end_date": date(2026, 9, 20),
        "staff_payment_due_date": None,
        "identity_status": "一般市民",
    }
    assignment = {
        "id": 12,
        "staff_id": 99,
        "hourly_rate": Decimal("250.00"),
        "planned_hours": Decimal("180.00"),
        "actual_hours": Decimal("180.00"),
        "floor_fee_allocated": Decimal("0.00"),
    }

    cursor = _MockCursor(orders=[order], assignments=[assignment], existing_obligations=[])
    conn = _MockConnection(cursor)

    res = sync_historical_staff_baseline_obligations(conn, case_no="115000088", dry_run=False)

    assert res["scanned_orders"] == 1
    assert res["created_count"] == 1
    assert res["updated_count"] == 0
    assert res["skipped_count"] == 0

    detail = res["details"][0]
    assert detail["case_no"] == "115000088"
    assert detail["staff_id"] == 99
    # 20 days * 9 hrs * 250 NT$/hr = 45,000 NT$
    assert detail["amount_ntd"] == 45000
    # completed 2026-09-20 -> due date 2026-10-15
    assert detail["due_date"] == "2026-10-15"

    writes = [sql for sql, _ in cursor.executed if sql.startswith("INSERT INTO") or sql.startswith("UPDATE")]
    assert any("UPDATE orders SET staff_payment_due_date" in w for w in writes)
    assert any("INSERT INTO staff_obligation_events" in w for w in writes)
    assert any("INSERT INTO staff_obligations" in w for w in writes)


def test_sync_idempotent_skips_when_obligation_already_exists():
    order = {
        "case_no": "115000088",
        "client_id": 1,
        "staff_id": 99,
        "status": "歷史訂單－服務完成",
        "lifecycle_version": 1,
        "service_days": 20,
        "service_hours_per_day": Decimal("9.0"),
        "floor_fee": Decimal("0"),
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 20),
        "actual_start_date": date(2026, 9, 1),
        "actual_end_date": date(2026, 9, 20),
        "staff_payment_due_date": date(2026, 10, 15),
        "identity_status": "一般市民",
    }
    assignment = {
        "id": 12,
        "staff_id": 99,
        "hourly_rate": Decimal("250.00"),
        "planned_hours": Decimal("180.00"),
        "actual_hours": Decimal("180.00"),
        "floor_fee_allocated": Decimal("0.00"),
    }
    existing = [{
        "obligation_identity": "staff-obligation:115000088:99",
        "amount_due_ntd": 45000,
        "due_date": date(2026, 10, 15),
        "status": "open",
        "current_event_id": 5,
    }]

    cursor = _MockCursor(orders=[order], assignments=[assignment], existing_obligations=existing)
    conn = _MockConnection(cursor)

    res = sync_historical_staff_baseline_obligations(conn, case_no="115000088", dry_run=False)

    assert res["scanned_orders"] == 1
    assert res["created_count"] == 0
    assert res["updated_count"] == 0
    assert res["skipped_count"] == 1


def test_sync_dry_run_does_not_mutate():
    order = {
        "case_no": "115000088",
        "client_id": 1,
        "staff_id": 99,
        "status": "歷史訂單－服務完成",
        "lifecycle_version": 1,
        "service_days": 20,
        "service_hours_per_day": Decimal("9.0"),
        "floor_fee": Decimal("0"),
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 20),
        "actual_start_date": date(2026, 9, 1),
        "actual_end_date": date(2026, 9, 20),
        "staff_payment_due_date": None,
        "identity_status": "一般市民",
    }
    assignment = {
        "id": 12,
        "staff_id": 99,
        "hourly_rate": Decimal("250.00"),
        "planned_hours": Decimal("180.00"),
        "actual_hours": Decimal("180.00"),
        "floor_fee_allocated": Decimal("0.00"),
    }

    cursor = _MockCursor(orders=[order], assignments=[assignment], existing_obligations=[])
    conn = _MockConnection(cursor)

    res = sync_historical_staff_baseline_obligations(conn, case_no="115000088", dry_run=True)

    assert res["created_count"] == 1
    # Dry run must not perform writes
    writes = [sql for sql, _ in cursor.executed if sql.startswith("INSERT INTO") or sql.startswith("UPDATE")]
    assert writes == []

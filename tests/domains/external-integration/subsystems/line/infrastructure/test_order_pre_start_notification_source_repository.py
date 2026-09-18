"""
File: test_order_pre_start_notification_source_repository.py
Description: 驗證 OrderPreStartNotificationSourceRepository 與 Worker 的資料庫查詢與事務封裝。
"""

from datetime import date, datetime, timezone

from infrastructure.mysql.order_pre_start_notification_source_repository import (
    MySqlOrderPreStartNotificationSourceRepository,
)
from infrastructure.mysql.order_pre_start_notification_source_worker import (
    MySqlOrderPreStartNotificationSourceWorker,
)


class MockCursor:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockConnection:
    def __init__(self, rows=None):
        self._cursor = MockCursor(rows)
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_repository_find_due_candidates_maps_rows() -> None:
    mock_rows = [
        {
            "case_no": "CASE-001",
            "effective_start_date": "2026-08-20",
            "first_payment_required": 30000,
            "first_payment_received": 10000,
            "client_line_user_id": "U_USER_001",
        },
        {
            "case_no": "CASE-002",
            "effective_start_date": "2026-08-20",
            "first_payment_required": 25000,
            "first_payment_received": 25000,
            "client_line_user_id": "U_USER_002",
        },
    ]

    conn = MockConnection(mock_rows)
    repo = MySqlOrderPreStartNotificationSourceRepository(conn)
    candidates = repo.find_due_candidates(date(2026, 8, 20))

    assert len(candidates) == 2

    c1 = candidates[0]
    assert c1.case_no == "CASE-001"
    assert c1.planned_start_date == "2026-08-20"
    assert c1.first_payment_amount == 20000
    assert c1.already_settled is False
    assert c1.client_line_user_id == "U_USER_001"

    c2 = candidates[1]
    assert c2.case_no == "CASE-002"
    assert c2.first_payment_amount == 0
    assert c2.already_settled is True
    assert c2.client_line_user_id == "U_USER_002"
    assert "o.start_date" in conn._cursor.last_query
    assert "o.service_start_date" not in conn._cursor.last_query


def test_repository_find_second_payment_due_candidates() -> None:
    mock_rows = [
        {
            "case_no": "CASE-201",
            "second_payment_due_date": "2026-09-10",
            "second_payment_required": 40000,
            "second_payment_received": 15000,
            "client_line_user_id": "U_USER_201",
        },
        {
            "case_no": "CASE-202",
            "second_payment_due_date": "2026-09-10",
            "second_payment_required": 35000,
            "second_payment_received": 35000,
            "client_line_user_id": "U_USER_202",
        },
        {
            "case_no": "CASE-203-NO-SECOND-PAYMENT",
            "second_payment_due_date": "2026-09-10",
            "second_payment_required": 0,
            "second_payment_received": 0,
            "client_line_user_id": "U_USER_203",
        },
    ]

    conn = MockConnection(mock_rows)
    repo = MySqlOrderPreStartNotificationSourceRepository(conn)
    candidates = repo.find_second_payment_due_candidates(date(2026, 9, 10))

    # CASE-203 with second_payment_required == 0 should be omitted!
    assert len(candidates) == 2

    c1 = candidates[0]
    assert c1.case_no == "CASE-201"
    assert c1.second_payment_due_date == "2026-09-10"
    assert c1.second_payment_amount == 25000
    assert c1.already_settled is False

    c2 = candidates[1]
    assert c2.case_no == "CASE-202"
    assert c2.second_payment_amount == 0
    assert c2.already_settled is True


def test_worker_commits_on_processed_events(monkeypatch) -> None:
    class DummyProjector:
        def __init__(self, scanner, registry):
            pass

        def run_once(self, now, target_date=None):
            return 2

    monkeypatch.setattr(
        "infrastructure.mysql.order_pre_start_notification_source_worker.OrderPreStartNotificationSourceProjector",
        DummyProjector,
    )

    committed = []

    class DummyUoW:
        def __init__(self, connection):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def commit(self):
            committed.append(True)

    monkeypatch.setattr(
        "infrastructure.mysql.order_pre_start_notification_source_worker.MySqlUnitOfWork",
        DummyUoW,
    )

    conn = MockConnection()
    worker = MySqlOrderPreStartNotificationSourceWorker(
        lambda: conn,
        lambda: datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc),
    )

    result = worker.run_once(target_date=date(2026, 8, 20))
    assert result == 2
    assert committed == [True]
    assert conn.closed is True

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


def test_repository_uses_formal_start_day_scanner(monkeypatch):
    dates=[]
    class Scanner:
        def __init__(self,conn): assert conn is connection
        def find_due_candidates(self,day): dates.append(day); return ('typed-candidate',)
    monkeypatch.setattr('infrastructure.mysql.order_pre_start_notification_source_repository.MySqlServiceStartDayRepository',Scanner)
    connection=MockConnection()
    result=MySqlOrderPreStartNotificationSourceRepository(connection).find_due_candidates(date(2026,8,20))
    assert result==('typed-candidate',)
    assert dates==[date(2026,8,20)]


def test_repository_delegates_second_payment_due_and_success(monkeypatch):
    dates=[]
    class Scanner:
        def __init__(self,connection):assert connection is conn
        def find_due_candidates(self,day):dates.append(day);return ('group-reminder',)
        def find_settlement_candidates(self):return ('group-success',)
    monkeypatch.setattr('infrastructure.mysql.order_pre_start_notification_source_repository.MySqlSecondPaymentNotificationRepository',Scanner)
    conn=MockConnection();repo=MySqlOrderPreStartNotificationSourceRepository(conn)
    assert repo.find_second_payment_due_candidates(date(2026,9,10))==('group-reminder',)
    assert repo.find_second_payment_settlement_candidates()==('group-success',)
    assert dates==[date(2026,9,10)]


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

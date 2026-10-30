"""
File: test_mysql_connection_pool.py
Description: 驗證 MySQL 執行緒安全常駐連線池之重用、交易狀態重置、逾期探測淘汰與測試庫隔離契約。
"""

from __future__ import annotations

from pathlib import Path
import pymysql
import pytest

from infrastructure.mysql import mysql_adapter


class _FakeRawConnection:
    def __init__(self, *, ping_error: Exception | None = None, rollback_error: Exception | None = None) -> None:
        self.open = True
        self._autocommit = False
        self.rollbacks = 0
        self.commits = 0
        self.closes = 0
        self.pings: list[bool] = []
        self.autocommit_calls: list[bool] = []
        self.ping_error = ping_error
        self.rollback_error = rollback_error

    def cursor(self, cursor=None):
        del cursor
        return "fake-cursor"

    def begin(self) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error

    def get_autocommit(self) -> bool:
        return self._autocommit

    def autocommit(self, value: bool) -> None:
        self._autocommit = bool(value)
        self.autocommit_calls.append(self._autocommit)

    def ping(self, reconnect: bool = True) -> None:
        self.pings.append(reconnect)
        if self.ping_error is not None:
            raise self.ping_error

    def close(self) -> None:
        self.open = False
        self.closes += 1


@pytest.fixture(autouse=True)
def _clean_pools(monkeypatch):
    mysql_adapter.close_connection_pools()
    monkeypatch.setitem(mysql_adapter.DB_CONFIG, "database", "union_db")
    monkeypatch.setenv("DB_POOL_MAX_IDLE", "4")
    monkeypatch.setenv("DB_POOL_MAX_AGE_SECONDS", "300")
    monkeypatch.setenv("DB_POOL_PING_IDLE_SECONDS", "15")
    yield
    mysql_adapter.close_connection_pools()


def test_pooled_connection_reuses_socket_resets_transaction_and_blocks_use_after_close(monkeypatch):
    created: list[_FakeRawConnection] = []

    def fake_connect(**kwargs):
        del kwargs
        raw = _FakeRawConnection()
        created.append(raw)
        return raw

    monkeypatch.setattr(mysql_adapter.pymysql, "connect", fake_connect)

    first = mysql_adapter.get_connection()
    assert len(created) == 1
    first.autocommit(True)
    assert first.cursor() == "fake-cursor"
    first.close()

    with pytest.raises(pymysql.err.InterfaceError):
        first.cursor()

    assert created[0].rollbacks == 1
    assert created[0].get_autocommit() is False
    assert created[0].closes == 0

    second = mysql_adapter.get_connection()
    assert len(created) == 1
    assert second.cursor() == "fake-cursor"
    second.close()

    mysql_adapter.close_connection_pools()
    assert created[0].closes == 1


def test_broken_rollback_or_failed_idle_ping_evicts_socket_and_creates_fresh_connection(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(mysql_adapter, "monotonic", lambda: now[0])

    raw_queue = [
        _FakeRawConnection(rollback_error=pymysql.err.OperationalError(2006, "gone away")),
        _FakeRawConnection(ping_error=pymysql.err.OperationalError(2013, "lost connection")),
        _FakeRawConnection(),
    ]
    created: list[_FakeRawConnection] = []

    def fake_connect(**kwargs):
        del kwargs
        raw = raw_queue.pop(0)
        created.append(raw)
        return raw

    monkeypatch.setattr(mysql_adapter.pymysql, "connect", fake_connect)

    broken = mysql_adapter.get_connection()
    broken.close()
    assert created[0].closes == 1

    stale = mysql_adapter.get_connection()
    assert len(created) == 2
    stale.close()
    assert created[1].closes == 0

    now[0] += 20.0
    recovered = mysql_adapter.get_connection()
    assert created[1].pings == [False]
    assert created[1].closes == 1
    assert len(created) == 3
    recovered.close()


def test_max_idle_cap_disposable_test_db_bypass_and_profile_bucket_isolation(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DB_POOL_MAX_IDLE", "1")
    created: list[tuple[str | None, str | None, _FakeRawConnection]] = []

    def fake_connect(**kwargs):
        raw = _FakeRawConnection()
        created.append((kwargs.get("user"), kwargs.get("database"), raw))
        return raw

    monkeypatch.setattr(mysql_adapter.pymysql, "connect", fake_connect)

    c1 = mysql_adapter.get_connection()
    c2 = mysql_adapter.get_connection()
    c1.close()
    c2.close()
    assert created[0][2].closes == 0
    assert created[1][2].closes == 1

    # lu_test_* disposable test databases bypass pooling by default so DROP DATABASE never leaves stale sockets
    monkeypatch.setitem(mysql_adapter.DB_CONFIG, "database", "lu_test_disposable_case")
    unpooled = mysql_adapter.get_connection()
    assert isinstance(unpooled, _FakeRawConnection)
    unpooled.close()
    assert unpooled.closes == 1

    # Different NAS profiles isolate credentials in distinct pool buckets
    monkeypatch.setitem(mysql_adapter.DB_CONFIG, "database", "union_db")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "nas")
    access_pw = tmp_path / "access.pw"
    maint_pw = tmp_path / "maint.pw"
    access_pw.write_text("access-secret\n", encoding="utf-8")
    maint_pw.write_text("maint-secret\n", encoding="utf-8")
    monkeypatch.setenv("DB_ACCESS_USER", "lu_access")
    monkeypatch.setenv("DB_ACCESS_PASSWORD_FILE", str(access_pw))
    monkeypatch.setenv("DB_MAINTENANCE_USER", "lu_maint")
    monkeypatch.setenv("DB_MAINTENANCE_PASSWORD_FILE", str(maint_pw))

    access_conn = mysql_adapter.get_connection(profile="access")
    access_conn.close()
    maint_conn = mysql_adapter.get_connection(profile="maintenance")
    maint_conn.close()

    users = [entry[0] for entry in created[-2:]]
    assert users == ["lu_access", "lu_maint"]

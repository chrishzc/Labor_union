from __future__ import annotations

from types import SimpleNamespace

import pytest

import api.dependencies.admin_auth as admin_auth
import subsystems.access.authentication_session as auth_session


class FakeCursor:
    def __init__(
        self,
        *,
        existing_user: bool = False,
        fail_query: bool = False,
        fail_factor_insert: bool = False,
    ) -> None:
        self.existing_user = existing_user
        self.fail_query = fail_query
        self.fail_factor_insert = fail_factor_insert
        self.execute_calls: list[str] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self.execute_calls.append(sql)
        if len(self.execute_calls) == 1 and self.fail_query:
            raise RuntimeError("query failed")
        if "INSERT INTO admin_totp_factors" in sql and self.fail_factor_insert:
            raise RuntimeError("factor insert failed")

    def fetchone(self):
        return {"id": 1} if self.existing_user else None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.commit_calls = 0
        self.close_calls = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commit_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def _enable_root_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_ROOT_USERNAME", "root")
    monkeypatch.setenv("DEV_ROOT_PASSWORD", "test-password")


def _install_factor_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_session, "bootstrap_root_admin", lambda **kwargs: 7)
    cipher = SimpleNamespace(
        encrypt=lambda value: SimpleNamespace(ciphertext="test-ciphertext", key_version="test-v1")
    )
    monkeypatch.setattr(auth_session, "totp_cipher_from_environment", lambda: cipher)


@pytest.mark.parametrize(
    ("app_env", "username", "password"),
    [
        ("production", "root", "password"),
        ("development", "", "password"),
        ("development", "root", ""),
    ],
)
def test_root_bootstrap_does_not_open_connection_without_allowed_configuration(
    monkeypatch: pytest.MonkeyPatch,
    app_env: str,
    username: str,
    password: str,
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("DEV_ROOT_USERNAME", username)
    monkeypatch.setenv("DEV_ROOT_PASSWORD", password)
    monkeypatch.setattr(
        admin_auth,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("connection must not be opened")),
    )

    admin_auth.ensure_development_root_admin()


def test_existing_root_releases_connection_without_creating_or_committing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_root_bootstrap(monkeypatch)
    cursor = FakeCursor(existing_user=True)
    conn = FakeConnection(cursor)
    monkeypatch.setattr(admin_auth, "get_connection", lambda: conn)

    admin_auth.ensure_development_root_admin()

    assert conn.commit_calls == 0
    assert conn.close_calls == 1
    assert len(cursor.execute_calls) == 1


def test_successful_root_bootstrap_commits_factor_and_releases_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_root_bootstrap(monkeypatch)
    _install_factor_dependencies(monkeypatch)
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    monkeypatch.setattr(admin_auth, "get_connection", lambda: conn)

    admin_auth.ensure_development_root_admin()

    assert conn.commit_calls == 1
    assert conn.close_calls == 1
    assert len(cursor.execute_calls) == 2


def test_query_failure_still_releases_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_root_bootstrap(monkeypatch)
    cursor = FakeCursor(fail_query=True)
    conn = FakeConnection(cursor)
    monkeypatch.setattr(admin_auth, "get_connection", lambda: conn)

    admin_auth.ensure_development_root_admin()

    assert conn.commit_calls == 0
    assert conn.close_calls == 1


def test_bootstrap_failure_still_releases_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_root_bootstrap(monkeypatch)
    cursor = FakeCursor()
    conn = FakeConnection(cursor)
    monkeypatch.setattr(admin_auth, "get_connection", lambda: conn)
    monkeypatch.setattr(
        auth_session,
        "bootstrap_root_admin",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bootstrap failed")),
    )

    admin_auth.ensure_development_root_admin()

    assert conn.commit_calls == 0
    assert conn.close_calls == 1


def test_factor_insert_failure_still_releases_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_root_bootstrap(monkeypatch)
    _install_factor_dependencies(monkeypatch)
    cursor = FakeCursor(fail_factor_insert=True)
    conn = FakeConnection(cursor)
    monkeypatch.setattr(admin_auth, "get_connection", lambda: conn)

    admin_auth.ensure_development_root_admin()

    assert conn.commit_calls == 0
    assert conn.close_calls == 1

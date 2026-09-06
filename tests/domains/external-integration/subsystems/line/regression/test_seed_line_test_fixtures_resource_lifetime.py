from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import seed_line_test_fixtures as seed_module


class _FakeCursor:
    def __init__(self, *, execute_error: Exception | None = None) -> None:
        self.execute_error = execute_error
        self.closed = False
        self.lastrowid = 101

    def execute(self, *_args, **_kwargs) -> None:
        if self.execute_error is not None:
            raise self.execute_error

    def fetchone(self):
        return None

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(
        self,
        *,
        cursor: _FakeCursor | None = None,
        cursor_error: Exception | None = None,
    ) -> None:
        self.cursor_instance = cursor or _FakeCursor()
        self.cursor_error = cursor_error
        self.closed = False
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self, *_args, **_kwargs):
        if self.cursor_error is not None:
            raise self.cursor_error
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed = True


class _Dependency:
    def __init__(
        self,
        value=None,
        *,
        next_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.value = value
        self.next_error = next_error
        self.close_error = close_error
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.next_error is not None:
            raise self.next_error
        return self.value

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class _ReadyStatusService:
    def query(self, _case_no: str):
        return SimpleNamespace(ready=True, recommendation=None)


class _FailingStatusService:
    def query(self, _case_no: str):
        raise RuntimeError("status failed")


class _BootstrapNeededStatusService:
    def query(self, _case_no: str):
        return SimpleNamespace(ready=False, recommendation=object())


class _FailingWorkflow:
    def preview(self, _intent, _correlation_id):
        raise RuntimeError("workflow failed")


@pytest.fixture(autouse=True)
def _test_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")


def _install_dependencies(monkeypatch, status_dependency: _Dependency, workflow_dependency: _Dependency) -> None:
    monkeypatch.setattr(seed_module, "get_case_architecture_bootstrap_status_service", lambda: status_dependency)
    monkeypatch.setattr(seed_module, "get_case_architecture_bootstrap_workflow", lambda: workflow_dependency)


def test_production_guard_runs_before_connection_acquisition(monkeypatch) -> None:
    connection_calls = 0

    def _unexpected_connection():
        nonlocal connection_calls
        connection_calls += 1
        raise AssertionError("production guard must run before DB acquisition")

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(seed_module, "get_connection", _unexpected_connection)

    with pytest.raises(RuntimeError, match="production"):
        seed_module.seed_fixtures(verbose=False)

    assert connection_calls == 0


def test_cursor_acquisition_failure_still_closes_connection(monkeypatch) -> None:
    connection = _FakeConnection(cursor_error=RuntimeError("cursor failed"))
    monkeypatch.setattr(seed_module, "get_connection", lambda: connection)

    with pytest.raises(RuntimeError, match="cursor failed"):
        seed_module.seed_fixtures(verbose=False)

    assert connection.closed is True
    assert connection.commit_calls == 0


def test_fixture_failure_closes_cursor_and_connection_without_commit(monkeypatch) -> None:
    cursor = _FakeCursor(execute_error=RuntimeError("fixture failed"))
    connection = _FakeConnection(cursor=cursor)
    monkeypatch.setattr(seed_module, "get_connection", lambda: connection)

    with pytest.raises(RuntimeError, match="fixture failed"):
        seed_module.seed_fixtures(verbose=False)

    assert cursor.closed is True
    assert connection.closed is True
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


@pytest.mark.parametrize("failing_dependency", ["status", "workflow"])
def test_dependency_acquisition_failure_closes_every_acquired_resource(monkeypatch, failing_dependency: str) -> None:
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor=cursor)
    monkeypatch.setattr(seed_module, "get_connection", lambda: connection)

    status_dependency = _Dependency(_ReadyStatusService())
    workflow_dependency = _Dependency(object())
    if failing_dependency == "status":
        status_dependency.next_error = RuntimeError("status dependency failed")
    else:
        workflow_dependency.next_error = RuntimeError("workflow dependency failed")
    _install_dependencies(monkeypatch, status_dependency, workflow_dependency)

    with pytest.raises(RuntimeError, match=f"{failing_dependency} dependency failed"):
        seed_module.seed_fixtures(verbose=False)

    assert cursor.closed is True
    assert connection.closed is True
    assert connection.commit_calls == 1
    assert status_dependency.closed is True
    if failing_dependency == "workflow":
        assert workflow_dependency.closed is True


def test_status_failure_after_fixture_commit_closes_generators(monkeypatch) -> None:
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor=cursor)
    monkeypatch.setattr(seed_module, "get_connection", lambda: connection)
    status_dependency = _Dependency(_FailingStatusService())
    workflow_dependency = _Dependency(object())
    _install_dependencies(monkeypatch, status_dependency, workflow_dependency)

    with pytest.raises(RuntimeError, match="status failed"):
        seed_module.seed_fixtures(verbose=False)

    assert connection.commit_calls == 1
    assert cursor.closed is True
    assert connection.closed is True
    assert status_dependency.closed is True
    assert workflow_dependency.closed is True


def test_workflow_failure_after_fixture_commit_is_not_reported_ready(monkeypatch) -> None:
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor=cursor)
    monkeypatch.setattr(seed_module, "get_connection", lambda: connection)
    status_dependency = _Dependency(_BootstrapNeededStatusService())
    workflow_dependency = _Dependency(_FailingWorkflow())
    _install_dependencies(monkeypatch, status_dependency, workflow_dependency)

    with pytest.raises(RuntimeError, match="workflow failed"):
        seed_module.seed_fixtures(verbose=False)

    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert cursor.closed is True
    assert connection.closed is True
    assert status_dependency.closed is True
    assert workflow_dependency.closed is True


def test_status_dependency_closes_even_when_workflow_close_fails(monkeypatch) -> None:
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor=cursor)
    monkeypatch.setattr(seed_module, "get_connection", lambda: connection)
    status_dependency = _Dependency(_ReadyStatusService())
    workflow_dependency = _Dependency(object(), close_error=RuntimeError("workflow close failed"))
    _install_dependencies(monkeypatch, status_dependency, workflow_dependency)

    with pytest.raises(RuntimeError, match="workflow close failed"):
        seed_module.seed_fixtures(verbose=False)

    assert workflow_dependency.closed is True
    assert status_dependency.closed is True


def test_success_closes_all_resources_and_reports_ready(monkeypatch) -> None:
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor=cursor)
    monkeypatch.setattr(seed_module, "get_connection", lambda: connection)
    status_dependency = _Dependency(_ReadyStatusService())
    workflow_dependency = _Dependency(object())
    _install_dependencies(monkeypatch, status_dependency, workflow_dependency)

    result = seed_module.seed_fixtures(verbose=False)

    assert result["status"] == "ready"
    assert connection.commit_calls == 1
    assert cursor.closed is True
    assert connection.closed is True
    assert status_dependency.closed is True
    assert workflow_dependency.closed is True

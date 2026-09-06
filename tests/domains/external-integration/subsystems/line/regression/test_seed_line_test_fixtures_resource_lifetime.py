from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class _Value:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs


class _EnsureCaseArchitectureBootstrap(_Value):
    pass


def _stub_module(name: str, **attributes) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_seed_module():
    pymysql = _stub_module(
        "pymysql",
        cursors=SimpleNamespace(DictCursor=object()),
    )
    stubs = {
        "dotenv": _stub_module("dotenv", load_dotenv=lambda *args, **kwargs: None),
        "pymysql": pymysql,
        "infrastructure": _stub_module("infrastructure"),
        "infrastructure.mysql": _stub_module("infrastructure.mysql"),
        "infrastructure.mysql.mysql_adapter": _stub_module(
            "infrastructure.mysql.mysql_adapter",
            get_connection=lambda: None,
        ),
        "api": _stub_module("api"),
        "api.dependencies": _stub_module("api.dependencies"),
        "api.dependencies.case_architecture_bootstrap": _stub_module(
            "api.dependencies.case_architecture_bootstrap",
            get_case_architecture_bootstrap_status_service=lambda: None,
            get_case_architecture_bootstrap_workflow=lambda: None,
        ),
        "shared_kernel": _stub_module("shared_kernel"),
        "shared_kernel.identities": _stub_module(
            "shared_kernel.identities",
            ActorContext=_Value,
            CorrelationId=_Value,
            ExpectedVersion=_Value,
            IdempotencyKey=_Value,
        ),
        "subsystems": _stub_module("subsystems"),
        "subsystems.bootstrap": _stub_module("subsystems.bootstrap"),
        "subsystems.bootstrap.case_architecture_workflow": _stub_module(
            "subsystems.bootstrap.case_architecture_workflow",
            EnsureCaseArchitectureBootstrap=_EnsureCaseArchitectureBootstrap,
        ),
    }
    script_path = Path(__file__).resolve().parents[6] / "scripts" / "seed_line_test_fixtures.py"
    spec = importlib.util.spec_from_file_location("issue_228_seed_line_test_fixtures", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


seed_module = _load_seed_module()


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


class SeedFixtureResourceLifetimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {"APP_ENV": "test"}, clear=False)
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()

    def _install_dependencies(self, status_dependency: _Dependency, workflow_dependency: _Dependency):
        return (
            patch.object(seed_module, "get_case_architecture_bootstrap_status_service", lambda: status_dependency),
            patch.object(seed_module, "get_case_architecture_bootstrap_workflow", lambda: workflow_dependency),
        )

    def test_production_guard_runs_before_connection_acquisition(self) -> None:
        connection_calls = 0

        def _unexpected_connection():
            nonlocal connection_calls
            connection_calls += 1
            raise AssertionError("production guard must run before DB acquisition")

        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False), patch.object(
            seed_module, "get_connection", _unexpected_connection
        ):
            with self.assertRaisesRegex(RuntimeError, "production"):
                seed_module.seed_fixtures(verbose=False)

        self.assertEqual(connection_calls, 0)

    def test_cursor_acquisition_failure_still_closes_connection(self) -> None:
        connection = _FakeConnection(cursor_error=RuntimeError("cursor failed"))
        with patch.object(seed_module, "get_connection", lambda: connection):
            with self.assertRaisesRegex(RuntimeError, "cursor failed"):
                seed_module.seed_fixtures(verbose=False)

        self.assertTrue(connection.closed)
        self.assertEqual(connection.commit_calls, 0)

    def test_fixture_failure_closes_cursor_and_connection_without_commit(self) -> None:
        cursor = _FakeCursor(execute_error=RuntimeError("fixture failed"))
        connection = _FakeConnection(cursor=cursor)
        with patch.object(seed_module, "get_connection", lambda: connection):
            with self.assertRaisesRegex(RuntimeError, "fixture failed"):
                seed_module.seed_fixtures(verbose=False)

        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)
        self.assertEqual(connection.commit_calls, 0)
        self.assertEqual(connection.rollback_calls, 0)

    def test_dependency_acquisition_failure_closes_every_acquired_resource(self) -> None:
        for failing_dependency in ("status", "workflow"):
            with self.subTest(failing_dependency=failing_dependency):
                cursor = _FakeCursor()
                connection = _FakeConnection(cursor=cursor)
                status_dependency = _Dependency(_ReadyStatusService())
                workflow_dependency = _Dependency(object())
                if failing_dependency == "status":
                    status_dependency.next_error = RuntimeError("status dependency failed")
                else:
                    workflow_dependency.next_error = RuntimeError("workflow dependency failed")
                status_patch, workflow_patch = self._install_dependencies(status_dependency, workflow_dependency)

                with patch.object(seed_module, "get_connection", lambda: connection), status_patch, workflow_patch:
                    with self.assertRaisesRegex(RuntimeError, f"{failing_dependency} dependency failed"):
                        seed_module.seed_fixtures(verbose=False)

                self.assertTrue(cursor.closed)
                self.assertTrue(connection.closed)
                self.assertEqual(connection.commit_calls, 1)
                self.assertTrue(status_dependency.closed)
                if failing_dependency == "workflow":
                    self.assertTrue(workflow_dependency.closed)

    def test_status_failure_after_fixture_commit_closes_generators(self) -> None:
        cursor = _FakeCursor()
        connection = _FakeConnection(cursor=cursor)
        status_dependency = _Dependency(_FailingStatusService())
        workflow_dependency = _Dependency(object())
        status_patch, workflow_patch = self._install_dependencies(status_dependency, workflow_dependency)

        with patch.object(seed_module, "get_connection", lambda: connection), status_patch, workflow_patch:
            with self.assertRaisesRegex(RuntimeError, "status failed"):
                seed_module.seed_fixtures(verbose=False)

        self.assertEqual(connection.commit_calls, 1)
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)
        self.assertTrue(status_dependency.closed)
        self.assertTrue(workflow_dependency.closed)

    def test_workflow_failure_after_fixture_commit_is_not_reported_ready(self) -> None:
        cursor = _FakeCursor()
        connection = _FakeConnection(cursor=cursor)
        status_dependency = _Dependency(_BootstrapNeededStatusService())
        workflow_dependency = _Dependency(_FailingWorkflow())
        status_patch, workflow_patch = self._install_dependencies(status_dependency, workflow_dependency)

        with patch.object(seed_module, "get_connection", lambda: connection), status_patch, workflow_patch:
            with self.assertRaisesRegex(RuntimeError, "workflow failed"):
                seed_module.seed_fixtures(verbose=False)

        self.assertEqual(connection.commit_calls, 1)
        self.assertEqual(connection.rollback_calls, 0)
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)
        self.assertTrue(status_dependency.closed)
        self.assertTrue(workflow_dependency.closed)

    def test_status_dependency_closes_even_when_workflow_close_fails(self) -> None:
        cursor = _FakeCursor()
        connection = _FakeConnection(cursor=cursor)
        status_dependency = _Dependency(_ReadyStatusService())
        workflow_dependency = _Dependency(object(), close_error=RuntimeError("workflow close failed"))
        status_patch, workflow_patch = self._install_dependencies(status_dependency, workflow_dependency)

        with patch.object(seed_module, "get_connection", lambda: connection), status_patch, workflow_patch:
            with self.assertRaisesRegex(RuntimeError, "workflow close failed"):
                seed_module.seed_fixtures(verbose=False)

        self.assertTrue(workflow_dependency.closed)
        self.assertTrue(status_dependency.closed)

    def test_success_closes_all_resources_and_reports_ready(self) -> None:
        cursor = _FakeCursor()
        connection = _FakeConnection(cursor=cursor)
        status_dependency = _Dependency(_ReadyStatusService())
        workflow_dependency = _Dependency(object())
        status_patch, workflow_patch = self._install_dependencies(status_dependency, workflow_dependency)

        with patch.object(seed_module, "get_connection", lambda: connection), status_patch, workflow_patch:
            result = seed_module.seed_fixtures(verbose=False)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(connection.commit_calls, 1)
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)
        self.assertTrue(status_dependency.closed)
        self.assertTrue(workflow_dependency.closed)


if __name__ == "__main__":
    unittest.main()

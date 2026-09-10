from __future__ import annotations

from collections import Counter
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
    script_path = Path(__file__).resolve().parents[7] / "scripts" / "seed_line_test_fixtures.py"
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
        self.executions: list[tuple[object, object]] = []

    def execute(self, *args, **_kwargs) -> None:
        if self.execute_error is not None:
            raise self.execute_error
        self.executions.append((args[0], args[1] if len(args) > 1 else ()))
        if len(args) > 1:
            statement, parameters = args[:2]
            assert statement.count("%s") == len(parameters)

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
        self.post_bootstrap = patch.object(
            seed_module, "_seed_post_bootstrap_owner_facts", lambda *_args: None
        )
        self.post_bootstrap.start()
        self.readback = patch.object(
            seed_module,
            "_verify_fixture_readback",
            lambda: {
                "stage_counts": {item["stage_code"]: 1 for item in seed_module._CORE_STAGE_SCENARIOS},
                "historical_lifecycle_counts": {
                    "unserved": 1,
                    "in_service": 1,
                    "service_completed": 1,
                    "accounting_completed": 1,
                },
            },
        )
        self.readback.start()

    def tearDown(self) -> None:
        self.readback.stop()
        self.post_bootstrap.stop()
        self.environment.stop()

    def _install_dependencies(self, status_dependency: _Dependency, workflow_dependency: _Dependency):
        return (
            patch.object(seed_module, "get_case_architecture_bootstrap_status_service", lambda: status_dependency),
            patch.object(seed_module, "get_case_architecture_bootstrap_workflow", lambda: workflow_dependency),
        )

    def test_order_scenarios_cover_every_lifecycle_and_approved_variant(self) -> None:
        scenarios = seed_module._ORDER_SCENARIOS
        self.assertEqual(len(scenarios), 15)
        self.assertEqual(len({item["case_no"] for item in scenarios}), 15)
        self.assertEqual(len({item["phone"] for item in scenarios}), 15)
        self.assertEqual(
            Counter(item["status"] for item in scenarios),
            Counter({
                "待補件": 1,
                "洽談中": 2,
                "訂單成立": 1,
                "服務中": 2,
                "訂單完成": 2,
                "訂單取消": 2,
                "歷史訂單－未服務": 1,
                "歷史訂單－服務中": 1,
                "歷史訂單－服務完成": 2,
                "歷史訂單－帳務完成": 1,
            }),
        )
        by_case = {item["case_no"]: item for item in scenarios}
        self.assertEqual(by_case["CASE-2026-M304"]["identity_status"], "補助市民")
        self.assertEqual(len(by_case["CASE-2026-M306"]["staff_keys"]), 2)
        self.assertEqual(by_case["CASE-2026-M307"]["payment"][2], "待結算")
        self.assertEqual(by_case["CASE-2026-M308"]["payment"][2], "已結清")
        self.assertEqual(by_case["CASE-2026-M310"]["assignment_status"], "cancelled")

    def test_historical_restart_fixture_seeds_supported_service_mode(self) -> None:
        cursor = _FakeCursor()
        scenario = next(
            item for item in seed_module._ORDER_SCENARIOS
            if item["case_no"] == "CASE-2026-H305"
        )

        seed_module._seed_scenario_client(cursor, scenario)

        statement, parameters = cursor.executions[-1]
        self.assertIn("service_type", statement)
        self.assertIn("連續服務", parameters)
        self.assertNotIn("到宅坐月子", parameters)

    def test_service_scenarios_use_exact_continuous_assignment_ranges_without_staff_overlap(self) -> None:
        occupied: set[tuple[str, object]] = set()
        for scenario in seed_module._ALL_ORDER_SCENARIOS:
            staff_keys = tuple(scenario.get("staff_keys", ()))
            if not staff_keys or scenario.get("assignment_status") == "cancelled":
                continue
            periods = tuple(scenario.get("assignment_periods", ())) or tuple(
                (scenario["start_date"], scenario["end_date"], scenario["service_days"])
                for _staff_key in staff_keys
            )
            statuses = tuple(scenario.get("assignment_statuses", ()))
            active_days = 0
            for index, (staff_key, period) in enumerate(zip(staff_keys, periods, strict=True)):
                status = statuses[index] if statuses else scenario.get("assignment_status", "planned")
                days = seed_module._inclusive_dates(period[0], period[1])
                self.assertEqual(len(days), period[2])
                if status not in {"cancelled", "replaced"}:
                    active_days += len(days)
                    for work_date in days:
                        self.assertNotIn((staff_key, work_date), occupied)
                        occupied.add((staff_key, work_date))
            self.assertEqual(active_days, scenario["service_days"])
            self.assertEqual(scenario.get("service_mode"), "連續服務")

    def test_terminal_helpers_record_real_lifecycle_transitions(self) -> None:
        source = Path(seed_module.__file__).read_text(encoding="utf-8")
        self.assertIn("'evaluation_time_reached','服務中','訂單完成'", source)
        self.assertIn("'order_cancellation_applied'", source)
        self.assertIn("'historical_order_adoption','洽談中'", source)
        self.assertIn("'historical_accounting_settled','歷史訂單－服務完成','歷史訂單－帳務完成'", source)
        self.assertNotIn("'service_period_elapsed','服務中','服務中'", source)
        self.assertIn("INSERT INTO scheduling_generations", source)
        self.assertIn("INSERT INTO scheduling_effective_occupancy", source)
        self.assertIn("historical_service_day_projections", source)
        self.assertIn("historical_client_payment_projections", source)
        self.assertIn("historical_staff_payout_projections", source)

    def test_terminal_orders_are_seeded_from_their_real_pre_transition_state(self) -> None:
        by_case = {item["case_no"]: item for item in seed_module._ALL_ORDER_SCENARIOS}
        for case_no, expected_order_status, expected_assignment_status in (
            ("CASE-2026-S12", "洽談中", "completed"),
            ("CASE-2026-M310", "洽談中", "planned"),
            ("CASE-2026-H304", "洽談中", "completed"),
        ):
            with self.subTest(case_no=case_no):
                cursor = _FakeCursor()
                seed_module._seed_scenario_order(
                    cursor,
                    by_case[case_no],
                    99,
                    {f"staff_{index}": index for index in range(1, 7)},
                )
                order_insert = next(
                    parameters
                    for statement, parameters in cursor.executions
                    if statement.startswith("INSERT INTO orders")
                )
                assignment_insert = next(
                    parameters
                    for statement, parameters in cursor.executions
                    if statement.startswith("INSERT INTO case_staff_assignments")
                )
                self.assertEqual(order_insert[3], expected_order_status)
                self.assertEqual(assignment_insert[-1], expected_assignment_status)

    def test_core_stage_scenarios_cover_every_stage_once(self) -> None:
        scenarios = seed_module._CORE_STAGE_SCENARIOS
        self.assertEqual(len(scenarios), 13)
        self.assertEqual(len({item["case_no"] for item in scenarios}), 13)
        self.assertEqual(len({item["phone"] for item in scenarios}), 13)
        self.assertEqual(
            [item["stage_code"] for item in scenarios],
            [
                "intake_validation",
                "matching_pool",
                "caregiver_line_delivery",
                "caregiver_willingness_reply",
                "formal_recommendation",
                "external_signing_dispatch",
                "external_signing_completion",
                "deposit_settlement",
                "confirmed_service_dates",
                "formal_service",
                "service_completion",
                "client_settlement",
                "staff_payout",
            ],
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
        self.assertEqual(len(result["order_scenarios"]), 15)
        self.assertEqual(len(result["core_stage_scenarios"]), 13)
        self.assertTrue(all(result["fixture_readback"]["stage_counts"].values()))
        self.assertEqual(connection.commit_calls, 1)
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)
        self.assertTrue(status_dependency.closed)
        self.assertTrue(workflow_dependency.closed)


if __name__ == "__main__":
    unittest.main()

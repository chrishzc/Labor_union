"""Task 97 contract tests for the typed Orders lifecycle control query."""

from datetime import date, datetime, timezone
import inspect
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.dependencies.admin_auth import require_system_admin
from api.routes import orders as orders_route
from api.schemas.order_lifecycle_control import OrderLifecycleControlStateView
from infrastructure.mysql import order_lifecycle_control_query_repository as repository_module
from infrastructure.mysql.order_lifecycle_control_query_repository import (
    MySqlOrderLifecycleControlQueryRepository,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.lifecycle_control_read_facts import (
    ActualStartControlReadFacts,
    OrderLifecycleControlReadFacts,
)
from subsystems.orders.lifecycle_control_read_projection import (
    OrderLifecycleControlQueryService,
    build_order_lifecycle_control_state,
)


def _facts() -> OrderLifecycleControlReadFacts:
    return OrderLifecycleControlReadFacts(
        case_no="CASE-1",
        lifecycle_version=3,
        canonical_status="訂單成立",
        current_actual_start_date="2026-08-01",
        actual_start_control=ActualStartControlReadFacts(
            state="active",
            current_event_id=7,
            required_date="2026-08-01",
            required_settlement_identity="settlement-1",
        ),
        deposit_reconciled=True,
        deposit_settlement_identity="settlement-1",
        deposit_settlement_date="2026-07-15",
        deposit_blockers=(),
    )


class _Cursor:
    def __init__(self, result: object) -> None:
        self.result = result
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement: str, parameters: tuple[object, ...]) -> None:
        self.statements.append((statement, parameters))

    def fetchone(self):
        return self.result

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, result: object) -> None:
        self.cursor_instance = _Cursor(result)
        self.closed = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_query_service_projects_owner_facts_without_connection() -> None:
    calls: list[tuple[str, datetime]] = []

    class Repository:
        def fetch_by_case_no(self, case_no: str, as_of: datetime):
            calls.append((case_no, as_of))
            return _facts()

    result = OrderLifecycleControlQueryService(Repository()).query("CASE-1")

    assert result.case_no == "CASE-1"
    assert result.actual_start_reconfirmation.can_reconfirm is True
    assert calls[0][0] == "CASE-1"
    assert calls[0][1].tzinfo is not None


def test_query_service_rejects_noncanonical_case_number_before_repository_call() -> None:
    class Repository:
        def fetch_by_case_no(self, *_args):
            raise AssertionError("repository must not run")

    with pytest.raises(ValueError):
        OrderLifecycleControlQueryService(Repository()).query(" CASE-1")


def test_mysql_adapter_owns_read_cursor_but_neither_commit_nor_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection(None)
    monkeypatch.setattr(
        repository_module,
        "load_order_lifecycle_control_read_facts",
        lambda **_kwargs: _facts(),
    )

    result = MySqlOrderLifecycleControlQueryRepository(connection).fetch_by_case_no(
        "CASE-1", datetime(2026, 8, 29, tzinfo=timezone.utc)
    )

    assert result.case_no == "CASE-1"
    assert connection.closed is False
    assert connection.commits == 0
    assert connection.rollbacks == 0


def test_route_returns_closed_typed_projection_and_preserves_payload() -> None:
    application = SimpleNamespace(query=lambda _case_no: type(
        "Result", (), {
            "case_no": "CASE-1",
            "lifecycle_version": 3,
            "canonical_status": "訂單成立",
            "actual_start_reconfirmation": type(
                "Control", (), {
                    "state": "not_required",
                    "required_date": None,
                    "current_actual_start_date": "2026-08-01",
                    "blockers": ("enter_service.actual_start_reconfirmation_inactive",),
                    "can_reconfirm": False,
                }
            )(),
        }
    )())

    result = orders_route.get_order_lifecycle_control_state_route(
        case_no="CASE-1", principal=SimpleNamespace(), application=application
    )

    assert isinstance(result.data, OrderLifecycleControlStateView)
    assert result.data.model_dump() == {
        "case_no": "CASE-1",
        "lifecycle_version": 3,
        "canonical_status": "訂單成立",
        "actual_start_reconfirmation": {
            "state": "not_required",
            "required_date": None,
            "current_actual_start_date": "2026-08-01",
            "blockers": ["enter_service.actual_start_reconfirmation_inactive"],
            "can_reconfirm": False,
        },
    }


def test_route_requires_authentication_and_uses_application_dependency() -> None:
    app = FastAPI()
    app.include_router(orders_route.router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
        1, "admin", "管理員", "system_admin"
    )
    app.dependency_overrides[
        orders_route.get_order_lifecycle_control_application
    ] = lambda: SimpleNamespace(
        query=lambda _case_no: build_order_lifecycle_control_state(_facts())
    )

    response = TestClient(app).get(
        "/api/v1/orders/CASE-1/lifecycle-control-state"
    )

    assert response.status_code == 200
    assert response.json()["data"]["case_no"] == "CASE-1"


def test_public_view_rejects_unknown_projection_field() -> None:
    payload = {
        "case_no": "CASE-1",
        "lifecycle_version": 3,
        "canonical_status": "訂單成立",
        "actual_start_reconfirmation": {
            "state": "not_required",
            "required_date": None,
            "current_actual_start_date": None,
            "blockers": [],
            "can_reconfirm": False,
        },
        "unexpected": True,
    }

    with pytest.raises(ValidationError):
        OrderLifecycleControlStateView.model_validate(payload)


def test_route_has_no_resource_or_transaction_ownership() -> None:
    source = inspect.getsource(
        orders_route.get_order_lifecycle_control_state_route
    )

    for forbidden in ("get_connection", "cursor", "execute", "commit", "rollback"):
        assert forbidden not in source

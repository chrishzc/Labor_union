"""Incomplete persisted Orders terms must not break client registry detail reads."""

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.order_terms import OrderTermsApplication
from api.routes import client_registry
from infrastructure.mysql.order_terms_read_model import load_registry_terms_facts


class _OrderCursor:
    def __init__(self, row):
        self.row = row
        self.current = None

    def execute(self, sql, parameters):
        assert sql.startswith("SELECT ")
        assert parameters == (self.row["case_no"],)
        if "FROM orders o " in sql:
            self.current = self.row
        elif "FROM scheduling_aggregates " in sql:
            self.current = None
        elif "FROM client_finance_accounts " in sql:
            self.current = self.row.get("finance_account")
        elif "FROM payroll_case_accounts " in sql:
            self.current = self.row.get("payroll_account")
        else:
            raise AssertionError("registry must not read mutation impact facts")

    def fetchone(self):
        return self.current


@pytest.fixture
def order_row():
    return {
        "case_no": "TERMS-NULL-TEST",
        "lifecycle_version": 0,
        "start_date": date(2026, 10, 1),
        "service_days": 5,
        "service_hours_per_day": 8,
        "floor_fee": 0,
        "service_start_time": None,
        "service_end_time": None,
        "service_end_day_offset": None,
        "requires_cooking": False,
        "service_data_locked": False,
        "client_identity_status": "一般市民",
    }


@pytest.fixture
def registry_client(order_row):
    case_no = order_row["case_no"]
    detail = SimpleNamespace(
        case_no=case_no,
        client=SimpleNamespace(client_id=1, version=0, values={"name": "測試客戶"}),
        beclass=SimpleNamespace(
            status="unbound", record_id=None, source_kind=None, version=None, values=None,
            financial_fields_locked=False,
        ),
        order_information=SimpleNamespace(status="unbound", values=None, field_issues={}),
        finance=SimpleNamespace(status="not_ready", code="client_finance_bootstrap_required", values=None),
    )

    def load_for_registry(requested_case_no):
        return load_registry_terms_facts(_OrderCursor(order_row), requested_case_no)

    terms = OrderTermsApplication(
        connection=None,
        repository=SimpleNamespace(load_for_registry=load_for_registry),
        workflow=None,
    )
    app = FastAPI()
    app.include_router(client_registry.router)
    app.dependency_overrides[client_registry.require_registry_reader] = lambda: None
    app.dependency_overrides[client_registry.get_client_registry_query_application] = (
        lambda: SimpleNamespace(query=lambda _: detail)
    )
    app.dependency_overrides[client_registry.get_order_terms_application] = lambda: terms
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "missing_field", ["start_date", "service_days", "service_hours_per_day", "floor_fee"],
)
def test_missing_required_terms_preserve_client_detail(registry_client, order_row, missing_field):
    order_row[missing_field] = None

    response = registry_client.get(f"/api/v1/admin/registries/clients/{order_row['case_no']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["client"]["values"]["name"] == "測試客戶"
    assert payload["data"]["order_terms"] == {
        "status": "not_ready",
        "code": f"order_terms_{missing_field}_required",
        "data": None,
        "field_capabilities": {},
    }
    assert order_row[missing_field] is None


def test_complete_terms_preserve_zero_fee_false_cooking_and_empty_time(registry_client, order_row):
    response = registry_client.get(f"/api/v1/admin/registries/clients/{order_row['case_no']}")

    assert response.status_code == 200
    section = response.json()["data"]["order_terms"]
    assert section["status"] == "ready"
    assert section["code"] is None
    terms = section["data"]["terms"]
    assert terms["service_days"] == 5
    assert terms["floor_fee_ntd"] == 0
    assert terms["requires_cooking"] is False
    assert terms["service_time"] == {
        "start_time": None, "end_time": None, "end_day_offset": None,
    }


@pytest.mark.parametrize("locked", [False, True])
def test_historical_terms_remain_visible_without_daily_schedule(registry_client, order_row, locked):
    order_row.update(
        status="歷史訂單－服務完成", service_data_locked=locked,
        finance_account={"aggregate_version": 7}, payroll_account={"aggregate_version": 8},
    )
    response = registry_client.get(f"/api/v1/admin/registries/clients/{order_row['case_no']}")

    assert response.status_code == 200
    section = response.json()["data"]["order_terms"]
    assert section["status"] == "ready"
    assert section["data"]["terms"]["planned_start_date"] == "2026-10-01"
    assert section["data"]["client_finance_version"] == 7
    assert section["data"]["payroll_version"] == 8
    assert section["data"]["service_data_locked"] is locked
    assert section["field_capabilities"]["planned_start_date"]["editable"] is not locked

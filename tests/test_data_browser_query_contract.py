"""
File: test_data_browser_query_contract.py
Description: 驗證六來源 masked Data Browser query、cursor 與 strict view。
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.routes import data_browser_admin
from api.schemas.data_browser import DataBrowserMaskedPageView
from infrastructure.mysql.data_browser_query_repository import (
    DataBrowserQueryRepository,
    DataBrowserSourceNotFound,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_value = _Cursor(rows)

    def cursor(self):
        return self.cursor_value

    def close(self):
        return None


def test_orders_query_is_bounded_and_strictly_typed():
    connection = _Connection(
        [
            {
                "case_no": "115000001",
                "status": "服務中",
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
                "created_at": "2026-07-01T00:00:00",
                "updated_at": "2026-08-01T00:00:00",
            },
            {
                "case_no": "115000002",
                "status": "訂單成立",
                "start_date": None,
                "end_date": None,
                "created_at": "2026-07-02T00:00:00",
                "updated_at": "2026-08-02T00:00:00",
            },
        ]
    )
    page = DataBrowserQueryRepository(connection).query_masked_page(
        "orders",
        limit=1,
        after=None,
        query="服務中",
    )
    view = DataBrowserMaskedPageView.model_validate(page)

    assert view.source_id == "orders"
    assert len(view.items) == 1
    assert view.items[0].row_identity == "115000001"
    assert view.next_cursor == "115000001"
    assert connection.cursor_value.params[-1] == 2
    assert "`orders`" in connection.cursor_value.sql
    assert "LIMIT %s" in connection.cursor_value.sql


def test_unknown_source_and_invalid_cursor_fail_before_query():
    connection = _Connection([])
    repository = DataBrowserQueryRepository(connection)

    try:
        repository.query_masked_page("unknown", limit=25, after=None, query=None)
    except DataBrowserSourceNotFound as error:
        assert str(error) == "source_not_found"
    else:
        raise AssertionError("unknown source must fail")

    try:
        repository.query_masked_page("clients", limit=25, after="0", query=None)
    except ValueError as error:
        assert str(error) == "cursor_invalid"
    else:
        raise AssertionError("invalid cursor must fail")

    assert connection.cursor_value.sql == ""


def test_masked_page_schema_rejects_extra_public_fields():
    payload = {
        "source_id": "clients",
        "items": [],
        "next_cursor": None,
        "raw_rows": [{"phone": "SENSITIVE_PHONE_SENTINEL"}],
    }
    try:
        DataBrowserMaskedPageView.model_validate(payload)
    except ValueError:
        pass
    else:
        raise AssertionError("extra raw rows must be rejected")


def test_masked_source_route_returns_typed_page(monkeypatch):
    connection = _Connection(
        [{
            "case_no": "115000001",
            "status": "服務中",
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
            "created_at": "2026-07-01T00:00:00",
            "updated_at": "2026-08-01T00:00:00",
        }]
    )
    monkeypatch.setattr(data_browser_admin, "get_connection", lambda: connection)
    app = FastAPI()
    app.include_router(data_browser_admin.router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="operator")

    response = TestClient(app).get(
        "/api/v1/admin/data-browser/sources/orders?limit=25"
    )

    assert response.status_code == 200
    assert response.json()["data"]["source_id"] == "orders"
    assert response.json()["data"]["items"][0]["display_title"] == "訂單 115000001"

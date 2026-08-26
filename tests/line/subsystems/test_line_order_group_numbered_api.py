"""
File: test_line_order_group_numbered_api.py
Description: 驗證 LINE 訂單群組與事件 additive numbered Query 的 strict metadata、identity 與輸入界線。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_order_group_reader
from api.routes import line_order_groups
from domains.line.order_group import (
    LineOrderGroupBindingSnapshot,
    LineOrderGroupBindingStatus,
)
from shared_kernel.identities import ActorContext, ExpectedVersion
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.order_group_contracts import (
    LineOrderGroupEventPage,
    LineOrderGroupEventRecord,
    LineOrderGroupNumberedPage,
    LineOrderGroupPage,
)
from subsystems.line.order_group_application import LineOrderGroupQueryApplication


def _principal() -> AdminPrincipal:
    return AdminPrincipal(7, "group-reader", "群組查詢", "operator")


def _client(monkeypatch, application) -> TestClient:
    app = FastAPI()
    app.include_router(line_order_groups.router)
    app.dependency_overrides[require_line_order_group_reader] = _principal
    monkeypatch.setattr(
        line_order_groups,
        "get_line_order_group_query_application",
        lambda: application,
    )
    return TestClient(app)


def test_numbered_group_and_event_queries_return_server_metadata(monkeypatch) -> None:
    snapshot = LineOrderGroupBindingSnapshot(
        "CASE-2026-001",
        None,
        LineOrderGroupBindingStatus.ACTIVE,
        ExpectedVersion(3),
    )
    event = LineOrderGroupEventRecord(
        9,
        snapshot.case_no,
        "group_activated",
        "admin:7",
        datetime(2026, 8, 25, tzinfo=UTC),
    )

    class Application:
        def list_numbered(self, actor, *, status, page, page_size):
            assert (actor.actor_id, status, page, page_size) == (
                "admin:7",
                "active",
                2,
                25,
            )
            return LineOrderGroupNumberedPage((snapshot,), 2, 25, 26, 2)

        def events_numbered(self, actor, case_no, *, page, page_size):
            assert (actor.actor_id, case_no, page, page_size) == (
                "admin:7",
                snapshot.case_no,
                1,
                10,
            )
            return LineOrderGroupEventPage((event,), 1, 10, 11, 2)

    client = _client(monkeypatch, Application())
    group_response = client.get(
        "/api/v1/line/order-groups/numbered?status=active&page=2&page_size=25"
    )
    event_response = client.get(
        f"/api/v1/line/order-groups/{snapshot.case_no}/events/numbered?page=1&page_size=10"
    )

    assert group_response.status_code == 200
    assert group_response.json() == {
        "items": [{"case_no": snapshot.case_no, "group_id": None, "status": "active", "version": 3}],
        "page": 2,
        "page_size": 25,
        "total": 26,
        "total_pages": 2,
    }
    assert event_response.status_code == 200
    assert event_response.json()["total_pages"] == 2
    assert event_response.json()["items"][0]["case_no"] == snapshot.case_no


def test_numbered_queries_reject_invalid_page_and_unknown_status(monkeypatch) -> None:
    client = _client(monkeypatch, object())

    assert client.get("/api/v1/line/order-groups/numbered?page=0").status_code == 422
    assert client.get("/api/v1/line/order-groups/numbered?status=unknown").status_code == 422
    assert client.get("/api/v1/line/order-groups/CASE-1/events/numbered?page_size=201").status_code == 422


def test_legacy_limit_query_keeps_compatibility_response(monkeypatch) -> None:
    snapshot = LineOrderGroupBindingSnapshot(
        "CASE-LEGACY-1", None, LineOrderGroupBindingStatus.ACTIVE, ExpectedVersion(2)
    )

    class Application:
        def list(self, actor, *, status, limit):
            assert (actor.actor_id, status, limit) == ("admin:7", "active", 50)
            return LineOrderGroupPage((snapshot,), 1)

    response = _client(monkeypatch, Application()).get(
        "/api/v1/line/order-groups?status=active&limit=50"
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [{
            "case_no": "CASE-LEGACY-1",
            "group_id": None,
            "status": "active",
            "version": 2,
        }],
        "total": 1,
    }


def test_numbered_application_queries_do_not_commit() -> None:
    class Repository:
        def list_numbered(self, *, status, page, page_size):
            return LineOrderGroupNumberedPage((), page, page_size, 0, 0)

        def events_numbered(self, case_no, *, page, page_size):
            return LineOrderGroupEventPage((), page, page_size, 0, 0)

    class UnitOfWork:
        order_groups = Repository()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def commit(self):
            raise AssertionError("numbered observation query must not commit")

    application = LineOrderGroupQueryApplication(UnitOfWork)
    actor = ActorContext("admin:7", ("line.order_group.read",))

    assert application.list_numbered(actor, status=None, page=1, page_size=25).total == 0
    assert application.events_numbered(actor, "CASE-1", page=1, page_size=25).total == 0

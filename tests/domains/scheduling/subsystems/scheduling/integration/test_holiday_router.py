"""
File: test_holiday_router.py
Description: 以真實 FastAPI 邊界驗證 Holiday 延遲連線快取、零寫入預覽、儲存失效與錯誤封套。
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import holidays as holiday_dependencies
from api.dependencies.admin_auth import require_admin
from api.dependencies.holidays import get_holiday_maintenance_application
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import holidays as route
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.holiday_calendar_query import HolidayCalendarFacts, HolidayFact
from subsystems.scheduling.holiday_maintenance import HolidayMaintenanceApplication


class _Connection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


class _UnitOfWork:
    def __init__(self, connection):
        self._connection = connection
        self._committed = False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None or not self._committed:
            self._connection.rollback()
        return False

    def commit(self):
        self._connection.commit()
        self._committed = True


class _Repository:
    def __init__(self) -> None:
        self.holidays: dict[date, HolidayFact] = {}
        self.receipts = {}

    def query(self, from_date, to_date, *, lock):
        del lock
        rows = tuple(
            self.holidays[key]
            for key in sorted(self.holidays)
            if from_date <= key <= to_date
        )
        version = fingerprint_payload(
            {
                "source": "fake:holidays/v1",
                "holidays": tuple(
                    (row.holiday_date.isoformat(), row.holiday_name, row.is_double_pay_default)
                    for row in rows
                ),
            }
        ).value
        return HolidayCalendarFacts("fake:holidays/v1", version, rows)

    def load_receipt(self, family, key):
        return self.receipts.get((family, key))

    def save_receipt(self, family, key, request_fingerprint, _preview, _actor, _reason, result):
        self.receipts[(family, key)] = {
            "request_fingerprint": request_fingerprint,
            "result_snapshot": result,
        }

    def upsert_holiday(self, holiday_date, holiday_name, double_pay):
        self.holidays[holiday_date] = HolidayFact(holiday_date, holiday_name, double_pay)

    def delete_holiday(self, holiday_date):
        self.holidays.pop(holiday_date)


def _client(monkeypatch):
    from subsystems.scheduling.holiday_query_cache import (
        configure_holiday_query_cache_backend,
        invalidate_holiday_query_cache,
    )

    configure_holiday_query_cache_backend(lambda: None)
    invalidate_holiday_query_cache()
    connection = _Connection()
    repository = _Repository()
    monkeypatch.setattr(route, "get_connection", lambda: connection)
    monkeypatch.setattr(route, "MySqlSchedulingHolidayQuery", lambda _connection: repository)
    app = FastAPI()
    app.include_router(route.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7,
        "holiday-test",
        "測試人員",
        "admin",
    )
    app.dependency_overrides[get_holiday_maintenance_application] = lambda: HolidayMaintenanceApplication(
        repository,
        lambda: _UnitOfWork(connection),
        holiday_dependencies._invalidate_cache_after_commit,
    )
    return TestClient(app), connection, repository


def _preview(client):
    return client.post(
        "/api/v1/holidays/preview",
        headers={"X-Correlation-ID": "holiday-preview-01"},
        json={
            "action": "upsert",
            "holiday_date": "2026-10-10",
            "holiday_name": "國慶日",
            "from_date": "2026-10-01",
            "to_date": "2026-10-31",
        },
    )


def test_query_and_preview_return_typed_horizon_without_commit(monkeypatch):
    client, connection, _repository = _client(monkeypatch)

    query = client.get(
        "/api/v1/holidays?from_date=2026-10-01&to_date=2026-10-31"
    )
    preview = _preview(client)

    assert query.status_code == 200
    assert query.json()["data"]["planning_horizon"]["from_date"] == "2026-10-01"
    assert len(query.json()["data"]["calendar_version"]) == 64
    assert preview.status_code == 200
    assert preview.json()["data"]["command"]["expected_calendar_version"]
    assert connection.commits == 0


def test_apply_commits_once_replays_and_cache_failure_does_not_rewrite_outcome(
    monkeypatch,
):
    client, connection, _repository = _client(monkeypatch)
    preview = _preview(client).json()["data"]
    monkeypatch.setattr(
        holiday_dependencies,
        "invalidate_holiday_query_cache",
        lambda: (_ for _ in ()).throw(RuntimeError("cache unavailable")),
    )
    body = {
        **preview["command"],
        "preview_fingerprint": preview["preview_fingerprint"],
        "reason": "年度設定",
    }
    headers = {
        "Idempotency-Key": "holiday-apply-01",
        "X-Correlation-ID": "holiday-correlation-01",
    }

    first = client.post("/api/v1/holidays/apply", headers=headers, json=body)
    replay = client.post("/api/v1/holidays/apply", headers=headers, json=body)

    assert first.status_code == replay.status_code == 200
    assert first.json()["data"] == replay.json()["data"]
    assert first.json()["data"]["changed"] is True
    assert connection.commits == 2
    assert connection.rollbacks == 0


def test_stale_apply_and_malformed_requests_use_global_typed_envelope(monkeypatch):
    client, connection, repository = _client(monkeypatch)
    preview = _preview(client).json()["data"]
    repository.holidays[date(2026, 10, 9)] = HolidayFact(
        date(2026, 10, 9),
        "新增根事實",
        False,
    )
    body = {
        **preview["command"],
        "preview_fingerprint": preview["preview_fingerprint"],
        "reason": "年度設定",
    }
    stale = client.post(
        "/api/v1/holidays/apply",
        headers={
            "Idempotency-Key": "holiday-stale-01",
            "X-Correlation-ID": "holiday-stale-correlation",
        },
        json=body,
    )
    malformed = client.post(
        "/api/v1/holidays/preview",
        json={"action": "upsert", "holiday_date": "not-a-date"},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["error"]["code"] == "stale_preview"
    assert stale.headers["X-Correlation-ID"] == "holiday-stale-correlation"
    assert malformed.status_code == 422
    assert malformed.json()["detail"]["error"]["code"] == "request_validation_error"
    assert connection.rollbacks == 1


def test_openapi_declares_global_typed_errors_for_every_holiday_operation(monkeypatch):
    client, _connection, _repository = _client(monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]

    for path, method in (
        ("/api/v1/holidays", "get"),
        ("/api/v1/holidays/preview", "post"),
        ("/api/v1/holidays/apply", "post"),
    ):
        response_schema = paths[path][method]["responses"]["422"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"].endswith("/GlobalTypedErrorResponseView")


def test_holiday_query_reuses_projection_cache_without_opening_db_until_apply_invalidates(
    monkeypatch,
):
    from subsystems.scheduling.holiday_query_cache import (
        configure_holiday_query_cache_backend,
        invalidate_holiday_query_cache,
    )

    client, _connection, _repository = _client(monkeypatch)
    opened_connections = 0

    def counted_connection():
        nonlocal opened_connections
        opened_connections += 1
        return _Connection()

    redis_store: dict[str, str] = {}

    class _Backend:
        def get(self, key: str) -> str | None:
            return redis_store.get(key)

        def set(self, key: str, payload: str, ttl_seconds: float) -> None:
            del ttl_seconds
            redis_store[key] = payload

        def delete(self, keys: tuple[str, ...]) -> None:
            for key in keys:
                redis_store.pop(key, None)

        def delete_prefix(self, prefix: str) -> None:
            for key in [item for item in redis_store if item.startswith(prefix)]:
                redis_store.pop(key, None)

    monkeypatch.setattr(route, "get_connection", counted_connection)
    configure_holiday_query_cache_backend(lambda: _Backend())
    invalidate_holiday_query_cache()
    try:
        first = client.get("/api/v1/holidays?from_date=2026-10-01&to_date=2026-10-31")
        second = client.get("/api/v1/holidays?from_date=2026-10-01&to_date=2026-10-31")
        assert first.status_code == second.status_code == 200
        assert opened_connections == 1
        assert len(redis_store) == 1

        preview = _preview(client).json()["data"]
        applied = client.post(
            "/api/v1/holidays/apply",
            headers={"Idempotency-Key": "holiday-cache-invalidate-01"},
            json={
                **preview["command"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "年度新增",
            },
        )
        assert applied.status_code == 200
        assert redis_store == {}

        refreshed = client.get("/api/v1/holidays?from_date=2026-10-01&to_date=2026-10-31")
        assert refreshed.status_code == 200
        assert opened_connections == 2
        assert len(refreshed.json()["data"]["holidays"]) == 1
    finally:
        configure_holiday_query_cache_backend(route.default_redis_cache_backend)
        invalidate_holiday_query_cache()

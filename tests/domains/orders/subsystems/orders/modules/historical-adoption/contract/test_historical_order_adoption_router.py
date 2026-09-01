"""
File: test_historical_order_adoption_router.py
Description: 驗證訂單歷史 workbook HTTP Preview／Apply typed result、conflict 與暫存清理。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_admin
from api.dependencies.historical_order_adoption import get_historical_order_workbook_import_service
from api.routes.historical_order_adoption import router
from subsystems.orders.historical_order_workbook_import import (
    HistoricalOrderStatusCounts, HistoricalOrderWorkbookConflict, HistoricalOrderWorkbookPreview,
    HistoricalOrderWorkbookReceipt,
)


class _Service:
    def __init__(
        self,
        conflict: bool = False,
        conflict_code: str = "historical_order_workbook_idempotency_conflict",
    ) -> None:
        self.conflict = conflict
        self.conflict_code = conflict_code
        self.paths: list[Path] = []

    def preview(self, path):
        self.paths.append(Path(path))
        return HistoricalOrderWorkbookPreview(
            "0" * 64, "1" * 64, 1, 1, 0, 0, 0, 0, 0,
            HistoricalOrderStatusCounts(0, 1, 0, 0), "2" * 64,
        )

    def apply(self, path, key, preview, actor, correlation):
        self.paths.append(Path(path))
        if self.conflict:
            raise HistoricalOrderWorkbookConflict(self.conflict_code)
        return HistoricalOrderWorkbookReceipt(
            "0" * 64, 1, 1, 0, 0, 0, 0, 0, False,
            HistoricalOrderStatusCounts(0, 1, 0, 0),
        )


def test_preview_and_apply_remove_server_temporary_workbooks():
    service = _Service()
    client = _client(service)
    preview = client.post("/api/v1/orders/historical-adoption/workbooks/preview", files=_file())
    apply = client.post(
        "/api/v1/orders/historical-adoption/workbooks/apply", headers=_headers(),
        data={"preview_fingerprint": "2" * 64}, files=_file(),
    )

    assert preview.status_code == 200
    assert apply.status_code == 200
    assert all(path.exists() is False for path in service.paths)


def test_apply_conflict_is_typed_and_removes_temporary_workbook():
    service = _Service(conflict=True)
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply", headers=_headers(),
        data={"preview_fingerprint": "2" * 64}, files=_file(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "historical_order_workbook_idempotency_conflict"
    assert service.paths[0].exists() is False


def test_apply_stale_preview_is_a_conflict_not_a_validation_error():
    service = _Service(conflict=True, conflict_code="historical_order_preview_stale")
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply", headers=_headers(),
        data={"preview_fingerprint": "2" * 64}, files=_file(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "historical_order_preview_stale"


def test_database_dependency_unavailable_is_typed(monkeypatch):
    import api.dependencies.historical_order_adoption as dependency
    import pymysql

    monkeypatch.setattr(dependency, "get_connection", lambda: (_ for _ in ()).throw(pymysql.OperationalError(2003, "offline")))
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")

    response = TestClient(application).post("/api/v1/orders/historical-adoption/workbooks/preview", files=_file())

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "historical_order_import_database_unavailable"


def test_apply_reports_pending_status_constraint_as_database_upgrade_required():
    service = _Service()

    def fail_apply(*_args):
        raise OperationalError(
            3819,
            "Check constraint 'chk_order_lifecycle_state_event_before_status' is violated.",
        )

    service.apply = fail_apply
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply",
        headers=_headers(),
        data={"preview_fingerprint": "2" * 64},
        files=_file(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "historical_order_database_upgrade_required"
    )


def _client(service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")
    app.dependency_overrides[get_historical_order_workbook_import_service] = lambda: service
    return TestClient(app)


def _headers():
    return {"Idempotency-Key": "historical-order-router-test", "X-Correlation-ID": "historical-order-router-test"}


def _file():
    return {"workbook": ("orders.xlsx", b"test", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

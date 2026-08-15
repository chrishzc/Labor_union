"""
File: test_staff_historical_workbook_api.py
Description: 驗證 Staff 歷史 workbook API 的 Preview、Apply、conflict 與暫存清理。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_historical_workbook import get_staff_historical_workbook_service
from api.routes.staff_historical_workbook import router
from subsystems.case_import.staff_historical_workbook_adoption import (
    StaffHistoricalWorkbookConflict,
    StaffHistoricalWorkbookPreview,
    StaffHistoricalWorkbookReceipt,
)


class _Service:
    def __init__(self, conflict: bool = False) -> None:
        self.conflict = conflict
        self.paths: list[Path] = []

    def preview(self, path, revision):
        self.paths.append(Path(path))
        return _preview()

    def apply(self, path, revision, fingerprint, key, actor, correlation):
        self.paths.append(Path(path))
        if self.conflict:
            raise StaffHistoricalWorkbookConflict("staff_historical_workbook_idempotency_conflict")
        return _receipt()


def _client(service: _Service) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")
    app.dependency_overrides[get_staff_historical_workbook_service] = lambda: service
    return TestClient(app)


def test_preview_is_typed_and_removes_uploaded_workbook():
    service = _Service()
    response = _client(service).post("/api/v1/case-import/staff-historical/workbooks/preview", files={"workbook": ("staff.xlsx", b"fixture", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    assert response.status_code == 200
    assert response.json()["data"]["preview_fingerprint"] == "a" * 64
    assert service.paths[0].exists() is False


def test_apply_conflict_is_typed_and_removes_uploaded_workbook():
    service = _Service(conflict=True)
    response = _client(service).post("/api/v1/case-import/staff-historical/workbooks/apply", headers={"Idempotency-Key": "staff-key", "X-Correlation-ID": "staff-correlation", "X-Preview-Fingerprint": "a" * 64}, files={"workbook": ("staff.xlsx", b"fixture", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "staff_historical_workbook_idempotency_conflict"
    assert service.paths[0].exists() is False


def test_apply_returns_typed_terminal_receipt():
    service = _Service()
    response = _client(service).post(
        "/api/v1/case-import/staff-historical/workbooks/apply",
        headers={
            "Idempotency-Key": "staff-key",
            "X-Correlation-ID": "staff-correlation",
            "X-Preview-Fingerprint": "a" * 64,
        },
        files={"workbook": ("staff.xlsx", b"fixture", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["created_count"] == 1
    assert response.json()["data"]["replayed_workbook"] is False


def _preview() -> StaffHistoricalWorkbookPreview:
    return StaffHistoricalWorkbookPreview("0" * 64, 1, 1, 0, 0, 0, 0, "a" * 64)


def _receipt() -> StaffHistoricalWorkbookReceipt:
    return StaffHistoricalWorkbookReceipt("0" * 64, 1, 1, 0, 0, 0, 0, 0, "a" * 64, False)

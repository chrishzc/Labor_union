"""
File: test_hcm_import_router.py
Description: 驗證 HCM upload route 的 typed result、conflict 與暫存檔終端清理。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.hcm_import import (
    get_hcm_historical_workbook_import_service,
    get_hcm_workbook_import_service,
)
from api.routes.hcm_import import router
from subsystems.case_import.hcm_workbook_import import HcmWorkbookConflict, HcmWorkbookPreview, HcmWorkbookReceipt


class _Service:
    def __init__(self, conflict: bool = False) -> None:
        self._conflict = conflict
        self.upload_paths: list[Path] = []

    def load_frame(self, source_path: str) -> pd.DataFrame:
        self.upload_paths.append(Path(source_path))
        return pd.DataFrame({"case_no": ["HCM-TEST"]})

    def ingest(self, frame, source_path, key, actor, correlation_id):
        if self._conflict:
            raise HcmWorkbookConflict("hcm_workbook_idempotency_conflict")
        return HcmWorkbookReceipt("0" * 64, 1, 1, 0, 0, 0, 0, False)

    def preview(self, frame, source_path):
        return HcmWorkbookPreview("0" * 64, 1, 1, 0, 0, "1" * 64)

    def apply(self, frame, source_path, preview_fingerprint, key, actor, correlation_id):
        assert preview_fingerprint == "1" * 64
        return self.ingest(frame, source_path, key, actor, correlation_id)


def _client(service: _Service) -> TestClient:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")
    application.dependency_overrides[get_hcm_workbook_import_service] = lambda: service
    application.dependency_overrides[get_hcm_historical_workbook_import_service] = lambda: service
    return TestClient(application)


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": "hcm-router-test", "X-Correlation-ID": "hcm-router-test"}


def test_success_returns_typed_receipt_and_removes_temporary_workbook():
    service = _Service()
    response = _client(service).post(
        "/api/v1/case-import/hcm/workbooks/ingest",
        headers=_headers(),
        files={"workbook": ("hcm.xlsx", b"test", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["inserted_count"] == 1
    assert service.upload_paths[0].exists() is False


def test_preview_then_apply_use_separate_typed_endpoints_and_cleanup():
    service = _Service()
    client = _client(service)
    files = {"workbook": ("hcm.xlsx", b"test", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    preview = client.post("/api/v1/case-import/hcm/workbooks/preview", files=files)
    applied = client.post(
        "/api/v1/case-import/hcm/workbooks/apply",
        headers={**_headers(), "X-Preview-Fingerprint": "1" * 64},
        files=files,
    )

    assert preview.status_code == 200
    assert preview.json()["data"]["ready_count"] == 1
    assert applied.status_code == 200
    assert all(path.exists() is False for path in service.upload_paths)


def test_historical_preview_then_apply_use_the_same_typed_contract():
    service = _Service()
    client = _client(service)
    files = {"workbook": ("hcm.xlsx", b"test", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    preview = client.post("/api/v1/case-import/hcm/historical-workbooks/preview", files=files)
    applied = client.post(
        "/api/v1/case-import/hcm/historical-workbooks/apply",
        headers={**_headers(), "X-Preview-Fingerprint": "1" * 64}, files=files,
    )

    assert preview.status_code == 200
    assert applied.status_code == 200


def test_same_key_conflict_is_typed_and_removes_temporary_workbook():
    service = _Service(conflict=True)
    response = _client(service).post(
        "/api/v1/case-import/hcm/workbooks/ingest",
        headers=_headers(),
        files={"workbook": ("hcm.xlsx", b"test", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "hcm_workbook_idempotency_conflict"
    assert service.upload_paths[0].exists() is False

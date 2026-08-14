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
from api.dependencies.hcm_import import get_hcm_workbook_import_service
from api.routes.hcm_import import router
from subsystems.case_import.hcm_workbook_import import HcmWorkbookConflict, HcmWorkbookReceipt


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
        return HcmWorkbookReceipt("0" * 64, 1, 1, 0, 0, 0, False)


def _client(service: _Service) -> TestClient:
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")
    application.dependency_overrides[get_hcm_workbook_import_service] = lambda: service
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

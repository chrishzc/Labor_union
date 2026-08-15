"""
File: test_import_warning_tracking_api.py
Description: 驗證匯入警示 API 的嚴格 payload、Preview 與 Apply 邊界。
"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.import_warning_tracking import get_import_warning_tracking_application
from api.routes.import_warning_tracking import router
from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from subsystems.anomalies.import_warning_tracking_workflow import (
    ImportWarningTask,
    WarningTransitionPreview,
)


class _Application:
    def __init__(self) -> None:
        self.applied = False
        self.task = ImportWarningTask("warning-1", "hcm", "IMPORT-004", "phone", "masked", ("invalid_phone",), ImportWarningTrackingStatus.OPEN, 1, None)

    def query_tasks(self, **_):
        return (self.task,)

    def preview(self, request):
        return WarningTransitionPreview(request.occurrence_identity, 1, ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION, 2)

    def apply(self, request):
        self.applied = True
        return WarningTransitionPreview(request.occurrence_identity, 1, ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION, 2)


def _client(application: _Application) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="operator-1")
    app.dependency_overrides[get_import_warning_tracking_application] = lambda: application
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": "warning-apply-1", "X-Correlation-ID": "warning-correlation-1"}


def test_preview_is_typed_and_does_not_apply() -> None:
    application = _Application()

    response = _client(application).post("/api/v1/import-warning-tracking/tasks/warning-1/preview", headers=_headers(), json={"expected_version": 1, "target_status": "awaiting_external_confirmation", "reason_code": "contact_started"})

    assert response.status_code == 200
    assert response.json()["data"]["resulting_version"] == 2
    assert application.applied is False


def test_apply_rejects_corrected_payload_before_application() -> None:
    application = _Application()

    response = _client(application).post("/api/v1/import-warning-tracking/tasks/warning-1/apply", headers=_headers(), json={"expected_version": 1, "target_status": "awaiting_external_confirmation", "reason_code": "contact_started", "corrected_fields": {"phone": "123"}})

    assert response.status_code == 422
    assert application.applied is False

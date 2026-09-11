"""Regression coverage for runtime alert target preview response serialization."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_alert_manager
from api.routes import runtime_health
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.runtime_alert_target_contracts import LineAlertTargetMutationPreview


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "admin", "管理員", "system_admin")


def test_disable_preview_serializes_typed_fingerprint(monkeypatch) -> None:
    class Application:
        def preview(self, command):
            assert command.target_id == 7
            assert command.enabled is False
            return LineAlertTargetMutationPreview(
                operation="disable",
                target_id=7,
                previous_state="active",
                resulting_state="disabled",
                current_version="version-2",
                preview_fingerprint=PreviewFingerprint("f" * 64),
                apply_ready=True,
            )

    monkeypatch.setattr(runtime_health, "_app", lambda: Application())
    app = FastAPI()
    app.include_router(runtime_health.router)
    app.dependency_overrides[require_line_alert_manager] = _principal

    response = TestClient(app).post(
        "/api/v1/runtime/line-alert-targets/7/preview",
        json={
            "expected_version": "version-1",
            "enabled": False,
            "reason": "停用異常通知群組",
            "idempotency_key": "line-alert-disable-preview-1",
            "correlation_id": "line-alert-disable-preview-1",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "operation": "disable",
        "target_id": 7,
        "previous_state": "active",
        "resulting_state": "disabled",
        "current_version": "version-2",
        "preview_fingerprint": "f" * 64,
        "apply_ready": True,
    }

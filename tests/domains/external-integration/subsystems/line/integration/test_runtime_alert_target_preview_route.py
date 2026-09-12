"""Regression coverage for runtime alert target preview response serialization."""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_line_alert_manager
from api.routes import runtime_health
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.runtime_alert_target_contracts import (
    LineAlertTargetMutationPreview,
    LineAlertTargetMutationReceipt,
)


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


def test_disable_preview_then_apply_passes_the_same_fingerprint(monkeypatch) -> None:
    fingerprint = "a" * 64

    class Application:
        def preview(self, command):
            assert command.target_id == 7
            assert command.enabled is False
            assert command.expected_version == "version-1"
            return LineAlertTargetMutationPreview(
                operation="disable",
                target_id=7,
                previous_state="active",
                resulting_state="disabled",
                current_version="version-1",
                preview_fingerprint=PreviewFingerprint(fingerprint),
                apply_ready=True,
            )

        def set_enabled(self, command):
            assert command.target_id == 7
            assert command.enabled is False
            assert command.expected_version == "version-1"
            assert command.preview_fingerprint == PreviewFingerprint(fingerprint)
            assert command.correlation_id.value == "line-alert-disable-apply-1"
            assert command.idempotency_key.value == "line-alert-disable-apply-1"
            return LineAlertTargetMutationReceipt(
                receipt_id="receipt-7",
                command_family="line_alert_target",
                operation="disable",
                target_id=7,
                previous_state="active",
                resulting_state="disabled",
                current_version="version-2",
                replayed=False,
                correlation_id=command.correlation_id.value,
                committed_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
            )

    monkeypatch.setattr(runtime_health, "_app", lambda: Application())
    app = FastAPI()
    app.include_router(runtime_health.router)
    app.dependency_overrides[require_line_alert_manager] = _principal
    preview_response = TestClient(app).post(
        "/api/v1/runtime/line-alert-targets/7/preview",
        json={
            "expected_version": "version-1",
            "enabled": False,
            "reason": "解除異常通知群組",
            "idempotency_key": "line-alert-disable-apply-1",
            "correlation_id": "line-alert-disable-apply-1",
        },
    )
    assert preview_response.status_code == 200
    apply_response = TestClient(app).patch(
        "/api/v1/runtime/line-alert-targets/7",
        json={
            "expected_version": "version-1",
            "enabled": False,
            "reason": "解除異常通知群組",
            "idempotency_key": "line-alert-disable-apply-1",
            "correlation_id": "line-alert-disable-apply-1",
            "preview_fingerprint": preview_response.json()["data"]["preview_fingerprint"],
        },
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["data"].items() >= {
        "operation": "disable",
        "target_id": 7,
        "previous_state": "active",
        "resulting_state": "disabled",
    }.items()

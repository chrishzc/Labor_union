"""
File: test_admin_entry_targets_routes.py
Description: 驗證 entry target routes 的 auth provenance、typed errors、router 掛載與 file-only audit。
"""

from datetime import datetime, timezone

from fastapi import Request
from fastapi.testclient import TestClient

import api.main as main_module
from api.dependencies.admin_auth import require_admin
from api.main import app
from api.routes.admin_entry_targets import get_admin_entry_target_control
from subsystems.access.admin_entry_target_control import AdminEntryTargetControl, ArtifactHealth, make_initial_state
from subsystems.access.authentication_session import AdminPrincipal


class MemoryStore:
    def __init__(self):
        self.state = make_initial_state()

    def read(self):
        return self.state

    def mutate(self, operation):
        next_state, result = operation(self.state)
        self.state = next_state
        return result


def test_routes_are_mounted_and_apply_uses_file_receipt_not_db_audit(monkeypatch) -> None:
    store = MemoryStore()

    class HealthyArtifact:
        def query(self):
            return ArtifactHealth(True, "react-v1", "a" * 64, "api-v1")

    control = AdminEntryTargetControl(
        store,
        HealthyArtifact(),
        clock=lambda: datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
    )
    app.dependency_overrides[get_admin_entry_target_control] = lambda: control
    def principal(request: Request):
        value = AdminPrincipal(7, "operator", "Operator", "admin", is_root=True)
        request.state.admin_principal = value
        return value

    app.dependency_overrides[require_admin] = principal
    audit_calls = []
    monkeypatch.setattr(main_module, "record_admin_audit", lambda **kwargs: audit_calls.append(kwargs))
    try:
        with TestClient(app) as client:
            queried = client.get("/api/v1/admin/entry-targets")
            resolved = client.get("/api/v1/admin/entry-targets/ui-react:%23system-status")
            previewed = client.post(
                "/api/v1/admin/entry-targets/preview",
                headers={"Idempotency-Key": "preview-system-status-1", "X-Correlation-ID": "correlation-preview-1"},
                json={
                    "entry_id": "ui-react:#system-status",
                    "expected_state_revision": 2,
                    "expected_entry_revision": 1,
                    "expected_current_target": "streamlit",
                    "desired_target": "react",
                    "required_react_artifact": {
                        "version": "react-v1",
                        "digest": "a" * 64,
                        "api_compatibility_revision": "api-v1"
                    },
                    "reason_code": "activate_react"
                },
            )
            applied = client.post(
                "/api/v1/admin/entry-targets/apply",
                headers={"Idempotency-Key": "rollback-1", "X-Correlation-ID": "correlation-1"},
                json={
                    "entry_id": "ui-react:#orders",
                    "expected_state_revision": 2,
                    "expected_entry_revision": 1,
                    "expected_current_target": "streamlit",
                    "desired_target": "streamlit",
                    "required_react_artifact": None,
                    "reason_code": "rollback"
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert queried.status_code == 200
    assert len(queried.json()["data"]["entries"]) == 12
    assert resolved.status_code == 200
    assert resolved.json()["data"]["entry_id"] == "ui-react:#system-status"
    assert resolved.json()["data"]["replacement_group"] == "reports-system"
    assert previewed.status_code == 200
    assert previewed.json()["data"]["entry_id"] == "ui-react:#system-status"
    assert store.state.revision == 2
    assert applied.status_code == 409
    assert applied.json()["detail"]["error"]["code"] == "entry_target_noop"
    assert audit_calls == []


def test_apply_success_sets_file_receipt_marker_without_spoofed_actor(monkeypatch) -> None:
    class AlwaysHealthy:
        def query(self):
            from subsystems.access.admin_entry_target_control import ArtifactHealth

            return ArtifactHealth(True, "react-v1", "a" * 64, "api-v1")

    control = AdminEntryTargetControl(MemoryStore(), AlwaysHealthy())
    app.dependency_overrides[get_admin_entry_target_control] = lambda: control
    def principal(request: Request):
        value = AdminPrincipal(7, "operator", "Operator", "admin")
        request.state.admin_principal = value
        return value

    app.dependency_overrides[require_admin] = principal
    audit_calls = []
    monkeypatch.setattr(main_module, "record_admin_audit", lambda **kwargs: audit_calls.append(kwargs))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/entry-targets/apply",
                headers={"Idempotency-Key": "switch-1", "X-Correlation-ID": "correlation-1"},
                json={
                    "entry_id": "ui-react:#orders",
                    "expected_state_revision": 2,
                    "expected_entry_revision": 1,
                    "expected_current_target": "streamlit",
                    "desired_target": "react",
                    "required_react_artifact": {
                        "version": "react-v1",
                        "digest": "a" * 64,
                        "api_compatibility_revision": "api-v1"
                    },
                    "reason_code": "activate_react"
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["actor_id"] == "admin:7"
    assert audit_calls == []


def test_invalid_apply_does_not_fall_through_to_db_audit(monkeypatch) -> None:
    def principal(request: Request):
        value = AdminPrincipal(7, "operator", "Operator", "admin")
        request.state.admin_principal = value
        return value

    app.dependency_overrides[get_admin_entry_target_control] = lambda: AdminEntryTargetControl(MemoryStore())
    app.dependency_overrides[require_admin] = principal
    audit_calls = []
    monkeypatch.setattr(main_module, "record_admin_audit", lambda **kwargs: audit_calls.append(kwargs))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/entry-targets/apply",
                headers={"Idempotency-Key": "invalid-1", "X-Correlation-ID": "correlation-1"},
                json={"entry_id": "ui-react:#orders"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert audit_calls == []


def test_unrelated_authenticated_mutation_keeps_existing_db_audit(monkeypatch) -> None:
    path = "/api/v1/_test/unrelated-audit-contract"
    if not any(getattr(route, "path", None) == path for route in app.routes):
        @app.post(path)
        def unrelated_mutation(request: Request):
            request.state.admin_principal = AdminPrincipal(7, "operator", "Operator", "admin")
            return {"status": "ok"}

    audit_calls = []
    monkeypatch.setattr(main_module, "record_admin_audit", lambda **kwargs: audit_calls.append(kwargs))

    with TestClient(app) as client:
        response = client.post(path)

    assert response.status_code == 200
    assert len(audit_calls) == 1
    assert audit_calls[0]["request_path"] == path


def test_react_switch_without_host_health_returns_typed_503() -> None:
    def principal(request: Request):
        value = AdminPrincipal(7, "operator", "Operator", "admin")
        request.state.admin_principal = value
        return value

    app.dependency_overrides[get_admin_entry_target_control] = lambda: AdminEntryTargetControl(MemoryStore())
    app.dependency_overrides[require_admin] = principal
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/entry-targets/apply",
                headers={"Idempotency-Key": "switch-no-host", "X-Correlation-ID": "correlation-1"},
                json={
                    "entry_id": "ui-react:#orders",
                    "expected_state_revision": 2,
                    "expected_entry_revision": 1,
                    "expected_current_target": "streamlit",
                    "desired_target": "react",
                    "required_react_artifact": {
                        "version": "react-v1",
                        "digest": "a" * 64,
                        "api_compatibility_revision": "api-v1"
                    },
                    "reason_code": "activate_react"
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "react_artifact_unavailable"

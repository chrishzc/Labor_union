"""
File: test_admin_auth_security.py
Description: 驗證管理員登入、同權業務存取與開發 auth profile 的安全邊界。
"""

from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import (
    admin_auth_is_enabled,
    require_admin,
    require_capability,
    require_root,
    require_line_menu_publisher,
    require_line_task_controller,
)
from api.routes.admin_auth import _local_developer_session_enabled
from subsystems.access.authentication_session import (
    AdminPrincipal,
    hash_admin_password,
    has_required_capability,
    has_required_role,
    verify_admin_password,
)
from ui.pages.shared import local_developer_session_is_enabled


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE_DIRECTORIES = (
    ROOT / "api",
    ROOT / "ui",
    ROOT / "subsystems",
    ROOT / "infrastructure",
    ROOT / "scripts",
)


def test_admin_password_is_salted_and_verifiable():
    first = hash_admin_password("a-long-test-password")
    second = hash_admin_password("a-long-test-password")

    assert first != second
    assert "a-long-test-password" not in first
    assert verify_admin_password("a-long-test-password", first)
    assert not verify_admin_password("wrong-password", first)


def test_all_enabled_internal_roles_satisfy_legacy_role_guards():
    manager = AdminPrincipal(1, "manager", "Manager", "line_manager")
    viewer = AdminPrincipal(2, "viewer", "Viewer", "line_viewer")

    assert has_required_role(manager, "line_viewer")
    assert has_required_role(manager, "line_manager")
    assert has_required_role(viewer, "line_manager")


def test_all_enabled_internal_roles_receive_equal_business_capabilities():
    manager = AdminPrincipal(1, "manager", "Manager", "line_manager")
    agent = AdminPrincipal(2, "agent", "Agent", "line_agent")

    assert has_required_capability(manager, "line.identity.review")
    assert has_required_capability(manager, "line.task.control")
    assert has_required_capability(agent, "line.review.read")
    assert has_required_capability(agent, "line.task.control")
    assert not has_required_capability(agent, "unknown.capability")


def test_line_router_dependencies_target_their_operation_capabilities():
    assert require_line_task_controller is not require_line_menu_publisher


def test_line_config_keeps_public_liff_read_but_protects_management_routes():
    source = (ROOT / "api/routes/line_system_config.py").read_text(encoding="utf-8")

    assert '@public_router.get("/liff"' in source
    assert "dependencies=[Depends(require_line_viewer)]" in source
    assert "dependencies=[Depends(require_line_manager)]" in source


def test_streamlit_line_client_uses_session_transport():
    source = (ROOT / "ui/api_clients/line_api_client.py").read_text(encoding="utf-8")
    page = (ROOT / "ui/pages/07_line_management.py").read_text(encoding="utf-8")

    assert "build_cloud_run_invocation_headers" in source
    assert "headers = build_cloud_run_invocation_headers()" in source
    assert 'headers["Authorization"] = f"Bearer {token}"' in source
    assert "os.getenv" not in page


def test_legacy_human_shared_key_has_no_active_runtime_caller():
    legacy_markers = ("LEGACY_SHARED_KEY", "X-Legacy-Shared-Key")
    matches = []
    for directory in RUNTIME_SOURCE_DIRECTORIES:
        for path in directory.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if any(marker in source for marker in legacy_markers):
                matches.append(path.relative_to(ROOT).as_posix())

    assert matches == []


def test_machine_identity_remains_on_its_separate_scoped_contract():
    source = (ROOT / "api/dependencies/internal_service_auth.py").read_text(
        encoding="utf-8"
    )

    assert "INTERNAL_SERVICE_SHARED_KEY" in source
    assert "google_oidc" in source


def test_streamlit_displays_recovery_codes_without_retaining_them_in_session():
    source = (ROOT / "ui/app.py").read_text(encoding="utf-8")

    assert 'st.session_state["access_control_recovery_codes"]' not in source
    assert 'st.code("\\n".join(codes), language=None)' in source


def test_admin_login_bypass_is_limited_to_development(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_bypass")
    assert not admin_auth_is_enabled()

    monkeypatch.setenv("APP_ENV", "production")
    assert admin_auth_is_enabled()


def test_missing_or_invalid_auth_profile_fails_closed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.delenv("ACCESS_CONTROL_PROFILE", raising=False)

    assert admin_auth_is_enabled()

    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "unexpected")
    assert admin_auth_is_enabled()


def test_local_developer_session_requires_exact_local_profile_and_enabled_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "true")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_developer_session")
    assert _local_developer_session_enabled()
    assert local_developer_session_is_enabled()

    monkeypatch.setenv("APP_ENV", "production")
    assert not _local_developer_session_enabled()
    assert not local_developer_session_is_enabled()


def test_local_bypass_principal_cannot_administer_real_accounts():
    bypass = AdminPrincipal(
        None, "development-bypass", "開發模式管理員", "system_admin", is_root=True
    )

    try:
        require_root(bypass)
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("local_bypass must not administer Account Center")


def test_local_bypass_still_enforces_registered_and_denied_capabilities(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("ACCESS_CONTROL_PROFILE", "local_bypass")
    request = Request({"type": "http"})
    principal = require_admin(request, None)

    require_capability("line.customer_service.read")(request, principal)

    for capability in ("line.rich_menu.publish", "unknown.capability"):
        with pytest.raises(HTTPException) as raised:
            require_capability(capability)(request, principal)
        assert raised.value.status_code == 403


@pytest.mark.parametrize(
    ("invalid_state", "authorization"),
    (
        ("disabled", "Bearer disabled-token"),
        ("revoked", "Bearer revoked-token"),
        ("expired", "Bearer expired-token"),
        ("missing-session", "Bearer missing-session-token"),
        ("missing-token", None),
    ),
)
def test_invalid_admin_session_fails_closed_before_downstream(
    monkeypatch, invalid_state, authorization
):
    looked_up_tokens = []
    downstream_calls = []

    def fake_get_admin_session(token):
        looked_up_tokens.append(token)
        return None

    monkeypatch.setattr(
        "api.dependencies.admin_auth.get_admin_session", fake_get_admin_session
    )

    def invoke_protected_application():
        principal = require_admin(Request({"type": "http"}), authorization)
        downstream_calls.append(principal)

    with pytest.raises(HTTPException) as raised:
        invoke_protected_application()

    assert raised.value.status_code == 401, invalid_state
    expected_lookup = [authorization.partition(" ")[2]] if authorization else []
    assert looked_up_tokens == expected_lookup, invalid_state
    assert downstream_calls == [], invalid_state


@pytest.mark.parametrize(
    ("invalid_state", "authorization", "expected_detail"),
    (
        ("disabled", "Bearer disabled-token", "管理員 Session 已失效或過期"),
        ("revoked", "Bearer revoked-token", "管理員 Session 已失效或過期"),
        ("expired", "Bearer expired-token", "管理員 Session 已失效或過期"),
        ("missing-session", "Bearer missing-session-token", "管理員 Session 已失效或過期"),
        ("missing-token", None, "缺少有效的管理員 Session"),
    ),
)
def test_invalid_admin_session_http_boundary_blocks_endpoint(
    monkeypatch, invalid_state, authorization, expected_detail
):
    looked_up_tokens = []
    downstream_calls = []

    def fake_get_admin_session(token):
        looked_up_tokens.append(token)
        return None

    monkeypatch.setattr(
        "api.dependencies.admin_auth.get_admin_session", fake_get_admin_session
    )
    app = FastAPI()

    @app.get("/sentinel")
    def sentinel_endpoint(principal=Depends(require_admin)):
        downstream_calls.append(principal)
        return {"ok": True}

    request_kwargs = {"headers": {"Authorization": authorization}} if authorization else {}
    with TestClient(app) as client:
        response = client.get("/sentinel", **request_kwargs)

    assert response.status_code == 401, invalid_state
    assert response.json() == {"detail": expected_detail}, invalid_state
    assert "ok" not in response.json(), invalid_state
    expected_lookup = [authorization.partition(" ")[2]] if authorization else []
    assert looked_up_tokens == expected_lookup, invalid_state
    assert downstream_calls == [], invalid_state

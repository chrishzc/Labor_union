from pathlib import Path

from api.dependencies.admin_auth import (
    admin_auth_is_enabled,
    require_line_menu_publisher,
    require_line_task_controller,
)
from subsystems.access.authentication_session import (
    AdminPrincipal,
    hash_admin_password,
    has_required_capability,
    has_required_role,
    verify_admin_password,
)


ROOT = Path(__file__).resolve().parents[1]


def test_admin_password_is_salted_and_verifiable():
    first = hash_admin_password("a-long-test-password")
    second = hash_admin_password("a-long-test-password")

    assert first != second
    assert "a-long-test-password" not in first
    assert verify_admin_password("a-long-test-password", first)
    assert not verify_admin_password("wrong-password", first)


def test_admin_role_order_is_enforced():
    manager = AdminPrincipal(1, "manager", "Manager", "line_manager")
    viewer = AdminPrincipal(2, "viewer", "Viewer", "line_viewer")

    assert has_required_role(manager, "line_viewer")
    assert has_required_role(manager, "line_manager")
    assert not has_required_role(viewer, "line_manager")


def test_fixed_role_bundles_authorize_capabilities_without_role_ordering():
    manager = AdminPrincipal(1, "manager", "Manager", "line_manager")
    agent = AdminPrincipal(2, "agent", "Agent", "line_agent")

    assert has_required_capability(manager, "line.identity.review")
    assert has_required_capability(manager, "line.task.control")
    assert has_required_capability(agent, "line.review.read")
    assert not has_required_capability(agent, "line.task.control")
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

    assert 'headers: dict[str, str] = {}' in source
    assert 'headers["Authorization"] = f"Bearer {token}"' in source
    assert "os.getenv" not in page


def test_admin_login_bypass_is_limited_to_development(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("APP_ENV", "development")
    assert not admin_auth_is_enabled()

    monkeypatch.setenv("APP_ENV", "production")
    assert admin_auth_is_enabled()

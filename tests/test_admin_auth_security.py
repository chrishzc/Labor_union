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
    reset_admin_password,
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


def test_reset_admin_password_replaces_hash_and_revokes_sessions(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.updated_hash = None
            self.revoked_admin_id = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, sql, params=()):
            if "UPDATE admin_users" in sql:
                self.updated_hash = params[0]
            if "UPDATE admin_sessions" in sql:
                self.revoked_admin_id = params[0]

        def fetchone(self):
            return {"id": 7}

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()
            self.committed = False
            self.closed = False

        def begin(self):
            pass

        def cursor(self, *_args, **_kwargs):
            return self.cursor_instance

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("rollback should not be called")

        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(
        "subsystems.access.authentication_session.get_connection",
        lambda: connection,
    )

    admin_id = reset_admin_password(username=" Ting ", new_password="new-password-1234")

    assert admin_id == 7
    assert connection.committed
    assert connection.closed
    assert connection.cursor_instance.revoked_admin_id == 7
    assert verify_admin_password(
        "new-password-1234", connection.cursor_instance.updated_hash
    )


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

    assert 'headers: dict[str, str] = {}' in source
    assert 'headers["Authorization"] = f"Bearer {token}"' in source
    assert "os.getenv" not in page


def test_admin_login_bypass_is_limited_to_development(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("APP_ENV", "development")
    assert not admin_auth_is_enabled()

    monkeypatch.setenv("APP_ENV", "production")
    assert admin_auth_is_enabled()

"""Policy checks for the approved privacy-safe administrator audit workflow."""

from __future__ import annotations

import inspect
from pathlib import Path

from api.routes import admin_audit
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.access.security_audit_query import mask_audit_details, mask_ip_address


ROOT = Path(__file__).resolve().parents[1]


def test_audit_display_masks_ip_and_sensitive_detail_values() -> None:
    assert mask_ip_address("203.0.113.9") == "203.0.113.***"
    assert mask_ip_address("not-an-ip") == "***"
    assert mask_audit_details({"token": "secret", "nested": {"phone": "0912"}}) == {
        "token": "***", "nested": {"phone": "***"}
    }


def test_audit_routes_require_only_an_authenticated_administrator() -> None:
    source = (ROOT / "api/routes/admin_audit.py").read_text(encoding="utf-8")

    assert "Depends(require_admin)" in source
    assert "require_capability" not in source
    assert "admin.audit.detail.read" not in source
    assert '"操作紀錄",' not in (ROOT / "api/routes/line_admin.py").read_text(encoding="utf-8")


def test_any_authenticated_administrator_can_open_masked_detail(monkeypatch) -> None:
    monkeypatch.setattr(admin_audit, "get_admin_audit_detail", lambda _: _audit_detail(2))
    principal = AdminPrincipal(1, "reader", "Reader", "line_viewer")

    response = admin_audit.audit_detail(7, principal)
    assert response.data.id == 7


def test_opening_a_masked_audit_detail_does_not_require_a_reason() -> None:
    parameters = inspect.signature(admin_audit.audit_detail).parameters

    assert "reason" not in parameters


def _audit_detail(actor_id: int) -> dict:
    return {
        "id": 7, "admin_user_id": actor_id, "actor_display_name": "Actor",
        "action": "line.review.approve", "resource_type": None, "resource_id": None,
        "request_path": None, "http_method": "POST", "result_status": 200,
        "ip_address_masked": "203.0.113.***", "created_at": "2026-08-09T08:00:00",
        "details": {"reason": "approved"},
    }


def test_retention_archives_after_two_years_without_deleting_archive() -> None:
    source = (ROOT / "subsystems/access/security_audit_query.py").read_text(encoding="utf-8")
    schema = (ROOT / "db/schema_parts/151_admin_security_audit_retention.sql").read_text(encoding="utf-8")

    assert "ONLINE_RETENTION_YEARS = 2" in source
    assert "INTERVAL 2 YEAR" in source
    assert "INSERT IGNORE INTO admin_audit_log_archive" in source
    assert "DELETE FROM admin_audit_log_archive" not in source
    assert "admin_audit_log_archive" in schema

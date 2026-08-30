"""
File: test_access_audit_public_query_contract.py
Description: 驗證稽核清單輸出為伺服器遮罩 typed page。
"""

from datetime import datetime

from api.routes import admin_audit
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.access.security_audit_query import (
    AuditDetailField,
    AuditDetailItem,
    AuditListItem,
    AuditPage,
    AuditQueryStorageError,
)


def test_masked_audit_query_does_not_expose_raw_details(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_audit,
        "list_admin_audits",
        lambda **_: AuditPage(
            items=[
                AuditListItem(
                    audit_id=10,
                    occurred_at=datetime.fromisoformat("2026-08-20T10:00:00+08:00"),
                    actor_label_masked="根***",
                    action_family="authentication",
                    target_label_masked="session:se***",
                    ip_address_masked="127.0.0.***",
                    outcome="success",
                    reason_code="admin.login.success",
                )
            ],
            page=1,
            page_size=25,
            total=1,
        ),
    )

    response = admin_audit.list_audits(_=AdminPrincipal(1, "admin", "管理員", "system_admin"))
    item = response.data.items[0]
    assert item.audit_id == 10
    assert item.actor_label_masked == "根***"
    assert item.target_label_masked == "session:se***"
    assert item.occurred_at.isoformat() == "2026-08-20T10:00:00+08:00"
    assert not hasattr(item, "details")


def test_masked_detail_is_a_closed_allowlist_and_never_returns_raw_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_audit,
        "get_admin_audit_detail",
        lambda _, **__: AuditDetailItem(
            audit_id=11,
            occurred_at=datetime.fromisoformat("2026-08-20T10:00:00+08:00"),
            actor_label_masked="管***",
            action_family="account_security",
            target_label_masked="account:12***",
            ip_address_masked="127.0.0.***",
            outcome="success",
            reason_code="admin.account.enabled_changed",
            details=(
                AuditDetailField("reason", "provided"),
                AuditDetailField("enabled", "disabled"),
            ),
        ),
    )

    response = admin_audit.audit_detail(11, AdminPrincipal(1, "admin", "管理員", "system_admin"))
    dumped = response.data.model_dump()

    assert dumped["details"] == [
        {"key": "reason", "value_masked": "provided"},
        {"key": "enabled", "value_masked": "disabled"},
    ]
    assert "password" not in str(dumped).lower()
    assert "request_path" not in dumped


def test_storage_failure_maps_to_safe_typed_503(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_audit,
        "list_admin_audits",
        lambda **_: (_ for _ in ()).throw(AuditQueryStorageError("private storage detail")),
    )

    error = None
    try:
        admin_audit.list_audits(_=AdminPrincipal(1, "admin", "管理員", "system_admin"))
    except Exception as caught:
        error = caught

    assert error is not None
    assert getattr(error, "status_code", None) == 503
    assert "private storage detail" not in str(getattr(error, "detail", error))

"""
File: test_access_account_center_public_contract.py
Description: 驗證帳號清冊只公開最小 typed GET 欄位。
"""

import asyncio
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from api.routes import account_center
from api.schemas.account_center import AccountCreateRequest, AccountEnabledRequest, AccountPasswordResetRequest
from subsystems.access.authentication_session import AccountCommandReceipt, AdminPrincipal, hash_admin_password, verify_admin_password
from subsystems.access import authentication_session as authentication


@pytest.mark.parametrize("length,accepted", [(9, False), (10, True), (11, True), (12, True)])
def test_create_reset_and_bootstrap_password_minimum(length, accepted) -> None:
    password = "x" * length
    commands = [
        (AccountCreateRequest, dict(username="mock-user", display_name="Mock")),
        (AccountPasswordResetRequest, dict(expected_version=1)),
    ]
    for model, fields in commands:
        payload = dict(**fields, password=password, reason="boundary test", idempotency_key="mock-password-boundary")
        if accepted:
            model.model_validate(payload)
        else:
            with pytest.raises(ValidationError):
                model.model_validate(payload)
    if accepted:
        encoded = hash_admin_password(password)
        assert verify_admin_password(password, encoded)
        assert not verify_admin_password(password + "wrong", encoded)
    else:
        with pytest.raises(ValueError, match="10 個字元"):
            hash_admin_password(password)


def test_account_directory_projection_excludes_roles_and_personal_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        account_center,
        "list_account_center_users",
        lambda **_kwargs: [AdminPrincipal(1, "root-user", "根帳號", "system_admin", is_root=True)],
    )

    response = asyncio.run(account_center.list_accounts(None))
    item = response.data[0]

    assert item.model_dump() == {
        "id": 1,
        "username": "root-user",
        "display_name": "根帳號",
        "enabled": True,
        "is_root": True,
        "access_control_version": 1,
    }


def test_account_mutation_request_is_closed_and_route_returns_typed_receipt(monkeypatch) -> None:
    principal = AdminPrincipal(1, "root", "Root", "system_admin", is_root=True)
    receipt = AccountCommandReceipt(
        operation="account-enabled",
        target_account_id=2,
        resulting_access_control_version=4,
        receipt_identity="a" * 64,
        replayed=False,
    )
    monkeypatch.setattr(account_center, "set_account_center_enabled", lambda **_kwargs: receipt)
    payload = AccountEnabledRequest(
        enabled=False,
        reason="停用離職帳號",
        expected_version=3,
        idempotency_key="disable-account-2",
    )

    response = asyncio.run(account_center.set_enabled(2, payload, principal))

    assert response.data.model_dump() == {
        "operation": "account-enabled",
        "target_account_id": 2,
        "resulting_access_control_version": 4,
        "receipt_identity": "a" * 64,
        "replayed": False,
        "account": None,
    }
    with pytest.raises(ValidationError):
        AccountEnabledRequest.model_validate({**payload.model_dump(), "role": "system_admin"})


def test_disabling_account_keeps_receipt_and_revocation_without_audit() -> None:
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [{"admin_user_id": 1}, None, None, {"id": 2, "access_control_version": 3}, None]
    actor = AdminPrincipal(1, "root", "Root", "system_admin", is_root=True)

    receipt = authentication.set_account_center_enabled(
        connection_factory=lambda: conn, actor=actor, account_id=2, enabled=False,
        reason="test", expected_version=3, idempotency_key="disable-without-audit",
    )

    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("UPDATE admin_sessions" in sql for sql in statements)
    assert any("INSERT INTO admin_command_receipts" in sql for sql in statements)
    assert all("admin_audit_logs" not in sql and "admin_security_alert_outbox" not in sql for sql in statements)
    assert receipt.resulting_access_control_version == 4
    conn.commit.assert_called_once()


@pytest.mark.parametrize(
    ("command", "extra"),
    [
        (authentication.set_account_center_enabled, {"enabled": False}),
        (authentication.revoke_account_center_sessions, {}),
        (authentication.reset_account_center_mfa, {}),
    ],
)
def test_online_account_commands_stop_during_pending_receipt_conversion(command, extra) -> None:
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [{"admin_user_id": 1}, {"unprotected": 1}]
    actor = AdminPrincipal(1, "root", "Root", "system_admin", is_root=True)
    with pytest.raises(account_center.AccountReceiptProtectionError, match="account_receipt_conversion_required") as caught:
        command(
            connection_factory=lambda: conn, actor=actor, account_id=2, expected_version=3,
            idempotency_key="fixture-command", reason="", **extra,
        )
    assert cursor.execute.call_count == 2
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()
    assert account_center._storage_unavailable(caught.value).status_code == 503


def test_account_command_rechecks_current_root_before_touching_receipts() -> None:
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"admin_user_id": 9}
    actor = AdminPrincipal(1, "former-root", "Former root", "system_admin", is_root=True)

    with pytest.raises(ValueError, match="admin_version_conflict"):
        authentication.set_account_center_enabled(
            connection_factory=lambda: conn, actor=actor, account_id=2, enabled=False,
            reason="", expected_version=3, idempotency_key="stale-root",
        )

    cursor.execute.assert_called_once()
    assert "admin_root_account" in cursor.execute.call_args.args[0]
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()


def test_account_command_errors_are_redacted_and_stable() -> None:
    conflict = account_center._command_error(ValueError("internal SQL duplicate detail"))
    unavailable = account_center._storage_unavailable(RuntimeError("secret storage location"))

    assert conflict.status_code == 409
    assert conflict.detail["error"]["code"] == "admin_account_conflict"
    assert "SQL" not in str(conflict.detail)
    assert unavailable.status_code == 503
    assert "secret storage location" not in str(unavailable.detail)

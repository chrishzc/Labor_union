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


@pytest.mark.parametrize("failure", [None, "database", "identity", "version", "duplicate", "audit"])
def test_local_root_recovery_preserves_identity_and_is_atomic(monkeypatch, failure):
    monkeypatch.setenv("APP_ENV", "development")
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [
        {"database_name": "wrong" if failure == "database" else "lu_test_recovery"},
        {"id": 2 if failure == "identity" else 1, "enabled": 1,
         "access_control_version": 2 if failure == "version" else 1},
        {"id": 2} if failure == "duplicate" else None,
    ]
    audit = MagicMock(side_effect=RuntimeError("audit failed") if failure == "audit" else None)
    monkeypatch.setattr(authentication, "_record_admin_audit_with_cursor", audit)
    args = dict(connection_factory=lambda: conn, target_database="lu_test_recovery",
                expected_account_id=1, expected_version=1, username="MockRoot",
                password="mock-only-password", reason="authorized local test")
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            authentication.recover_local_root_credentials(**args)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
    else:
        assert authentication.recover_local_root_credentials(**args) == 2
        conn.commit.assert_called_once()
        updates = [call.args for call in cursor.execute.call_args_list if call.args[0].startswith("UPDATE")]
        assert len(updates) == 2
        assert updates[0][1][0] == "mockroot"
        assert authentication.verify_admin_password(args["password"], updates[0][1][1])
        assert updates[0][1][2] == 1
        assert "admin_sessions" in updates[1][0]
        assert "mock-only-password" not in str(audit.call_args)
        assert "admin_totp" not in str(cursor.execute.call_args_list)
    conn.close.assert_called_once()


@pytest.mark.parametrize("environment,target", [("production", "lu_test_recovery"), ("development", "union_db")])
def test_local_root_recovery_rejects_nonlocal_scope(monkeypatch, environment, target):
    monkeypatch.setenv("APP_ENV", environment)
    factory = MagicMock()
    with pytest.raises(ValueError):
        authentication.recover_local_root_credentials(
            connection_factory=factory, target_database=target, expected_account_id=1,
            expected_version=1, username="mock", password="mock-only-password", reason="test")
    factory.assert_not_called()


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


def test_account_command_errors_are_redacted_and_stable() -> None:
    conflict = account_center._command_error(ValueError("internal SQL duplicate detail"))
    unavailable = account_center._storage_unavailable(RuntimeError("secret storage location"))

    assert conflict.status_code == 409
    assert conflict.detail["error"]["code"] == "admin_account_conflict"
    assert "SQL" not in str(conflict.detail)
    assert unavailable.status_code == 503
    assert "secret storage location" not in str(unavailable.detail)

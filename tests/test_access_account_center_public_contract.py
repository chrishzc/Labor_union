"""
File: test_access_account_center_public_contract.py
Description: 驗證帳號清冊只公開最小 typed GET 欄位。
"""

import asyncio

import pytest
from pydantic import ValidationError

from api.routes import account_center
from api.schemas.account_center import AccountEnabledRequest
from subsystems.access.authentication_session import AccountCommandReceipt, AdminPrincipal


def test_account_directory_projection_excludes_roles_and_personal_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        account_center,
        "list_account_center_users",
        lambda: [AdminPrincipal(1, "root-user", "根帳號", "system_admin", is_root=True)],
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

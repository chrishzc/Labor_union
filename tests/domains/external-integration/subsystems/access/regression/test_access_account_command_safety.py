"""
File: test_access_account_command_safety.py
Description: 驗證帳號中心 command fingerprint、同 key 回放與 payload 衝突保護。
"""

import base64
from types import SimpleNamespace

import pytest

from subsystems.access.account_receipt_fingerprints import (
    KEY_SETTING,
    AccountReceiptProtectionError,
    protect_receipt_fingerprint,
)
from subsystems.access import authentication_session as auth
from subsystems.access.authentication_session import (
    AdminPrincipal,
    _account_command_fingerprint,
    _replay_account_create,
    _replay_account_command,
)


def test_account_command_fingerprint_is_stable_and_reason_bound() -> None:
    actor = AdminPrincipal(1, "root", "Root", "system_admin", is_root=True)
    first = _account_command_fingerprint(
        actor=actor, account_id=2, expected_version=3, reason="MFA device lost", payload={"enabled": False}
    )
    assert first == _account_command_fingerprint(
        actor=actor, account_id=2, expected_version=3, reason="MFA device lost", payload={"enabled": False}
    )
    assert first != _account_command_fingerprint(
        actor=actor, account_id=2, expected_version=3, reason="Different reason", payload={"enabled": False}
    )


def test_same_key_replays_only_identical_account_command() -> None:
    actor = AdminPrincipal(1, "root", "Root", "system_admin", is_root=True)
    cursor = _ReceiptCursor()
    assert not _replay_account_command(cursor, "account-enabled", "key-1", actor, 2, 1, "reason", {"enabled": False})
    cursor.receipt = {"request_fingerprint": _account_command_fingerprint(
        actor=actor, account_id=2, expected_version=1, reason="reason", payload={"enabled": False}
    )}
    assert _replay_account_command(cursor, "account-enabled", "key-1", actor, 2, 1, "reason", {"enabled": False})
    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        _replay_account_command(cursor, "account-enabled", "key-1", actor, 2, 1, "reason", {"enabled": True})


def test_account_create_replay_returns_only_the_original_safe_account_view() -> None:
    actor = AdminPrincipal(1, "root", "Root", "system_admin", is_root=True)
    payload = {"username": "new-user", "password_hash": "sha256:masked", "display_name": "New", "linked_line_user_id": None}
    cursor = _ReceiptCursor()
    key = b"account receipt test key".ljust(32, b"0")
    legacy = _account_command_fingerprint(
        actor=actor, account_id=0, expected_version=1, reason="create", payload=payload
    )
    cursor.receipt = {
        "request_fingerprint": protect_receipt_fingerprint(key, "account-create", "key-create", legacy),
        "idempotency_key": "key-create",
        "result_snapshot": '{"id":2,"username":"new-user","display_name":"New","role":"system_admin"}',
    }
    replayed = _replay_account_create(cursor, "key-create", actor, "create", payload, protection_key=key)
    assert replayed == AdminPrincipal(2, "new-user", "New", "system_admin")
    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        _replay_account_create(
            cursor, "key-create", actor, "create", {**payload, "password_hash": "sha256:different"},
            protection_key=key,
        )


def test_password_receipt_without_key_stops_before_opening_connection(monkeypatch) -> None:
    monkeypatch.delenv(KEY_SETTING, raising=False)
    actor = AdminPrincipal(1, "root", "Root", "system_admin", is_root=True)
    def connect():
        pytest.fail("missing receipt key must not open a connection")
    with pytest.raises(AccountReceiptProtectionError, match="account_receipt_key_unavailable"):
        auth.create_account_center_user_with_receipt(
            connection_factory=connect, actor=actor, username="child", display_name="Child",
            idempotency_key="create-child", reason="", password="password-for-fixture",
        )
    with pytest.raises(AccountReceiptProtectionError, match="account_receipt_key_unavailable"):
        auth.reset_account_center_password(
            connection_factory=connect, actor=actor, account_id=2, expected_version=1,
            idempotency_key="reset-child", reason="", password="password-for-fixture",
        )


def test_verified_short_legacy_password_can_upgrade_without_changing_password() -> None:
    salt = b"0123456789abcdef"
    password = "legacy"
    digest = auth._derive_password(password, salt, auth._LEGACY_SCRYPT)
    legacy = "scrypt$16384$8$1$" + "$".join(
        base64.urlsafe_b64encode(field).decode("ascii") for field in (salt, digest)
    )
    assert auth.verify_admin_password(password, legacy)
    statements = []
    cursor = SimpleNamespace(execute=lambda statement, params: statements.append((statement, params)))
    auth._upgrade_verified_account_hash(cursor, {"id": 2, "is_root": False, "password_hash": legacy}, password)
    [(statement, (current, account_id, previous))] = statements
    assert "BINARY password_hash=%s" in statement
    assert account_id == 2 and previous == legacy and current.startswith("scrypt$131072$8$1$")
    assert auth.verify_admin_password(password, current)
    with pytest.raises(ValueError):
        auth.hash_admin_password(password)


class _ReceiptCursor:
    def __init__(self) -> None:
        self.receipt = None

    def execute(self, _statement, _parameters) -> None:
        return None

    def fetchone(self):
        return self.receipt

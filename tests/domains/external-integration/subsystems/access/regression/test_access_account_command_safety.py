"""
File: test_access_account_command_safety.py
Description: 驗證帳號中心 command fingerprint、同 key 回放與 payload 衝突保護。
"""

import pytest

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
    cursor.receipt = {
        "request_fingerprint": _account_command_fingerprint(
            actor=actor, account_id=0, expected_version=1, reason="create", payload=payload
        ),
        "result_snapshot": '{"id":2,"username":"new-user","display_name":"New","role":"system_admin"}',
    }
    replayed = _replay_account_create(cursor, "key-create", actor, "create", payload)
    assert replayed == AdminPrincipal(2, "new-user", "New", "system_admin")
    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        _replay_account_create(cursor, "key-create", actor, "create", {**payload, "display_name": "Other"})


class _ReceiptCursor:
    def __init__(self) -> None:
        self.receipt = None

    def execute(self, _statement, _parameters) -> None:
        return None

    def fetchone(self):
        return self.receipt

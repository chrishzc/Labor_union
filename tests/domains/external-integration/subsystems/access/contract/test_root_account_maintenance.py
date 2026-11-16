"""Focused transaction and terminal guard contracts for offline root maintenance."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pymysql
import pytest

from scripts import root_account_maintenance as terminal
from subsystems.access import root_account_maintenance as maintenance


def _connection():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    return connection, cursor


def _grant():
    return maintenance.VerifiedRoot(
        account_id=41, username="root-example", version=7, factor_id=48,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@pytest.mark.parametrize("previous_step", [None, 20, 21])
def test_verify_root_consumes_step_without_creating_session(monkeypatch, previous_step):
    conn, cursor = _connection()
    cursor.fetchone.side_effect = [
        {"id": 41, "username": "root-example", "password_hash": "test-hash",
         "enabled": True, "access_control_version": 7},
        {"attempt_count": 0},
        {"id": 48, "seed_ciphertext": "test-ciphertext", "encryption_key_version": "1",
         "last_successful_step": previous_step},
    ]
    monkeypatch.setattr(maintenance.auth, "verify_admin_password", lambda *_: True)
    monkeypatch.setattr(maintenance, "verify_totp", lambda **_: MagicMock(matched_step=20))
    if previous_step is None:
        grant = maintenance.verify_root(lambda: conn, MagicMock(), "root-example", "example", "123456")
        assert (grant.account_id, grant.version, grant.factor_id) == (41, 7, 48)
        cursor.execute.assert_any_call(
            "UPDATE admin_totp_factors SET last_successful_step=%s WHERE id=%s", (20, 48),
        )
    else:
        with pytest.raises(maintenance.RootMaintenanceRejected, match="驗證失敗"):
            maintenance.verify_root(lambda: conn, MagicMock(), "root-example", "example", "123456")
        assert not any("last_successful_step=%s" in call.args[0] for call in cursor.execute.call_args_list)
    conn.commit.assert_called_once()
    assert not any("admin_sessions" in call.args[0] for call in cursor.execute.call_args_list)


@pytest.mark.parametrize("failure", ["stale", "stale-factor", "audit", "unknown", None])
def test_rename_is_atomic_with_revocation_and_audit(monkeypatch, failure):
    conn, cursor = _connection()
    cursor.fetchone.side_effect = [
        {"id": 41, "enabled": True, "password_hash": "test-hash",
         "access_control_version": 9 if failure == "stale" else 7},
        {"id": 49 if failure == "stale-factor" else 48},
        None,
    ]
    audit = MagicMock(side_effect=RuntimeError("test audit failure") if failure == "audit" else None)
    monkeypatch.setattr(maintenance.auth, "_record_admin_audit_with_cursor", audit)
    if failure == "unknown":
        conn.commit.side_effect = pymysql.err.OperationalError(2013, "test connection interruption")
    grant = _grant()
    change = maintenance.RenameRoot(" New Name ")
    expected_errors = {
        "stale": maintenance.RootMaintenanceConflict,
        "stale-factor": maintenance.RootMaintenanceConflict,
        "audit": RuntimeError,
        "unknown": maintenance.RootMaintenanceCommitUnknown,
    }
    if failure:
        with pytest.raises(expected_errors[failure]):
            maintenance.apply_root_change(lambda: conn, grant, change)
    else:
        assert maintenance.apply_root_change(lambda: conn, grant, change) == ()
    if failure in {"stale", "stale-factor", "audit"}:
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
    else:
        conn.commit.assert_called_once()
        cursor.execute.assert_any_call("UPDATE admin_users SET username=%s WHERE id=%s", ("new name", 41))
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        assert any("UPDATE admin_sessions" in statement for statement in statements)
        assert any("UPDATE admin_mfa_enrollment_challenges" in statement for statement in statements)
        assert any("UPDATE admin_password_login_challenges" in statement for statement in statements)
        assert not any("UPDATE admin_totp_factors" in statement for statement in statements)
        assert audit.call_args.kwargs["details"]["operation_id"] == grant.operation_id
    with pytest.raises(maintenance.RootMaintenanceRejected, match="驗證已失效"):
        maintenance.apply_root_change(lambda: conn, grant, change)


def test_interactive_denied_auth_never_prompts_operation(monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").touch()
    (tmp_path / ".env.nas-maintenance").touch()
    settings = {"host": "localhost", "port": 33331, "database": "lu_test_example", "runtime": {}}
    monkeypatch.setattr(terminal, "_require_stopped_runtime", MagicMock())
    monkeypatch.setattr(terminal, "_target_settings", lambda _: settings)
    monkeypatch.setattr(terminal, "_connection_factory", MagicMock())
    monkeypatch.setattr(terminal, "totp_cipher_from_settings", MagicMock())
    monkeypatch.setattr(terminal, "_secret", MagicMock(return_value="example"))
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=[
        "ROOT localhost:33331/lu_test_example", "root-example",
    ]))
    monkeypatch.setattr(terminal, "verify_root", MagicMock(
        side_effect=maintenance.RootMaintenanceRejected("example rejection"),
    ))
    with pytest.raises(maintenance.RootMaintenanceRejected):
        terminal._interactive(tmp_path)
    assert "修改登入帳號" not in capsys.readouterr().out


def test_connection_preserves_pinned_ca_and_rejects_mysql_without_tls(monkeypatch):
    conn, cursor = _connection()
    cursor.fetchone.return_value = ("Ssl_cipher", "")
    mysql_connect = MagicMock(return_value=conn)
    monkeypatch.setattr(terminal.pymysql, "connect", mysql_connect)
    settings = {
        "host": "nas.example.test", "port": 3306, "database": "union_db",
        "runtime": {"DB_USER": "example", "DB_PASSWORD": "synthetic-password"},
        "tls": {"ssl": {"ca": "synthetic-pinned-ca.pem", "check_hostname": True}},
    }
    with pytest.raises(maintenance.RootMaintenanceRejected, match="未使用 TLS"):
        terminal._connection_factory(settings)()
    options = mysql_connect.call_args.kwargs
    assert options["ssl"] == settings["tls"]["ssl"]
    assert not any(key.startswith("ssl_") for key in options)
    conn.close.assert_called_once()

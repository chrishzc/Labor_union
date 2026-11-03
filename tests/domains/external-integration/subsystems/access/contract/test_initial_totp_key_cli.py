"""Initial encryption setup preserves valid keys and never writes account data."""
from unittest.mock import Mock

import pytest

from scripts import configure_initial_totp_key as cli
from subsystems.access.totp import totp_cipher_from_settings


@pytest.fixture
def entry(tmp_path, monkeypatch):
    for name in tuple(cli.os.environ):
        if name in {"APP_ENV", "DEPLOYMENT_PROFILE", cli.KEYRING, cli.ACTIVE} or name.startswith("DB_"):
            monkeypatch.delenv(name)
    path = tmp_path / ".env"
    path.write_bytes(b"# retained\r\nAPP_ENV=development\r\nDB_DATABASE=union_db\r\nACCESS_CONTROL_TOTP_KEYRING=v1:replace_with_fernet_key\r\nACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION=v1\r\n")
    factory = Mock()
    monkeypatch.setattr(cli, "_runtime", Mock(return_value=("union_db", factory)))
    empty = Mock()
    monkeypatch.setattr(cli, "_require_empty_accounts", empty)
    return path, factory, empty


def test_preview_cancel_and_initialization_persist_without_showing_key(entry, capsys):
    path, _, empty = entry
    original = path.read_bytes()
    assert cli.main([], env_file=path) == 0
    assert path.read_bytes() == original
    assert cli.main(["--apply"], env_file=path, confirm=lambda _: "cancel") == 1
    assert path.read_bytes() == original
    empty.reset_mock()
    assert cli.main(["--apply"], env_file=path, confirm=lambda _: "INITIALIZE TOTP union_db") == 0
    assert empty.call_count == 2
    settings = cli.dotenv_values(path)
    cipher = totp_cipher_from_settings(settings[cli.KEYRING], settings[cli.ACTIVE])
    encrypted = cipher.encrypt("JBSWY3DPEHPK3PXP")
    assert cipher.decrypt(encrypted) == "JBSWY3DPEHPK3PXP"
    assert path.read_bytes().startswith(b"# retained\r\nAPP_ENV=development\r\nDB_DATABASE=union_db\r\n")
    assert settings[cli.KEYRING] not in capsys.readouterr().out
    assert list(path.parent.iterdir()) == [path]
    persisted = path.read_bytes()
    empty.reset_mock()
    assert cli.main(["--apply"], env_file=path, confirm=Mock(side_effect=AssertionError)) == 0
    assert path.read_bytes() == persisted
    empty.assert_not_called()


def test_existing_accounts_or_confirmation_race_never_replace_file(entry):
    path, _, empty = entry
    original = path.read_bytes()
    empty.side_effect = cli.ConfigurationBlocked("已有帳號或驗證資料")
    confirm = Mock()
    assert cli.main(["--apply"], env_file=path, confirm=confirm) == 2
    confirm.assert_not_called()
    assert path.read_bytes() == original
    empty.side_effect = [None, cli.ConfigurationBlocked("已有帳號或驗證資料")]
    assert cli.main(["--apply"], env_file=path, confirm=lambda _: "INITIALIZE TOTP union_db") == 2
    assert path.read_bytes() == original


def test_env_override_blocks_without_echoing_value(entry, monkeypatch, capsys):
    path, _, empty = entry
    monkeypatch.setenv(cli.KEYRING, "private-override-value")
    assert cli.main(["--apply"], env_file=path) == 2
    empty.assert_not_called()
    assert "private-override-value" not in capsys.readouterr().out


def test_file_changed_during_confirmation_is_preserved(entry):
    path, _, _ = entry
    changed = b"# operator changes\n"
    def confirm(_):
        path.write_bytes(changed)
        return "INITIALIZE TOTP union_db"
    assert cli.main(["--apply"], env_file=path, confirm=confirm) == 2
    assert path.read_bytes() == changed
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("setting,value", [("APP_ENV", "production"), ("DB_HOST", "nas.example.test"), ("DB_DATABASE", "other_database")])
def test_runtime_refuses_production_remote_and_wrong_database(entry, monkeypatch, setting, value):
    from infrastructure.mysql import mysql_adapter
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(setting, value)
    monkeypatch.setattr(mysql_adapter, "_database_config_from_environment", lambda: {
        "host": cli.os.getenv("DB_HOST", "127.0.0.1"), "database": cli.os.getenv("DB_DATABASE", "union_db")})
    monkeypatch.setattr(cli, "load_dotenv", Mock())
    # Exercise the real guard, not the fixture's isolated runtime adapter.
    with pytest.raises(cli.ConfigurationBlocked):
        REAL_RUNTIME(entry[0])


REAL_RUNTIME = cli._runtime


def test_write_failure_removes_transient_secret_file(entry, monkeypatch, capsys):
    path, _, _ = entry
    original = path.read_bytes()
    monkeypatch.setattr(cli.os, "replace", Mock(side_effect=OSError("private-driver-details")))
    assert cli.main(["--apply"], env_file=path, confirm=lambda _: "INITIALIZE TOTP union_db") == 2
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]
    assert "private-driver-details" not in capsys.readouterr().out

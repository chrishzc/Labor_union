"""Protect NAS target selection and read-only readiness before runtime startup."""

from unittest.mock import Mock

import pytest

from scripts import check_runtime_database as readiness


@pytest.fixture
def database_environment(monkeypatch):
    values = {
        "APP_ENV": "development",
        "DB_HOST": "nas.test",
        "DB_PORT": "3307",
        "DB_USER": "test_app",
        "DB_PASSWORD": "synthetic-private-value",
        "DB_DATABASE": "lu_test_nas",
        "DB_SSL_MODE": "disabled",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST.", "127.0.0.1", "::1"])
def test_nas_rejects_local_target_before_connecting(database_environment, monkeypatch, host):
    monkeypatch.setenv("DB_HOST", host)
    with pytest.raises(readiness.RuntimeDatabaseBlocked, match="remote DB_HOST"):
        readiness.configured_database(require_remote=True)


def test_dry_run_uses_process_target_without_opening_connection(database_environment, monkeypatch):
    connect = Mock(side_effect=AssertionError("dry-run connected"))
    monkeypatch.setattr(readiness.pymysql, "connect", connect)
    config, database = readiness.configured_database(require_remote=True)
    assert (config.host, config.port, database) == ("nas.test", 3307, "lu_test_nas")
    assert readiness.check_database(dry_run=True, require_remote=True) == {
        "status": "configured", "connection": "not_run", "schema": "not_run",
    }
    connect.assert_not_called()


@pytest.mark.parametrize("key,value", [
    ("APP_ENV", "production"), ("DB_DATABASE", "mysql"),
    ("DB_DATABASE", "bad;database"), ("DB_PORT", "65536"), ("DB_PASSWORD", ""),
])
def test_invalid_target_stops_before_connection(database_environment, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(readiness.RuntimeDatabaseBlocked):
        readiness.configured_database(require_remote=True)


def test_schema_connection_preserves_tls_and_is_read_only(database_environment, monkeypatch):
    for key, value in {
        "DB_SSL_MODE": "verify_identity", "DB_SSL_CA": "ca.pem",
        "DB_SSL_CERT": "client.pem", "DB_SSL_KEY": "client.key",
    }.items():
        monkeypatch.setenv(key, value)
    connect = Mock()
    monkeypatch.setattr(readiness.pymysql, "connect", connect)
    config, database = readiness.configured_database(require_remote=True)
    config.connect(database)
    kwargs = connect.call_args.kwargs
    assert kwargs["host"] == "nas.test"
    assert kwargs["port"] == 3307
    assert kwargs["database"] == database
    assert kwargs["ssl"] == {
        "ca": "ca.pem", "cert": "client.pem", "key": "client.key", "check_hostname": True,
    }
    assert kwargs["init_command"] == "SET SESSION TRANSACTION READ ONLY"
    assert kwargs["connect_timeout"] == 5
    assert kwargs["read_timeout"] == kwargs["write_timeout"] == 30


@pytest.mark.parametrize("requested,connect_timeout,query_timeout", [(0.5, 0.5, 0.5), (7, 5, 7), (60, 5, 30)])
def test_schema_connection_respects_explicit_timeout_budget(database_environment, monkeypatch, requested, connect_timeout, query_timeout):
    connect = Mock()
    monkeypatch.setattr(readiness.pymysql, "connect", connect)
    config, database = readiness.configured_database(require_remote=True)
    config.connect(database, timeout_seconds=requested)
    assert connect.call_args.kwargs["connect_timeout"] == connect_timeout
    assert connect.call_args.kwargs["read_timeout"] == query_timeout
    assert connect.call_args.kwargs["write_timeout"] == query_timeout


@pytest.mark.parametrize("status", ["ready", "blocked", "preview"])
def test_pending_or_drifted_schema_blocks_runtime(database_environment, monkeypatch, status):
    monkeypatch.setattr(readiness.updater, "build_additive_preview", lambda *args: {"status": status})
    with pytest.raises(readiness.RuntimeDatabaseBlocked, match="schema is not current"):
        readiness.check_database(require_remote=True)


def test_current_schema_must_pass_canonical_gate(database_environment, monkeypatch):
    preview = {"status": "current"}
    monkeypatch.setattr(readiness.updater, "build_additive_preview", lambda *args: preview)
    gate = Mock()
    monkeypatch.setattr(readiness.updater, "require_current_database", gate)
    assert readiness.check_database(require_remote=True)["schema"] == "current"
    gate.assert_called_once_with(preview)
    gate.side_effect = RuntimeError("canonical release mismatch")
    with pytest.raises(RuntimeError, match="canonical release mismatch"):
        readiness.check_database(require_remote=True)


def test_driver_error_does_not_print_credentials(database_environment, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "check_database", Mock(side_effect=RuntimeError(
        database_environment["DB_PASSWORD"],
    )))
    monkeypatch.setattr("sys.argv", ["check_runtime_database"])
    assert readiness.main() == 1
    output = capsys.readouterr().out
    assert database_environment["DB_PASSWORD"] not in output
    assert '"status": "blocked"' in output

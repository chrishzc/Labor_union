"""NAS initialization must never turn an existing database into a reset target."""

import json
import os
from unittest.mock import Mock

import pytest

from scripts import initialize_nas_schema as nas


@pytest.fixture
def env_file(monkeypatch, tmp_path):
    for key in list(os.environ):
        if key.startswith("DB_") or key == "APP_ENV":
            monkeypatch.delenv(key)
    path = tmp_path / ".env"
    path.write_text(
        'APP_ENV=development\nDB_HOST=nas.test\nDB_PORT=3307\nDB_DATABASE=union_db\n'
        'DB_USER=union_app\nDB_PASSWORD="synthetic # password"\n', encoding="utf-8",
    )
    return path


def test_loads_quoted_env_credentials_and_tls(env_file):
    with env_file.open("a", encoding="utf-8") as handle:
        handle.write("DB_SSL_MODE=verify_identity\nDB_SSL_CA=ca.pem\nDB_SSL_CERT=client.pem\nDB_SSL_KEY=client.key\n")
    config = nas.load_configuration(env_file)
    assert config["database"] == "union_db" and config["port"] == 3307
    assert config["password"] == "synthetic # password"
    assert config["ssl"]["check_hostname"] is True


@pytest.mark.parametrize("before,after", [
    ("development", "production"), ("union_db", "another_db"),
    ("nas.test", "127.0.0.2"), ("nas.test", "LOCALHOST."),
    ("3307", "65536"), ("nas.test", "::1"),
])
def test_refuses_unapproved_target(env_file, before, after):
    env_file.write_text(env_file.read_text(encoding="utf-8").replace(before, after), encoding="utf-8")
    with pytest.raises(nas.InitializationBlocked):
        nas.load_configuration(env_file)


def test_conflicting_process_target_is_not_silently_used(env_file, monkeypatch):
    monkeypatch.setenv("DB_HOST", "other.test")
    with pytest.raises(nas.InitializationBlocked, match="DB_HOST conflicts"):
        nas.load_configuration(env_file)


def test_process_override_of_an_omitted_default_is_rejected(env_file, monkeypatch):
    env_file.write_text(env_file.read_text(encoding="utf-8").replace("DB_PORT=3307\n", ""), encoding="utf-8")
    monkeypatch.setenv("DB_PORT", "3307")
    with pytest.raises(nas.InitializationBlocked, match="DB_PORT conflicts"):
        nas.load_configuration(env_file)


def test_canonical_plan_preserves_order_and_removes_database_controls():
    plan = nas.schema_plan()
    assembly = nas.load_schema_assembly()
    assert plan["schema_parts"] == [p.name for p in assembly.active_artifact_paths]
    assert all(not nas.DATABASE_CONTROL.match(s["sql"]) for s in plan["steps"])
    artifacts = list(dict.fromkeys(s["artifact"] for s in plan["steps"]))
    assert artifacts == [assembly.base_schema_path.name, *plan["schema_parts"]]
    assert any(s["sql"].upper().startswith("INSERT") for s in plan["steps"])


def test_corrupt_manifest_stops_before_any_connection(monkeypatch):
    monkeypatch.setattr(nas, "verify_manifest", lambda _: ["digest mismatch"])
    connect = Mock()
    monkeypatch.setattr(nas.pymysql, "connect", connect)
    with pytest.raises(nas.InitializationBlocked, match="manifest verification"):
        nas.schema_plan()
    connect.assert_not_called()


class Connection:
    def __init__(self, *, occupied=None, lock=1, fail_insert=False):
        self.occupied, self.lock, self.fail_insert = occupied, lock, fail_insert
        self.statements = []
        self.row = None
        self.closed = False

    def cursor(self, *args):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql)
        self.row = None
        if "GET_LOCK" in sql:
            self.row = {"acquired": self.lock}
        elif "SELECT DATABASE()" in sql:
            self.row = {"database_name": "union_db", "server": "synthetic-nas"}
        elif self.occupied and "information_schema." + self.occupied in sql:
            self.row = {"1": 1}
        elif self.fail_insert and sql.startswith("INSERT"):
            raise RuntimeError("synthetic-secret-provider-message")

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True


@pytest.fixture
def execution(monkeypatch, tmp_path):
    config = {"host": "nas.test", "port": 3307, "database": "union_db"}
    plan = {
        "assembly_id": "synthetic", "release_id": "synthetic", "expected": {},
        "steps": [
            {"artifact": "synthetic.sql", "ordinal": 1, "sql": "CREATE TABLE sentinel(id INT)"},
            {"artifact": "synthetic.sql", "ordinal": 2, "sql": "INSERT INTO sentinel VALUES (1)"},
        ],
    }
    monkeypatch.setattr(nas, "verify_database_objects", lambda *_: [])
    monkeypatch.setattr(nas, "_verify_current", lambda _: None)
    return config, plan, tmp_path


@pytest.mark.parametrize("occupied", ["tables", "routines", "events"])
def test_existing_objects_stop_without_schema_writes(execution, monkeypatch, occupied):
    connection = Connection(occupied=occupied)
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    config, plan, root = execution
    with pytest.raises(nas.InitializationBlocked, match="not empty"):
        nas.initialize(config, plan, apply=True, receipt_root=root)
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in connection.statements)
    assert connection.closed
    assert not list(root.iterdir())


def test_lock_conflict_stops_before_schema_writes(execution, monkeypatch):
    connection = Connection(lock=0)
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    with pytest.raises(nas.InitializationBlocked, match="holds the database lock"):
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    assert len(connection.statements) == 1 and connection.closed


def test_readonly_preflight_writes_nothing(execution, monkeypatch):
    connection = Connection()
    connect = Mock(return_value=connection)
    monkeypatch.setattr(nas.pymysql, "connect", connect)
    assert nas.initialize(*execution[:2], receipt_root=execution[2])["status"] == "ready"
    assert connect.call_args.kwargs["init_command"] == "SET SESSION TRANSACTION READ ONLY"
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in connection.statements)
    assert not list(execution[2].iterdir())


def test_failure_keeps_partial_journal_without_provider_detail(execution, monkeypatch):
    connection = Connection(fail_insert=True)
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    with pytest.raises(nas.InitializationBlocked, match="DDL may be committed") as error:
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    journal = next(execution[2].glob("*/journal.jsonl")).read_text(encoding="utf-8")
    assert "synthetic-secret-provider-message" not in str(error.value) + journal
    assert "CREATE TABLE sentinel" not in journal
    events = [json.loads(line) for line in journal.splitlines()]
    assert [e["event"] for e in events] == ["started", "prepared", "applied", "prepared", "failed_partial"]
    assert events[-1]["completed_statements"] == 1 and connection.closed


def test_success_requires_descriptor_verification(execution, monkeypatch):
    connection = Connection()
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    gate = Mock(side_effect=RuntimeError("descriptor mismatch"))
    monkeypatch.setattr(nas, "_verify_current", gate)
    with pytest.raises(nas.InitializationBlocked, match="DDL may be committed"):
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    gate.assert_called_once()


def test_cli_dry_run_does_not_connect(env_file, monkeypatch, capsys):
    config = nas.load_configuration(env_file)
    monkeypatch.setattr(nas, "load_configuration", lambda: config)
    connect = Mock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(nas.pymysql, "connect", connect)
    assert nas.main(["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["connection"] == "not_run"
    connect.assert_not_called()


def test_cli_sanitizes_connection_errors(monkeypatch, capsys):
    monkeypatch.setattr(nas, "load_configuration", Mock(side_effect=ValueError("synthetic-secret")))
    assert nas.main([]) == 1
    assert "synthetic-secret" not in capsys.readouterr().out

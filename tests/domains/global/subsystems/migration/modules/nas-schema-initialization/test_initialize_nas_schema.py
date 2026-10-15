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


def test_compact_plan_creates_final_objects_without_historical_upgrades():
    plan = nas.schema_plan()
    from scripts.compact_fresh_schema import MANIFEST_PATH, SQL_PATH
    from scripts.fresh_schema_policy import retired_fresh_tables
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert plan["schema_parts"] == [SQL_PATH.name]
    assert all(not nas.DATABASE_CONTROL.match(s["sql"]) for s in plan["steps"])
    assert not any(s["sql"].upper().startswith(("ALTER ", "DROP ", "PREPARE ", "EXECUTE ")) for s in plan["steps"])
    assert not plan["expected"]["tables"] & retired_fresh_tables()
    assert "government_payers" in plan["expected"]["tables"]
    assert len(plan["steps"]) == manifest["statement_count"]
    assert any(s["sql"].upper().startswith("INSERT") for s in plan["steps"])


def test_corrupt_manifest_stops_before_any_connection(monkeypatch):
    monkeypatch.setattr(nas, "verify_manifest", lambda _: ["digest mismatch"])
    connect = Mock()
    monkeypatch.setattr(nas.pymysql, "connect", connect)
    with pytest.raises(nas.InitializationBlocked, match="manifest verification"):
        nas.source_schema_plan()
    connect.assert_not_called()


@pytest.mark.parametrize("changed", ["sql", "bindings"])
def test_stale_compact_asset_is_rejected_before_connection(tmp_path, monkeypatch, changed):
    from scripts import compact_fresh_schema as compact
    manifest = json.loads(compact.MANIFEST_PATH.read_text(encoding="utf-8"))
    sql = tmp_path / "current.sql"
    sql.write_bytes(compact.SQL_PATH.read_bytes())
    if changed == "sql":
        sql.write_text(sql.read_text(encoding="utf-8") + "\n-- drift\n", encoding="utf-8")
    else:
        manifest["source_bindings"]["retirement_policy_sha256"] = "0" * 64
    manifest_path = tmp_path / "current.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(compact, "SQL_PATH", sql)
    monkeypatch.setattr(compact, "MANIFEST_PATH", manifest_path)
    connect = Mock()
    monkeypatch.setattr(nas.pymysql, "connect", connect)
    with pytest.raises(nas.InitializationBlocked, match="regenerate"):
        nas.schema_plan()
    connect.assert_not_called()


class Connection:
    def __init__(self, *, occupied=None, lock=1, fail_insert=False,
                 version="8.0.46", read_only=0, engine="DEFAULT", grants=None):
        self.occupied, self.lock, self.fail_insert = occupied, lock, fail_insert
        self.version, self.read_only, self.engine = version, read_only, engine
        self.grants = grants if grants is not None else ["GRANT ALL PRIVILEGES ON *.* TO `synthetic`@`%`"]
        self.statements = []
        self.row = None
        self.rows = []
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
        self.rows = []
        if "GET_LOCK" in sql:
            self.row = {"acquired": self.lock}
        elif "SELECT DATABASE()" in sql:
            self.row = {"database_name": "union_db", "server": "synthetic-nas"}
        elif "SELECT VERSION()" in sql:
            self.row = {"mysql_version": self.version, "version_comment": "MySQL Community Server"}
        elif "@@read_only" in sql:
            self.row = {"read_only": self.read_only, "super_read_only": 0, "log_bin": 1,
                        "trust_function_creators": 0, "partial_revokes": 0, "active_roles": "NONE"}
        elif "information_schema.engines" in sql:
            self.row = {"support": self.engine}
        elif sql.startswith("SHOW GRANTS"):
            self.rows = [{"grant": grant} for grant in self.grants]
        elif self.occupied and "information_schema." + self.occupied in sql:
            self.row = {"1": 1}
        elif self.fail_insert and sql.startswith("INSERT"):
            raise RuntimeError("synthetic-secret-provider-message")

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

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
    monkeypatch.setattr(nas, "_preflight_metadata", lambda _: None)
    return config, plan, tmp_path


@pytest.mark.parametrize("options,reason", [
    ({"version": "5.7.44"}, "版本不相容"),
    ({"version": "10.11.6-MariaDB"}, "版本不相容"),
    ({"read_only": 1}, "唯讀模式"),
    ({"engine": "NO"}, "InnoDB"),
    ({"grants": ["GRANT CREATE, SELECT, INSERT, REFERENCES ON `union_db`.* TO `synthetic`@`%`"]}, "缺少資料庫權限 TRIGGER"),
    ({"grants": ["GRANT ALL PRIVILEGES ON `union_db`.* TO `synthetic`@`%`"]}, "log_bin_trust_function_creators=0"),
])
def test_server_precheck_failure_stops_before_any_schema_write(execution, monkeypatch, options, reason):
    connection = Connection(**options)
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    config, plan, root = execution
    plan["expected"] = {"triggers": {"synthetic_trigger"}}
    with pytest.raises(nas.InitializationBlocked, match=reason):
        nas.initialize(config, plan, apply=True, receipt_root=root)
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER", "SET GLOBAL")) for s in connection.statements)
    assert not list(root.iterdir()) and connection.closed


def test_metadata_precheck_timeout_stops_before_writes_and_shows_reason(execution, monkeypatch):
    connection = Connection()
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    monkeypatch.setattr(nas, "_preflight_metadata", Mock(side_effect=nas.pymysql.err.OperationalError(2013, "synthetic-private-detail")))
    with pytest.raises(nas.InitializationBlocked, match="逾時或連線中斷") as error:
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    assert "synthetic-private-detail" not in str(error.value)
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in connection.statements)
    assert not list(execution[2].iterdir())


def test_database_changed_during_preflight_is_rechecked_before_writing(execution, monkeypatch):
    connection = Connection()
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    monkeypatch.setattr(nas, "_preflight_metadata", lambda _: setattr(connection, "occupied", "tables"))
    with pytest.raises(nas.InitializationBlocked, match="not empty"):
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in connection.statements)
    assert not list(execution[2].iterdir())


def test_preflight_permissions_are_checked_again_after_confirmation(execution, monkeypatch):
    admitted = Connection()
    refused = Connection(grants=["GRANT SELECT ON `union_db`.* TO `synthetic`@`%`"])
    monkeypatch.setattr(nas.pymysql, "connect", Mock(side_effect=[admitted, refused]))
    assert nas.initialize(*execution[:2], receipt_root=execution[2])["preflight"] == "passed"
    with pytest.raises(nas.InitializationBlocked, match="缺少資料庫權限"):
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in refused.statements)


def test_grant_scope_wildcards_revokes_and_roles_do_not_expand_authority():
    required = {"CREATE", "SELECT", "TRIGGER"}
    grants = ["GRANT CREATE, SELECT, TRIGGER ON *.* TO `synthetic`@`%`",
              "REVOKE TRIGGER ON `union_db`.* FROM `synthetic`@`%`"]
    assert nas._effective_privileges(grants, "union_db", True, required)[0] == {"CREATE", "SELECT"}
    grants.append("GRANT TRIGGER ON `union_db`.* TO `synthetic`@`%`")
    assert nas._effective_privileges(grants, "union_db", True, required)[0] == required
    assert nas._schema_scope_matches("`union\\_db`.*", "union_db", False)
    assert not nas._schema_scope_matches("`union\\_db`.*", "unionXdb", False)
    assert not nas._schema_scope_matches("`other`.*", "union_db", False)
    assert not nas._schema_scope_matches("`union%`.*", "union_db", True)
    assert nas._active_role_clause("`app``role`@`%`,`reader`@`localhost`") == " USING `app``role`@`%`,`reader`@`localhost`"
    with pytest.raises(nas.InitializationBlocked):
        nas._active_role_clause("`reader`@`%`; DROP DATABASE union_db")


def test_replace_view_accepts_drop_limited_to_that_view(execution, monkeypatch):
    connection = Connection(grants=[
        "GRANT CREATE,SELECT,INSERT,REFERENCES,CREATE VIEW,SHOW VIEW ON `union_db`.* TO `synthetic`@`%`",
        "GRANT DROP ON `union_db`.`v_order_details` TO `synthetic`@`%`",
    ])
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    execution[1]["expected"] = {"views": {"v_order_details"}}
    assert nas.initialize(*execution[:2], receipt_root=execution[2])["preflight"] == "passed"
    connection.grants[-1] = "GRANT DROP ON `union_db`.`unrelated_view` TO `synthetic`@`%`"
    with pytest.raises(nas.InitializationBlocked, match="DROP"):
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in connection.statements)


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


@pytest.mark.parametrize("current", [True, False])
def test_existing_schema_is_diagnosed_in_the_same_entry_without_writes(execution, monkeypatch, current):
    connection = Connection(occupied="tables")
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    gate = Mock(side_effect=None if current else nas.pymysql.err.OperationalError(2013, "synthetic-private-detail"))
    monkeypatch.setattr(nas, "_verify_current", gate)
    with pytest.raises(nas.InitializationBlocked) as error:
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    gate.assert_called_once()
    assert ("現有結構已通過完整版本查核" if current else "現有結構尚未通過完整版本查核") in str(error.value)
    assert "synthetic-private-detail" not in str(error.value)
    assert not any(s.startswith(("CREATE", "INSERT", "DROP", "ALTER")) for s in connection.statements)
    assert not list(execution[2].iterdir())


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
    assert "Phase: statements; completed: 1/2" in str(error.value)
    assert "All schema statements completed" not in str(error.value)
    assert "CREATE TABLE sentinel" not in journal
    events = [json.loads(line) for line in journal.splitlines()]
    assert [e["event"] for e in events] == ["started", "prepared", "applied", "prepared", "failed_partial"]
    assert events[-1]["completed_statements"] == 1 and connection.closed


def test_success_requires_descriptor_verification(execution, monkeypatch):
    connection = Connection()
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    gate = Mock(side_effect=RuntimeError("descriptor mismatch"))
    monkeypatch.setattr(nas, "_verify_current", gate)
    with pytest.raises(nas.InitializationBlocked, match="DDL may be committed") as error:
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    gate.assert_called_once()
    assert "All schema statements completed, but verification failed" in str(error.value)
    assert "Phase: current_schema; completed: 2/2" in str(error.value)
    assert "descriptor mismatch" not in str(error.value)


def test_verification_timeout_reports_numeric_error_without_driver_text(execution, monkeypatch):
    connection = Connection()
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: connection)
    monkeypatch.setattr(nas, "_verify_current", Mock(side_effect=nas.pymysql.err.OperationalError(2013, "synthetic-private-provider-detail")))
    with pytest.raises(nas.InitializationBlocked) as error:
        nas.initialize(*execution[:2], apply=True, receipt_root=execution[2])
    assert "MySQL errno: 2013" in str(error.value)
    assert "completed: 2/2" in str(error.value)
    assert "synthetic-private-provider-detail" not in str(error.value)


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

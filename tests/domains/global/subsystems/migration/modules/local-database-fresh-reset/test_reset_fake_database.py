"""
檔案：test_reset_fake_database.py
說明：驗證 MySQL schema reset 的目標資料庫、環境、遠端主機授權與 root 認證保留契約。
"""

from pathlib import Path

import pytest

from scripts import reset_fake_database as resetter


def _config(database="lu_test_current", host="127.0.0.1"):
    return {"host": host, "port": 3306, "database": database, "user": "tester", "password": "x"}


def _assembly(tmp_path: Path):
    base = tmp_path / "schema.sql"
    base.write_text(
        "CREATE TABLE current_table (id INT PRIMARY KEY);",
        encoding="utf-8",
    )
    return type("Assembly", (), {
        "assembly_id": "current-test",
        "base_schema_path": base,
        "active_artifact_paths": (),
    })()


def test_validate_target_accepts_explicit_operator_or_disposable_target():
    assert resetter.validate_target(
        _config("union_db"), {"APP_ENV": "development"}, "union_db"
    ) == "union_db"
    with pytest.raises(resetter.FakeDatabaseResetError, match="exactly match"):
        resetter.validate_target(_config("lu_test_a"), {"APP_ENV": "development"}, "lu_test_b")
    assert resetter.validate_target(
        _config("lu_test_a"), {"APP_ENV": "development"}, "lu_test_a"
    ) == "lu_test_a"


def test_validate_target_rejects_remote_and_production():
    with pytest.raises(resetter.FakeDatabaseResetError, match="host"):
        resetter.validate_target(_config(host="db.example.com"), {"APP_ENV": "development"}, "lu_test_current")
    with pytest.raises(resetter.FakeDatabaseResetError, match="production"):
        resetter.validate_target(_config(), {"APP_ENV": "production"}, "lu_test_current")
    with pytest.raises(resetter.FakeDatabaseResetError, match="production"):
        resetter.validate_target(
            _config(), {"APP_ENV": "production"}, "lu_test_current", operator_reset=True
        )
    with pytest.raises(resetter.FakeDatabaseResetError, match="local MySQL host"):
        resetter.validate_target(
            _config("union_db", host="db.example.com"), {"APP_ENV": "production"},
            "union_db", operator_reset=True,
        )


def test_production_operator_launcher_requires_exact_confirmation(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(resetter, "DB_CONFIG", _config("union_db"))
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    monkeypatch.setenv("APP_ENV", "production")
    plan = tmp_path / "plan.json"
    args = ["--operator-reset", "--target-database", "union_db", "--plan-receipt", str(plan)]
    monkeypatch.setattr(resetter, "_check_connected_identity", lambda *_a, **_k: pytest.fail("must not connect"))

    assert resetter.main([*args, "--dry-run"]) == 0
    assert '"side_effects": "none"' in capsys.readouterr().out
    assert plan.is_file()

    assert resetter.main([*args, "--apply", "--confirm-apply", "reset"]) == 2
    assert "--confirm-apply must exactly equal 'RESET'" in capsys.readouterr().out


def test_preview_uses_canonical_assembly_without_connecting(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    result = resetter.reset(
        target_database="lu_test_current",
        config=_config(),
        environment={"APP_ENV": "development"},
        connection_factory=lambda **_: pytest.fail("preview must not connect"),
    )
    assert result["status"] == "preview"
    assert result["side_effects"] == "none"
    assert result["business_fixture_rows_loaded"] == 0
    assert result["plan_fingerprint"]


def test_union_db_requires_explicit_operator_route(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(
        resetter,
        "_canonical_bootstrap_contract",
        lambda: (assembly, {"release_id": "r1"}),
    )
    with pytest.raises(
        resetter.FakeDatabaseResetError, match="operator reset"
    ):
        resetter.reset(
            target_database="union_db",
            config=_config("union_db"),
            environment={"APP_ENV": "development"},
        )


@pytest.mark.parametrize("app_env", ["development", "production"])
def test_operator_reset_uses_plan_and_preserves_root_before_drop(
    monkeypatch, tmp_path, app_env
):
    assembly = _assembly(tmp_path)
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "terminal.json"
    config = _config("union_db")
    calls = []
    monkeypatch.setattr(resetter, "capture_root_authentication", lambda *_a, **_k: calls.append("capture") or {})
    monkeypatch.setattr(resetter, "save_root_authentication", lambda *_a, **_k: calls.append("durable_backup") or {"status": "encrypted_and_verified"})
    monkeypatch.setattr(resetter, "restore_root_authentication", lambda *_a, **_k: calls.append("restore_and_compare") or {"status": "preserved"})
    monkeypatch.setattr(
        resetter,
        "_canonical_bootstrap_contract",
        lambda: (assembly, {"release_id": "r1"}),
    )
    monkeypatch.setattr(
        resetter,
        "_check_connected_identity",
        lambda *_args, **_kwargs: {
            "database": None,
            "server": "local",
            "port": 3306,
        },
    )
    monkeypatch.setattr(
        resetter,
        "rebuild_schema",
        lambda *_args, **_kwargs: calls.append("drop_rebuild") or {"schema_postcheck": "pass"},
    )
    resetter.reset(
        operator_reset=True,
        target_database="union_db",
        plan_receipt=plan_path,
        config=config,
        environment={"APP_ENV": app_env},
    )
    result = resetter.reset(
        apply=True,
        operator_reset=True,
        confirm_apply="RESET",
        target_database="union_db",
        plan_receipt=plan_path,
        receipt_path=receipt_path,
        config=config,
        environment={"APP_ENV": app_env},
    )
    assert result["status"] == "completed"
    assert result["backup_receipt"]["policy"] == "business_discard_root_auth_preserved"
    assert result["root_authentication"]["status"] == "preserved"
    assert calls == ["capture", "durable_backup", "drop_rebuild", "restore_and_compare"]
    assert receipt_path.is_file()


def test_operator_backup_failure_never_drops_database(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    monkeypatch.setattr(resetter, "_check_connected_identity", lambda *_a, **_k: {})
    monkeypatch.setattr(resetter, "capture_root_authentication", lambda *_a, **_k: {})
    def fail_backup(*_args):
        raise resetter.RootPreservationError("backup failed")
    monkeypatch.setattr(resetter, "save_root_authentication", fail_backup)
    monkeypatch.setattr(resetter, "rebuild_schema", lambda *_a, **_k: pytest.fail("must not DROP"))
    config = _config("union_db")
    plan = tmp_path / "plan.json"
    resetter.reset(operator_reset=True, target_database="union_db", config=config,
                   environment={"APP_ENV": "development"}, plan_receipt=plan)
    with pytest.raises(resetter.FakeDatabaseResetError, match="backup failed"):
        resetter.reset(apply=True, operator_reset=True, confirm_apply="RESET", target_database="union_db",
                       config=config, environment={"APP_ENV": "development"}, plan_receipt=plan,
                       receipt_path=tmp_path / "receipt.json")


def test_connected_identity_query_uses_mapping_rows():
    captured = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return None

        def fetchone(self):
            return {
                "database_name": None,
                "server": "local",
                "port": 3306,
            }

    class Connection:
        def cursor(self, cursorclass):
            captured["cursorclass"] = cursorclass
            return Cursor()

        def close(self):
            return None

    identity = resetter._check_connected_identity(
        _config("lu_test_identity"),
        "lu_test_identity",
        lambda **_kwargs: Connection(),
    )

    assert captured["cursorclass"] is resetter.pymysql.cursors.DictCursor
    assert identity == {"database": None, "server": "local", "port": 3306}


def test_apply_requires_plan_backup_and_exact_confirmation_before_connect(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    with pytest.raises(resetter.FakeDatabaseResetError, match="exact"):
        resetter.reset(
            apply=True,
            target_database="lu_test_current",
            confirm_database="wrong",
            config=_config(),
            environment={"APP_ENV": "development"},
            connection_factory=lambda **_: pytest.fail("must not connect"),
        )


def test_backup_receipt_requires_mysql_dump_and_exact_target(tmp_path):
    path = tmp_path / "backup.sql"
    path.write_text("-- MySQL dump\nUSE `lu_test_current`;\n", encoding="utf-8")
    receipt = resetter._validate_backup(path, "lu_test_current")
    assert receipt["target_database"] == "lu_test_current"
    with pytest.raises(resetter.FakeDatabaseResetError, match="identify"):
        resetter._validate_backup(path, "lu_test_other")


def test_rebuild_executes_target_not_default_database(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    executed = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, statement, _parameters=None): executed.append(statement)

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): self.committed = True
        def rollback(self): self.rolled_back = True
        def close(self): self.closed = True

    monkeypatch.setattr(resetter, "verify_database_objects", lambda *_args: [])
    report = resetter.rebuild_schema(
        assembly, {"expected": {}}, "lu_test_current", config=_config(), connection_factory=lambda **_: Connection()
    )
    assert "USE `lu_test_current`" in executed
    assert all("union_db" not in statement for statement in executed)
    assert report["schema_postcheck"] == "pass"


def test_terminal_receipt_verify_and_replay_are_read_only(monkeypatch, tmp_path):
    path = tmp_path / "terminal.json"
    path.write_text('{"receipt_status":"committed","target_database":"lu_test_current"}\n', encoding="utf-8")
    for mode, expected in (("verify", "verified"), ("replay", "replayed")):
        result = resetter.reset(
            target_database="lu_test_current",
            config=_config(),
            environment={"APP_ENV": "development"},
            receipt_path=path,
            **{mode: True},
        )
        assert result["status"] == expected


def test_changed_schema_invalidates_reset_plan_before_connecting(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    plan = tmp_path / "plan.json"
    settings = dict(target_database="lu_test_current", config=_config(),
                    environment={"APP_ENV": "development"}, plan_receipt=plan,
                    connection_factory=lambda **_: pytest.fail("stale plan must not connect or DROP"))
    resetter.reset(**settings)
    assembly.base_schema_path.write_text("CREATE TABLE changed_table(id INT);", encoding="utf-8")
    with pytest.raises(resetter.FakeDatabaseResetError, match="plan drift"):
        resetter.reset(**settings, apply=True, confirm_apply="APPLY lu_test_current",
                       receipt_path=tmp_path / "terminal.json")


def test_real_reset_preview_uses_compact_baseline_without_connecting():
    from scripts.compact_fresh_schema import SQL_PATH, load_compact_plan
    expected = load_compact_plan()
    assembly, manifest = resetter._canonical_bootstrap_contract()
    assert assembly.base_schema_path == SQL_PATH and not assembly.active_artifact_paths
    assert manifest["expected"] == expected["expected"]
    result = resetter.reset(target_database="lu_test_current", config=_config(),
                            environment={"APP_ENV": "development"},
                            connection_factory=lambda **_: pytest.fail("preview must not connect"))
    assert result["assembly_id"] == expected["assembly_id"]
    assert result["base_schema_sha256"] == resetter._sha256_bytes(SQL_PATH)
    assert result["schema_parts"] == []


def test_validate_target_supports_nas_operator_and_remote_host():
    nas_db = "lu_nas_restore_20261106094646_f005ea7e"
    # 支援 lu_nas_* 作為 operator target
    assert resetter.validate_target(
        _config(nas_db), {"APP_ENV": "development"}, nas_db, operator_reset=True
    ) == nas_db

    # 未指定 target_database 時，自動推導當前 DB_DATABASE
    assert resetter.validate_target(
        _config(nas_db), {"APP_ENV": "development"}, operator_reset=True
    ) == nas_db

    # 開發環境下，allow_remote_host=True 或環境變數放寬遠端 host
    remote_host = "192.168.1.50"
    assert resetter.validate_target(
        _config(nas_db, host=remote_host),
        {"APP_ENV": "development"},
        nas_db,
        operator_reset=True,
        allow_remote_host=True,
    ) == nas_db

    assert resetter.validate_target(
        _config(nas_db, host=remote_host),
        {"APP_ENV": "development", "ALLOW_REMOTE_RESET": "1"},
        nas_db,
        operator_reset=True,
    ) == nas_db

    # 未開啟 allow_remote_host 時，開發環境仍拒絕遠端 host
    with pytest.raises(resetter.FakeDatabaseResetError, match="local MySQL host"):
        resetter.validate_target(
            _config(nas_db, host=remote_host),
            {"APP_ENV": "development"},
            nas_db,
            operator_reset=True,
        )

    # production 模式下支援 lu_nas_* operator reset（含本機或明確授權的遠端 host）
    assert resetter.validate_target(
        _config(nas_db),
        {"APP_ENV": "production"},
        nas_db,
        operator_reset=True,
    ) == nas_db

    assert resetter.validate_target(
        _config(nas_db, host=remote_host),
        {"APP_ENV": "production"},
        nas_db,
        operator_reset=True,
        allow_remote_host=True,
    ) == nas_db

    # production 模式下未傳入 allow_remote_host 時仍拒絕遠端 host
    with pytest.raises(resetter.FakeDatabaseResetError, match="local MySQL host"):
        resetter.validate_target(
            _config(nas_db, host=remote_host),
            {"APP_ENV": "production"},
            nas_db,
            operator_reset=True,
        )


def test_operator_reset_supports_nas_restore_database(monkeypatch, tmp_path):
    nas_db = "lu_nas_restore_20261106094646_f005ea7e"
    assembly = _assembly(tmp_path)
    plan_path = tmp_path / "plan.json"
    receipt_path = tmp_path / "terminal.json"
    config = _config(nas_db, host="192.168.1.100")
    calls = []
    monkeypatch.setattr(resetter, "capture_root_authentication", lambda *_a, **_k: calls.append("capture") or {})
    monkeypatch.setattr(resetter, "save_root_authentication", lambda *_a, **_k: calls.append("durable_backup") or {"status": "encrypted_and_verified"})
    monkeypatch.setattr(resetter, "restore_root_authentication", lambda *_a, **_k: calls.append("restore_and_compare") or {"status": "preserved"})
    monkeypatch.setattr(
        resetter,
        "_canonical_bootstrap_contract",
        lambda: (assembly, {"release_id": "r1"}),
    )
    monkeypatch.setattr(
        resetter,
        "_check_connected_identity",
        lambda *_args, **_kwargs: {
            "database": None,
            "server": "nas-server",
            "port": 3306,
        },
    )
    monkeypatch.setattr(
        resetter,
        "rebuild_schema",
        lambda *_args, **_kwargs: calls.append("drop_rebuild") or {"schema_postcheck": "pass"},
    )
    # Plan
    resetter.reset(
        operator_reset=True,
        target_database=nas_db,
        allow_remote_host=True,
        plan_receipt=plan_path,
        config=config,
        environment={"APP_ENV": "development"},
    )
    # Apply
    result = resetter.reset(
        apply=True,
        operator_reset=True,
        allow_remote_host=True,
        confirm_apply="RESET",
        confirm_database=nas_db,
        target_database=nas_db,
        plan_receipt=plan_path,
        receipt_path=receipt_path,
        config=config,
        environment={"APP_ENV": "development"},
    )
    assert result["status"] == "completed"
    assert result["target_database"] == nas_db
    assert calls == ["capture", "durable_backup", "drop_rebuild", "restore_and_compare"]
    assert receipt_path.is_file()


def test_main_cli_supports_inferred_target_database_and_remote_host(monkeypatch, tmp_path, capsys):
    nas_db = "lu_nas_restore_demo"
    monkeypatch.setattr(resetter, "DB_CONFIG", _config(nas_db, host="10.0.0.5"))
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    monkeypatch.setenv("APP_ENV", "development")
    plan = tmp_path / "plan.json"
    # CLI 未帶 --target-database，但帶 --allow-remote-host 與 --operator-reset
    args = ["--operator-reset", "--allow-remote-host", "--plan-receipt", str(plan), "--dry-run"]
    monkeypatch.setattr(resetter, "_check_connected_identity", lambda *_a, **_k: pytest.fail("must not connect"))

    assert resetter.main(args) == 0
    assert '"target_database": "lu_nas_restore_demo"' in capsys.readouterr().out
    assert plan.is_file()

from pathlib import Path

import pytest

from scripts import reset_fake_database as resetter


def _config(database="lu_test_current", host="127.0.0.1"):
    return {"host": host, "port": 3306, "database": database, "user": "tester", "password": "x"}


def _assembly(tmp_path: Path):
    base = tmp_path / "schema.sql"
    part = tmp_path / "1012_current.sql"
    base.write_text(
        "DROP DATABASE IF EXISTS union_db; CREATE DATABASE union_db; USE union_db;",
        encoding="utf-8",
    )
    part.write_text("CREATE TABLE current_table (id INT PRIMARY KEY);", encoding="utf-8")
    return type("Assembly", (), {
        "assembly_id": "current-test",
        "base_schema_path": base,
        "active_artifact_paths": (part,),
    })()


def test_validate_target_requires_explicit_allowlisted_disposable_target():
    with pytest.raises(resetter.FakeDatabaseResetError, match="lu_test"):
        resetter.validate_target(_config("union_db"), {"APP_ENV": "development"}, "union_db")
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


def test_preview_uses_canonical_assembly_without_connecting(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    monkeypatch.setattr(resetter, "expected_database_objects", lambda _manifest: {})
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


def test_apply_requires_plan_backup_and_exact_confirmation_before_connect(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "_canonical_bootstrap_contract", lambda: (assembly, {"release_id": "r1"}))
    monkeypatch.setattr(resetter, "expected_database_objects", lambda _manifest: {})
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

    monkeypatch.setattr(resetter, "load_schema_paths", lambda _cursor, paths: [p.name for p in paths])
    monkeypatch.setattr(resetter, "expected_database_objects", lambda _manifest: {})
    monkeypatch.setattr(resetter, "verify_database_objects", lambda *_args: [])
    report = resetter.rebuild_schema(
        assembly, {}, "lu_test_current", config=_config(), connection_factory=lambda **_: Connection()
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

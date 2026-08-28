from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import reset_fake_database as resetter


def _assembly(tmp_path: Path):
    base = tmp_path / "schema.sql"
    part = tmp_path / "1012_current.sql"
    base.write_text(
        "DROP DATABASE IF EXISTS union_db; CREATE DATABASE union_db; USE union_db;",
        encoding="utf-8",
    )
    part.write_text("CREATE TABLE current_table (id INT PRIMARY KEY);", encoding="utf-8")
    return SimpleNamespace(
        assembly_id="current-test",
        base_schema_path=base,
        active_artifact_paths=(part,),
    )


def test_preview_uses_canonical_assembly_without_connecting(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "DB_CONFIG", {
        "host": "127.0.0.1", "port": 3306, "database": "union_db"
    })
    monkeypatch.setattr(
        resetter, "_canonical_bootstrap_contract", lambda: (assembly, {})
    )
    monkeypatch.setenv("APP_ENV", "development")

    def refused_connection(**_kwargs):
        raise AssertionError("preview must not connect")

    result = resetter.reset(connection_factory=refused_connection)

    assert result["status"] == "preview"
    assert result["side_effects"] == "none"
    assert result["mode"] == "canonical_empty_database"
    assert result["terminal_schema_artifact"] == "1012_current.sql"
    assert result["business_fixture"] == "none"


def test_apply_requires_exact_database_confirmation_before_connect(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    monkeypatch.setattr(resetter, "DB_CONFIG", {
        "host": "localhost", "port": 3306, "database": "union_db"
    })
    monkeypatch.setattr(
        resetter, "_canonical_bootstrap_contract", lambda: (assembly, {})
    )
    monkeypatch.setenv("APP_ENV", "development")

    with pytest.raises(resetter.FakeDatabaseResetError, match="requires"):
        resetter.reset(apply=True, connection_factory=lambda **_kwargs: None)


def test_target_refuses_remote_production_and_non_union_database():
    with pytest.raises(resetter.FakeDatabaseResetError, match="local MySQL"):
        resetter.validate_target(
            {"host": "db.example.com", "database": "union_db"},
            {"APP_ENV": "development"},
        )
    with pytest.raises(resetter.FakeDatabaseResetError, match="must be union_db"):
        resetter.validate_target(
            {"host": "127.0.0.1", "database": "other"},
            {"APP_ENV": "development"},
        )
    with pytest.raises(resetter.FakeDatabaseResetError, match="production"):
        resetter.validate_target(
            {"host": "127.0.0.1", "database": "union_db"},
            {"APP_ENV": "production"},
        )
    with pytest.raises(resetter.FakeDatabaseResetError, match="development"):
        resetter.validate_target(
            {"host": "127.0.0.1", "database": "union_db"},
            {"APP_ENV": "staging"},
        )


def test_rebuild_executes_canonical_paths_and_postcheck(monkeypatch, tmp_path):
    assembly = _assembly(tmp_path)
    executed = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _parameters=None):
            executed.append(statement)

    class Connection:
        committed = False
        rolled_back = False
        closed = False

        def cursor(self):
            return Cursor()

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    connection = Connection()
    loaded = []
    monkeypatch.setattr(
        resetter,
        "load_schema_paths",
        lambda _cursor, paths: loaded.extend(paths) or [path.name for path in paths],
    )
    monkeypatch.setattr(resetter, "expected_database_objects", lambda _manifest: {})
    monkeypatch.setattr(
        resetter, "verify_database_objects", lambda _cursor, _database, _expected: []
    )

    report = resetter.rebuild_schema(
        assembly,
        {},
        connection_factory=lambda **_kwargs: connection,
    )

    assert connection.committed and connection.closed and not connection.rolled_back
    assert loaded == list(assembly.active_artifact_paths)
    assert "USE `union_db`" in executed
    assert report["business_fixture_rows_loaded"] == 0
    assert report["schema_postcheck"] == "pass"


def test_database_reset_preflight_uses_canonical_files_not_fixture():
    from scripts.launcher_preflight import PROFILE_REQUIREMENTS

    requirements = PROFILE_REQUIREMENTS["database-reset"]["files"]
    assert "fixtures/db_snapshot_v2/v3/manifest.json" not in requirements
    assert "db/schema_assembly/labor_union_fresh_schema_v1.json" in requirements
    assert "db/cutover_releases/labor_union_validation_schema_v1.json" in requirements

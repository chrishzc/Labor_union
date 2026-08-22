"""
File: test_update_local_database_docker_client.py
Description: 驗證本機DB升級可將MySQL client呼叫轉送至Docker容器。
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts import migrate_preserved_database_additive_schema as migration
from scripts import update_local_database as update


def test_running_compose_mysql_is_selected_when_host_clients_are_missing(
    monkeypatch,
):
    monkeypatch.setattr(update.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        update.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="true\n"
        ),
    )

    assert update.resolve_mysql_container() == "mysql_db"


def test_host_clients_remain_preferred_over_implicit_docker(monkeypatch):
    monkeypatch.setattr(update.shutil, "which", lambda name: f"C:/{name}.exe")

    assert update.resolve_mysql_container() is None


def test_restore_dump_uses_mysql_inside_configured_container(tmp_path, monkeypatch):
    dump_path = tmp_path / "source.sql"
    dump_path.write_bytes(b"SELECT 1;")
    captured = {}

    def run(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(update.subprocess, "run", run)
    config = SimpleNamespace(
        host="127.0.0.1", port=3306, user="root", password="unit-test-only"
    )

    update.restore_dump(
        config, "union_db", dump_path, mysql_container="mysql_db"
    )

    assert captured["command"][:7] == [
        "docker", "exec", "-i", "-e", "MYSQL_PWD", "mysql_db", "mysql"
    ]
    assert captured["command"][-1] == "union_db"
    assert captured["env"]["MYSQL_PWD"] == "unit-test-only"


def test_environment_file_container_is_forwarded_to_apply(tmp_path, monkeypatch):
    environment = tmp_path / ".env"
    environment.write_text(
        "DB_DATABASE=lu_test_dataset\nMYSQL_CONTAINER=mysql_db\n", encoding="utf-8"
    )
    config = SimpleNamespace(host="127.0.0.1", port=3306, user="root")
    preview = {"source_database": "lu_test_dataset", "status": "ready"}
    captured = {}

    monkeypatch.setattr(update.migration, "config_from_env", lambda _: (config, "lu_test_dataset"))
    monkeypatch.setattr(update, "validate_local_source", lambda *_: None)
    monkeypatch.setattr(update, "build_additive_preview", lambda *_args, **_kwargs: preview)

    def apply_update(*args, **kwargs):
        captured.update(kwargs)
        return {"status": "completed"}

    monkeypatch.setattr(update, "apply_additive_update", apply_update)

    result = update.update_local_database(
        environment_file=environment,
        receipt_root=tmp_path / "receipts",
        apply=True,
        confirm_configured_database=True,
    )

    assert result == {"status": "completed"}
    assert captured["mysql_container"] == "mysql_db"


def test_local_tcp_forward_port_overrides_environment_port(tmp_path, monkeypatch):
    environment = tmp_path / ".env"
    environment.write_text("DB_DATABASE=lu_test_dataset\n", encoding="utf-8")
    config = migration.DatabaseConfig(
        host="127.0.0.1", port=3306, user="root", password="unit-test-only"
    )
    captured = {}

    monkeypatch.setattr(
        update.migration,
        "config_from_env",
        lambda _: (config, "lu_test_dataset"),
    )
    monkeypatch.setattr(update, "validate_local_source", lambda *_args, **_kwargs: None)

    def build_additive_preview(actual_config, source, *_args, **_kwargs):
        captured.update(config=actual_config, source=source)
        return {"status": "ready", "source_database": source}

    monkeypatch.setattr(update, "build_additive_preview", build_additive_preview)

    result = update.update_local_database(
        environment_file=environment,
        receipt_root=tmp_path / "receipts",
        database_port=13306,
    )

    assert result["source_database"] == "lu_test_dataset"
    assert captured["config"].host == "127.0.0.1"
    assert captured["config"].port == 13306
    assert captured["config"].password == "unit-test-only"


def test_local_tcp_forward_port_rejects_invalid_value():
    config = migration.DatabaseConfig(
        host="127.0.0.1", port=3306, user="root", password="unit-test-only"
    )

    try:
        update.with_database_port(config, 70000)
    except update.LocalDatabaseUpdateError as error:
        assert str(error) == "database port must be between 1 and 65535"
    else:
        raise AssertionError("invalid database port must fail closed")


def test_candidate_python_uses_utf8_and_hashes_non_utf8_stderr(monkeypatch):
    captured = {}

    def run(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(
            returncode=0,
            stdout=b'{"status":"completed"}\r\n',
            stderr=b"mysql diagnostic: \xb7",
        )

    monkeypatch.setattr(migration.subprocess, "run", run)
    config = SimpleNamespace(
        host="127.0.0.1", port=3306, user="root", password="unit-test-only"
    )

    result = migration._run_project_python(
        ["scripts/example.py"], config=config, database="candidate"
    )

    assert captured["env"]["PYTHONUTF8"] == "1"
    assert captured["env"]["PYTHONIOENCODING"] == "utf-8"
    assert result["result"] == {"status": "completed"}
    assert len(result["stderr_sha256"]) == 64

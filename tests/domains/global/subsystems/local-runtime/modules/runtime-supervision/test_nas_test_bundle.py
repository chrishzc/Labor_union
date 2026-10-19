"""Protect preview login/TLS boundaries and the zero-work LINE startup check."""
import hashlib
import json
import sys
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from scripts import nas_test_runtime, package_nas_preview, run_line_worker


def test_line_check_never_enters_a_work_cycle(monkeypatch):
    client = Mock()
    client.run_line_cycle.side_effect = AssertionError("LINE work must not run")
    monkeypatch.setattr(run_line_worker, "PrivateOperationsClient", lambda _: client)
    monkeypatch.setattr(run_line_worker, "discard_database_credentials", lambda: None)
    monkeypatch.setattr(sys, "argv", ["run_line_worker", "--check"])
    assert run_line_worker.main() == 0
    client.check.assert_called_once_with()
    client.run_line_cycle.assert_not_called()


def test_line_check_auth_failure_does_not_process_work(monkeypatch):
    from infrastructure.http.private_operations_client import PrivateOperationError
    client = Mock()
    client.check.side_effect = PrivateOperationError("denied", retryable=False)
    monkeypatch.setattr(run_line_worker, "PrivateOperationsClient", lambda _: client)
    monkeypatch.setattr(run_line_worker, "discard_database_credentials", lambda: None)
    monkeypatch.setattr(sys, "argv", ["run_line_worker", "--check"])
    assert run_line_worker.main() == 2
    client.run_line_cycle.assert_not_called()


@pytest.mark.parametrize("name,value", [
    ("APP_ENV", "development"), ("ACCESS_CONTROL_PROFILE", "local_bypass"),
    ("ENABLE_ADMIN_AUTH", "false"), ("DB_HOST", "existing-nas"),
    ("DB_DATABASE", "union_db"), ("DB_SSL_MODE", "disabled"),
])
def test_preview_rejects_bypass_or_existing_database(monkeypatch, name, value):
    for key, setting in {"APP_ENV": "production", "ACCESS_CONTROL_PROFILE": "production",
                         "ENABLE_ADMIN_AUTH": "true", "DB_HOST": "db",
                         "DB_DATABASE": nas_test_runtime.DATABASE,
                         "DB_SSL_MODE": "verify_identity"}.items():
        monkeypatch.setenv(key, setting)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        nas_test_runtime.require_login_mode()


def test_server_tls_without_client_key_and_partial_mtls_rejected(monkeypatch):
    from infrastructure.mysql.mysql_adapter import _database_config_from_environment
    monkeypatch.setenv("DB_SSL_MODE", "verify_identity")
    monkeypatch.setenv("DB_SSL_CA", "synthetic-ca.pem")
    monkeypatch.setenv("DB_SSL_CERT", "")
    monkeypatch.setenv("DB_SSL_KEY", "")
    assert _database_config_from_environment()["ssl"] == {
        "ca": "synthetic-ca.pem", "check_hostname": True,
    }
    monkeypatch.setenv("DB_SSL_CERT", "synthetic-client.pem")
    with pytest.raises(RuntimeError, match="both"):
        _database_config_from_environment()


@pytest.mark.parametrize("name", [".env", "api/.env.local", "config/credentials.json",
                                  "config/service_account_nas.json", "db/local.sqlite",
                                  "line/token.json", "ui_react/node_modules/dep/index.js"])
def test_build_context_does_not_admit_local_credentials_or_data(name):
    assert not package_nas_preview.include_source(name)


def test_prepare_refuses_existing_data_before_writing_settings(tmp_path):
    settings, data = tmp_path / "settings", tmp_path / "data"
    settings.mkdir()
    data.mkdir()
    (data / "existing").write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        nas_test_runtime.prepare(settings, data)
    assert list(settings.iterdir()) == []
    assert (data / "existing").read_text() == "preserve"


def _verified_source_bundle(root):
    root.mkdir()
    (root / "init").mkdir()
    contents = {
        "bundle.json": json.dumps({"image": "labor-union-nas-test:local", "source_ref": "frozen-source"}),
        "verification.json": json.dumps({"image_digest": "sha256:synthetic"}),
        "init/10-fresh-schema.sql": "-- frozen image's schema\n",
        "init/20-restrict-app.sh": "#!/bin/bash\ndocker_process_sql <<'SQL'\nSELECT 1;\nSQL\n",
    }
    for name, content in contents.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n"
        for name in contents), encoding="utf-8")
    return root


def test_synology_handoff_preserves_image_and_security_boundaries(tmp_path):
    import yaml
    source = _verified_source_bundle(tmp_path / "original")
    output = tmp_path / "gui"
    package_nas_preview.prepare_synology(output, source)
    read = lambda folder: yaml.safe_load((output / folder / "docker-compose.yml").read_text(encoding="utf-8"))
    setup, app, line = read("01-prepare"), read("02-app"), read("03-line-check")
    initializer = setup["services"]["prepare"]
    assert initializer["network_mode"] == "none"
    assert initializer["restart"] == "no"
    assert initializer["user"] == "0:0"
    assert initializer["read_only"] is True
    assert initializer["tmpfs"] == ["/tmp:rw,noexec,nosuid,size=64m"]
    runtime_mount = "../runtime/nas_test_runtime.py:/app/scripts/nas_test_runtime.py:ro"
    assert initializer["volumes"] == ["../settings:/settings", "app-data:/data", runtime_mount]
    assert "prepare()" in initializer["command"][-1]
    assert set(app["services"]) == {"db", "redis", "api"}
    assert "ports" not in app["services"]["api"]
    assert app["volumes"]["app-data"]["external"] is True
    assert "ports" not in app["services"]["db"]
    assert "ports" not in app["services"]["redis"]
    assert app["services"]["api"]["environment"]["ENABLE_ADMIN_AUTH"] == "true"
    assert setup["volumes"]["app-data"]["name"] == app["volumes"]["app-data"]["name"]
    assert "--require-secure-transport=ON" in app["services"]["db"]["command"]
    assert line["services"]["line-check"]["command"][-1] == "--check"
    assert line["services"]["line-check"]["restart"] == "no"
    assert line["networks"]["app"] == {"external": True, "name": app["networks"]["app"]["name"]}
    for service in (initializer, app["services"]["api"], line["services"]["line-check"]):
        assert service["image"] == package_nas_preview.SYNOLOGY_IMAGE
        assert service["pull_policy"] == "never"
        assert runtime_mount in service["volumes"]
        assert "build" not in service
    assert (output / "init/10-fresh-schema.sql").read_bytes() == (
        b"SET NAMES utf8mb4;\n" + (source / "init/10-fresh-schema.sql").read_bytes())
    assert (output / "init/20-restrict-app.sql").read_text(encoding="utf-8") == "SELECT 1;\n"
    assert not (output / "init/20-restrict-app.sh").exists()
    assert "99-ready.sh" in {path.name for path in (output / "init").iterdir()}
    assert "test -f /var/lib/mysql/.lu-preview-initialized" in app["services"]["db"]["healthcheck"]["test"][-1]
    with zipfile.ZipFile(output.with_suffix(".zip")) as archive:
        assert archive.testzip() is None
        assert "settings/" in archive.namelist()
        assert not any(name.endswith((".env", ".pem", ".tar")) for name in archive.namelist())


def test_synology_handoff_rejects_changed_source_schema(tmp_path):
    source = _verified_source_bundle(tmp_path / "original")
    (source / "init/10-fresh-schema.sql").write_text("changed since image build", encoding="utf-8")
    output = tmp_path / "gui"
    with pytest.raises(ValueError, match="checksum mismatch"):
        package_nas_preview.prepare_synology(output, source)
    assert not output.exists()


@pytest.mark.parametrize("schema_present", [True, False])
def test_preview_schema_gate_handles_adapter_dict_default_without_losing_missing_object_check(monkeypatch, schema_present):
    import pymysql
    from scripts import compact_fresh_schema
    from infrastructure.mysql import mysql_adapter
    connection = Mock()

    def open_cursor(kind=pymysql.cursors.DictCursor):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        def execute(sql, parameters=None):
            rows = []
            if "information_schema.tables" in sql and parameters[1] == "BASE TABLE" and schema_present:
                rows = [("required_table",)] if kind is pymysql.cursors.Cursor else [{"table_name": "required_table"}]
            cursor.fetchall.return_value = rows
        cursor.execute.side_effect = execute
        return cursor

    connection.cursor.side_effect = open_cursor
    monkeypatch.setattr(mysql_adapter, "get_connection", lambda: connection)
    monkeypatch.setattr(compact_fresh_schema, "load_compact_plan", lambda: {
        "expected": {"tables": {"required_table"}, "views": set(), "triggers": set()}})
    if schema_present:
        nas_test_runtime.verify_schema()
    else:
        with pytest.raises(ValueError, match="schema mismatch"):
            nas_test_runtime.verify_schema()
    connection.close.assert_called_once()


def test_management_preview_excludes_line_without_changing_auth_environment(monkeypatch):
    from fastapi import APIRouter, FastAPI
    app, line = FastAPI(), APIRouter()
    async def webhook():
        return {}
    async def line_admin():
        return {}
    async def admin():
        return {}
    line_admin.__module__ = "api.routes.line_admin"
    line.add_api_route("/webhook", webhook)
    app.include_router(line)
    app.add_api_route("/api/v1/line/tasks", line_admin)
    app.add_api_route("/api/v1/line/staff-self-service/logs", admin)
    app.add_api_route("/api/v1/admin/auth/login", admin)
    for key, value in {"APP_ENV": "production", "ACCESS_CONTROL_PROFILE": "production",
                       "ENABLE_ADMIN_AUTH": "true", "DB_HOST": "db",
                       "DB_DATABASE": nas_test_runtime.DATABASE, "DB_SSL_MODE": "verify_identity"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setitem(sys.modules, "api.main", SimpleNamespace(app=app, line_router=line))
    result = nas_test_runtime.management_preview_app()
    paths = result.openapi()["paths"]
    assert "/webhook" not in paths
    assert "/api/v1/line/tasks" not in paths
    assert "/api/v1/line/staff-self-service/logs" not in paths
    assert "/api/v1/admin/auth/login" in paths
    nas_test_runtime.require_login_mode()

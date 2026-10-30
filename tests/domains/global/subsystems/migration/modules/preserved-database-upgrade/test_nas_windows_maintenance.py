"""NAS SQL maintenance: no local target, no source reset, verified switch only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts import nas_database_maintenance as nas


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # Tests never read the workstation's real environment or credentials.
    for key in tuple(os.environ):
        if key.startswith("DB_") or key == "APP_ENV":
            monkeypatch.delenv(key)
    runtime = tmp_path / ".env"
    runtime.write_bytes(b'# untouched\r\nDB_HOST=nas.invalid\r\nDB_DATABASE="union_db"\r\nDB_USER=fixture_app\r\nDB_PASSWORD=fixture_runtime\r\n')
    config = tmp_path / ".env.nas-maintenance"
    config.write_text(f'NAS_MAINTENANCE_ENABLED=1\nNAS_EXPECTED_HOST=nas.invalid\nNAS_BACKUP_USER=fixture_reader\nNAS_BACKUP_PASSWORD=fixture_readonly\nNAS_MAINTENANCE_USER=fixture_writer\nNAS_MAINTENANCE_PASSWORD=fixture_admin\nNAS_BACKUP_DIR={tmp_path.as_posix()}\n', encoding="utf-8")
    monkeypatch.setattr(nas, "private_directory", lambda p: (Path(p).mkdir(parents=True, exist_ok=True) or Path(p)))
    return nas.load_settings(runtime, config)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.0.0.2", "::1", "0.0.0.0", "::"])
def test_local_development_targets_rejected_before_connection(settings, host, monkeypatch):
    path = settings["environment_file"]
    path.write_text(f"DB_HOST={host}\nDB_DATABASE=union_db\n", encoding="utf-8")
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("no local connection allowed"))
    with pytest.raises(nas.MaintenanceBlocked, match="本機"):
        nas.load_settings(path, settings["settings_file"])


def test_opt_in_and_target_pin_are_required(settings):
    path = settings["settings_file"]
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace("ENABLED=1", "ENABLED=0"), encoding="utf-8")
    with pytest.raises(nas.MaintenanceBlocked, match="尚未啟用"):
        nas.load_settings(settings["environment_file"], path)
    path.write_text(original.replace("EXPECTED_HOST=nas.invalid", "EXPECTED_HOST=other.invalid"), encoding="utf-8")
    with pytest.raises(nas.MaintenanceBlocked, match="位址"):
        nas.load_settings(settings["environment_file"], path)


def test_dry_run_never_connects_creates_backup_or_registers_task(settings, monkeypatch):
    monkeypatch.setattr(nas.shutil, "which", lambda name: name)
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("dry-run must not connect"))
    monkeypatch.setattr(nas, "configure_daily_backup", lambda *_args, **_kw: pytest.fail("must not schedule"))
    assert nas.main(["upgrade", "--dry-run", "--environment-file", str(settings["environment_file"]),
                     "--settings-file", str(settings["settings_file"])]) == 0
    assert not settings["backup_root"].exists()


def make_backup(settings, monkeypatch, exit_code=0):
    monkeypatch.setattr(nas.shutil, "which", lambda name: name)
    monkeypatch.setattr(nas, "schema_inventory", lambda *_: {"tables": [{"name": "fixture", "kind": "BASE TABLE"}],
                         "charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"})
    monkeypatch.setattr(nas.migration, "server_identity", lambda *_: {"server": "fixture-server", "database": "union_db"})
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs["env"]))
        kwargs["stdout"].write(b"-- synthetic fixture\n-- Dump completed on 2026-10-30\n")
        return SimpleNamespace(returncode=exit_code)
    monkeypatch.setattr(nas.subprocess, "run", run)
    return nas.backup(settings), calls


def test_daily_dump_is_complete_keeps_history_and_never_puts_password_in_arguments(settings, monkeypatch):
    first, calls = make_backup(settings, monkeypatch)
    second = nas.backup(settings)
    assert first != second and first.exists()
    assert nas.validate_backup(first)["status"] == "completed"
    command, environment = calls[0]
    assert "--single-transaction" in command and "--quick" in command
    assert "--databases" not in command and "union_db" == command[-1]
    assert "fixture_readonly" not in " ".join(command)
    assert environment["MYSQL_PWD"] == "fixture_readonly"
    assert settings["environment_file"].read_bytes().startswith(b"# untouched\r\n")


def test_failed_dump_keeps_old_backup_and_partial_cannot_be_restored(settings, monkeypatch):
    first, _ = make_backup(settings, monkeypatch)
    before = (first / "database.sql").read_bytes()
    monkeypatch.setattr(nas.subprocess, "run", lambda command, **kw: SimpleNamespace(returncode=9))
    with pytest.raises(nas.MaintenanceBlocked, match="未完成"):
        nas.backup(settings)
    assert (first / "database.sql").read_bytes() == before
    partial = next(settings["backup_root"].glob(".partial-*"))
    with pytest.raises(nas.MaintenanceBlocked, match="尚未完成"):
        nas.validate_backup(partial)


def test_tampered_backup_stops_before_any_restore_connection(settings, monkeypatch):
    path, _ = make_backup(settings, monkeypatch)
    (path / "database.sql").write_text("corrupted", encoding="utf-8")
    monkeypatch.setattr(nas, "writer", lambda *_: pytest.fail("must verify before connecting"))
    with pytest.raises(nas.MaintenanceBlocked, match="檢查碼"):
        nas.restore(settings, path)


def test_external_backup_folder_is_not_executed_as_sql(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(nas, "writer", lambda *_: pytest.fail("untrusted paths must not connect"))
    with pytest.raises(nas.MaintenanceBlocked, match="專用備份資料夾"):
        nas.restore(settings, tmp_path / "downloaded-backup")


def test_runtime_switch_preserves_all_other_env_bytes_and_rejects_stale(settings, tmp_path):
    path = settings["environment_file"]
    original_acl = None
    if os.name == "nt":
        literal = "'" + str(path).replace("'", "''") + "'"
        protected = nas.run_windows_powershell(f"$acl=Get-Acl -LiteralPath {literal}; $acl.SetAccessRuleProtection($true,$true); Set-Acl -LiteralPath {literal} -AclObject $acl; (Get-Acl -LiteralPath {literal}).Sddl")
        assert protected.returncode == 0
        original_acl = protected.stdout.strip()
    before = path.read_bytes()
    original_hash = nas.digest(path)
    nas.switch_runtime(settings, "lu_nas_restore_fixture", original_hash, tmp_path)
    assert path.read_bytes() == before.replace(b'DB_DATABASE="union_db"', b'DB_DATABASE="lu_nas_restore_fixture"')
    if original_acl is not None:
        actual = nas.run_windows_powershell(f"(Get-Acl -LiteralPath {literal}).Sddl")
        assert actual.returncode == 0 and actual.stdout.strip() == original_acl
    with pytest.raises(nas.MaintenanceBlocked, match="已改變"):
        nas.switch_runtime(settings, "lu_nas_restore_other", original_hash, tmp_path)
    assert path.read_bytes().count(b"lu_nas_restore_fixture") == 1


def test_candidate_config_refuses_source_connection_and_keeps_tls(settings, monkeypatch):
    settings["tls"] = {"ssl": {"ca": "fixture-ca", "check_hostname": True}}
    config = nas.writer(settings, "lu_nas_upgrade_fixture")
    with pytest.raises(nas.MaintenanceBlocked, match="只能操作"):
        config.connect("union_db")
    calls = []
    monkeypatch.setattr(nas.pymysql, "connect", lambda **kw: calls.append(kw))
    config.connect("lu_nas_upgrade_fixture")
    assert calls[0]["ssl"]["check_hostname"] is True


def test_upgrade_preserves_order_and_never_switches_when_verification_fails(settings, monkeypatch, tmp_path):
    steps = []
    monkeypatch.setattr(nas.shutil, "which", lambda name: name)
    monkeypatch.setattr(nas.migration, "build_plan", lambda *_: {"status": "ready", "candidate_exists": False})
    monkeypatch.setattr(nas, "backup", lambda *_: steps.append("backup") or tmp_path)
    monkeypatch.setattr(nas, "validate_backup", lambda *_: {"created_at": "fixture", "server": "fixture", "sha256": "a", "size": 1})
    monkeypatch.setattr(nas.migration, "restore_candidate", lambda *_: steps.append("restore"))
    monkeypatch.setattr(nas.migration, "apply_schema", lambda *_: steps.append("apply"))
    monkeypatch.setattr(nas, "schema_inventory", lambda *_args, **_kw: {})
    monkeypatch.setattr(nas.migration, "verify_candidate", lambda *_: steps.append("verify") or {"status": "failed"})
    monkeypatch.setattr(nas, "prepare_runtime_access", lambda *_: pytest.fail("failed validation must not grant"))
    monkeypatch.setattr(nas.migration, "switch_environment", lambda *_args, **_kw: pytest.fail("failed validation must not switch"))
    before = settings["environment_file"].read_bytes()
    with pytest.raises(nas.MaintenanceBlocked, match="驗證未通過"):
        nas.upgrade(settings)
    assert steps == ["backup", "restore", "apply", "verify"]
    assert settings["environment_file"].read_bytes() == before


def test_schedule_stale_is_typed_and_does_not_register(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(nas, "SCHEDULE", tmp_path / "schedule.json")
    nas.save(nas.SCHEDULE, {"version": 4, "time": "18:00", "enabled": True})
    monkeypatch.setattr(nas, "_configure_daily_backup", lambda *_args, **_kw: pytest.fail("stale must not register"))
    with pytest.raises(nas.ScheduleConflict):
        nas.configure_daily_backup("17:00", expected_version=3)


@pytest.mark.skipif(os.name != "nt", reason="Windows schedule command composition")
def test_daily_schedule_uses_hidden_interactive_account_without_password_and_records_version(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(nas, "SCHEDULE", tmp_path / "schedule.json")
    calls = []
    monkeypatch.setattr(nas.subprocess, "run", lambda command, **kw: calls.append(command) or SimpleNamespace(returncode=0))
    result = nas.configure_daily_backup(environment_file=settings["environment_file"], settings_file=settings["settings_file"], expected_version=0)
    assert result["time"] == "18:00" and result["version"] == 1
    script = calls[0][-1]
    assert "-LogonType Interactive" in script and "-StartWhenAvailable" in script
    assert "--scheduled" in script and "pythonw.exe" in script
    assert "fixture_admin" not in script and "fixture_readonly" not in script
    assert "Existing task belongs to another installation" in script
    assert json.loads(nas.SCHEDULE.read_text(encoding="utf-8"))["version"] == 1


def test_escaped_schema_grants_copy_only_to_exact_new_candidate(settings, monkeypatch):
    commands = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, command, parameters=()):
            commands.append((command, parameters))
            self.command = command
        def fetchone(self):
            if "CURRENT_USER" in self.command: return {"account": "fixture_app@%"}
            if "partial_revokes" in self.command: return {"partial_revokes": 0}
            return {"name": "lu_nas_restore_fixture"}
        def fetchall(self):
            return [{"grant": "GRANT SELECT,INSERT ON `union\\_db`.* TO `fixture_app`@`%`"}]
    connection = SimpleNamespace(cursor=lambda: Cursor(), close=lambda: None)
    config = SimpleNamespace(connect=lambda *_: connection)
    monkeypatch.setattr(nas, "writer", lambda *_: config)
    nas._copy_schema_access(settings, "lu_nas_restore_fixture", config)
    grants = [sql for sql, _ in commands if sql.startswith("GRANT ")]
    assert grants == [r"GRANT INSERT,SELECT ON `lu\_nas\_restore\_fixture`.* TO %s@%s"]
    assert all(not sql.startswith(("ALTER USER", "DROP", "REVOKE")) for sql, _ in commands)


def test_enabled_sql_events_are_blocked_before_import():
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, *_): pass
        def fetchone(self): return {"scheduler": "ON"}
    config = SimpleNamespace(connect=lambda: SimpleNamespace(cursor=lambda: Cursor(), close=lambda: None))
    with pytest.raises(nas.MaintenanceBlocked, match="自動資料庫事件"):
        nas.require_event_scheduler_safe(config, {"inventory": {"events": ["fixture"]}})


def test_schedule_api_requires_auth_validates_time_and_returns_typed_conflict(monkeypatch):
    from api.routes import database_backup as route
    from api.dependencies.admin_auth import require_admin, require_persisted_admin
    from api.dependencies import admin_auth
    monkeypatch.setattr(admin_auth, "admin_auth_is_enabled", lambda: True)
    monkeypatch.setattr(admin_auth, "get_admin_session", lambda *_args, **_kw: None)
    app = FastAPI()
    app.include_router(route.router)
    client = TestClient(app)
    assert client.get("/api/v1/system/database-backup").status_code in {401, 403}
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[require_persisted_admin] = lambda: object()
    assert client.put("/api/v1/system/database-backup/schedule", json={"time": "25:00", "expected_version": 0}).status_code == 422
    def conflict(*_, **__):
        raise nas.ScheduleConflict("備份時間已由其他人修改，請重新載入後再儲存。")
    monkeypatch.setattr(route, "configure_daily_backup", conflict)
    response = client.put("/api/v1/system/database-backup/schedule", json={"time": "18:00", "expected_version": 0})
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "backup_schedule_stale"


@pytest.mark.skipif(os.name != "nt", reason="real Windows batch contract")
@pytest.mark.parametrize("filename,mode", [("backup_nas_database.bat", "backup"), ("initialize_nas_schema.bat", "upgrade"), ("restore_nas_database.bat", "restore")])
def test_three_windows_launchers_delegate_without_initialization_or_reset(tmp_path, filename, mode):
    root = tmp_path / "project with spaces"
    launcher = root / "scripts/launchers" / filename
    launcher.parent.mkdir(parents=True)
    shutil.copyfile(nas.ROOT / "scripts/launchers" / filename, launcher)
    (root / ".venv/Scripts").mkdir(parents=True)
    shutil.copyfile(nas.ROOT / ".venv/Scripts/python.exe", root / ".venv/Scripts/python.exe")
    shutil.copyfile(nas.ROOT / ".venv/pyvenv.cfg", root / ".venv/pyvenv.cfg")
    (root / "scripts/nas_database_maintenance.py").write_text('import json,sys\nprint(json.dumps(sys.argv[1:]))\n', encoding="utf-8")
    result = subprocess.run(["cmd.exe", "/d", "/c", "call", str(launcher), "--dry-run"], capture_output=True,
                            encoding="utf-8", errors="replace", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.dumps([mode, "--dry-run"]) in result.stdout
    assert "-m scripts.initialize_nas_schema" not in launcher.read_text(encoding="utf-8")

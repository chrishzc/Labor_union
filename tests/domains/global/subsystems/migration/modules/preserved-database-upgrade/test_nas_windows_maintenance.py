"""Internal SQL maintenance: flexible deployment, no source reset, verified switch."""
import json
import gzip
import io
from contextlib import nullcontext
from datetime import datetime, timedelta
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts import nas_database_maintenance as nas
IS_NAS_DESTINATION = nas.is_nas_destination


@pytest.mark.skipif(os.name != "nt", reason="Windows manager file sharing and venv redirector")
def test_restore_installation_lock_accepts_manager_ancestry_and_blocks_other_launches(tmp_path: Path) -> None:
    lock_path = tmp_path / "scratch" / "windows-remote" / "manager.lock"
    lock_path.parent.mkdir(parents=True)
    probe = tmp_path / "restore_lock_probe.py"
    probe.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from scripts import nas_database_maintenance as nas\n"
        "print(os.getppid(), flush=True)\n"
        "try:\n"
        "    with nas._restore_installation_lock({'environment_file': Path(os.environ['LU_TEST_LOCK_ROOT']) / '.env'}):\n"
        "        print('entered restore lock')\n"
        "except nas.MaintenanceBlocked as exc:\n"
        "    print(exc)\n"
        "    raise SystemExit(8)\n",
        encoding="utf-8",
    )
    manager = tmp_path / "manager_lock_probe.ps1"
    manager.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n"
        "$env:LABOR_UNION_RESTORE_MANAGER_PID = [string]$PID\n"
        "Write-Output $PID\n"
        "$stream = [IO.File]::Open($env:LU_TEST_LOCK_PATH, 'OpenOrCreate', 'ReadWrite', 'None')\n"
        "try {\n"
        "    & $env:LU_TEST_PYTHON $env:LU_TEST_PROBE\n"
        "    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
        "    Remove-Item Env:LABOR_UNION_RESTORE_MANAGER_PID\n"
        "    & $env:LU_TEST_PYTHON $env:LU_TEST_PROBE\n"
        "    if ($LASTEXITCODE -ne 8) { throw 'Expected competing lock to block' }\n"
        "    $env:LABOR_UNION_RESTORE_MANAGER_PID = '4294967295'\n"
        "    & $env:LU_TEST_PYTHON $env:LU_TEST_PROBE\n"
        "    exit $LASTEXITCODE\n"
        "} finally { $stream.Dispose() }\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(manager)],
        cwd=nas.ROOT,
        env={**os.environ, "LU_TEST_LOCK_PATH": str(lock_path), "LU_TEST_LOCK_ROOT": str(tmp_path),
             "LU_TEST_PROBE": str(probe), "LU_TEST_PYTHON": sys.executable,
             "PYTHONPATH": str(nas.ROOT), "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 8, (result.stdout, result.stderr)
    manager_pid, restore_parent, entered, _, blocked, _, invalid_owner_blocked = result.stdout.decode("utf-8").splitlines()
    if sys.prefix != sys.base_prefix:
        assert restore_parent != manager_pid
    assert entered == "entered restore lock"
    assert blocked == "另一項管理操作正在執行，請待該操作完成再復原。"
    assert invalid_owner_blocked == blocked


def test_nas_does_not_execute_the_retired_subsidy_relabeling(monkeypatch, tmp_path):
    candidate = 'lu_nas_upgrade_synthetic'
    connection = nas.ConnectionConfig({'host': 'nas.invalid', 'port': 3306, 'ssl_mode': 'VERIFY_IDENTITY',
        'tls_files': {}}, user='fixture', password='fixture', candidate=candidate)
    monkeypatch.setattr(connection, 'connect', lambda *_args, **_kw: pytest.fail('retired backfill cannot connect'))
    with pytest.raises(nas.MaintenanceBlocked, match='已退役'):
        connection.run_manifest_backfill(SimpleNamespace(backfill_id='subsidy-period-policy-v1'),
            'apply', candidate, tmp_path/'plan.json', tmp_path/'backup.sql', tmp_path/'receipt.json')
    assert connection.run_manifest_backfill(SimpleNamespace(backfill_id='twins-payroll-rate-snapshots-v1'),
        'apply', candidate, tmp_path/'plan.json', tmp_path/'backup.sql', tmp_path/'receipt.json') is False


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # Tests never read the workstation's real environment or credentials.
    for key in tuple(os.environ):
        if key.startswith("DB_") or key in {"APP_ENV", "CONTROLLED_FILE_STORAGE_ROOT"}:
            monkeypatch.delenv(key)
    runtime = tmp_path / ".env"
    runtime.write_bytes(b'# untouched\r\nDB_HOST=nas.invalid\r\nDB_DATABASE="union_db"\r\nDB_USER=fixture_app\r\nDB_PASSWORD=fixture_runtime\r\nCONTROLLED_FILE_STORAGE_ROOT=\\\\nas.invalid\\fixture\r\n')
    config = tmp_path / ".env.nas-maintenance"
    config.write_text('NAS_MAINTENANCE_ENABLED=1\nNAS_EXPECTED_HOST=nas.invalid\nNAS_BACKUP_USER=fixture_reader\nNAS_BACKUP_PASSWORD=fixture_readonly\nNAS_MAINTENANCE_USER=fixture_writer\nNAS_MAINTENANCE_PASSWORD=fixture_admin\n', encoding="utf-8")
    monkeypatch.setattr(nas, "private_directory", lambda p: (Path(p).mkdir(parents=True, exist_ok=True) or Path(p)))
    if os.name != "nt":
        monkeypatch.setattr(nas, "is_nas_destination", lambda _: True)
    result = nas.load_settings(runtime, config)
    result["backup_root"] = tmp_path / nas.BACKUP_FOLDER
    result["backup_root"].mkdir()
    monkeypatch.setattr(nas, "is_nas_destination", lambda _: True)
    monkeypatch.setattr(nas, "LOCAL_STATUS", tmp_path / "local-state/last-result.json")
    tick = iter(range(100))
    monkeypatch.setattr(nas, "backup_time", lambda: datetime(2026, 10, 30, 18, 0, tzinfo=nas.TAIPEI) + timedelta(seconds=next(tick)))
    return result


@pytest.fixture
def unpinned_remote_settings(settings, tmp_path):
    runtime = settings["environment_file"]
    runtime.write_text(runtime.read_text(encoding="utf-8").replace(
        "nas.invalid", "192.168.1.239").replace(
        '"union_db"', '"lu_nas_restore_20261117032757_4ad2acd6"'), encoding="utf-8")
    loaded = nas.load_settings(runtime, tmp_path / "absent-maintenance-settings")
    loaded["backup_root"] = settings["backup_root"]
    assert not loaded["settings_file"].exists()
    return loaded


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.0.0.2", "::1", "0.0.0.0", "::"])
def test_local_development_targets_load_without_connection(settings, host, monkeypatch):
    path = settings["environment_file"]
    path.write_text(f"DB_HOST={host}\nDB_DATABASE=union_db\n", encoding="utf-8")
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("no local connection allowed"))
    assert nas.load_settings(path, settings["settings_file"])["host"] == host


def test_old_opt_in_and_target_pin_do_not_block_maintenance(settings):
    path = settings["settings_file"]
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace("ENABLED=1", "ENABLED=0"), encoding="utf-8")
    assert nas.load_settings(settings["environment_file"], path)["host"] == "nas.invalid"
    path.write_text(original.replace("EXPECTED_HOST=nas.invalid", "EXPECTED_HOST=other.invalid"), encoding="utf-8")
    assert nas.load_settings(settings["environment_file"], path)["host"] == "nas.invalid"


@pytest.mark.parametrize("host", ["127.0.0.1", "192.168.1.239"])
def test_maintenance_uses_selected_env_without_deployment_gates(settings, tmp_path, monkeypatch, host):
    runtime = settings["environment_file"]
    runtime.write_text(f"DB_HOST={host}\nDB_PORT=3307\nDB_DATABASE=custom_business\n"
                       "DB_USER=fixture_app\nDB_PASSWORD=fixture_runtime\nDEPLOYMENT_PROFILE=nas\n", encoding="utf-8")
    config = settings["settings_file"]
    config.write_text("NAS_MAINTENANCE_ENABLED=0\nNAS_EXPECTED_HOST=obsolete.invalid\n"
                      "NAS_EXPECTED_PORT=9999\n", encoding="utf-8")
    monkeypatch.setenv("DB_HOST", "unselected.invalid")
    monkeypatch.setenv("DB_PASSWORD", "unselected")
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", "unselected-storage")
    monkeypatch.setattr(nas, "ROOT", tmp_path)
    loaded = nas.load_settings(runtime, config)
    assert (loaded["host"], loaded["port"], loaded["database"]) == (host, 3307, "custom_business")
    assert loaded["values"]["NAS_BACKUP_USER"] == loaded["values"]["NAS_MAINTENANCE_USER"] == "fixture_app"
    assert loaded["values"]["NAS_BACKUP_PASSWORD"] == loaded["values"]["NAS_MAINTENANCE_PASSWORD"] == "fixture_runtime"
    assert loaded["backup_root"] == tmp_path / "backups" / nas.BACKUP_FOLDER
    assert nas.is_nas_maintenance_target(loaded) == (host != "127.0.0.1")
    assert not loaded["backup_root"].exists()


@pytest.mark.parametrize("explicit_location", ["runtime", "maintenance", "storage_root"])
def test_maintenance_accepts_and_creates_selected_local_backup(settings, tmp_path, monkeypatch, explicit_location):
    runtime = settings["environment_file"]
    config = settings["settings_file"]
    chosen = tmp_path / "new-local-root" / "chosen-folder"
    content = runtime.read_text(encoding="utf-8")
    if explicit_location == "storage_root":
        content = content.replace(r"\\nas.invalid\fixture", str(chosen))
        expected = chosen / nas.BACKUP_FOLDER
    else:
        config.write_text(config.read_text(encoding="utf-8") + f"NAS_BACKUP_DIR={chosen}\n", encoding="utf-8")
        if explicit_location == "runtime":
            content += f"NAS_BACKUP_DIR={chosen / 'runtime-wins'}\n"
            chosen /= "runtime-wins"
        expected = chosen
    runtime.write_text(content, encoding="utf-8")
    monkeypatch.setattr(nas, "is_nas_destination", lambda _: False)
    loaded = nas.load_settings(runtime, config)
    assert loaded["backup_root"] == expected
    assert not expected.exists()
    assert nas.destination_ready(loaded, writable=True) == expected
    assert expected.is_dir() and not list(expected.iterdir())


def test_maintenance_keeps_explicit_maintenance_credentials(settings):
    loaded = nas.load_settings(settings["environment_file"], settings["settings_file"])
    assert loaded["values"]["NAS_BACKUP_USER"] == "fixture_reader"
    assert loaded["values"]["NAS_MAINTENANCE_USER"] == "fixture_writer"
    assert loaded["values"]["NAS_BACKUP_PASSWORD"] == "fixture_readonly"
    assert loaded["values"]["NAS_MAINTENANCE_PASSWORD"] == "fixture_admin"


def test_internal_upgrade_main_has_no_extra_confirmation_and_keeps_failure_visible(settings, tmp_path, monkeypatch):
    runtime = settings["environment_file"]
    runtime.write_text(runtime.read_text(encoding="utf-8") + f"NAS_BACKUP_DIR={tmp_path / 'local-upgrade'}\n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("internal upgrade does not prompt"))
    monkeypatch.setattr(nas, "maintenance_lock", lambda *_: nullcontext())
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("no database connection"))
    calls = []
    def failed_upgrade(current):
        calls.append(current["backup_root"])
        raise nas.MaintenanceBlocked("synthetic integrity failure")
    monkeypatch.setattr(nas, "upgrade", failed_upgrade)
    assert nas.main(["upgrade", "--environment-file", str(runtime),
                     "--settings-file", str(settings["settings_file"])]) == 2
    assert calls == [tmp_path / "local-upgrade"]
    assert (tmp_path / "local-upgrade").is_dir()


@pytest.mark.parametrize("configured,override,host,expected", [
    ('APP_ENV="production" # formal host', None, "localhost", "candidate"),
    ("APP_ENV=development", " PRODUCTION ", "127.0.0.1", "candidate"),
    ("APP_ENV=production", "development", "127.0.0.1", "direct"),
    ("", None, "::1", "direct"),
    ("APP_ENV=production", " ", "127.0.0.2", "blocked_candidate"),
    ("APP_ENV=production", "staging", "127.0.0.1", "invalid_mode"),
])
def test_internal_loopback_upgrade_uses_the_windows_application_environment(
    settings: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], configured: str, override: str | None,
    host: str, expected: str,
) -> None:
    from scripts import update_local_database as updater

    runtime = settings["environment_file"]
    runtime.write_text(
        f"DB_HOST={host}\nDB_DATABASE=union_db\nDB_USER=fixture_app\n"
        f"NAS_BACKUP_DIR={tmp_path / 'local-upgrade'}\n{configured}\n",
        encoding="utf-8",
    )
    if override is not None:
        monkeypatch.setenv("APP_ENV", override)
    monkeypatch.setattr(nas, "maintenance_lock", lambda *_: nullcontext())
    monkeypatch.setattr(nas, "resolve_client_tool", lambda name: name)
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("no database connection"))
    monkeypatch.setattr(nas, "backup", lambda *_: pytest.fail("preflight must not start backup"))
    paths: list[str] = []

    def direct_upgrade(**arguments: object) -> dict[str, object]:
        paths.append("direct")
        assert arguments == {
            "environment_file": runtime,
            "apply": True,
            "confirm_configured_database": True,
        }
        return {"status": "current"}

    def candidate_plan(
        config: nas.migration.SeparateDatabaseConfig, source: str, candidate: str,
        *, source_recovery_root: Path,
    ) -> dict[str, object]:
        paths.append("candidate")
        assert source == config.source.database == "union_db"
        assert candidate == config.candidate.database and candidate.startswith("lu_nas_upgrade_")
        assert isinstance(config.source.config, nas.ConnectionConfig) and config.source.config.readonly
        assert isinstance(config.candidate.config, nas.ConnectionConfig) and config.candidate.config.candidate == candidate
        assert source_recovery_root == updater.DEFAULT_RECEIPT_ROOT
        if expected == "blocked_candidate":
            raise nas.migration.UpgradeBlocked("synthetic candidate preflight failure")
        return {"status": "ready", "candidate_exists": False, "source_objects": {"fixture.sql": "exact"}}

    monkeypatch.setattr(updater, "update_local_database", direct_upgrade)
    monkeypatch.setattr(nas.migration, "build_plan", candidate_plan)
    monkeypatch.setattr(updater, "build_additive_preview", lambda *_: {"status": "current"})
    monkeypatch.setattr(updater, "require_current_database", lambda preview: preview)

    before = runtime.read_bytes()
    status = nas.main(["upgrade", "--environment-file", str(runtime),
                       "--settings-file", str(tmp_path / "absent-maintenance-settings")])
    assert runtime.read_bytes() == before
    output = capsys.readouterr().out
    if expected == "blocked_candidate":
        assert status == 2 and paths == ["candidate"]
        assert "synthetic candidate preflight failure" in output
    elif expected == "invalid_mode":
        assert status == 2 and paths == []
        assert "APP_ENV" in output
    else:
        assert status == 0 and paths == [expected]
        assert "資料庫結構已是最新版本" in output


def test_missing_shared_storage_root_accepts_explicit_backup_directory(settings):
    path = settings["environment_file"]
    path.write_text('\n'.join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("CONTROLLED_FILE_STORAGE_ROOT=")), encoding="utf-8")
    config = settings["settings_file"]
    config.write_text(config.read_text(encoding="utf-8") + 'NAS_BACKUP_DIR=\\\\other.invalid\\legacy\\' + nas.BACKUP_FOLDER + '\n', encoding="utf-8")
    loaded = nas.load_settings(path, config)
    assert loaded["backup_root"] == Path(r"\\other.invalid\legacy") / nas.BACKUP_FOLDER


def test_explicit_backup_destination_overrides_shared_storage_root(settings):
    config = settings["settings_file"]
    config.write_text(config.read_text(encoding="utf-8") + 'NAS_BACKUP_DIR=\\\\other.invalid\\legacy\n', encoding="utf-8")
    loaded = nas.load_settings(settings["environment_file"], config)
    assert loaded["backup_root"] == Path(r"\\other.invalid\legacy")


def test_process_storage_override_cannot_redirect_backup(settings, monkeypatch):
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", r"\\other.invalid\share")
    loaded = nas.load_settings(settings["environment_file"], settings["settings_file"])
    assert loaded["backup_root"] == Path(r"\\nas.invalid\fixture") / nas.BACKUP_FOLDER


def test_windows_source_mode_flag_does_not_override_pinned_nas_target(settings, monkeypatch):
    path = settings["environment_file"]
    path.write_text(path.read_text(encoding="utf-8") + "APP_ENV=production\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "development")
    assert nas.load_settings(path, settings["settings_file"])["host"] == "nas.invalid"
    monkeypatch.setenv("DB_HOST", "other.invalid")
    assert nas.load_settings(path, settings["settings_file"])["host"] == "nas.invalid"


@pytest.mark.parametrize("root", ["D:/backups", "Z:/share", r"\\localhost\share"])
def test_runtime_local_storage_root_is_accepted_for_backup(settings, monkeypatch, root):
    monkeypatch.setattr(nas, "is_nas_destination", IS_NAS_DESTINATION)
    path = settings["environment_file"]
    path.write_text(path.read_text(encoding="utf-8").replace(r"\\nas.invalid\fixture", root), encoding="utf-8")
    loaded = nas.load_settings(path, settings["settings_file"])
    expected = Path(root)
    if not expected.is_absolute():
        expected = path.parent / expected
    assert loaded["backup_root"] == expected / nas.BACKUP_FOLDER


@pytest.mark.parametrize("path", ["D:/LaborUnionBackups", "C:/work/05_資料庫冷備份 (db_backups)", r"\\localhost\share\db_backups", r"\\127.0.0.2\share\db_backups", r"\\?\C:\db_backups"])
def test_local_and_loopback_backup_roots_are_never_nas(path):
    assert not IS_NAS_DESTINATION(Path(path))


def test_unreadable_destination_fails_before_mysql(settings, monkeypatch):
    root = settings["backup_root"] / "missing-mount"
    settings["backup_root"] = root
    monkeypatch.setattr(nas.FileSystemControlledFileStorage, "readiness", lambda *_: SimpleNamespace(ready=False))
    monkeypatch.setattr(nas, "reader", lambda *_: pytest.fail("offline destination must precede database connection"))
    with pytest.raises(nas.MaintenanceBlocked, match="無法讀取"):
        nas.backup(settings)
    assert root.is_dir() and not list(root.iterdir())


def test_denied_nas_write_fails_before_dump_without_local_fallback(settings, monkeypatch):
    original = Path.open
    def deny_probe(path, *args, **kwargs):
        if path.name.startswith(".readiness-"):
            raise PermissionError("synthetic denied NAS")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", deny_probe)
    monkeypatch.setattr(nas, "reader", lambda *_: pytest.fail("write readiness precedes source query"))
    with pytest.raises(nas.MaintenanceBlocked, match="不會改存本機"):
        nas.backup(settings)
    assert not list(settings["backup_root"].rglob("*.gz"))


@pytest.mark.parametrize("shared_account", [False, True])
def test_dry_run_never_connects_creates_backup_or_registers_task(settings, monkeypatch, shared_account):
    if shared_account:
        path = settings["settings_file"]
        content = path.read_text(encoding="utf-8")
        path.write_text(content.replace("fixture_reader", "root").replace("fixture_writer", "root")
                        .replace("fixture_readonly", "fixture_shared").replace("fixture_admin", "fixture_shared"), encoding="utf-8")
    monkeypatch.setattr(nas.shutil, "which", lambda name: name)
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("dry-run must not connect"))
    monkeypatch.setattr(nas, "configure_daily_backup", lambda *_args, **_kw: pytest.fail("must not schedule"))
    assert nas.main(["upgrade", "--dry-run", "--environment-file", str(settings["environment_file"]),
                     "--settings-file", str(settings["settings_file"])]) == 0
    assert not list(settings["backup_root"].iterdir())
    assert not nas.LOCAL_STATUS.exists()


def test_shared_root_still_uses_readonly_backup_session(settings, monkeypatch):
    path = settings["settings_file"]
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("fixture_reader", "root").replace("fixture_writer", "root")
                    .replace("fixture_readonly", "fixture_shared").replace("fixture_admin", "fixture_shared"), encoding="utf-8")
    loaded = nas.load_settings(settings["environment_file"], path)
    calls = []
    monkeypatch.setattr(nas.pymysql, "connect", lambda **kwargs: calls.append(kwargs))
    nas.reader(loaded).connect("union_db")
    nas.writer(loaded, "lu_nas_restore_fixture").connect("lu_nas_restore_fixture")
    assert all(call["user"] == "root" and call["password"] == "fixture_shared" for call in calls)
    assert calls[0]["init_command"] == "SET SESSION TRANSACTION READ ONLY"
    assert "init_command" not in calls[1]


@pytest.mark.parametrize("key", ["NAS_BACKUP_USER", "NAS_BACKUP_PASSWORD", "NAS_MAINTENANCE_USER", "NAS_MAINTENANCE_PASSWORD"])
def test_missing_maintenance_credential_uses_existing_runtime_account(settings, key):
    path = settings["settings_file"]
    path.write_text('\n'.join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith(key + "=")), encoding="utf-8")
    loaded = nas.load_settings(settings["environment_file"], path)
    expected = {"NAS_MAINTENANCE_USER": "fixture_app", "NAS_MAINTENANCE_PASSWORD": "fixture_runtime",
                "NAS_BACKUP_USER": "fixture_writer", "NAS_BACKUP_PASSWORD": "fixture_admin"}
    assert loaded["values"][key] == expected[key]


def make_backup(settings, monkeypatch, exit_code=0):
    monkeypatch.setattr(nas.shutil, "which", lambda name: name)
    monkeypatch.setattr(nas, "schema_inventory", lambda *_: {"tables": [{"name": "fixture", "kind": "BASE TABLE"}],
                         "charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"})
    monkeypatch.setattr(nas.migration, "server_identity", lambda *_: {"server": "fixture-server", "database": "union_db"})
    calls = []
    class Process:
        def __init__(self, command, **kwargs):
            self.stdout = io.BytesIO(b"-- MySQL dump\n-- Host: fixture    Database: union_db\n-- synthetic fixture\n-- Dump completed on 2026-10-30\n")
            self.code = exit_code
            calls.append((command, kwargs["env"]))
        def wait(self, **_): return self.code
        def poll(self): return self.code
        def kill(self): self.code = 9
    monkeypatch.setattr(nas.subprocess, "Popen", Process)
    return nas.backup(settings), calls


def test_first_backup_creates_only_fixed_child_under_existing_nas_root(settings, monkeypatch):
    root = settings["backup_root"]
    root.rmdir()
    archive, _ = make_backup(settings, monkeypatch)
    assert archive.is_file() and archive.parent.parent == root
    assert nas.validate_backup(archive)["status"] == "completed"


def test_missing_backup_root_is_created_for_first_backup(settings, monkeypatch):
    parent = settings["backup_root"].parent / "unavailable-share"
    settings["backup_root"] = parent / nas.BACKUP_FOLDER
    archive, _ = make_backup(settings, monkeypatch)
    assert archive.is_file() and archive.parent.parent == settings["backup_root"]
    assert parent.is_dir()


def test_readonly_status_does_not_create_missing_backup_child(settings):
    root = settings["backup_root"]
    root.rmdir()
    with pytest.raises(nas.MaintenanceBlocked, match="無法讀取"):
        nas.destination_ready(settings)
    assert not root.exists()


def test_denied_child_creation_stops_before_database_access(settings, monkeypatch):
    root = settings["backup_root"]
    root.rmdir()
    original = Path.mkdir
    def deny_child(path, *args, **kwargs):
        if path == root:
            raise PermissionError("synthetic NAS denied mkdir")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", deny_child)
    monkeypatch.setattr(nas, "reader", lambda *_: pytest.fail("creation failure must precede database access"))
    with pytest.raises(nas.MaintenanceBlocked, match="新增資料夾權限"):
        nas.backup(settings)
    assert not root.exists()


def test_restore_selection_prefers_default_backup_without_manual_path(settings, monkeypatch):
    archive, _ = make_backup(settings, monkeypatch)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "1")
    assert nas.choose_backup(settings) == archive
    assert len(prompts) == 1 and "備份編號" in prompts[0]


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_empty_default_backup_opens_file_picker_without_path_input(settings, monkeypatch, tmp_path, missing):
    archive, _ = make_backup(settings, monkeypatch)
    default = tmp_path / "new-share" / nas.BACKUP_FOLDER
    if not missing:
        default.mkdir(parents=True)
    settings["backup_root"] = default
    calls = []
    monkeypatch.setattr(nas, "select_backup_file", lambda current: calls.append(current["backup_root"]) or archive)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("must not ask the operator to type a path"))
    assert nas.choose_backup(settings) == archive
    assert calls == [default]
    assert settings["backup_root"] == default and default.exists() == (not missing)


def test_restore_main_accepts_manual_file_before_any_default_destination_or_database_check(settings, monkeypatch, tmp_path):
    archive, _ = make_backup(settings, monkeypatch)
    settings["backup_root"] = tmp_path / "new-share" / nas.BACKUP_FOLDER
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("restore does not prompt for confirmation"))
    monkeypatch.setattr(nas, "select_backup_file", lambda *_: archive)
    monkeypatch.setattr(nas, "load_settings", lambda *_: settings)
    monkeypatch.setattr(nas, "writer", lambda *_: object())
    monkeypatch.setattr(nas, "maintenance_lock", lambda *_: nullcontext())
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("no database connection allowed"))
    calls = []
    monkeypatch.setattr(nas, "restore", lambda current, selected: calls.append((current["backup_root"], selected)) or tmp_path)
    assert nas.main(["restore"]) == 0
    assert calls == [(settings["backup_root"], archive)]
    assert not settings["backup_root"].exists()


@pytest.mark.skipif(os.name != "nt", reason="native Windows file picker transport")
def test_file_picker_uses_native_single_file_dialog_sta_utf8_and_no_user_timeout(settings, monkeypatch, tmp_path):
    settings["backup_root"] = tmp_path / "NAS O'Brien" / nas.BACKUP_FOLDER
    selected = str(tmp_path / "中文路徑" / "union_db_20261030_180000.sql.gz")
    calls = []
    monkeypatch.setattr(nas.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(returncode=0, stdout=selected))
    assert nas.select_backup_file(settings) == Path(selected)
    args, options = calls[0]
    assert "-STA" in args and options["timeout"] is None
    assert "-WindowStyle" not in args
    assert options["creationflags"] == nas.subprocess.CREATE_NO_WINDOW
    assert options["encoding"] == "utf-8"
    script = args[-1]
    assert "OpenFileDialog" in script and "*.zip;*.sql.gz" in script
    assert "$dialog.CheckFileExists=$true" in script and "$dialog.Multiselect=$false" in script
    assert "O''Brien" in script and "UTF8Encoding" in script


@pytest.mark.skipif(os.name != "nt", reason="native Windows file picker transport")
@pytest.mark.parametrize("returncode,message", [(0, "已取消"), (1, "無法開啟")])
def test_file_picker_cancel_or_failure_does_not_fall_back_to_typed_path(settings, monkeypatch, returncode, message):
    monkeypatch.setattr(nas, "run_windows_powershell", lambda *_args, **_kwargs: SimpleNamespace(returncode=returncode, stdout=""))
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("no typed-path fallback"))
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("cancel must not connect"))
    with pytest.raises(nas.MaintenanceBlocked, match=message):
        nas.select_backup_file(settings)


def test_verified_manual_source_is_read_only_and_restore_creates_no_journal_folder(settings, monkeypatch, tmp_path):
    archive, _ = make_backup(settings, monkeypatch)
    before = archive.read_bytes()
    parent = tmp_path / "replacement-share"
    parent.mkdir()
    settings["backup_root"] = parent / nas.BACKUP_FOLDER
    monkeypatch.setattr(nas, "writer", lambda *_: object())
    monkeypatch.setattr(nas, "maintenance_lock", lambda *_: nullcontext(object()))
    def stop_after_validation(*_):
        raise nas.MaintenanceBlocked("synthetic stop before database import")
    monkeypatch.setattr(nas, "_restore_server", stop_after_validation)
    with pytest.raises(nas.MaintenanceBlocked, match="synthetic stop"):
        nas.restore(settings, archive)
    assert not settings["backup_root"].exists()
    assert archive.read_bytes() == before


def test_manual_backup_parent_junction_is_rejected_before_database_access(settings, monkeypatch):
    archive, _ = make_backup(settings, monkeypatch)
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda path: path == archive.parent or original(path))
    monkeypatch.setattr(nas, "writer", lambda *_: pytest.fail("linked source must not connect"))
    with pytest.raises(nas.MaintenanceBlocked, match="轉接點"):
        nas.restore(settings, archive)


def test_daily_dump_is_complete_keeps_history_and_never_puts_password_in_arguments(settings, monkeypatch):
    first, calls = make_backup(settings, monkeypatch)
    second = nas.backup(settings)
    assert first != second and first.exists()
    assert nas.validate_backup(first)["status"] == "completed"
    assert first.parent.name == "2026-10" and first.name == "union_db_20261030_180000.zip"
    with zipfile.ZipFile(first, "r") as zf:
        assert set(zf.namelist()) == {
            "union_db_20261030_180000.sql.gz",
            "union_db_20261030_180000.sql.gz.sha256",
            "union_db_20261030_180000.json",
        }
        assert b"synthetic fixture" in gzip.decompress(zf.read("union_db_20261030_180000.sql.gz"))
    assert not list(settings["backup_root"].rglob("*.sql"))
    assert not list(settings["backup_root"].rglob("*.sql.gz"))
    assert not (settings["backup_root"] / "_receipts").exists()
    command, environment = calls[0]
    assert "--single-transaction" in command and "--quick" in command
    assert "--databases" not in command and "union_db" == command[-1]
    assert "fixture_readonly" not in " ".join(command)
    assert environment["MYSQL_PWD"] == "fixture_readonly"
    assert settings["environment_file"].read_bytes().startswith(b"# untouched\r\n")


def test_failed_dump_keeps_old_backup_and_partial_cannot_be_restored(settings, monkeypatch):
    first, _ = make_backup(settings, monkeypatch)
    before = first.read_bytes()
    class FailedProcess:
        stdout = io.BytesIO(b"incomplete")
        def wait(self, **_): return 9
        def poll(self): return 9
        def kill(self): pass
    monkeypatch.setattr(nas.subprocess, "Popen", lambda *_args, **_kw: FailedProcess())
    with pytest.raises(nas.MaintenanceBlocked, match="未完成"):
        nas.backup(settings)
    assert first.read_bytes() == before
    partial = next((settings["backup_root"] / "_partial").glob("*/union_db_*.gz"))
    with pytest.raises(nas.MaintenanceBlocked, match="不能復原"):
        nas.validate_backup(partial)


def test_tampered_backup_stops_before_any_restore_connection(settings, monkeypatch):
    path, _ = make_backup(settings, monkeypatch)
    path.write_bytes(b"corrupted")
    monkeypatch.setattr(nas, "writer", lambda *_: pytest.fail("must verify before connecting"))
    with pytest.raises(nas.MaintenanceBlocked, match="檢查碼"):
        nas.restore(settings, path)


def _rewrite_zip_bundle(bundle: Path, transform) -> None:
    with zipfile.ZipFile(bundle, "r") as src:
        entries = {name: src.read(name) for name in src.namelist()}
    transform(entries)
    with zipfile.ZipFile(bundle, "w") as dst:
        for name, data in entries.items():
            ctype = zipfile.ZIP_STORED if name.endswith(".sql.gz") else zipfile.ZIP_DEFLATED
            dst.writestr(name, data, compress_type=ctype)


def test_tampered_checksum_stops_before_restore(settings, monkeypatch):
    path, _ = make_backup(settings, monkeypatch)
    sql_name = path.stem + ".sql.gz"
    _rewrite_zip_bundle(path, lambda entries: entries.__setitem__(
        sql_name + ".sha256", ('0' * 64 + "  " + sql_name + "\n").encode("ascii")
    ))
    monkeypatch.setattr(nas, "writer", lambda *_: pytest.fail("checksum failure must not connect"))
    with pytest.raises(nas.MaintenanceBlocked, match="檢查碼"):
        nas.restore(settings, path)


def test_full_disk_during_compression_never_publishes_success(settings, monkeypatch):
    first, _ = make_backup(settings, monkeypatch)
    original = first.read_bytes()
    def full_disk(*_args, **_kw):
        raise OSError("synthetic disk full")
    monkeypatch.setattr(nas.gzip.GzipFile, "write", full_disk)
    with pytest.raises(OSError):
        nas.backup(settings)
    assert [path for path, _ in nas.available_backups(settings)] == [first]
    assert first.read_bytes() == original


def test_bad_gzip_crc_is_rejected_even_with_matching_archive_checksum(settings, monkeypatch):
    import hashlib
    path, _ = make_backup(settings, monkeypatch)
    sql_name = path.stem + ".sql.gz"
    json_name = path.stem + ".json"
    def corrupt_inner_gzip(entries):
        truncated = entries[sql_name][:-6]
        entries[sql_name] = truncated
        new_hash = hashlib.sha256(truncated).hexdigest()
        info = json.loads(entries[json_name].decode("utf-8"))
        info.update(sha256=new_hash, size=len(truncated))
        entries[json_name] = json.dumps(info).encode("utf-8")
        entries[sql_name + ".sha256"] = f"{new_hash}  {sql_name}\n".encode("ascii")
    _rewrite_zip_bundle(path, corrupt_inner_gzip)
    monkeypatch.setattr(nas, "writer", lambda *_: pytest.fail("bad compression must not create a database"))
    with pytest.raises(nas.MaintenanceBlocked, match="壓縮檔損壞"):
        nas.restore(settings, path)


def test_uncommitted_pair_is_excluded_and_previous_archive_is_kept(settings, monkeypatch):
    first, _ = make_backup(settings, monkeypatch)
    original = first.read_bytes()
    monkeypatch.setattr(nas, "_publish_backup_bundle", lambda *_args: (_ for _ in ()).throw(OSError("synthetic publication failure")))
    with pytest.raises(OSError):
        nas.backup(settings)
    assert [path for path, _ in nas.available_backups(settings)] == [first]
    assert first.read_bytes() == original
    assert list(first.parent.glob("*.zip")) == [first]


def test_same_second_backup_never_overwrites_existing_artifact(settings, monkeypatch):
    first, calls = make_backup(settings, monkeypatch)
    monkeypatch.setattr(nas, "backup_time", lambda: datetime(2026, 10, 30, 18, 0, tzinfo=nas.TAIPEI))
    original = first.read_bytes()
    with pytest.raises(nas.MaintenanceBlocked, match="不覆寫"):
        nas.backup(settings)
    assert len(calls) == 1 and first.read_bytes() == original


def test_offline_failure_is_visible_without_claiming_backup_readiness(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(nas, "SCHEDULE", tmp_path / "schedule.json")
    monkeypatch.setattr(nas, "load_settings", lambda *_, **_kw: settings)
    nas.record_backup_result(settings, "passed", created_at="2026-10-30T10:00:00+00:00")
    settings["backup_root"] = settings["backup_root"] / "offline"
    monkeypatch.setattr(nas.FileSystemControlledFileStorage, "readiness", lambda *_: SimpleNamespace(ready=False))
    assert nas.main(["backup", "--scheduled"]) == 2
    status = nas.backup_status()
    assert status["configured"] and not status["storage_ready"] and not status["disaster_recovery_ready"]
    assert status["last_result"]["status"] == "failed"
    assert status["last_backup"] == "2026-10-30T10:00:00+00:00"
    assert settings["backup_root"].is_dir() and not list(settings["backup_root"].iterdir())


def test_compressed_import_streams_sql_bytes_to_client_without_plaintext_file(tmp_path):
    payload = ("中文復原資料\n".encode() + b"\x00\xff") * 10000
    archive = tmp_path / "fixture.sql.gz"
    archive.write_bytes(gzip.compress(payload))
    bundle = tmp_path / "fixture.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.write(archive, arcname="fixture.sql.gz", compress_type=zipfile.ZIP_STORED)
    output = tmp_path / "digest.txt"
    command = [sys.executable, "-c", "import sys,hashlib;from pathlib import Path;h=hashlib.sha256();[(h.update(c)) for c in iter(lambda:sys.stdin.buffer.read(65536),b'')];Path(sys.argv[1]).write_text(h.hexdigest())", str(output)]
    import hashlib
    expected_digest = hashlib.sha256(payload).hexdigest()
    for source in (archive, bundle):
        output.unlink(missing_ok=True)
        result = nas.migration.restore_sql_dump(command, source, os.environ.copy())
        assert result.returncode == 0 and output.read_text() == expected_digest
    assert not list(tmp_path.glob("*.sql"))


def test_validate_dump_accepts_zip_bundle_with_bundle_digest(tmp_path):
    sql_bytes = b"-- MySQL dump\n-- Host: fixture    Database: union_db\n-- Dump completed on 2026-11-12\n"
    inner = tmp_path / "union_db_20261112_090000.sql.gz"
    inner.write_bytes(gzip.compress(sql_bytes))
    bundle = tmp_path / "union_db_20261112_090000.zip"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.write(inner, arcname=inner.name, compress_type=zipfile.ZIP_STORED)
    receipt = tmp_path / "backup.receipt.json"
    receipt.write_text(json.dumps({
        "kind": "source_backup", "database": "union_db",
        "server": "fixture-server", "sha256": nas.digest(bundle), "size": bundle.stat().st_size,
    }), encoding="utf-8")
    verified = nas.migration.validate_dump(bundle, receipt, "union_db", {"server": "fixture-server"})
    assert verified["sha256"] == nas.digest(bundle)


def test_legacy_three_file_backup_remains_discoverable_and_single_zip_deletion_is_clean(settings, monkeypatch):
    import hashlib
    bundle, _ = make_backup(settings, monkeypatch)
    root = settings["backup_root"]
    legacy_dir = root / "2026-09"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_archive = legacy_dir / "union_db_20260915_180000.sql.gz"
    raw_sql = b"-- MySQL dump\n-- Host: fixture    Database: union_db\n-- legacy\n-- Dump completed on 2026-09-15\n"
    compressed = gzip.compress(raw_sql)
    legacy_archive.write_bytes(compressed)
    archive_sha = hashlib.sha256(compressed).hexdigest()
    legacy_archive.with_suffix(".gz.sha256").write_text(f"{archive_sha}  {legacy_archive.name}\n", encoding="ascii")
    receipt = {
        "format": "nas-sql-backup/v2",
        "status": "completed",
        "created_at": "2026-09-15T10:00:00+00:00",
        "database": "union_db",
        "server": "fixture-server",
        "sha256": archive_sha,
        "size": len(compressed),
        "inventory": {"tables": [], "charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"},
        "archive": legacy_archive.name,
        "month": "2026-09",
        "sql_sha256": hashlib.sha256(raw_sql).hexdigest(),
        "sql_size": len(raw_sql),
    }
    nas.receipt_path(legacy_archive).parent.mkdir(parents=True, exist_ok=True)
    nas.receipt_path(legacy_archive).write_text(json.dumps(receipt), encoding="utf-8")

    listed = [path for path, _ in nas.available_backups(settings)]
    assert listed == [bundle, legacy_archive]
    assert nas.validate_backup(bundle)["status"] == "completed"
    assert nas.validate_backup(legacy_archive)["status"] == "completed"

    # Deleting the single .zip file completely removes that backup with zero sidecar files left.
    bundle.unlink()
    assert [path for path, _ in nas.available_backups(settings)] == [legacy_archive]


def test_arbitrary_external_file_is_not_executed_as_sql(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(nas, "writer", lambda *_: pytest.fail("untrusted paths must not connect"))
    with pytest.raises(nas.MaintenanceBlocked, match="不能復原"):
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


@pytest.mark.parametrize("deployment", ["pinned_remote", "unpinned_remote", "local_test", "windows_production"])
@pytest.mark.parametrize("verified", [False, True])
def test_upgrade_preserves_order_and_never_switches_when_validation_or_procedures_fail(
    settings, monkeypatch, tmp_path, request, deployment, verified,
):
    from scripts import update_local_database as updater

    steps = []
    local_test = deployment == "local_test"
    production = deployment == "windows_production"
    if deployment == "unpinned_remote":
        settings = request.getfixturevalue("unpinned_remote_settings")
    monkeypatch.setattr(nas, "is_nas_destination", lambda _: False)
    monkeypatch.setattr(updater, "update_local_database", lambda **_:
                        pytest.fail("NAS upgrade must not alter the configured source"))
    monkeypatch.setattr(nas, "protect_account_receipts", lambda *_args, **_kwargs: 0)
    if local_test:
        settings.update(host="127.0.0.1", database="lu_nas_fixture", settings_file=tmp_path / "absent")
    if production:
        monkeypatch.setenv("APP_ENV", "production")
        settings.update(host="127.0.0.1", database="lu_nas_upgrade_previous", settings_file=tmp_path / "absent")

    def candidate_preview(_config, database, _receipt_root):
        assert verified and database.startswith("lu_nas_upgrade_")
        steps.append("startup_check")
        return {"status": "current"} if production else {"status": "blocked"}

    monkeypatch.setattr(updater, "build_additive_preview", candidate_preview)
    if production:
        def require_current(preview):
            assert preview == {"status": "current"}
            return preview
        monkeypatch.setattr(updater, "require_current_database", require_current)
    monkeypatch.setattr(nas.shutil, "which", lambda name: name)
    source_connect = Mock(side_effect=AssertionError("upgrade must not read raw questionnaire answers"))
    monkeypatch.setattr(nas.pymysql, "connect", source_connect)

    def plan(*_args, **kwargs):
        assert kwargs["source_recovery_root"] == updater.DEFAULT_RECEIPT_ROOT
        steps.append("plan")
        return {
            "status": "ready",
            "candidate_exists": False,
            "source_objects": {
                "1037_twins_payroll_policy.sql": "absent" if local_test else "exact",
                "fixture.sql": "absent",
            },
            "source_data": {"beclass_records": {}, "orders": {}},
        }
    monkeypatch.setattr(nas.migration, "build_plan", plan)
    monkeypatch.setattr(nas, "backup", lambda *_: steps.append("backup") or tmp_path)
    monkeypatch.setattr(nas, "validate_backup", lambda *_: {"created_at": "fixture", "server": "fixture", "sha256": "a", "size": 1})
    monkeypatch.setattr(nas.migration, "restore_candidate", lambda *_: steps.append("restore"))
    def apply(*_args, **kwargs):
        assert kwargs["source_recovery_root"] == updater.DEFAULT_RECEIPT_ROOT
        steps.append("apply")
    monkeypatch.setattr(nas.migration, "apply_schema", apply)
    monkeypatch.setattr(nas, "schema_inventory", lambda *_args, **_kw: {})
    monkeypatch.setattr(nas.migration, "verify_candidate", lambda *_: steps.append("verify") or {
        "status": "verified" if verified else "failed",
    })
    def prepare(*_args):
        assert verified and not local_test
        steps.append("prepare")
    monkeypatch.setattr(nas, "prepare_runtime_access", prepare)
    connection = SimpleNamespace(close=lambda: steps.append("close"))
    monkeypatch.setattr(nas.migration.SeparateDatabaseConfig, "connect", lambda *_args: connection)
    from infrastructure.mysql import nas_mutations
    def install_procedures(actual):
        assert not production, "Windows production must not install NAS compatibility procedures"
        assert actual is connection
        steps.append("procedures")
        raise ValueError("NAS security procedure drift; no changes applied")
    monkeypatch.setattr(nas_mutations, "ensure_nas_procedures", install_procedures)
    def switch(_environment, source, candidate, *_receipts, config, environment_writer):
        assert production and verified
        assert source == "lu_nas_upgrade_previous"
        assert config.source.config.readonly
        assert config.candidate.config.candidate == candidate
        steps.append("switch")
    monkeypatch.setattr(nas.migration, "switch_environment", switch)
    before = settings["environment_file"].read_bytes()
    if verified and local_test:
        with pytest.raises(updater.LocalDatabaseUpdateError, match="release chain is not current"):
            nas.upgrade(settings)
    elif verified and production:
        assert nas.upgrade(settings)
    elif verified:
        with pytest.raises(ValueError, match="NAS security procedure drift"):
            nas.upgrade(settings)
    else:
        with pytest.raises(nas.MaintenanceBlocked, match="驗證未通過"):
            nas.upgrade(settings)
    assert steps == ["plan", "backup", "restore", "apply", "verify"] + (
        ["startup_check"] if verified and local_test
        else ["startup_check", "prepare", "switch"] if verified and production
        else ["prepare", "procedures", "close"] if verified
        else [])
    source_connect.assert_not_called()
    assert settings["environment_file"].read_bytes() == before


@pytest.mark.parametrize("source_state", ["exact", "absent", None])
def test_twins_backfill_runs_only_when_source_policy_is_not_current(monkeypatch, source_state):
    backfill = SimpleNamespace(
        backfill_id="twins-payroll-rate-snapshots-v1",
        artifact=SimpleNamespace(relative_path="scripts/backfill_twins_payroll_rate_snapshots.py"),
    )
    monkeypatch.setattr(nas.migration, "RELEASE_MANIFEST", SimpleNamespace(backfills=(backfill,)))
    source_objects = {} if source_state is None else {"1037_twins_payroll_policy.sql": source_state}
    assert nas.migration._required_manifest_backfills(source_objects) == (
        () if source_state == "exact" else (backfill,)
    )


def test_current_twins_policy_skips_backfill_without_reading_answers(monkeypatch, tmp_path):
    monkeypatch.setattr(nas.migration, "RELEASE_MANIFEST", SimpleNamespace(backfills=(
        SimpleNamespace(
            backfill_id="twins-payroll-rate-snapshots-v1",
            artifact=SimpleNamespace(relative_path="scripts/backfill_twins_payroll_rate_snapshots.py"),
        ),
    )))
    monkeypatch.setattr(nas.migration, "_candidate_preddl_dump",
                        Mock(side_effect=AssertionError("no backfill dump is needed")))
    config = Mock()
    assert nas.migration._run_manifest_backfills(
        config, "lu_nas_upgrade_fixture", tmp_path / "operation.json",
        mysql_container=None, source_objects={"1037_twins_payroll_policy.sql": "exact"},
    ) == ()
    config.connect.assert_not_called()


@pytest.mark.parametrize("missing", ["mysql", "mysqldump"])
def test_unpinned_remote_upgrade_requires_native_tools_before_database_access(
    unpinned_remote_settings, monkeypatch, missing,
):
    from scripts import update_local_database as updater

    monkeypatch.setattr(nas, "resolve_client_tool", lambda name: None if name == missing else name)
    monkeypatch.setattr(nas, "reader", lambda *_: pytest.fail("tools must be checked before connection"))
    monkeypatch.setattr(updater, "update_local_database", lambda **_: pytest.fail("no direct upgrade"))
    with pytest.raises(nas.MaintenanceBlocked, match="mysql 與 mysqldump"):
        nas.upgrade(unpinned_remote_settings)


def test_unpinned_remote_upgrade_accepts_local_backup_before_source_preflight(
    unpinned_remote_settings, monkeypatch,
):
    monkeypatch.setattr(nas, "resolve_client_tool", lambda name: name)
    monkeypatch.setattr(nas, "is_nas_destination", lambda _: False)
    def blocked_plan(*_args, **_kwargs):
        raise nas.migration.UpgradeBlocked("synthetic source preflight failure")
    monkeypatch.setattr(nas.migration, "build_plan", blocked_plan)
    monkeypatch.setattr(nas, "backup", lambda *_: pytest.fail("failed source preflight cannot start backup"))
    monkeypatch.setattr(nas.pymysql, "connect", lambda **_: pytest.fail("no live database"))
    with pytest.raises(nas.migration.UpgradeBlocked, match="synthetic source preflight failure"):
        nas.upgrade(unpinned_remote_settings)
    assert nas.destination_ready(unpinned_remote_settings, writable=True) == unpinned_remote_settings["backup_root"]


@pytest.mark.parametrize("state", ["partial", "drift"])
def test_unpinned_remote_upgrade_stops_at_source_preflight_without_backup_or_writes(
    unpinned_remote_settings, monkeypatch, state,
):
    from scripts import update_local_database as updater

    monkeypatch.setattr(nas, "resolve_client_tool", lambda name: name)
    def blocked_plan(*_args, **_kwargs):
        raise nas.migration.UpgradeBlocked(f"source contains {state} owned objects")
    monkeypatch.setattr(nas.migration, "build_plan", blocked_plan)
    monkeypatch.setattr(nas, "backup", lambda *_: pytest.fail("blocked source must be retained"))
    monkeypatch.setattr(updater, "update_local_database", lambda **_: pytest.fail("no direct retry"))
    with pytest.raises(nas.migration.UpgradeBlocked, match=state):
        nas.upgrade(unpinned_remote_settings)


def test_current_local_test_database_does_not_create_candidate(settings, monkeypatch, tmp_path):
    from scripts import update_local_database as updater

    settings.update(host="127.0.0.1", database="lu_nas_fixture", settings_file=tmp_path / "absent")
    monkeypatch.setattr(nas, "resolve_client_tool", lambda name: name)
    monkeypatch.setattr(nas.migration, "build_plan", lambda *_args, **_kwargs: {
        "status": "ready", "candidate_exists": False, "source_objects": {
            "fixture.sql": "exact", "1031_weekly_report_batches.sql": "absent",
        },
    })
    preview = {"status": "current"}
    monkeypatch.setattr(updater, "build_additive_preview", lambda *_: preview)
    checked = []
    monkeypatch.setattr(updater, "require_current_database", checked.append)
    monkeypatch.setattr(nas, "destination_ready", lambda *_args, **_kwargs:
                        pytest.fail("current schema needs no backup destination"))
    monkeypatch.setattr(nas, "backup", lambda *_: pytest.fail("current schema needs no upgrade"))
    assert nas.upgrade(settings) is None
    assert checked == [preview]


@pytest.mark.parametrize(
    "override",
    [
        {"host": "nas.invalid", "ssl_mode": "VERIFY_IDENTITY", "receipt_target_pinned": False},
        {"host": "nas.invalid", "ssl_mode": "DISABLED", "receipt_target_pinned": True},
        {"host": "127.0.0.1", "database": "union_db", "runtime": {"APP_ENV": "development"}},
        {"host": "127.0.0.1", "database": "lu_test_fixture", "runtime": {"APP_ENV": "production"}},
    ],
)
def test_receipt_conversion_refuses_unverified_target_before_connection(settings, monkeypatch, override):
    settings.update(override)
    monkeypatch.setattr(nas, "load_settings", lambda *_, **_kw: settings)
    monkeypatch.setattr(nas, "reader", lambda *_: pytest.fail("invalid receipt target must not connect"))
    assert nas.main(["protect-account-receipts"]) == 2


def test_receipt_conversion_allows_local_lu_nas_upgrade_in_development(settings):
    settings.update({"host": "127.0.0.1", "database": "lu_nas_upgrade_20261115133214_e5055f9a", "runtime": {"APP_ENV": "development"}})
    nas.require_account_receipt_conversion_target(settings)


def test_schedule_stale_is_typed_and_does_not_register(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(nas, "SCHEDULE", tmp_path / "schedule.json")
    nas.save(nas.SCHEDULE, {"version": 4, "time": "18:00", "enabled": True})
    monkeypatch.setattr(nas, "_configure_daily_backup", lambda *_args, **_kw: pytest.fail("stale must not register"))
    with pytest.raises(nas.ScheduleConflict):
        nas.configure_daily_backup("17:00", expected_version=3)


@pytest.mark.skipif(os.name != "nt", reason="Windows schedule command composition")
def test_daily_schedule_uses_hidden_interactive_account_without_password_and_records_version(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(nas, "SCHEDULE", tmp_path / "schedule.json")
    monkeypatch.setattr(nas, "load_settings", lambda *_args, **_kw: settings)
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


@pytest.mark.parametrize("source_grants,global_admin,blocked", [
    ([r"GRANT SELECT,INSERT ON `union\_db`.* TO `fixture_app`@`%`"], False, False),
    (["GRANT ALL PRIVILEGES ON *.* TO `fixture_app`@`%` WITH GRANT OPTION"], True, False),
    (["GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,DROP,REFERENCES,INDEX,ALTER,CREATE TEMPORARY TABLES,LOCK TABLES,EXECUTE,CREATE VIEW,SHOW VIEW,CREATE ROUTINE,ALTER ROUTINE,EVENT,TRIGGER ON *.* TO `fixture_app`@`%`"], True, False),
    (["GRANT SELECT ON *.* TO `fixture_app`@`%`"], False, True),
    (["GRANT ALL PRIVILEGES ON *.* TO `fixture_app`@`%`", "REVOKE SELECT ON `union_db`.* FROM `fixture_app`@`%`"], False, True),
])
def test_schema_access_copies_only_schema_grants_and_preserves_existing_global_admin(settings, monkeypatch, source_grants, global_admin, blocked):
    commands = []
    databases = []
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
            return [{"grant": grant} for grant in source_grants]
    connection = SimpleNamespace(cursor=lambda: Cursor(), close=lambda: None)
    config = SimpleNamespace(connect=lambda *args: databases.append(args) or connection)
    monkeypatch.setattr(nas, "writer", lambda *_: config)
    if blocked:
        with pytest.raises(nas.MaintenanceBlocked, match="特殊權限配置"):
            nas._copy_schema_access(settings, "lu_nas_restore_fixture", config)
    else:
        nas._copy_schema_access(settings, "lu_nas_restore_fixture", config)
    grants = [sql for sql, _ in commands if sql.startswith("GRANT ")]
    assert grants == ([] if global_admin or blocked else [r"GRANT INSERT,SELECT ON `lu\_nas\_restore\_fixture`.* TO %s@%s"])
    assert (("lu_nas_restore_fixture",) in databases) == (not blocked)
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


def test_resolve_client_tool_prioritizes_tools_mysql_folder(tmp_path, monkeypatch):
    tool_dir = tmp_path / "tools" / "mysql"
    tool_dir.mkdir(parents=True)
    fake_dump = tool_dir / ("mysqldump.exe" if os.name == "nt" else "mysqldump")
    fake_dump.write_text("dummy binary", encoding="utf-8")
    monkeypatch.setattr(nas, "ROOT", tmp_path)
    monkeypatch.setattr(nas.shutil, "which", lambda _: "fallback_from_path")

    resolved = nas.resolve_client_tool("mysqldump")
    assert resolved == str(fake_dump.resolve())
    assert nas.resolve_client_tool("mysql") == "fallback_from_path"


def test_verify_restored_inventory_semantic_match_and_mismatches():
    base = {
        "tables": [{"name": "members", "kind": "BASE TABLE"}, {"name": "v_members", "kind": "VIEW"}],
        "triggers": ["trg_members_update"],
        "routines": ["sp_calculate_fees"],
        "events": ["ev_daily_sync"],
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
        "definitions_sha256": "abc123expected",
    }
    # 1. definitions_sha256 與 collation 格式不同，但語意物件結構完全吻合 -> 放行通過
    actual_diff_sha = {
        "tables": [{"name": "members", "kind": "BASE TABLE"}, {"name": "v_members", "kind": "VIEW"}],
        "triggers": ["trg_members_update"],
        "routines": ["sp_calculate_fees"],
        "events": ["ev_daily_sync"],
        "charset": "utf8mb4",
        "collation": "utf8mb4_0900_ai_ci",
        "definitions_sha256": "xyz789drift",
    }
    nas.verify_restored_inventory(actual_diff_sha, base)

    # 2. 缺少表格 -> 拋出 MaintenanceBlocked 並指出缺少表格
    actual_missing_table = {
        "tables": [{"name": "v_members", "kind": "VIEW"}],
        "triggers": ["trg_members_update"],
        "routines": ["sp_calculate_fees"],
        "events": ["ev_daily_sync"],
        "charset": "utf8mb4",
    }
    with pytest.raises(nas.MaintenanceBlocked, match=r"缺少資料表: \['members'\]"):
        nas.verify_restored_inventory(actual_missing_table, base)

    # 3. 多出非預期表格
    actual_extra_table = {
        "tables": [{"name": "members", "kind": "BASE TABLE"}, {"name": "v_members", "kind": "VIEW"}, {"name": "hacked", "kind": "BASE TABLE"}],
        "triggers": ["trg_members_update"],
        "routines": ["sp_calculate_fees"],
        "events": ["ev_daily_sync"],
        "charset": "utf8mb4",
    }
    with pytest.raises(nas.MaintenanceBlocked, match=r"多出非預期資料表: \['hacked'\]"):
        nas.verify_restored_inventory(actual_extra_table, base)

    # 4. 表格型態不符
    actual_kind_mismatch = {
        "tables": [{"name": "members", "kind": "VIEW"}, {"name": "v_members", "kind": "VIEW"}],
        "triggers": ["trg_members_update"],
        "routines": ["sp_calculate_fees"],
        "events": ["ev_daily_sync"],
        "charset": "utf8mb4",
    }
    with pytest.raises(nas.MaintenanceBlocked, match=r"資料表型態不符: \['members'\]"):
        nas.verify_restored_inventory(actual_kind_mismatch, base)

    # 5. 缺少觸發程序或預存程序
    actual_missing_routine = {
        "tables": [{"name": "members", "kind": "BASE TABLE"}, {"name": "v_members", "kind": "VIEW"}],
        "triggers": ["trg_members_update"],
        "routines": [],
        "events": ["ev_daily_sync"],
        "charset": "utf8mb4",
    }
    with pytest.raises(nas.MaintenanceBlocked, match="缺少預存程序或函數"):
        nas.verify_restored_inventory(actual_missing_routine, base)

    # 6. 字元集不一致
    actual_wrong_charset = {
        "tables": [{"name": "members", "kind": "BASE TABLE"}, {"name": "v_members", "kind": "VIEW"}],
        "triggers": ["trg_members_update"],
        "routines": ["sp_calculate_fees"],
        "events": ["ev_daily_sync"],
        "charset": "latin1",
    }
    with pytest.raises(nas.MaintenanceBlocked, match="字元集不相符"):
        nas.verify_restored_inventory(actual_wrong_charset, base)


@pytest.fixture
def same_name_restore(settings, monkeypatch):
    archive, _ = make_backup(settings, monkeypatch)
    inventory = nas.validate_backup(archive)["inventory"]
    database = settings["database"]
    original = settings["environment_file"].read_bytes()
    server = {"id": "11111111-1111-4111-8111-111111111111"}
    data = {database: "original", "lu_test_neighbor": "neighbor"}
    defaults = {}
    steps = []
    fail = set()

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, statement, values=()):
            self.row = None
            if statement.startswith("CREATE DATABASE "):
                name = statement.split('`')[1]
                steps.append(("create", name))
                assert name not in data
                data[name] = None
                defaults[name] = {key: inventory[key] for key in ("charset", "collation")}
                if name == database and "create_unknown" in fail:
                    raise nas.MaintenanceBlocked("target create result lost")
            elif statement.startswith("DROP DATABASE "):
                name = statement.split('`')[1]
                steps.append(("drop", name))
                del data[name]
                if name == database and "drop_unknown" in fail:
                    raise nas.MaintenanceBlocked("target drop result lost")
            elif "default_character_set_name AS charset" in statement:
                self.row = defaults[values[0]] if data.get(values[0]) is None else None
            elif "information_schema.processlist" in statement:
                self.row = {"n": int("busy" in fail)}
            else:
                steps.append(("migration_sql", statement))

        def fetchone(self):
            return self.row

    connection = SimpleNamespace(cursor=Cursor, close=lambda: None)
    config = SimpleNamespace(host=settings["host"], port=settings["port"], user="fixture", password="fixture",
                             connect=lambda *_: connection, client_prefix=lambda *_: ["mysql"])
    lock = Mock(side_effect=lambda _: nullcontext(connection))
    monkeypatch.setattr(nas, "maintenance_lock", lock)
    monkeypatch.setattr(nas, "writer", lambda *_: config)
    monkeypatch.setattr(nas, "_restore_server", lambda _: (server["id"], "fixture-server"))
    monkeypatch.setattr(nas, "_restore_read_server", lambda _: (server["id"], "fixture-server"))
    monkeypatch.setattr(nas, "schema_inventory", lambda *_, **__: inventory)
    monkeypatch.setattr(nas.migration, "database_exists", lambda _, target: target in data)
    monkeypatch.setattr(nas, "_restore_check_credentials", lambda _, target, uuid: steps.append(("credentials", target)))
    monkeypatch.setattr(nas, "prepare_runtime_access", lambda _, target, **__: steps.append(("prepare", target)))
    monkeypatch.setattr(nas, "protect_account_receipts", lambda _, target, **__: steps.append(("protect", target)))
    monkeypatch.setattr(nas, "switch_runtime", lambda *args: pytest.fail("restore must keep .env bytes"))
    monkeypatch.setattr(nas, "require_event_scheduler_safe", lambda *_: None)

    def evidence(_, target, **kwargs):
        if target not in data or data[target] is None:
            raise nas.MaintenanceBlocked("missing evidence")
        return {
            "schema_sha256": "a" * 64,
            "rows": {"fixture": {"count": 1, "primary_key_sha256": "b" * 64,
                                 "full_row_sha256": nas._restore_hash(data[target])}},
        }

    monkeypatch.setattr(nas, "_restore_evidence", evidence)
    real_backup = nas.backup

    def backup(current, **kwargs):
        kind = kwargs["operation_root"].name
        steps.append(("backup", kind))
        if kind in fail:
            raise nas.MaintenanceBlocked("backup stage failed")
        return real_backup(current, **kwargs)

    monkeypatch.setattr(nas, "backup", backup)

    def import_sql(command, path, _):
        target = command[-1]
        steps.append(("import", target))
        assert {"--binary-mode", "--one-database"} <= set(command)
        if "candidate_import" in fail and target != database:
            return SimpleNamespace(returncode=1)
        if target == database:
            assert path != archive and path.parent.parent.name == "verified"
            if "target_import" in fail:
                data[target] = "partial"
                return SimpleNamespace(returncode=1)
        else:
            assert path == archive
        data[target] = "restored"
        return SimpleNamespace(returncode=int("target_import_unknown" in fail and target == database))

    monkeypatch.setattr(nas.migration, "restore_sql_dump", import_sql)
    from scripts import update_local_database as updater
    from infrastructure.mysql import nas_mutations
    monkeypatch.setattr(updater, "build_additive_preview", lambda *_: {"status": "current"})
    monkeypatch.setattr(updater, "require_current_database", lambda _: None)
    monkeypatch.setattr(nas_mutations, "ensure_nas_procedures", lambda _: steps.append(("procedures", None)))

    def startup_blocked():
        return nas.restore_startup_blocked(settings["host"], settings["port"], database,
                                           environment_file=settings["environment_file"])

    return SimpleNamespace(archive=archive, archive_bytes=archive.read_bytes(), data=data, steps=steps, fail=fail,
                           original=original, settings=settings, database=database, lock=lock,
                           startup_blocked=startup_blocked, server=server)


@pytest.mark.parametrize("conversion_ok", [True, False])
@pytest.mark.parametrize("procedures_ok", [True, False])
def test_restore_automatically_applies_pending_additive_migration(same_name_restore, monkeypatch, conversion_ok, procedures_ok):
    flow = same_name_restore
    from scripts import update_local_database as updater
    from infrastructure.mysql import nas_mutations
    previews = []

    def preview(_, database, run):
        previews.append(database)
        if len(previews) == 1:
            return {"status": "ready", "pending_releases": [{"release_id": "labor-union-hcm-review-status-2026-11-06-v1"}]}
        return {"status": "current"}

    def convert(_, database, *, apply):
        assert apply
        flow.steps.append(("protect", database))
        if not conversion_ok:
            raise nas.MaintenanceBlocked("fixture receipt conversion failed")

    def procedures(_):
        flow.steps.append(("procedures", None))
        if not procedures_ok:
            raise ValueError("NAS security procedure drift")

    monkeypatch.setattr(updater, "build_additive_preview", preview)
    monkeypatch.setattr(nas, "protect_account_receipts", convert)
    monkeypatch.setattr(nas_mutations, "ensure_nas_procedures", procedures)

    if conversion_ok and procedures_ok:
        nas.restore(flow.settings, flow.archive)
        assert flow.data[flow.database] == "restored"
        assert previews[-1] == flow.database
        assert [step[0] for step in flow.steps if step[0] in {"protect", "prepare", "procedures"}] == [
            "protect", "procedures", "prepare",
        ]
    else:
        match = "固定程序準備失敗" if conversion_ok else "fixture receipt conversion failed"
        with pytest.raises(nas.MaintenanceBlocked, match=match):
            nas.restore(flow.settings, flow.archive)
        assert flow.data[flow.database] == "original"
        assert not any(action == "drop" and target == flow.database for action, target in flow.steps)
        assert ("procedures", None) in flow.steps if conversion_ok else ("procedures", None) not in flow.steps
    assert len(previews) >= 2
    assert any(action == "migration_sql" and "hcm_review_status" in value for action, value in flow.steps)


def test_restore_blocks_incompatible_version_with_clear_reason(same_name_restore, monkeypatch):
    flow = same_name_restore
    from scripts import update_local_database as updater
    monkeypatch.setattr(updater, "build_additive_preview", lambda *_: {
        "status": "blocked", "blocked_reason": "schema_state_drift_detected",
    })
    with pytest.raises(nas.MaintenanceBlocked, match="不相容.*schema_state_drift_detected"):
        nas.restore(flow.settings, flow.archive)
    assert flow.data[flow.database] == "original"
    assert not (flow.settings["backup_root"] / "_maintenance").exists()
    assert not any(name.startswith("lu_nas_restore_") for name in flow.data)

    monkeypatch.setattr(updater, "build_additive_preview", lambda *_: {
        "status": "blocked",
        "code": "baseline_not_exact",
        "blocked_reason": "approved baseline is not exact: 000_base.sql=partial",
    })
    with pytest.raises(nas.MaintenanceBlocked, match=r"baseline_not_exact：approved baseline is not exact"):
        nas.restore(flow.settings, flow.archive)


@pytest.mark.parametrize("missing_target", [False, True])
def test_same_name_restore_twice_leaves_no_maintenance_folders(same_name_restore, missing_target):
    flow = same_name_restore
    other = flow.archive.with_name("other.zip")
    other.write_bytes(b"unrelated backup")
    if missing_target:
        del flow.data[flow.database]
    for _ in range(2):
        nas.restore(flow.settings, flow.archive)
        assert flow.data == {flow.database: "restored", "lu_test_neighbor": "neighbor"}
        assert not (flow.settings["backup_root"] / "_maintenance").exists()
        assert not (flow.settings["environment_file"].parent / "scratch/nas_database_maintenance/same-name-restore.json").exists()
        assert flow.archive.read_bytes() == flow.archive_bytes
        assert other.read_bytes() == b"unrelated backup"
        assert flow.settings["environment_file"].read_bytes() == flow.original
        assert not flow.startup_blocked()


@pytest.mark.parametrize("failure", ["candidate_import", "verified"])
def test_failure_before_replacement_cleans_up_temp_artifacts_and_allows_retry(same_name_restore, failure):
    flow = same_name_restore
    flow.fail.add(failure)
    with pytest.raises(nas.MaintenanceBlocked):
        nas.restore(flow.settings, flow.archive)
    assert flow.data[flow.database] == "original"
    assert flow.archive.read_bytes() == flow.archive_bytes
    assert not any(action == "drop" and target == flow.database for action, target in flow.steps)
    assert not any(name.startswith("lu_nas_restore_") for name in flow.data)
    assert not (flow.settings["backup_root"] / "_maintenance").exists()
    assert not (flow.settings["environment_file"].parent / "scratch/nas_database_maintenance/same-name-restore.json").exists()
    flow.fail.clear()
    nas.restore(flow.settings, flow.archive)
    assert flow.data[flow.database] == "restored"
    assert not any(name.startswith("lu_nas_restore_") for name in flow.data)


# NAS-RET-01..04: tmp_path ZIPs only; no connection to an actual NAS or DB.
def retention_bundle(settings, moment, *, managed=True, host=None, database=None):
    moment = datetime.fromisoformat(moment).replace(tzinfo=nas.TAIPEI)
    stem = moment.strftime("union_db_%Y%m%d_%H%M%S")
    folder = settings["backup_root"] / moment.strftime("%Y-%m")
    folder.mkdir(exist_ok=True)
    path = folder / (stem + ".zip")
    sql = b"-- synthetic fixture\n-- Dump completed on fixture\n"
    packed = gzip.compress(sql)
    archive = stem + ".sql.gz"
    sha = nas.hashlib.sha256(packed).hexdigest()
    receipt = {"format":"nas-sql-backup/v2", "status":"completed", "created_at":moment.isoformat(),
        "database":database or settings["database"], "host":host or settings["host"], "port":settings["port"],
        "sha256":sha, "size":len(packed), "archive":archive, "bundle":path.name, "month":folder.name,
        "sql_sha256":nas.hashlib.sha256(sql).hexdigest(), "sql_size":len(sql), "retention_managed":managed}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(archive, packed)
        zf.writestr(archive + ".sha256", sha + "  " + archive + "\n")
        zf.writestr(stem + ".json", json.dumps(receipt))
    return path


@pytest.mark.parametrize("custom_root", [False, True])
def test_retention_union_calendar_boundaries_latest_representatives_and_idempotency(settings, tmp_path, custom_root):
    if custom_root:
        settings["backup_root"] = tmp_path / "custom-backup-folder"
        settings["backup_root"].mkdir()
    moments = ["2025-12-31T18:00:00", "2026-01-31T18:00:00", "2026-02-15T18:00:00",
        "2026-02-28T18:00:00", "2026-11-15T18:00:00", "2026-11-21T18:00:00",
        "2026-11-22T18:00:00", "2026-11-30T18:00:00", "2026-12-22T18:00:00",
        "2026-12-23T18:00:00", "2026-12-27T18:00:00", "2026-12-31T18:00:00",
        "2027-01-05T18:00:00", "2027-01-05T19:00:00"]
    paths = {day:retention_bundle(settings, day) for day in moments}
    latest = paths["2027-01-05T18:00:00"]
    now = datetime(2027, 1, 5, 18, tzinfo=nas.TAIPEI)
    expired = {"2025-12-31T18:00:00", "2026-01-31T18:00:00", "2026-02-15T18:00:00",
               "2026-11-15T18:00:00", "2026-11-21T18:00:00", "2026-12-22T18:00:00"}
    assert nas.retain_scheduled_backups(settings, latest, now=now) == len(expired)
    assert {key for key,path in paths.items() if not path.exists()} == expired
    assert nas.retain_scheduled_backups(settings, latest, now=now) == 0
    journals = list((settings["backup_root"] / "_retention").glob("*.json"))
    assert len(journals) == 1
    receipt = json.loads(journals[0].read_text(encoding="utf-8"))
    assert receipt["status"] == "completed" and len(receipt["removed"]) == len(expired)
    assert {r["file"] for r in receipt["planned"]} == set(receipt["removed"])
    assert len(list(settings["backup_root"].glob("????-??/*.zip"))) == len(moments) - len(expired)


def test_retention_future_same_week_does_not_displace_valid_representative(settings):
    now = datetime(2027, 1, 5, 18, tzinfo=nas.TAIPEI)
    latest = retention_bundle(settings, "2027-01-05T18:00:00")
    previous = retention_bundle(settings, "2026-11-22T18:00:00")
    monthly = retention_bundle(settings, "2026-11-30T18:00:00")
    future = retention_bundle(settings, "2027-01-06T18:00:00")
    assert nas.retain_scheduled_backups(settings, latest, now=now) == 0
    assert all(path.exists() for path in (latest, previous, monthly, future))


def test_retention_preserves_unmarked_wrong_target_legacy_and_partial(settings):
    latest = retention_bundle(settings, "2027-01-05T18:00:00")
    unmarked = retention_bundle(settings, "2025-01-01T18:00:00", managed=None)
    other = retention_bundle(settings, "2025-01-02T18:00:00", host="other.invalid")
    other_db = retention_bundle(settings, "2025-01-03T18:00:00", database="other_db")
    legacy = unmarked.parent / "union_db_20250104_180000.sql.gz"
    legacy.write_bytes(b"legacy")
    partial = settings["backup_root"] / "_partial" / "fixture.pending"
    partial.parent.mkdir();partial.write_bytes(b"incomplete")
    before = {path:path.read_bytes() for path in (unmarked, other, other_db, legacy, partial)}
    assert nas.retain_scheduled_backups(settings, latest, now=datetime(2027,1,5,18,tzinfo=nas.TAIPEI)) == 0
    assert all(path.read_bytes() == content for path,content in before.items())


@pytest.mark.parametrize("damage", ["payload", "symlink", "junction"])
def test_retention_damage_blocks_all_removals(settings, monkeypatch, damage):
    latest = retention_bundle(settings, "2027-01-05T18:00:00")
    old = retention_bundle(settings, "2025-01-01T18:00:00")
    damaged = retention_bundle(settings, "2025-02-01T18:00:00")
    if damage == "payload":
        # Keep a valid receipt but tamper the payload, as a NAS corruption would.
        with zipfile.ZipFile(damaged) as zf:
            entries = {name:zf.read(name) for name in zf.namelist()}
        name = next(name for name in entries if name.endswith(".sql.gz"))
        entries[name] = b"damaged"
        with zipfile.ZipFile(damaged,"w") as zf:
            for name, value in entries.items():zf.writestr(name,value)
    else:
        method = "is_symlink" if damage == "symlink" else "is_junction"
        original = getattr(Path,method)
        monkeypatch.setattr(Path,method,lambda self: self==damaged.parent or original(self))
    with pytest.raises(nas.MaintenanceBlocked):
        nas.retain_scheduled_backups(settings,latest,now=datetime(2027,1,5,18,tzinfo=nas.TAIPEI))
    assert old.exists() and damaged.exists() and latest.exists()
    assert not (settings["backup_root"] / "_retention").exists()


def test_retention_new_scheduled_receipt_marker_only(settings, monkeypatch):
    manual, _ = make_backup(settings, monkeypatch)
    settings["scheduled_backup"] = True
    scheduled = nas.backup(settings)
    assert nas.validate_backup(manual)["retention_managed"] is False
    assert nas.validate_backup(scheduled)["retention_managed"] is True


def test_retention_backup_failure_never_runs_cleanup(settings, monkeypatch):
    monkeypatch.setattr(nas,"load_settings",lambda *_, **_kw:settings)
    monkeypatch.setattr(nas,"maintenance_lock",lambda *_:nullcontext())
    monkeypatch.setattr(nas,"backup",lambda *_: (_ for _ in ()).throw(nas.MaintenanceBlocked("synthetic failure")))
    monkeypatch.setattr(nas,"retain_scheduled_backups",lambda *_:pytest.fail("failed backup cannot clean"))
    assert nas.main(["backup","--scheduled"]) == 2


def test_retention_cleanup_failure_preserves_success_status_and_failure_receipt(settings, monkeypatch):
    latest = retention_bundle(settings, "2027-01-05T18:00:00")
    monkeypatch.setattr(nas,"load_settings",lambda *_, **_kw:settings)
    monkeypatch.setattr(nas,"maintenance_lock",lambda *_:nullcontext())
    monkeypatch.setattr(nas,"backup",lambda *_:latest)
    monkeypatch.setattr(nas,"retain_scheduled_backups",lambda *_: (_ for _ in ()).throw(nas.MaintenanceBlocked("synthetic failure")))
    assert nas.main(["backup","--scheduled"]) == 0
    status=json.loads(nas.LOCAL_STATUS.read_text(encoding="utf-8"))
    assert status["status"]=="passed" and status["last_success"]
    assert status["message"] == "備份已完成，過期備份清理未完成；請通知維護人員。"
    receipt=json.loads(next((settings["backup_root"] / "_retention").glob("*.json")).read_text(encoding="utf-8"))
    assert receipt["status"]=="failed" and latest.exists()

"""NAS SQL maintenance: no local target, no source reset, verified switch only."""
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
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts import nas_database_maintenance as nas
IS_NAS_DESTINATION = nas.is_nas_destination


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


def test_missing_shared_storage_root_has_no_local_default_or_legacy_override(settings):
    path = settings["environment_file"]
    path.write_text('\n'.join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("CONTROLLED_FILE_STORAGE_ROOT=")), encoding="utf-8")
    config = settings["settings_file"]
    config.write_text(config.read_text(encoding="utf-8") + 'NAS_BACKUP_DIR=\\\\other.invalid\\legacy\\' + nas.BACKUP_FOLDER + '\n', encoding="utf-8")
    with pytest.raises(nas.MaintenanceBlocked, match="不會改存本機"):
        nas.load_settings(path, config)


def test_backup_destination_is_derived_only_from_runtime_storage_root(settings):
    config = settings["settings_file"]
    config.write_text(config.read_text(encoding="utf-8") + 'NAS_BACKUP_DIR=\\\\other.invalid\\legacy\n', encoding="utf-8")
    loaded = nas.load_settings(settings["environment_file"], config)
    assert loaded["backup_root"] == Path(r"\\nas.invalid\fixture") / nas.BACKUP_FOLDER


def test_process_storage_override_cannot_redirect_backup(settings, monkeypatch):
    monkeypatch.setenv("CONTROLLED_FILE_STORAGE_ROOT", r"\\other.invalid\share")
    with pytest.raises(nas.MaintenanceBlocked, match="執行環境與設定檔不同"):
        nas.load_settings(settings["environment_file"], settings["settings_file"])


def test_windows_source_mode_flag_does_not_override_pinned_nas_target(settings, monkeypatch):
    path = settings["environment_file"]
    path.write_text(path.read_text(encoding="utf-8") + "APP_ENV=production\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "development")
    assert nas.load_settings(path, settings["settings_file"])["host"] == "nas.invalid"
    monkeypatch.setenv("DB_HOST", "other.invalid")
    with pytest.raises(nas.MaintenanceBlocked, match="執行環境與設定檔不同"):
        nas.load_settings(path, settings["settings_file"])


@pytest.mark.parametrize("root", ["D:/backups", "Z:/share", r"\\localhost\share"])
def test_runtime_local_storage_root_is_rejected_for_nas_backup(settings, monkeypatch, root):
    monkeypatch.setattr(nas, "is_nas_destination", IS_NAS_DESTINATION)
    path = settings["environment_file"]
    path.write_text(path.read_text(encoding="utf-8").replace(r"\\nas.invalid\fixture", root), encoding="utf-8")
    with pytest.raises(nas.MaintenanceBlocked, match="完整 UNC 路徑"):
        nas.load_settings(path, settings["settings_file"])


@pytest.mark.parametrize("path", ["D:/LaborUnionBackups", "C:/work/05_資料庫冷備份 (db_backups)", r"\\localhost\share\db_backups", r"\\127.0.0.2\share\db_backups", r"\\?\C:\db_backups"])
def test_local_and_loopback_backup_roots_are_never_nas(path):
    assert not IS_NAS_DESTINATION(Path(path))


def test_offline_nas_fails_before_mysql_and_does_not_create_root(settings, monkeypatch):
    root = settings["backup_root"] / "missing-mount"
    settings["backup_root"] = root
    monkeypatch.setattr(nas, "reader", lambda *_: pytest.fail("offline destination must precede database connection"))
    with pytest.raises(nas.MaintenanceBlocked, match="無法讀取"):
        nas.backup(settings)
    assert not root.exists()


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
def test_each_maintenance_credential_remains_required(settings, key):
    path = settings["settings_file"]
    path.write_text('\n'.join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith(key + "=")), encoding="utf-8")
    with pytest.raises(nas.MaintenanceBlocked, match="缺少備份或升級維護帳號"):
        nas.load_settings(settings["environment_file"], path)


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


def test_missing_nas_root_is_never_created(settings, monkeypatch):
    parent = settings["backup_root"].parent / "unavailable-share"
    settings["backup_root"] = parent / nas.BACKUP_FOLDER
    monkeypatch.setattr(nas, "reader", lambda *_: pytest.fail("missing share must precede database access"))
    with pytest.raises(nas.MaintenanceBlocked, match="不會自動建立共用根目錄"):
        nas.backup(settings)
    assert not parent.exists()


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
    monkeypatch.setattr("builtins.input", lambda *_: "確認")
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


def test_verified_manual_source_is_read_only_and_restore_creates_default_journal_folder(settings, monkeypatch, tmp_path):
    archive, _ = make_backup(settings, monkeypatch)
    before = archive.read_bytes()
    parent = tmp_path / "replacement-share"
    parent.mkdir()
    settings["backup_root"] = parent / nas.BACKUP_FOLDER
    monkeypatch.setattr(nas, "writer", lambda *_: SimpleNamespace(client_prefix=lambda *_: None))
    def stop_after_validation(*_):
        raise nas.MaintenanceBlocked("synthetic stop before database import")
    monkeypatch.setattr(nas, "require_event_scheduler_safe", stop_after_validation)
    with pytest.raises(nas.MaintenanceBlocked, match="synthetic stop"):
        nas.restore(settings, archive)
    assert settings["backup_root"].is_dir()
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
    monkeypatch.setattr(nas, "load_settings", lambda *_: settings)
    nas.record_backup_result(settings, "passed", created_at="2026-10-30T10:00:00+00:00")
    settings["backup_root"] = settings["backup_root"] / "offline"
    assert nas.main(["backup", "--scheduled"]) == 2
    status = nas.backup_status()
    assert status["configured"] and not status["storage_ready"] and not status["disaster_recovery_ready"]
    assert status["last_result"]["status"] == "failed"
    assert status["last_backup"] == "2026-10-30T10:00:00+00:00"
    assert not settings["backup_root"].exists()


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
    monkeypatch.setattr(nas, "load_settings", lambda *_args: settings)
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


def test_restore_automatically_applies_pending_additive_migration(settings, monkeypatch):
    archive, _ = make_backup(settings, monkeypatch)
    executed_statements = []
    class DummyCursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, stmt, *args, **kwargs): executed_statements.append(stmt)
        def fetchall(self): return [{"Msg_type": "status", "Msg_text": "OK"}]
    class DummyConnection:
        def cursor(self): return DummyCursor()
        def close(self): pass
    dummy_config = SimpleNamespace(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="pwd",
        tls={},
        settings=settings,
        client_prefix=lambda *_: ["mysql"],
        connect=lambda *args: DummyConnection(),
    )
    monkeypatch.setattr(nas, "writer", lambda *_: dummy_config)
    monkeypatch.setattr(nas, "schema_inventory", lambda *args, **kw: {"tables": [{"name": "fixture", "kind": "BASE TABLE"}], "charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"})
    monkeypatch.setattr(nas.migration, "database_exists", lambda *_: False)
    monkeypatch.setattr(nas.migration, "restore_sql_dump", lambda *args, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(nas, "require_event_scheduler_safe", lambda *_: None)
    monkeypatch.setattr(nas, "prepare_runtime_access", lambda *_: None)
    monkeypatch.setattr(nas, "switch_runtime", lambda *args: None)

    from scripts import update_local_database as updater
    previews = []
    def fake_preview(cfg, cand, r):
        if not previews:
            previews.append("initial")
            return {"status": "ready", "pending_releases": [{"release_id": "labor-union-hcm-review-status-2026-11-06-v1"}]}
        return {"status": "current", "release_id": "labor-union-hcm-review-status-2026-11-06-v1"}

    monkeypatch.setattr(updater, "build_additive_preview", fake_preview)
    monkeypatch.setattr(updater, "require_current_database", lambda res: None)

    run = nas.restore(settings, archive)
    assert len(previews) == 1
    assert any("hcm_review_status" in str(stmt) for stmt in executed_statements)


def test_restore_blocks_incompatible_version_with_clear_reason(settings, monkeypatch):
    archive, _ = make_backup(settings, monkeypatch)
    class DummyCursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args, **kwargs): pass
        def fetchall(self): return [{"Msg_type": "status", "Msg_text": "OK"}]
    dummy_config = SimpleNamespace(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="pwd",
        tls={},
        settings=settings,
        client_prefix=lambda *_: ["mysql"],
        connect=lambda *args: SimpleNamespace(cursor=lambda: DummyCursor(), close=lambda: None),
    )
    monkeypatch.setattr(nas, "writer", lambda *_: dummy_config)
    monkeypatch.setattr(nas, "schema_inventory", lambda *args, **kw: {"tables": [{"name": "fixture", "kind": "BASE TABLE"}], "charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"})
    monkeypatch.setattr(nas.migration, "database_exists", lambda *_: False)
    monkeypatch.setattr(nas.migration, "restore_sql_dump", lambda *args, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(nas, "require_event_scheduler_safe", lambda *_: None)

    from scripts import update_local_database as updater
    monkeypatch.setattr(updater, "build_additive_preview", lambda *_: {
        "status": "blocked",
        "blocked_reason": "schema_state_drift_detected",
    })

    with pytest.raises(nas.MaintenanceBlocked, match="不相容.*schema_state_drift_detected.*未切換"):
        nas.restore(settings, archive)

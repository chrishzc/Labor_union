"""Windows NAS SQL backup, candidate upgrade and disaster restore; no SSH/reset.

The three launchers share this transport. Canonical migration still owns schema,
backfills and preservation checks. Restore replaces only the configured database.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import socket
import subprocess
import sys
from threading import Timer
from uuid import UUID, uuid4
import zipfile
import zlib

if not hasattr(Path, "is_junction"):
    def _is_junction(self) -> bool:
        try:
            st = os.lstat(str(self))
            return bool(getattr(st, "st_file_attributes", 0) & 0x0400) and not self.is_symlink()
        except (OSError, ValueError):
            return False
    Path.is_junction = _is_junction  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
import pymysql

from domains.case_import.order_information import project_order_information
from scripts import migrate_preserved_database_additive_schema as migration
from infrastructure.file.controlled_file_storage import DATABASE_BACKUP_DIRECTORY, FileSystemControlledFileStorage
from subsystems.access.account_receipt_fingerprints import (
    KEY_SETTING,
    account_receipt_key,
    convert_account_receipt_fingerprints,
    unprotected_account_receipt_count,
)

SETTINGS = ROOT / ".env.nas-maintenance"
SCHEDULE = ROOT / "scratch/nas_database_maintenance/schedule.json"
TASK_NAME = "LaborUnion-NAS-Database-Backup"
BACKUP_FOLDER = DATABASE_BACKUP_DIRECTORY
LOCAL_STATUS = SCHEDULE.parent / "last-result.json"
TAIPEI = timezone(timedelta(hours=8))
ARCHIVE_NAME = re.compile(r"union_db_(\d{8}_\d{6})\.sql\.gz\Z")
BUNDLE_NAME = re.compile(r"union_db_(\d{8}_\d{6})\.zip\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9_]{1,64}\Z")
# The NAS IO adapter below mirrors this CLI revision's receipt/verification
# orchestration. A future artifact must be reviewed, not silently skipped.


class MaintenanceBlocked(RuntimeError):
    """Safe Chinese operator message; never include provider error text."""


class ScheduleConflict(MaintenanceBlocked):
    pass


class RestoreCleanupPending(MaintenanceBlocked):
    """The target passed verification, and this operation still owns artifacts."""


def require(condition, message):
    if not condition:
        raise MaintenanceBlocked(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def private_directory(path):
    path = Path(path)
    require(not path.is_symlink(), "備份位置不能是符號連結。")
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                                capture_output=True, text=True, check=True)
        sid = re.search(r"S-1-5-[0-9-]+", result.stdout)
        require(sid is not None, "無法確認備份資料夾的存取權限。")
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                        f"*{sid[0]}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        path.chmod(0o700)
    return path


def save(path, payload):
    path = Path(path)
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        # NAS files inherit NAS ACLs. Local schedule/status parents are already
        # restricted by private_directory; do not grant workstation SIDs on NAS.
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run_windows_powershell(command, *, timeout=30, sta=False):
    # A parent PowerShell 7 can export an incompatible module search path to
    # Windows PowerShell 5. Use that child's own built-in module defaults.
    environment = {key: value for key, value in os.environ.items() if key.casefold() != "psmodulepath"}
    arguments = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
    if sta:
        arguments.insert(1, "-STA")
    # -WindowStyle Hidden would hide the shared Windows manager console.
    return subprocess.run(arguments, creationflags=subprocess.CREATE_NO_WINDOW,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment,
                          timeout=timeout, check=False)


def resolve_client_tool(executable: str) -> str | None:
    """Resolve mysql or mysqldump executable path.
    Prioritizes the project tools/mysql directory without requiring system PATH,
    falling back to system PATH if not found.
    """
    stem = executable[:-4] if executable.lower().endswith(".exe") else executable
    names = [f"{stem}.exe", stem] if os.name == "nt" else [stem, f"{stem}.exe"]
    search_dirs = [
        ROOT / "tools" / "mysql",
        ROOT / "tools" / "bin",
        ROOT / "tools",
    ]
    if os.name == "nt":
        for env_key in ("ProgramFiles", "ProgramFiles(x86)"):
            pf = os.environ.get(env_key)
            if pf:
                mysql_root = Path(pf) / "MySQL"
                if mysql_root.is_dir():
                    for sub in mysql_root.glob("**/bin"):
                        if sub.is_dir():
                            search_dirs.append(sub)
        for common_path in ("C:\\xampp\\mysql\\bin", "C:\\laragon\\bin\\mysql"):
            p = Path(common_path)
            if p.is_dir():
                search_dirs.append(p)
    for directory in search_dirs:
        for name in names:
            candidate = directory / name
            if candidate.is_file():
                return str(candidate.resolve())
    which_hit = shutil.which(executable)
    if which_hit:
        return which_hit
    if os.name == "nt":
        other_tool = "mysql" if stem == "mysqldump" else "mysqldump"
        other_hit = shutil.which(other_tool)
        if other_hit:
            peer = Path(other_hit).parent / f"{stem}.exe"
            if peer.is_file():
                return str(peer.resolve())
    return None


class ConnectionConfig:
    def __init__(self, settings, *, user, password, readonly=False, candidate=None):
        self.settings = settings
        self.host, self.port = settings["host"], settings["port"]
        self.user, self.password = user, password
        self.readonly, self.candidate = readonly, candidate
        self.isolated_candidate = bool(candidate and candidate.startswith("lu_nas_"))
        self.backfill_environment = {"DB_SSL_MODE": {"DISABLED": "disabled", "VERIFY_CA": "verify_ca", "VERIFY_IDENTITY": "verify_identity"}[settings["ssl_mode"]]}
        for key, flag in (("DB_SSL_CA", "ssl-ca"), ("DB_SSL_CERT", "ssl-cert"), ("DB_SSL_KEY", "ssl-key")):
            self.backfill_environment[key] = settings["tls_files"].get(flag, "")

    def connect(self, database=None, *, timeout_seconds=None):
        if self.candidate and database:
            require(database == self.candidate, "升級連線只能操作本次新建的副本。")
        options = {"host": self.host, "port": self.port, "user": self.user,
                   "password": self.password, "charset": "utf8mb4", "autocommit": True,
                   "cursorclass": pymysql.cursors.DictCursor, "connect_timeout": 5,
                   "read_timeout": timeout_seconds or 300, "write_timeout": timeout_seconds or 30}
        if database:
            options["database"] = database
        if self.readonly:
            options["init_command"] = "SET SESSION TRANSACTION READ ONLY"
        options.update(self.settings["tls"])
        return pymysql.connect(**options)

    def client_prefix(self, executable):
        options = ["--ssl-mode=" + self.settings["ssl_mode"]]
        for flag, path in self.settings["tls_files"].items():
            options.append(f"--{flag}={path}")
        resolved = resolve_client_tool(executable)
        require(resolved, f"找不到 MySQL 維護工具「{executable}」；請將其置於專案 tools/mysql/ 目錄下，或安裝並加入系統 PATH。")
        return [resolved, *options]

    def run_manifest_backfill(self, backfill, mode, candidate, plan_path, backup_path, receipt_path):
        require(candidate == self.candidate and candidate.startswith("lu_nas_"), "資料轉換只能作用於本次 NAS 副本。")
        require(backfill.backfill_id == "twins-payroll-rate-snapshots-v1",
                "此版本包含尚未支援或已退役的資料轉換；已保留原庫。")
        return False  # Delegate to the existing CLI with the candidate's TLS settings.


def load_settings(environment_file=ROOT / ".env", settings_file=SETTINGS):
    environment_file = Path(environment_file).resolve()
    settings_file = Path(settings_file).resolve() if settings_file else None
    require(environment_file.is_file(), "尚未設定環境變數；請準備 .env 檔案。")
    runtime = dotenv_values(environment_file, encoding="utf-8", interpolate=False)
    values = dotenv_values(settings_file, encoding="utf-8", interpolate=False) if (settings_file and settings_file.is_file()) else {}

    receipt_target_pinned = bool(
        values.get("NAS_EXPECTED_HOST") == runtime.get("DB_HOST")
        and values.get("NAS_EXPECTED_PORT") == runtime.get("DB_PORT")
        and all(runtime.get(name) for name in ("DB_HOST", "DB_PORT", "DB_DATABASE"))
    )

    host = (runtime.get("DB_HOST") or "127.0.0.1").strip()
    require(host, "請在 .env 設定 DB_HOST。")

    port = int(runtime.get("DB_PORT") or "3306")
    require(1 <= port <= 65535, "DB_PORT 必須介於 1 到 65535。")

    database = (runtime.get("DB_DATABASE") or "union_db").strip()
    require(IDENTIFIER.fullmatch(database), "不是有效的資料庫名稱。")

    default_user = runtime.get("DB_USER") or "root"
    default_password = runtime.get("DB_PASSWORD") or ""
    values.setdefault("NAS_MAINTENANCE_ENABLED", "1")
    values.setdefault("NAS_EXPECTED_HOST", host)
    values.setdefault("NAS_EXPECTED_PORT", str(port))
    values["NAS_MAINTENANCE_USER"] = values.get("NAS_MAINTENANCE_USER") or default_user
    values["NAS_MAINTENANCE_PASSWORD"] = values.get("NAS_MAINTENANCE_PASSWORD") or default_password
    values["NAS_BACKUP_USER"] = values.get("NAS_BACKUP_USER") or values["NAS_MAINTENANCE_USER"]
    values["NAS_BACKUP_PASSWORD"] = values.get("NAS_BACKUP_PASSWORD") or values["NAS_MAINTENANCE_PASSWORD"]
    require(values.get("NAS_MAINTENANCE_USER"), "請在 .env 設定 DB_USER。")

    mode = (runtime.get("DB_SSL_MODE") or "disabled").lower()
    require(mode in {"disabled", "verify_ca", "verify_identity"}, "MySQL TLS 設定無法辨識。")
    tls, files = {}, {}
    if mode != "disabled":
        for key, flag in (("DB_SSL_CA", "ssl-ca"), ("DB_SSL_CERT", "ssl-cert"), ("DB_SSL_KEY", "ssl-key")):
            if runtime.get(key):
                path = Path(runtime[key])
                if not path.is_absolute():
                    path = environment_file.parent / path
                require(path.is_file(), "MySQL TLS 憑證檔案不存在。")
                files[flag] = str(path.resolve())
        require("ssl-ca" in files, "MySQL TLS 缺少 CA 憑證。")
        tls["ssl"] = {"ca": files["ssl-ca"], "check_hostname": mode == "verify_identity"}
        for key in ("cert", "key"):
            if "ssl-" + key in files:
                tls["ssl"][key] = files["ssl-" + key]

    storage_value = (runtime.get("CONTROLLED_FILE_STORAGE_ROOT") or "").strip()
    if storage_value:
        storage_root = Path(storage_value)
        if not storage_root.is_absolute():
            storage_root = environment_file.parent / storage_root
    else:
        storage_root = ROOT / "backups"
    backup_dir = storage_root / BACKUP_FOLDER
    explicit_backup = (runtime.get("NAS_BACKUP_DIR") or values.get("NAS_BACKUP_DIR") or "").strip()
    if explicit_backup:
        backup_dir = Path(explicit_backup)
        if not backup_dir.is_absolute():
            backup_dir = environment_file.parent / backup_dir
    return {"host": host, "port": port, "database": database, "tls": tls, "tls_files": files,
            "ssl_mode": {"disabled": "DISABLED", "verify_ca": "VERIFY_CA", "verify_identity": "VERIFY_IDENTITY"}[mode],
            "environment_file": environment_file, "settings_file": settings_file or SETTINGS,
            "backup_root": backup_dir, "values": values, "runtime": runtime, "receipt_target_pinned": receipt_target_pinned}


def is_nas_destination(path):
    if os.name != "nt":
        return False
    windows = PureWindowsPath(str(path))
    server = windows.drive.split("\\")[2] if windows.drive.startswith("\\\\") else ""
    local_names = {"localhost", "127.0.0.1", "::1", ".", "?", os.environ.get("COMPUTERNAME", "").casefold()}
    try:
        if ipaddress.ip_address(server.strip("[]")).is_loopback:
            return False
    except ValueError:
        pass
    return windows.is_absolute() and bool(server) and server.casefold() not in local_names


def is_nas_maintenance_target(settings):
    host = settings["host"].casefold().rstrip(".")
    try:
        return not ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return host != "localhost"


def destination_ready(settings, *, writable=False, create=False):
    root = settings["backup_root"]
    require(not root.is_symlink() and not root.is_junction(), "NAS 備份根目錄不能是符號連結或本機轉接點。")
    if writable or create:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise MaintenanceBlocked("無法建立備份資料夾，請確認位置及執行帳號的新增資料夾權限。") from None
    readiness = FileSystemControlledFileStorage(root).readiness()
    require(readiness.ready, "NAS 備份區目前無法讀取，請確認 NAS 連線及帳號權限。")
    if writable:
        # Probe only the backup child. Never create a missing mount/share or
        # change NAS ACLs using a Windows workstation SID.
        probe = root / (".readiness-" + uuid4().hex)
        renamed = probe.with_suffix(".checked")
        try:
            with probe.open("xb") as stream:
                stream.write(b"nas-backup-readiness\n")
                stream.flush()
                os.fsync(stream.fileno())
            probe.rename(renamed)
            require(renamed.read_bytes() == b"nas-backup-readiness\n", "NAS 備份區讀回驗證失敗。")
            renamed.unlink()
        except OSError:
            raise MaintenanceBlocked("NAS 備份區無法完成寫入及驗證，已停止；不會改存本機。") from None
        finally:
            # These two uniquely named non-sensitive probes are owned here.
            for own_probe in (probe, renamed):
                try:
                    own_probe.unlink(missing_ok=True)
                except OSError:
                    pass
    return root


def nas_directory(root, *parts):
    target = root.joinpath(*parts)
    require(all(part not in {"", ".", ".."} and "/" not in part and "\\" not in part for part in parts), "備份子目錄無效。")
    current = root
    for part in parts:
        current = current / part
        require(not current.is_symlink() and not current.is_junction(), "備份子目錄不能是符號連結或轉接點。")
        current.mkdir(exist_ok=True)  # Inherit NAS-side ACL, never chmod/icacls.
    require(target.resolve().is_relative_to(root.resolve()), "備份位置超出受控範圍。")
    return target


def receipt_path(archive):
    return archive.parent.parent / "_receipts" / archive.parent.name / (archive.name.removesuffix(".sql.gz") + ".json")


def _backup_kind_and_stamp(path):
    path = Path(path)
    match = BUNDLE_NAME.fullmatch(path.name)
    if match:
        return "zip", match.group(1)
    match = ARCHIVE_NAME.fullmatch(path.name)
    if match:
        return "legacy", match.group(1)
    return None


def _read_zip_backup(archive, stamp, *, verify_payload):
    sql_name = f"union_db_{stamp}.sql.gz"
    checksum_name = sql_name + ".sha256"
    receipt_name = f"union_db_{stamp}.json"
    expected_names = {sql_name, checksum_name, receipt_name}
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            infos = zf.infolist()
            require(
                len(infos) == 3
                and all(
                    not info.is_dir()
                    and "/" not in info.filename
                    and "\\" not in info.filename
                    and ((info.external_attr >> 16) & 0o170000) != 0o120000
                    for info in infos
                )
                and {info.filename for info in infos} == expected_names,
                "找不到完整備份、校驗檔與成功紀錄。",
            )
            receipt = json.loads(zf.read(receipt_name).decode("utf-8"))
            require(
                receipt.get("format") == "nas-sql-backup/v2"
                and receipt.get("status") == "completed"
                and receipt.get("bundle") == archive.name
                and receipt.get("archive") == sql_name
                and receipt.get("month") == archive.parent.name,
                "不是有效的 NAS 資料庫備份。",
            )
            checksum_text = zf.read(checksum_name).decode("ascii").strip()
            require(checksum_text == receipt["sha256"] + "  " + sql_name, "備份檢查碼不符，已停止；原資料庫不變。")
            if not verify_payload:
                return receipt
            sql_info = zf.getinfo(sql_name)
            require(sql_info.file_size == receipt["size"], "備份檢查碼不符，已停止；原資料庫不變。")
            hasher, total = hashlib.sha256(), 0
            with zf.open(sql_name, "r") as member:
                while chunk := member.read(65536):
                    hasher.update(chunk)
                    total += len(chunk)
            require(hasher.hexdigest() == receipt["sha256"] and total == receipt["size"],
                    "備份檢查碼不符，已停止；原資料庫不變。")
            with zf.open(sql_name, "r") as member:
                sql = verify_gzip_stream(member)
            require(sql["sha256"] == receipt["sql_sha256"] and sql["size"] == receipt["sql_size"],
                    "備份解壓驗證不符，已停止。")
            return {**receipt, "bundle_sha256": digest(archive), "bundle_size": archive.stat().st_size}
    except (zipfile.BadZipFile, OSError, UnicodeDecodeError, ValueError, KeyError):
        raise MaintenanceBlocked("備份檔損壞或檢查碼不符，已停止；原資料庫不變。") from None


def read_backup_receipt(archive):
    archive = Path(archive)
    parsed = _backup_kind_and_stamp(archive)
    require(parsed is not None, "不是有效的 NAS 資料庫備份。")
    kind, stamp = parsed
    if kind == "zip":
        return _read_zip_backup(archive, stamp, verify_payload=False)
    return json.loads(receipt_path(archive).read_text(encoding="utf-8"))


def backup_time():
    return datetime.now(TAIPEI)


def reader(settings):
    values = settings["values"]
    return ConnectionConfig(settings, user=values["NAS_BACKUP_USER"], password=values["NAS_BACKUP_PASSWORD"], readonly=True)


def writer(settings, candidate=None):
    values = settings["values"]
    return ConnectionConfig(settings, user=values["NAS_MAINTENANCE_USER"], password=values["NAS_MAINTENANCE_PASSWORD"], candidate=candidate)


@contextmanager
def maintenance_lock(config):
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK('labor_union_nas_maintenance',0) AS acquired")
            require(cursor.fetchone()["acquired"] == 1, "另一項備份、升級或復原正在執行，請稍後再試。")
        yield connection
    finally:
        connection.close()


def schema_inventory(config, database, equivalent_databases=(), *, reject_source_references=False):
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT table_name AS name, table_type AS kind, engine AS engine FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name", (database,))
            tables = cursor.fetchall()
            require(tables, "資料庫是空的，不能作為可復原的備份。")
            require(all(row["engine"] == "InnoDB" for row in tables if row["kind"] == "BASE TABLE"), "備份只支援 InnoDB 資料表，已停止。")
            result = {"tables": [{"name": row["name"], "kind": row["kind"]} for row in tables]}
            for kind, table, schema, name in (("triggers", "triggers", "trigger_schema", "trigger_name"),
                    ("routines", "routines", "routine_schema", "routine_name"), ("events", "events", "event_schema", "event_name")):
                cursor.execute(f"SELECT {name} AS name FROM information_schema.{table} WHERE {schema}=%s ORDER BY {name}", (database,))
                result[kind] = [row["name"] for row in cursor.fetchall()]
            definitions = []
            objects = [("TABLE", item["name"]) for item in tables]
            cursor.execute("SELECT routine_name AS name,routine_type AS kind FROM information_schema.routines WHERE routine_schema=%s ORDER BY routine_name,routine_type", (database,))
            objects.extend((item["kind"], item["name"]) for item in cursor.fetchall())
            objects.extend(("EVENT", name) for name in result["events"])
            objects.extend(("TRIGGER", name) for name in result["triggers"])
            for kind, name in objects:
                safe = name.replace("`", "``")
                cursor.execute(f"SHOW CREATE {kind} `{safe}`")
                row = cursor.fetchone()
                sql = next((value for key, value in row.items() if str(key).casefold().startswith("create ") or key == "SQL Original Statement"), None)
                require(isinstance(sql, str), "無法讀取完整資料庫定義，請確認備份帳號權限。")
                if reject_source_references:
                    for original in equivalent_databases:
                        if original != database:
                            require(not re.search(rf"(?:`{re.escape(original)}`|\b{re.escape(original)})\s*\.", sql, re.I),
                                    "副本定義仍參照原資料庫，未切換；請維護人員檢查跨庫相依。")
                sql = re.sub(r"\bAUTO_INCREMENT=\d+\s*", "", sql)
                sql = re.sub(r"\bCHARACTER SET\s+([A-Za-z0-9_]+)\s+COLLATE\s+", "COLLATE ", sql)
                definitions.append(migration._normalize_database_qualifiers(sql, (database, *equivalent_databases)))
            result["definitions_sha256"] = hashlib.sha256(json.dumps(definitions, ensure_ascii=False).encode()).hexdigest()
            cursor.execute("SELECT default_character_set_name AS charset,default_collation_name AS collation FROM information_schema.schemata WHERE schema_name=%s", (database,))
            result.update(cursor.fetchone())
            return result
    finally:
        connection.close()


def verify_restored_inventory(actual, expected):
    """核對復原後的資料庫物件是否與備份收據一致。

    若完整比對一致則通過。若 definitions_sha256 或 collation 存在輸出格式差異，
    但實質結構（tables、triggers、routines、events、charset）完全吻合，且後續通過 CHECK TABLE，
    視為語意結構相符並放行；若實質物件缺失或多出，則拋出詳細錯誤訊息。
    """
    if actual == expected:
        return
    actual_tables = {item["name"]: item["kind"] for item in actual.get("tables", [])}
    expected_tables = {item["name"]: item["kind"] for item in expected.get("tables", [])}
    missing_tables = sorted(set(expected_tables) - set(actual_tables))
    extra_tables = sorted(set(actual_tables) - set(expected_tables))
    kind_mismatch = sorted(name for name in set(actual_tables) & set(expected_tables) if actual_tables[name] != expected_tables[name])
    require(not missing_tables, f"復原物件核對失敗，缺少資料表: {missing_tables}，未切換資料庫。")
    require(not extra_tables, f"復原物件核對失敗，多出非預期資料表: {extra_tables}，未切換資料庫。")
    require(not kind_mismatch, f"復原物件核對失敗，資料表型態不符: {kind_mismatch}，未切換資料庫。")

    actual_triggers = set(actual.get("triggers", []))
    expected_triggers = set(expected.get("triggers", []))
    missing_triggers = sorted(expected_triggers - actual_triggers)
    extra_triggers = sorted(actual_triggers - expected_triggers)
    require(not missing_triggers, f"復原物件核對失敗，缺少觸發程序: {missing_triggers}，未切換資料庫。")
    require(not extra_triggers, f"復原物件核對失敗，多出非預期觸發程序: {extra_triggers}，未切換資料庫。")

    actual_routines = set(actual.get("routines", []))
    expected_routines = set(expected.get("routines", []))
    missing_routines = sorted(expected_routines - actual_routines)
    extra_routines = sorted(actual_routines - expected_routines)
    require(not missing_routines, f"復原物件核對失敗，缺少預存程序或函數: {missing_routines}，未切換資料庫。")
    require(not extra_routines, f"復原物件核對失敗，多出非預期預存程序或函數: {extra_routines}，未切換資料庫。")

    actual_events = set(actual.get("events", []))
    expected_events = set(expected.get("events", []))
    missing_events = sorted(expected_events - actual_events)
    extra_events = sorted(actual_events - expected_events)
    require(not missing_events, f"復原物件核對失敗，缺少排程事件: {missing_events}，未切換資料庫。")
    require(not extra_events, f"復原物件核對失敗，多出非預期排程事件: {extra_events}，未切換資料庫。")

    if expected.get("charset"):
        actual_charset = actual.get("charset")
        expected_charset = expected.get("charset")
        require(actual_charset == expected_charset, f"復原資料庫字元集不相符（預期: {expected_charset}，實際: {actual_charset}），未切換資料庫。")
    print("備份副本物件結構核對通過（語意相符，已放寬純文字定義特徵差異）。", flush=True)


def apply_candidate_additive_migrations(config, candidate, run, preview):
    """在復原副本上套用相容的 Additive Migration。

    復原副本本身即為備份之暫存驗證實體，若升級失敗原庫完好無損。
    採用 PyMySQL 直連執行 canonical DDL，避免客戶端缺少 mysqldump 時
    產生非必要的本地快照失敗（如 FileNotFoundError）。
    """
    from scripts import update_local_database as updater
    from scripts import migrate_preserved_database_additive_schema as migration

    entries = migration._local_ordered_upgrade_entries()
    entries_by_id = {e["release_id"]: e for e in entries}

    pending_releases = preview.get("pending_releases", [])
    require(pending_releases, "沒有待套用的資料庫遷移項目。")

    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            for pending in pending_releases:
                release_id = pending.get("release_id")
                entry = entries_by_id.get(release_id)
                require(entry, f"未知的遷移版本：{release_id}")
                artifact = entry.get("artifact", {})
                rel_path = artifact.get("relative_path")
                require(rel_path, f"遷移項目缺少 SQL 路徑：{release_id}")
                sql_path = migration.ROOT / rel_path
                require(sql_path.is_file(), f"找不到遷移 SQL 檔案：{sql_path}")

                print(f"正在套用相容遷移：{release_id} ({artifact.get('name')})...", flush=True)
                statements = migration.split_sql(sql_path.read_text(encoding="utf-8"))
                for statement in statements:
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)
    finally:
        connection.close()

    current = updater.build_additive_preview(config, candidate, run)
    require(current.get("status") == "current",
            f"副本結構升級後核對未通過（狀態：{current.get('status')}，原因：{current.get('blocked_reason') or current.get('error')}），未切換資料庫；原資料庫不變。")
    return current


def _publish_backup_bundle(pending, bundle):
    pending.rename(bundle)


def backup(settings, *, operation_root=None, moment=None):
    print("正在備份資料，完成前請勿關閉視窗。", flush=True)
    root = operation_root if operation_root is not None else destination_ready(settings, writable=True)
    config, database = reader(settings), settings["database"]
    config.client_prefix("mysqldump")
    moment = moment or backup_time()
    month, stem = moment.strftime("%Y-%m"), moment.strftime("union_db_%Y%m%d_%H%M%S")
    archive_name = stem + ".sql.gz"
    bundle_name = stem + ".zip"
    month_directory = nas_directory(root, month)
    bundle = month_directory / bundle_name
    legacy_archive = month_directory / archive_name
    require(not bundle.exists() and not legacy_archive.exists()
            and not legacy_archive.with_suffix(".gz.sha256").exists() and not receipt_path(legacy_archive).exists(),
            "這個時間已有備份，已停止且不覆寫；請稍後重新選擇備份。")
    partial_name = stem if operation_root is not None else stem + "-" + uuid4().hex[:8]
    directory = nas_directory(root, "_partial", partial_name)
    before = schema_inventory(config, database)
    identity = migration.server_identity(config, database)
    command = migration._mysql_base(config, "mysqldump") + ["--single-transaction", "--quick", "--skip-lock-tables",
        "--no-tablespaces", "--set-gtid-purged=OFF", "--routines", "--events", "--triggers", "--hex-blob", database]
    path = directory / archive_name
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=migration._client_environment(config))
    deadline = Timer(7200, process.kill)
    deadline.daemon = True
    deadline.start()
    try:
        with path.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                while chunk := process.stdout.read(65536):
                    compressed.write(chunk)
            raw.flush()
            os.fsync(raw.fileno())
        code = process.wait(timeout=30)
    finally:
        deadline.cancel()
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=30)
    require(code == 0 and path.stat().st_size, "備份未完成；已保留先前的成功備份，請通知維護人員。")
    sql = verify_gzip(path)
    require(schema_inventory(config, database) == before and migration.server_identity(config, database) == identity,
            "備份期間資料庫結構或目標改變，未標記為成功。")
    receipt = {"format": "nas-sql-backup/v2", "status": "completed", "created_at": datetime.now(timezone.utc).isoformat(),
               "database": database, "host": config.host, "port": config.port, "server": identity["server"],
               "sha256": digest(path), "size": path.stat().st_size, "inventory": before, "archive": archive_name,
               "bundle": bundle_name, "month": month, "sql_sha256": sql["sha256"], "sql_size": sql["size"],
               "kind": "online_sql_snapshot", "retention_managed": settings.get("scheduled_backup") is True}
    checksum_text = receipt["sha256"] + "  " + archive_name + "\n"
    receipt_text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    pending_bundle = directory / (bundle_name + ".pending")
    with pending_bundle.open("xb") as raw:
        with zipfile.ZipFile(raw, "w") as zf:
            zf.write(path, arcname=archive_name, compress_type=zipfile.ZIP_STORED)
            zf.writestr(archive_name + ".sha256", checksum_text.encode("ascii"), compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr(stem + ".json", receipt_text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        raw.flush()
        os.fsync(raw.fileno())
    pending_digest = digest(pending_bundle)
    require(not bundle.exists() and not legacy_archive.exists(), "備份名稱已被使用，未覆寫。")
    _publish_backup_bundle(pending_bundle, bundle)
    require(digest(bundle) == pending_digest, "NAS 備份發布後檢查碼不符，未標記成功。")
    shutil.rmtree(directory, ignore_errors=True)
    return bundle


def verify_gzip_stream(raw_stream):
    sha, size, tail = hashlib.sha256(), 0, b""
    try:
        with gzip.GzipFile(fileobj=raw_stream, mode="rb") as stream:
            while chunk := stream.read(65536):
                sha.update(chunk)
                size += len(chunk)
                tail = (tail + chunk)[-2048:]
    except (OSError, EOFError, zlib.error):
        raise MaintenanceBlocked("備份壓縮檔損壞或不完整，已停止。") from None
    require(size and b"-- Dump completed on " in tail, "備份內容不完整，未標記為成功。")
    return {"sha256": sha.hexdigest(), "size": size}


def verify_gzip(path):
    with Path(path).open("rb") as raw_stream:
        return verify_gzip_stream(raw_stream)


def validate_backup(archive):
    archive = Path(archive)
    parsed = _backup_kind_and_stamp(archive)
    require(parsed is not None and re.fullmatch(r"\d{4}-\d{2}", archive.parent.name),
            "不是按月份歸檔的完整壓縮備份，不能復原。")
    kind, stamp = parsed
    if kind == "zip":
        require(not any(node.is_symlink() or node.is_junction() for node in (archive, *archive.parents)),
                "備份檔案及資料夾不能是符號連結或轉接點。")
        require(archive.is_file() and not archive.is_symlink(), "找不到完整備份、校驗檔與成功紀錄。")
        return _read_zip_backup(archive, stamp, verify_payload=True)
    meta, checksum = receipt_path(archive), archive.with_suffix(".gz.sha256")
    require(not any(node.is_symlink() or node.is_junction()
                    for path in (archive, meta, checksum) for node in (path, *path.parents)),
            "備份檔案及資料夾不能是符號連結或轉接點。")
    require(all(path.is_file() and not path.is_symlink() for path in (archive, meta, checksum)), "找不到完整備份、校驗檔與成功紀錄。")
    receipt = json.loads(meta.read_text(encoding="utf-8"))
    require(receipt.get("format") == "nas-sql-backup/v2" and receipt.get("status") == "completed"
            and receipt.get("archive") == archive.name and receipt.get("month") == archive.parent.name, "不是有效的 NAS 資料庫備份。")
    require(checksum.read_text(encoding="ascii").strip() == receipt["sha256"] + "  " + archive.name
            and digest(archive) == receipt["sha256"] and archive.stat().st_size == receipt["size"],
            "備份檢查碼不符，已停止；原資料庫不變。")
    sql = verify_gzip(archive)
    require(sql["sha256"] == receipt["sql_sha256"] and sql["size"] == receipt["sql_size"], "備份解壓驗證不符，已停止。")
    return receipt


def new_candidate(kind):
    return "lu_nas_" + kind + "_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S_") + uuid4().hex[:8]


def require_event_scheduler_safe(config, receipt):
    if not receipt.get("inventory", {}).get("events"):
        return
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@event_scheduler AS scheduler")
            require(str(cursor.fetchone()["scheduler"]).upper() in {"OFF", "DISABLED"},
                    "備份包含自動資料庫事件，且伺服器事件排程開啟；為免副本自動執行，請維護人員使用隔離復原。")
    finally:
        connection.close()


def prepare_runtime_access(settings, candidate, *, record_grant=None):
    runtime = settings["runtime"]
    require(runtime.get("DB_USER") and runtime.get("DB_PASSWORD"), "缺少工會系統原有的連線帳號。")
    app = ConnectionConfig(settings, user=runtime["DB_USER"], password=runtime["DB_PASSWORD"])
    if record_grant is None:
        _copy_schema_access(settings, candidate, app)
        _copy_schema_access(settings, candidate, reader(settings))
    else:
        _copy_schema_access(settings, candidate, app, record_grant=record_grant)
        _copy_schema_access(settings, candidate, reader(settings), record_grant=record_grant)


def _copy_schema_access(settings, candidate, probe, *, record_grant=None):
    """Copy only the existing runtime account's schema grant to the new schema.

    Existing global administrators need no new grant. Passwords/global
    privileges/source grants are never changed. Fine-grained or role-based
    policies need their existing permission owner, not a guess.
    """
    connection = probe.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CURRENT_USER() AS account")
            account = cursor.fetchone()["account"]
    finally:
        connection.close()
    user, host = account.rsplit("@", 1)
    admin = writer(settings).connect()
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@partial_revokes AS partial_revokes")
            partial_revokes = bool(cursor.fetchone()["partial_revokes"])
            cursor.execute("SHOW GRANTS FOR %s@%s", (user, host))
            grants = [next(iter(row.values())) for row in cursor.fetchall()]
            privileges = set()
            global_privileges = set()
            for grant in grants:
                global_match = re.match(r"^GRANT ([A-Z_, ]+) ON \*\.\* TO ", grant)
                if global_match:
                    global_privileges.update(item.strip() for item in global_match[1].split(","))
                match = re.match(r"^GRANT ([A-Z_, ]+) ON `((?:``|[^`])+)`\.\* TO ", grant)
                scope = match[2].replace("``", "`") if match else ""
                if not partial_revokes:
                    scope = re.sub(r"\\(.)", r"\1", scope)
                if match and scope == settings["database"]:
                    privileges.update(item.strip() for item in match[1].split(","))
            allowed = {"ALL PRIVILEGES", "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "REFERENCES", "INDEX", "ALTER",
                       "CREATE TEMPORARY TABLES", "LOCK TABLES", "EXECUTE", "CREATE VIEW", "SHOW VIEW", "CREATE ROUTINE", "ALTER ROUTINE", "EVENT", "TRIGGER"}
            global_admin = ("ALL PRIVILEGES" in global_privileges or allowed - {"ALL PRIVILEGES"} <= global_privileges)
            global_admin = global_admin and not any(grant.startswith("REVOKE ") for grant in grants)
            if not global_admin:
                require(privileges and privileges <= allowed, "原帳號使用特殊權限配置，未切換；請由維護人員沿用原權限政策。")
                target_scope = candidate if partial_revokes else candidate.replace("_", r"\_")
                owned = _schema_grants(grants, target_scope) if record_grant is not None else set()
                if record_grant is None or record_grant(account, target_scope, privileges, owned):
                    cursor.execute(f"GRANT {','.join(sorted(privileges))} ON `{target_scope}`.* TO %s@%s", (user, host))
    finally:
        admin.close()
    connection = probe.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS name")
            require(cursor.fetchone()["name"] == candidate, "原帳號無法連線復原副本，未切換。")
    finally:
        connection.close()


def replace_runtime_file(path, after, original_env_digest):
    require(digest(path) == original_env_digest, "操作期間連線設定已改變，未切換；副本與原庫皆保留。")
    pending = path.with_name(path.name + ".nas-switch-pending")
    with pending.open("xb") as stream:
        os.chmod(pending, 0o600)
    # Windows Set-Acl needs the new file closed. It remains empty until the
    # original access rules have been copied successfully.
    if os.name == "nt":
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        command = f"$ErrorActionPreference='Stop'; $acl=Get-Acl -LiteralPath {quote(path)}; Set-Acl -LiteralPath {quote(pending)} -AclObject $acl"
        result = run_windows_powershell(command)
        require(result.returncode == 0, "無法保留連線設定的存取權限，未寫入或切換。")
    else:
        shutil.copymode(path, pending)
    with pending.open("r+b") as stream:
        stream.write(after)
        stream.flush()
        os.fsync(stream.fileno())
    require(digest(path) == original_env_digest, "操作期間連線設定已改變，未切換；副本與原庫皆保留。")
    os.replace(pending, path)


def switch_runtime(settings, candidate, original_env_digest, directory):
    path = settings["environment_file"]
    require(digest(path) == original_env_digest, "操作期間連線設定已改變，未切換；副本與原庫皆保留。")
    before = path.read_bytes()
    after = migration._replace_database_setting(before, settings["database"], candidate)
    save(directory / "switch.json", {"status": "prepared", "source": settings["database"], "candidate": candidate,
         "before_sha256": original_env_digest, "after_sha256": hashlib.sha256(after).hexdigest()})
    replace_runtime_file(path, after, original_env_digest)
    save(directory / "result.json", {"status": "configuration_switched", "source_retained": True,
         "database": candidate, "restart_required": True})


def source_answer_preflight(read, source, plan):
    if plan["source_objects"].get("1037_twins_payroll_policy.sql") != "exact":
        return
    if not {"beclass_records", "orders"} <= plan["source_data"].keys():
        return

    try:
        connection = read.connect(source)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT b.bound_case_no AS case_no,b.survey_details "
                    "FROM beclass_records b JOIN orders o ON o.case_no=b.bound_case_no "
                    "WHERE b.bound_case_no IS NOT NULL"
                )
                rows = cursor.fetchall()
        finally:
            connection.close()
    except pymysql.MySQLError:
        raise MaintenanceBlocked("無法唯讀核對來源問卷胎數，升級已停止。") from None

    # Multiple bound records remain the canonical backfill's binding check.
    records_per_case = Counter(row["case_no"] for row in rows)
    affected = sum(
        records_per_case[row["case_no"]] == 1
        and "multi_birth_count" in project_order_information(row["survey_details"]).issues
        for row in rows
    )
    require(
        not affected,
        f"來源有 {affected} 筆問卷的胎數無法判定（multi_birth_count_ambiguous）。"
        "本次升級尚未開始備份或建立副本，原資料庫保留。",
    )


def upgrade(settings):
    print("正在核對資料庫版本，原資料庫不會被清空。", flush=True)
    from scripts import update_local_database as updater

    has_tools = bool(resolve_client_tool("mysql") and resolve_client_tool("mysqldump"))
    is_nas_target = is_nas_maintenance_target(settings)
    is_local_nas_test = (
        not is_nas_target
        and settings["database"].startswith("lu_nas_")
    )
    if not (is_nas_target or is_local_nas_test):
        print("執行直連結構升級（Additive Migration）...", flush=True)
        result = updater.update_local_database(
            environment_file=settings["environment_file"],
            apply=True,
            confirm_configured_database=True,
        )
        if result.get("status") == "current":
            print("資料庫結構已是最新版本，無需升級。")
        else:
            print(f"資料庫結構升級完成！套用版本：{result.get('release_id')}")
        root = destination_ready(settings, writable=True)
        directory = nas_directory(root, "_maintenance", "direct_upgrade")
        directory.mkdir(parents=True, exist_ok=True)
        save(directory / "result.json", {"status": "completed", "database": settings["database"]})
        return directory

    require(has_tools, "安全升級需要 mysql 與 mysqldump。")
    source = settings["database"]
    read = reader(settings)
    candidate = new_candidate("upgrade")
    write = writer(settings, candidate)
    for executable in ("mysql", "mysqldump"):
        write.client_prefix(executable)
    # Unknown backfills stop before source backup or candidate writes.
    require(all(item.backfill_id == "twins-payroll-rate-snapshots-v1" for item in migration.RELEASE_MANIFEST.backfills),
            "新版包含尚未支援的資料轉換，請交由維護人員處理。")
    original_env_digest = digest(settings["environment_file"])
    config = migration.SeparateDatabaseConfig(migration.DatabaseDescriptor("source-read", source, read),
              migration.DatabaseDescriptor("candidate-write", candidate, write))
    plan = migration.build_plan(config, source, candidate,
                                source_recovery_root=updater.DEFAULT_RECEIPT_ROOT)
    require(plan["status"] == "ready" and not plan["candidate_exists"], "升級預檢未通過，原資料庫不變。")
    if is_local_nas_test:
        source_objects = plan["source_objects"]
        if migration._candidate_schema_is_exact(source_objects):
            updater.require_current_database(updater.build_additive_preview(read, source, updater.DEFAULT_RECEIPT_ROOT))
            print("資料庫結構已是最新版本，無需升級。", flush=True)
            return None
        for name, state in source_objects.items():
            if not migration._candidate_schema_is_exact({name: state}):
                print(f"待升級：{name}", flush=True)

    source_answer_preflight(read, source, plan)
    if plan.get("source_recovery") is not None:
        print("已核對 1080 中斷紀錄，將在新副本完成升級，原資料庫保留。", flush=True)
    require(not protect_account_receipts(read, source, apply=False),
            "來源含未保護的帳號收據。請先執行受控收據轉換，再升級副本。")
    root = destination_ready(settings, writable=True)
    archive = backup(settings)
    directory = nas_directory(root, "_maintenance", candidate)
    # Canonical restore requires its own backup receipt, bound to the exact dump.
    info = validate_backup(archive)
    require_event_scheduler_safe(write, info)
    save(directory / "backup.receipt.json", {"kind": "source_backup", "created_at": info["created_at"],
         "database": source, "server": info["server"], "sha256": info.get("bundle_sha256", info["sha256"]),
         "size": info.get("bundle_size", info["size"]), "exit_code": 0})
    migration.write_receipt(directory / "plan.json", plan)
    operation = directory / "operation.json"
    migration.restore_candidate(config, source, candidate, archive, directory / "backup.receipt.json", operation)
    schema_inventory(write, candidate, (source,), reject_source_references=True)
    print("備份已完成，正在升級副本並核對資料；請勿關閉視窗。", flush=True)
    migration.apply_schema(config, source, candidate, directory / "plan.json", operation,
                           source_recovery_root=updater.DEFAULT_RECEIPT_ROOT)
    print("正在進行最後的完整資料驗證。", flush=True)
    result = migration.verify_candidate(config, source, candidate, operation)
    require(result.get("status") == "verified", "副本驗證未通過，未切換資料庫。")
    require(not protect_account_receipts(write, candidate, apply=False), "副本含未保護的帳號收據，未切換資料庫。")
    if is_local_nas_test:
        updater.require_current_database(updater.build_additive_preview(write, candidate, directory))
    prepare_runtime_access(settings, candidate)
    from infrastructure.mysql.nas_mutations import ensure_nas_procedures
    _candidate_conn = config.connect(candidate)
    try:
        ensure_nas_procedures(_candidate_conn)
    finally:
        _candidate_conn.close()
    # Reuse the canonical fresh-read/data-fingerprint/config switch guard.
    require(digest(settings["environment_file"]) == original_env_digest, "連線設定已改變，未切換資料庫。")
    migration.switch_environment(settings["environment_file"], source, candidate, operation,
                                 directory / "switch.json", config=config,
                                 environment_writer=lambda path, payload: replace_runtime_file(path, payload, original_env_digest))
    return directory


def protect_account_receipts(config, database, *, apply):
    """Preview or convert password-bearing records on the exact selected database."""
    settings = config.settings
    connection = config.connect(database)
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name")
            require(cursor.fetchone()["database_name"] == database, "收據轉換資料庫目標不符。")
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s "
                "AND table_type='BASE TABLE'",
                (database, "admin_command_receipts"),
            )
            if cursor.fetchone() is None:
                require(not apply, "收據轉換缺少帳號收據資料表。")
                connection.rollback()
                return 0
            count = unprotected_account_receipt_count(cursor)
            if not apply or not count:
                connection.rollback()
                return count
            file_key = settings["runtime"].get(KEY_SETTING)
            process_key = os.environ.get(KEY_SETTING)
            require(not (file_key and process_key and file_key != process_key),
                    "收據金鑰的執行環境與受保護設定不同，已停止。")
            key = account_receipt_key(process_key or file_key or "")
            converted = convert_account_receipt_fingerprints(cursor, key)
        connection.commit()
        return converted
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def require_account_receipt_conversion_target(settings):
    is_local = settings["host"].casefold().rstrip(".") in {"localhost", "127.0.0.1", "::1"}
    if is_local:
        require(
            settings["database"].startswith(("lu_test_", "lu_nas_upgrade_"))
            and (settings["runtime"].get("APP_ENV") or "").casefold() in {"development", "dev", "local", "test"},
            "本機收據轉換只允許使用開發環境的 lu_test_* 或 lu_nas_upgrade_* 測試資料庫。",
        )
    else:
        require(settings["receipt_target_pinned"] and settings["ssl_mode"] == "VERIFY_IDENTITY",
                "正式收據轉換需指定 NAS 目標位址、連線埠、正式資料庫及可驗證主機身分的 TLS。")


class RestorePhase(str, Enum):
    PREPARED = "prepared"
    BACKING_UP = "backing_up"
    BACKUP_READY = "backup_ready"
    CREATING_CANDIDATE = "creating_candidate"
    CANDIDATE_CREATED = "candidate_created"
    IMPORTING_CANDIDATE = "importing_candidate"
    CANDIDATE_IMPORTED = "candidate_imported"
    PREPARING_CANDIDATE = "preparing_candidate"
    CANDIDATE_READY = "candidate_ready"
    EXPORTING = "exporting"
    EXPORT_READY = "export_ready"
    DROPPING_TARGET = "dropping_target"
    TARGET_DROPPED = "target_dropped"
    CREATING_TARGET = "creating_target"
    TARGET_CREATED = "target_created"
    IMPORTING_TARGET = "importing_target"
    VERIFYING_TARGET = "verifying_target"
    CLEANUP_PENDING = "cleanup_pending"
    COMPLETED = "completed"


_RESTORE_FORMAT = "nas-same-name-restore/v1"
_RESTORE_DB = re.compile(r"lu_nas_restore_\d{14}_[0-9a-f]{8}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RESTORE_CLEANUP = ("grants", "candidate", "before", "verified")
_RESTORE_BLOCKED_START = {
    RestorePhase.DROPPING_TARGET, RestorePhase.TARGET_DROPPED,
    RestorePhase.CREATING_TARGET, RestorePhase.TARGET_CREATED,
    RestorePhase.IMPORTING_TARGET, RestorePhase.VERIFYING_TARGET,
}


@dataclass(frozen=True)
class RestoreTarget:
    host: str
    port: int
    database: str

    @classmethod
    def from_connection(cls, host, port, database):
        return cls(host.strip().casefold().rstrip("."), int(port), database)

    def payload(self):
        return {"host": self.host, "port": self.port, "database": self.database}


def _restore_path(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts
            and not any(node.is_symlink() or node.is_junction() for node in (path, *path.parents)),
            "復原檔案位置超出本次操作範圍，或包含連結或轉接點。")
    return path


def _restore_marker(environment_file):
    return Path(environment_file).parent / "scratch" / "nas_database_maintenance" / "same-name-restore.json"


def _restore_read(path):
    _restore_path(path)
    if not path.exists():
        return None
    require(path.is_file() and path.stat().st_nlink == 1,
            "復原紀錄不是本次操作的獨立檔案。")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(payload, dict) and payload.get("format") == _RESTORE_FORMAT,
                "復原紀錄格式不符。")
        return payload
    except (OSError, UnicodeError, ValueError):
        raise MaintenanceBlocked("無法讀取本次復原紀錄，請維護人員核對。") from None


def _restore_write(path, payload):
    pending = _restore_path(path.with_name(path.name + ".pending"))
    _restore_path(path)
    if pending.exists():
        require(pending.is_file() and pending.stat().st_nlink == 1, "復原紀錄暫存檔身分不符。")
        pending.unlink()
    save(path, {"format": _RESTORE_FORMAT, **payload})


def _restore_hash(value):
    return hashlib.sha256(migration._canonical_json(value)).hexdigest()


def _restore_phase(state):
    try:
        phase = RestorePhase(state["phase"])
        target = state["target"]
        RestoreTarget(**target)
        require(
            _RESTORE_DB.fullmatch(state["candidate"])
            and state["candidate"].casefold() != target["database"].casefold()
            and all(_SHA256.fullmatch(state[key]) for key in ("environment_sha256", "archive_sha256", "archive_path_sha256"))
            and isinstance(state["target_existed"], bool),
            "復原紀錄的目標或備份身分不符。",
        )
        UUID(state["server_uuid"])
        if phase in _RESTORE_BLOCKED_START | {RestorePhase.CLEANUP_PENDING, RestorePhase.COMPLETED}:
            require(isinstance(state["evidence"], dict)
                    and _SHA256.fullmatch(state["evidence"]["schema_sha256"])
                    and isinstance(state["evidence"]["rows"], dict)
                    and _SHA256.fullmatch(state["verified_sha256"])
                    and (not state["target_existed"] or _SHA256.fullmatch(state["before_sha256"])),
                    "復原紀錄缺少目標驗證基準。")
        return phase
    except (TypeError, ValueError, KeyError):
        raise MaintenanceBlocked("復原紀錄缺少有效的目標或進度。") from None


def restore_startup_blocked(host, port, database, *, environment_file=ROOT / ".env"):
    """Read the local binding and its journal without opening a DB connection."""
    path = _restore_marker(environment_file)
    marker = _restore_read(path)
    if marker is None:
        return _restore_path(path.with_name(path.name + ".pending")).exists()
    try:
        requested = RestoreTarget.from_connection(host, port, database)
        recorded = RestoreTarget(**marker["target"])
        if (recorded.host, recorded.port, recorded.database.casefold()) != (
            requested.host, requested.port, requested.database.casefold(),
        ):
            return False
        journal = _restore_read(Path(marker["journal"]))
        require(journal is not None and journal["target"] == marker["target"]
                and journal["candidate"] == marker["candidate"],
                "本機與備份區的復原紀錄不相符。")
        return _restore_phase(journal) not in {RestorePhase.CLEANUP_PENDING, RestorePhase.COMPLETED}
    except (TypeError, ValueError, KeyError):
        raise MaintenanceBlocked("無法確認本機復原狀態。") from None


def _restore_require_stopped(settings):
    environment = Path(settings["environment_file"])
    state = environment.parent / "scratch" / "windows-remote" / "frontend-control" / "state.json"
    require(not state.exists(), "請先停止此安裝的工會系統與背景服務，再復原資料庫。")
    if os.name == "nt" and environment == ROOT / ".env":
        for port in (8000, 5173):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    raise MaintenanceBlocked("工會系統的服務連接埠仍在使用，請先停止服務。") from None


@contextmanager
def _restore_installation_lock(settings):
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes

    path = _restore_path(Path(settings["environment_file"]).parent / "scratch" / "windows-remote" / "manager.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    open_file = kernel.CreateFileW
    open_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_file.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = open_file(str(path), 0xC0000000, 0, None, 4, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        parent_holds_lock = (ctypes.get_last_error() == 32
                             and os.getenv("LABOR_UNION_RESTORE_MANAGER_PID") == str(os.getppid()))
        require(parent_holds_lock, "另一項管理操作正在執行，請待該操作完成再復原。")
        yield
        return
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


def _restore_server(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@server_uuid AS server_uuid, @@hostname AS hostname")
        row = cursor.fetchone()
    return str(UUID(row["server_uuid"])), row["hostname"]


def _restore_read_server(config):
    connection = config.connect()
    try:
        return _restore_server(connection)
    finally:
        connection.close()


def _restore_credentials(settings):
    runtime = settings["runtime"]
    require(runtime.get("DB_USER") and runtime.get("DB_PASSWORD"), "缺少工會系統原有的連線帳號。")
    return (
        ConnectionConfig(settings, user=runtime["DB_USER"], password=runtime["DB_PASSWORD"], readonly=True),
        reader(settings),
    )


def _restore_check_credentials(settings, database, server_uuid):
    for config in _restore_credentials(settings):
        connection = config.connect(database)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS name, @@server_uuid AS server_uuid")
                row = cursor.fetchone()
            require(row["name"] == database and str(UUID(row["server_uuid"])) == server_uuid,
                    "原連線帳號無法讀取本次復原資料庫。")
        finally:
            connection.close()


def _schema_grants(grants, scope):
    privileges = set()
    for grant in grants:
        match = re.match(r"^GRANT ([A-Z_, ]+) ON " + '`' + re.escape(scope) + '`' + r"\.\* TO ", grant)
        if match:
            privileges.update(item.strip() for item in match[1].split(","))
    return privileges


def _restore_full_rows(config, database, tables):
    connection = config.connect(database)
    try:
        result = {}
        with connection.cursor(pymysql.cursors.SSDictCursor) as cursor:
            for table in tables:
                safe = table.replace('`', '`' * 2)
                cursor.execute(f"SELECT * FROM {'`'}{safe}{'`'}")
                # SQL collation may tie distinct values in tables without a PK.
                rows = sorted(hashlib.sha256(migration._canonical_json(row)).digest() for row in cursor)
                hasher = hashlib.sha256()
                for row in rows:
                    hasher.update(row)
                result[table] = hasher.hexdigest()
        return result
    finally:
        connection.close()


def _restore_evidence(config, database, *, source=None, check_tables=False):
    equivalent = (source,) if source else ()
    inventory = schema_inventory(config, database, equivalent, reject_source_references=bool(source))
    snapshot = migration._schema_snapshot(config, database)
    snapshot.pop("sha256", None)
    programs = migration._restored_schema_program_evidence(snapshot, database)
    snapshot["triggers"] = programs["triggers"]
    snapshot["views"] = programs["views"]
    snapshot["show_create_tables"] = {
        name: re.sub(r"\bAUTO_INCREMENT=\d+\s*", "", migration._normalize_database_qualifiers(sql, (database,)))
        for name, sql in snapshot["show_create_tables"].items()
    }
    tables = [item["name"] for item in inventory["tables"] if item["kind"] == "BASE TABLE"]
    if check_tables:
        _restore_check_tables(config, database, tables)
    rows = migration._table_evidence(config, database)
    full_rows = _restore_full_rows(config, database, tables)
    require(set(rows) == set(full_rows), "復原證據的資料表範圍不相符。")
    return {
        "schema_sha256": _restore_hash({"inventory": inventory, "schema": snapshot}),
        "rows": {
            table: {"count": evidence["count"], "primary_key_sha256": evidence["primary_key_sha256"],
                    "full_row_sha256": full_rows[table]}
            for table, evidence in rows.items()
        },
    }


def _restore_check_tables(config, database, tables):
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            for table in tables:
                safe = table.replace('`', '`' * 2)
                cursor.execute(f"CHECK TABLE {'`'}{safe}{'`'}")
                results = cursor.fetchall()
                require(results and all(row["Msg_type"] != "error" for row in results)
                        and any(row["Msg_text"] == "OK" for row in results),
                        "復原資料表檢查失敗，已保留本次復原紀錄。")
    finally:
        connection.close()


def _restore_import(config, database, archive):
    command = migration._mysql_base(config, "mysql") + ["--binary-mode", "--one-database", database]
    result = migration.restore_sql_dump(command, archive, migration._client_environment(config))
    require(result.returncode == 0, "復原匯入未完成，已保留原備份及本次操作紀錄。")


def _restore_current(config, database, run, *, upgrade=False):
    from scripts import update_local_database as updater

    current = updater.build_additive_preview(config, database, run)
    if upgrade and current.get("status") == "ready" and current.get("pending_releases"):
        current = apply_candidate_additive_migrations(config, database, run, current)
    if current.get("status") != "current":
        reason = current.get("blocked_reason") or current.get("code")
        normalized = reason if isinstance(reason, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,95}", reason) else "schema_update_required"
        raise MaintenanceBlocked(f"備份與目前程式版本不相容（{normalized}），已停止復原。")
    updater.require_current_database(current)


@dataclass
class SameNameRestore:
    settings: dict
    target: RestoreTarget
    connection: object
    config: ConnectionConfig
    journal: Path
    run: Path
    marker: Path
    state: dict

    @property
    def candidate(self):
        return self.state["candidate"]

    @property
    def database(self):
        return self.target.database

    @property
    def phase(self):
        return _restore_phase(self.state)

    def record(self, phase, **evidence):
        updated = {**self.state, **evidence, "phase": phase.value}
        _restore_write(self.journal, updated)
        self.state = updated

    def check_identity(self):
        _restore_require_stopped(self.settings)
        require(
            digest(self.settings["environment_file"]) == self.state["environment_sha256"]
            and _restore_server(self.connection)[0] == self.state["server_uuid"],
            "本次復原的伺服器或 .env 設定已改變，已停止。",
        )

    def object_path(self, kind):
        moment = datetime.fromisoformat(self.state["backup_time"])
        stem = moment.strftime("union_db_%Y%m%d_%H%M%S")
        root = _restore_path(self.run / kind)
        return root, moment, root / moment.strftime("%Y-%m") / (stem + ".zip"), root / "_partial" / stem

    def backup_receipt(self, kind, database, *, expected=None):
        _, _, path, _ = self.object_path(kind)
        receipt = validate_backup(path)
        require(
            receipt.get("database") == database
            and receipt.get("host") == self.settings["host"]
            and receipt.get("port") == self.target.port
            and receipt.get("server") == self.state["server_name"]
            and (expected is None or receipt["bundle_sha256"] == expected),
            "本次復原的備份或匯出檔身分不符。",
        )
        return receipt

    def produce_backup(self, kind, database):
        root, moment, path, partial = self.object_path(kind)
        if not _restore_path(path).exists():
            require(not _restore_path(partial).exists(), "本次備份或匯出結果未明，請核對本次紀錄。")
            nas_directory(self.run, kind)
            settings = {**self.settings, "database": database, "scheduled_backup": False}
            require(_restore_read_server(reader(settings))[0] == self.state["server_uuid"],
                    "備份連線的伺服器身分不符。")
            require(backup(settings, operation_root=root, moment=moment) == path, "本次備份位置不符。")
        return self.backup_receipt(kind, database)

    def create_database(self, database, inventory):
        charset, collation = inventory["charset"], inventory["collation"]
        require(IDENTIFIER.fullmatch(charset) and IDENTIFIER.fullmatch(collation), "備份的資料庫字元集設定無效。")
        self.check_identity()
        quoted = '`' + database + '`'
        with self.connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE {quoted} CHARACTER SET {charset} COLLATE {collation}")

    def drop_database(self, database):
        self.check_identity()
        quoted = '`' + database + '`'
        with self.connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE {quoted}")

    def record_grant(self, account, scope, privileges, existing):
        account_hash = _restore_hash(account)
        entry = {"scope": scope, "privileges": sorted(privileges)}
        grants = self.state.get("grants", {})
        if account_hash in grants:
            require(grants[account_hash] == entry and existing == privileges, "暫存庫的帳號權限身分不符。")
            return False
        require(not existing, "暫存庫已有權限，無法確認屬於本次復原。")
        self.record(self.phase, grants={**grants, account_hash: entry})
        return True

    def revoke_grants(self):
        entries = self.state.get("grants", {})
        if not entries:
            return
        accounts = {}
        for probe in _restore_credentials(self.settings):
            connection = probe.connect()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT CURRENT_USER() AS account, @@server_uuid AS server_uuid")
                    result = cursor.fetchone()
                    require(str(UUID(result["server_uuid"])) == self.state["server_uuid"],
                            "清理連線的伺服器身分不符。")
                    accounts[_restore_hash(result["account"])] = result["account"].rsplit("@", 1)
            finally:
                connection.close()
        require(entries.keys() <= accounts.keys(), "無法確認本次所建的暫存庫權限。")
        with self.connection.cursor() as cursor:
            for account, entry in entries.items():
                scope = entry["scope"]
                require(scope in {self.candidate, self.candidate.replace("_", r"\_")},
                        "暫存庫的權限清理範圍不符。")
                user, host = accounts[account]
                cursor.execute("SHOW GRANTS FOR %s@%s", (user, host))
                existing = _schema_grants([next(iter(row.values())) for row in cursor.fetchall()], scope)
                if existing:
                    require(sorted(existing) == entry["privileges"], "暫存庫的權限已有變更，未清理。")
                    quoted = '`' + scope + '`'
                    cursor.execute(f"REVOKE {','.join(sorted(existing))} ON {quoted}.* FROM %s@%s", (user, host))
                    cursor.execute("SHOW GRANTS FOR %s@%s", (user, host))
                    require(not _schema_grants([next(iter(row.values())) for row in cursor.fetchall()], scope),
                            "本次暫存庫權限清理未完成。")

    def clean_file(self, kind):
        root, _, path, partial = self.object_path(kind)
        expected = self.state.get(kind + "_sha256")
        if expected is None:
            require(kind == "before" and not self.state["target_existed"]
                    and not _restore_path(root).exists(), "本次備份清理身分不符。")
            return
        path = _restore_path(path)
        partial = _restore_path(partial)
        if path.exists():
            database = self.database if kind == "before" else self.candidate
            receipt = self.backup_receipt(kind, database, expected=expected)
            require(path.stat().st_nlink == 1
                    and _restore_hash(str(path)) != self.state["archive_path_sha256"],
                    "本次清理檔案與來源備份身分重疊。")
            if partial.exists():
                staged = _restore_path(partial / receipt["archive"])
                require({file.name for file in partial.iterdir()} <= {staged.name},
                        "備份暫存目錄含無法確認的檔案，未清理。")
                if staged.exists():
                    require(staged.is_file() and staged.stat().st_nlink == 1
                            and digest(staged) == receipt["sha256"], "備份暫存檔身分不符。")
                    staged.unlink()
                partial.rmdir()
            path.unlink()
        require(not path.exists() and not partial.exists(), "備份或匯出檔清理未完成。")

    def cleanup(self):
        try:
            self.check_identity()
            require(migration.database_exists(self.config, self.database),
                    "同名目標庫已不在，已停止清理。")
            for item in _RESTORE_CLEANUP:
                if item in self.state.get("cleaned", []):
                    continue
                self.check_identity()
                self.record(RestorePhase.CLEANUP_PENDING, cleaning=item)
                if item == "grants":
                    self.revoke_grants()
                elif item == "candidate":
                    if migration.database_exists(self.config, self.candidate):
                        require(_restore_evidence(self.config, self.candidate) == self.state["evidence"],
                                "暫存驗證庫身分或內容已改變，未清理。")
                        self.drop_database(self.candidate)
                    require(not migration.database_exists(self.config, self.candidate), "暫存庫清理未完成。")
                else:
                    self.clean_file(item)
                self.record(RestorePhase.CLEANUP_PENDING, cleaning=None, cleaned=[*self.state.get("cleaned", []), item])
            _restore_write(self.run / "operation.json", {**self.state, "phase": RestorePhase.COMPLETED.value})
            marker = _restore_read(self.marker)
            require(marker is not None and marker.get("candidate") == self.candidate
                    and marker.get("journal") == str(self.journal) and marker.get("target") == self.target.payload(),
                    "本機復原紀錄身分已改變，未清理。")
            self.marker.unlink()
            require(not self.marker.exists(), "本機復原紀錄清理未完成。")
            self.record(RestorePhase.COMPLETED)
        except Exception:
            raise RestoreCleanupPending("資料復原成功，清理待完成。再次執行復原只會接續清理本次暫存物。") from None

    def prepare_candidate(self, info, archive):
        if self.phase == RestorePhase.BACKUP_READY:
            require(not migration.database_exists(self.config, self.candidate), "本次暫存庫名稱已存在，已停止。")
            self.record(RestorePhase.CREATING_CANDIDATE)
        if self.phase == RestorePhase.CREATING_CANDIDATE:
            require(not migration.database_exists(self.config, self.candidate), "暫存庫建立結果未明，請核對本次紀錄。")
            self.create_database(self.candidate, info["inventory"])
            self.record(RestorePhase.CANDIDATE_CREATED)
        if self.phase == RestorePhase.CANDIDATE_CREATED:
            self.check_identity()
            require(digest(_restore_path(archive)) == self.state["archive_sha256"],
                    "備份 A 已改變，未開始匯入。")
            require_event_scheduler_safe(self.config, info)
            self.record(RestorePhase.IMPORTING_CANDIDATE)
            _restore_import(self.config, self.candidate, archive)
            self.record(RestorePhase.CANDIDATE_IMPORTED)
        require(self.phase != RestorePhase.IMPORTING_CANDIDATE, "暫存庫匯入結果未明，請核對本次紀錄。")
        if self.phase == RestorePhase.CANDIDATE_IMPORTED:
            config = writer(self.settings, self.candidate)
            inventory = schema_inventory(config, self.candidate, (info["database"],), reject_source_references=True)
            verify_restored_inventory(inventory, info["inventory"])
            self.check_identity()
            self.record(RestorePhase.PREPARING_CANDIDATE)
            _restore_current(config, self.candidate, self.run, upgrade=True)
            protect_account_receipts(config, self.candidate, apply=True)
            from infrastructure.mysql.nas_mutations import ensure_nas_procedures
            connection = config.connect(self.candidate)
            try:
                ensure_nas_procedures(connection)
            except Exception:
                raise MaintenanceBlocked("暫存驗證庫的固定程序準備失敗，已保留本次紀錄。") from None
            finally:
                connection.close()
            prepare_runtime_access(self.settings, self.candidate, record_grant=self.record_grant)
            _restore_check_credentials(self.settings, self.candidate, self.state["server_uuid"])
            evidence = _restore_evidence(config, self.candidate, source=info["database"], check_tables=True)
            self.record(RestorePhase.CANDIDATE_READY, evidence=evidence)
        require(self.phase != RestorePhase.PREPARING_CANDIDATE, "暫存庫升級或準備結果未明，請核對本次紀錄。")

    def replace_target(self, final):
        if self.phase == RestorePhase.EXPORT_READY:
            self.check_identity()
            require(_restore_evidence(self.config, self.candidate) == self.state["evidence"],
                    "暫存驗證庫內容已改變，未重建目標庫。")
            require(migration.database_exists(self.config, self.database) == self.state["target_existed"],
                    "目標庫狀態已改變，未重建目標庫。")
            if self.state["target_existed"]:
                self.backup_receipt("before", self.database, expected=self.state["before_sha256"])
            self.record(RestorePhase.DROPPING_TARGET)
        if self.phase == RestorePhase.DROPPING_TARGET:
            if migration.database_exists(self.config, self.database):
                require(self.state["target_existed"]
                        and _restore_evidence(self.config, self.database) == self.state["before_evidence"],
                        "待替換資料庫內容已改變，未重建目標庫。")
                self.drop_database(self.database)
            self.record(RestorePhase.TARGET_DROPPED)
        if self.phase == RestorePhase.TARGET_DROPPED:
            self.record(RestorePhase.CREATING_TARGET)
        if self.phase == RestorePhase.CREATING_TARGET:
            if not migration.database_exists(self.config, self.database):
                self.create_database(self.database, final["inventory"])
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT default_character_set_name AS charset, default_collation_name AS collation "
                    "FROM information_schema.schemata WHERE schema_name=%s "
                    "AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=%s) "
                    "AND NOT EXISTS (SELECT 1 FROM information_schema.routines WHERE routine_schema=%s) "
                    "AND NOT EXISTS (SELECT 1 FROM information_schema.events WHERE event_schema=%s)",
                    (self.database,) * 4,
                )
                defaults = cursor.fetchone()
            require(defaults == {key: final["inventory"][key] for key in ("charset", "collation")},
                    "目標庫建立結果未明，請核對本次紀錄。")
            self.record(RestorePhase.TARGET_CREATED)
        if self.phase == RestorePhase.TARGET_CREATED:
            self.check_identity()
            self.record(RestorePhase.IMPORTING_TARGET)
            _restore_import(self.config, self.database, self.object_path("verified")[2])
            self.record(RestorePhase.VERIFYING_TARGET)
        if self.phase in {RestorePhase.IMPORTING_TARGET, RestorePhase.VERIFYING_TARGET}:
            self.check_identity()
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS n FROM information_schema.processlist WHERE db=%s", (self.database,))
                require(not cursor.fetchone()["n"], "目標庫仍有連線，尚無法核對復原結果。")
            require(_restore_evidence(self.config, self.database, source=self.candidate, check_tables=True) == self.state["evidence"],
                    "同名目標庫結構或資料與暫存基準不符，已保留本次復原資料。")
            _restore_check_credentials(self.settings, self.database, self.state["server_uuid"])
            _restore_current(self.config, self.database, self.run)
            self.record(RestorePhase.CLEANUP_PENDING, cleaned=[])

    def execute(self, info, archive):
        self.check_identity()
        if self.phase == RestorePhase.CLEANUP_PENDING:
            self.cleanup()
            return
        self.config.client_prefix("mysql")
        require_event_scheduler_safe(self.config, info)
        if self.phase == RestorePhase.PREPARED:
            if self.state["target_existed"]:
                before = _restore_evidence(self.config, self.database)
                self.record(RestorePhase.BACKING_UP, before_evidence=before)
            else:
                self.record(RestorePhase.BACKUP_READY)
        if self.phase == RestorePhase.BACKING_UP:
            self.check_identity()
            receipt = self.produce_backup("before", self.database)
            require(receipt["inventory"] == schema_inventory(self.config, self.database)
                    and _restore_evidence(self.config, self.database) == self.state["before_evidence"],
                    "替換前備份期間的目標庫內容已改變，未重建目標庫。")
            self.record(RestorePhase.BACKUP_READY, before_sha256=receipt["bundle_sha256"])
        self.prepare_candidate(info, archive)
        if self.phase == RestorePhase.CANDIDATE_READY:
            self.record(RestorePhase.EXPORTING)
        if self.phase == RestorePhase.EXPORTING:
            self.check_identity()
            final = self.produce_backup("verified", self.candidate)
            require(final["inventory"] == schema_inventory(self.config, self.candidate)
                    and _restore_evidence(self.config, self.candidate) == self.state["evidence"],
                    "匯出期間的暫存驗證庫內容已改變，未重建目標庫。")
            self.record(RestorePhase.EXPORT_READY, verified_sha256=final["bundle_sha256"])
        final = self.backup_receipt("verified", self.candidate, expected=self.state["verified_sha256"])
        if self.state["target_existed"]:
            self.backup_receipt("before", self.database, expected=self.state["before_sha256"])
        require_event_scheduler_safe(self.config, final)
        self.replace_target(final)
        self.cleanup()


def _restore_locked(settings, archive, info, root, config, connection):
    target = RestoreTarget.from_connection(settings["host"], settings["port"], settings["database"])
    env_digest = digest(settings["environment_file"])
    environment = dotenv_values(settings["environment_file"], encoding="utf-8", interpolate=False)
    configured = RestoreTarget.from_connection(environment.get("DB_HOST") or "127.0.0.1",
                                               environment.get("DB_PORT") or 3306,
                                               (environment.get("DB_DATABASE") or "").strip())
    require(configured == target and digest(settings["environment_file"]) == env_digest,
            "目前 .env 與本次復原設定不符，已停止。")
    server_uuid, hostname = _restore_server(connection)
    controller = nas_directory(root, "_maintenance", "_same_name_restore")
    key = _restore_hash({"server_uuid": server_uuid, "database": target.database.casefold()})
    journal = controller / (key + ".json")
    marker = _restore_marker(settings["environment_file"])
    existing = _restore_read(marker)
    if existing:
        linked = _restore_read(Path(existing.get("journal", "")))
        replacing_marker = linked is not None and Path(existing["journal"]) == journal and _restore_phase(linked) == RestorePhase.PREPARED
        require(linked is not None and linked.get("target") == existing.get("target")
                and (linked.get("candidate") == existing.get("candidate") or replacing_marker),
                "本機與備份區的復原紀錄不相符。")
        require(_restore_phase(linked) == RestorePhase.COMPLETED or Path(existing["journal"]) == journal,
                "此安裝已有未完成復原，請先核對原目標、伺服器及備份位置。")
    state = _restore_read(journal)
    binding = {"target": target.payload(), "environment_sha256": env_digest, "server_uuid": server_uuid}
    if info is not None:
        binding.update(archive_path_sha256=_restore_hash(str(archive)),
                       archive_sha256=info.get("bundle_sha256", info["sha256"]))
    else:
        require(state is not None and _restore_phase(state) == RestorePhase.CLEANUP_PENDING,
                "找不到可接續的已驗證復原，請選擇備份 A。")
    if state is None or _restore_phase(state) == RestorePhase.COMPLETED:
        require_event_scheduler_safe(config, info)
        candidate = new_candidate("restore")
        require(_RESTORE_DB.fullmatch(candidate) and candidate.casefold() != target.database.casefold(),
                "本次暫存庫名稱無效。")
        run = nas_directory(root, "_maintenance", candidate)
        state = {**binding, "candidate": candidate, "server_name": hostname,
                 "backup_time": backup_time().isoformat(), "phase": RestorePhase.PREPARED.value,
                 "target_existed": migration.database_exists(config, target.database)}
        _restore_write(journal, state)
    else:
        require(all(state.get(key) == value for key, value in binding.items()),
                "此目標已有未完成復原，請核對原 .env、備份 A 及伺服器身分。")
        run = _restore_path(root / "_maintenance" / state["candidate"])
        require(run.is_dir(), "本次復原紀錄的暫存目錄已遺失。")
    if not marker.parent.is_dir():
        _restore_path(marker)
        private_directory(marker.parent)
    _restore_write(marker, {"target": target.payload(), "candidate": state["candidate"], "journal": str(journal)})
    operation = SameNameRestore(settings, target, connection, config, journal, run, marker, state)
    operation.execute(info, archive)
    return run


def restore(settings, archive):
    info = None
    if archive is not None:
        archive = _restore_path(Path(archive).absolute())
        info = validate_backup(archive)
    database = settings["database"]
    require(IDENTIFIER.fullmatch(database) and database.casefold() not in migration.LOCAL_ADDITIVE_SYSTEM_DATABASES,
            "復原目標須為目前 .env 設定的應用資料庫。")
    with _restore_installation_lock(settings):
        _restore_require_stopped(settings)
        root = _restore_path(Path(settings["backup_root"]).absolute())
        destination_ready(settings, writable=True)
        config = writer(settings)
        with maintenance_lock(config) as connection:
            return _restore_locked(settings, archive, info, root, config, connection)


def restore_has_pending_cleanup(settings):
    marker = _restore_read(_restore_marker(settings["environment_file"]))
    if marker is None:
        return False
    state = _restore_read(Path(marker["journal"]))
    require(state is not None and state["target"] == marker["target"]
            and state["candidate"] == marker["candidate"], "本機與備份區的復原紀錄不相符。")
    return _restore_phase(state) == RestorePhase.CLEANUP_PENDING


@contextmanager
def schedule_lock():
    private_directory(SCHEDULE.parent)
    with (SCHEDULE.parent / "schedule.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def configure_daily_backup(at="18:00", *, environment_file=ROOT / ".env", settings_file=SETTINGS, expected_version=None):
    with schedule_lock():
        version = json.loads(SCHEDULE.read_text(encoding="utf-8")).get("version", 0) if SCHEDULE.is_file() else 0
        if expected_version is not None and expected_version != version:
            raise ScheduleConflict("備份時間已由其他人修改，請重新載入後再儲存。")
        return _configure_daily_backup(at, environment_file=environment_file, settings_file=settings_file, version=version + 1)


def _configure_daily_backup(at="18:00", *, environment_file=ROOT / ".env", settings_file=SETTINGS, version=1):
    require(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", at), "請填寫有效時間，例如 18:00。")
    settings = load_settings(environment_file, settings_file)
    require(os.name == "nt", "每日備份排程須在正式 Windows 電腦設定。")
    destination_ready(settings, writable=True)
    private_directory(SCHEDULE.parent)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    require(pythonw.is_file(), "缺少 Windows 背景執行工具，請維護人員檢查安裝。")
    # Literal values use PowerShell single-quote escaping, never shell expansion.
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    arguments = subprocess.list2cmdline([str(Path(__file__).resolve()), "backup", "--scheduled",
                 "--environment-file", str(settings["environment_file"]), "--settings-file", str(settings["settings_file"])])
    script = "$ErrorActionPreference='Stop'; " + "; ".join([
        f"$existing=Get-ScheduledTask -TaskName {quote(TASK_NAME)} -ErrorAction SilentlyContinue",
        f"if ($existing -and ($existing.Actions.Count -ne 1 -or $existing.Actions.Execute -ne {quote(pythonw)} -or $existing.Actions.Arguments -ne {quote(arguments)})) {{ throw 'Existing task belongs to another installation' }}",
        f"$action=New-ScheduledTaskAction -Execute {quote(pythonw)} -Argument {quote(arguments)} -WorkingDirectory {quote(ROOT)}",
        f"$trigger=New-ScheduledTaskTrigger -Daily -At {quote(at)}",
        "$principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited",
        "$options=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)",
        f"Register-ScheduledTask -TaskName {quote(TASK_NAME)} -Action $action -Trigger $trigger -Principal $principal -Settings $options -Force | Out-Null"])
    result = run_windows_powershell(script)
    require(result.returncode == 0, "每日排程設定失敗，請確認 Windows 帳號權限。")
    save(SCHEDULE, {"enabled": True, "time": at, "task_name": TASK_NAME, "version": version,
         "environment_file": str(settings["environment_file"]), "settings_file": str(settings["settings_file"])})
    return {"enabled": True, "time": at, "version": version, "requires_logged_in_computer": True}


def registered_backup_enabled():
    if os.name != "nt":
        return False
    script = (f"$task=Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue; "
              "if ($task -and $task.State -ne 'Disabled') { Write-Output 'enabled' }")
    completed = run_windows_powershell(script)
    return completed.returncode == 0 and completed.stdout.strip() == "enabled"


def available_backups(settings):
    root = settings["backup_root"]
    found = []
    for path in root.glob("????-??/union_db_*.zip"):
        if path.is_symlink() or not path.is_file():
            continue
        parsed = _backup_kind_and_stamp(path)
        if parsed is None or parsed[0] != "zip":
            continue
        try:
            info = _read_zip_backup(path, parsed[1], verify_payload=False)
            found.append((path, info))
        except (MaintenanceBlocked, OSError, ValueError):
            continue
    receipts_root = root / "_receipts"
    if receipts_root.is_dir():
        for path in receipts_root.glob("????-??/union_db_*.json"):
            if path.is_symlink():
                continue
            try:
                info = json.loads(path.read_text(encoding="utf-8"))
                name, month = info.get("archive", ""), info.get("month", "")
                if not ARCHIVE_NAME.fullmatch(name) or not re.fullmatch(r"\d{4}-\d{2}", month):
                    continue
                archive = root / month / name
                if (info.get("format") == "nas-sql-backup/v2" and info.get("status") == "completed"
                        and receipt_path(archive) == path and archive.is_file() and not archive.is_symlink()
                        and archive.with_suffix(".gz.sha256").is_file()):
                    found.append((archive, info))
            except (OSError, ValueError):
                continue
    found.sort(key=lambda item: (_backup_kind_and_stamp(item[0])[1], str(item[1].get("created_at", "")), item[0].suffix == ".zip"), reverse=True)
    yield from found


def _retention_path(root, path):
    """Resolve the exact ZIP within its canonical month before any removal."""
    root, path = Path(root), Path(path)
    parsed = _backup_kind_and_stamp(path)
    require(parsed is not None and parsed[0] == "zip"
            and path.parent.parent == root and path.parent.name == parsed[1][:4] + "-" + parsed[1][4:6],
            "滾動保存範圍無法確認，未清理備份。")
    require(not any(node.is_symlink() or node.is_junction() for node in (path, *path.parents)),
            "滾動保存遇到連結或轉接點，未清理備份。")
    require(path.resolve().is_relative_to(root.resolve()) and path.is_file(),
            "滾動保存範圍無法確認，未清理備份。")
    return datetime.strptime(parsed[1], "%Y%m%d_%H%M%S").replace(tzinfo=TAIPEI)


def retain_scheduled_backups(settings, latest, *, now=None):
    """Called under the maintenance lock only after a new scheduled backup succeeds.

    The union of calendar-day, ISO-week and calendar-month buckets determines
    retention. Unmarked, manual and legacy backups never enter this policy.
    """
    root = destination_ready(settings)
    now = (now or backup_time()).astimezone(TAIPEI)
    latest = Path(latest)
    _retention_path(root, latest)
    current = validate_backup(latest)
    target = (settings["host"], int(settings["port"]), settings["database"])
    matches = lambda info: (info.get("host"), info.get("port"), info.get("database")) == target
    require(current.get("retention_managed") is True and matches(current),
            "本次備份不符合排程保存範圍，未清理備份。")
    candidates = []
    for path in root.glob("????-??/union_db_*.zip"):
        moment = _retention_path(root, path)
        info = read_backup_receipt(path)
        if info.get("retention_managed") is not True or not matches(info):
            continue
        # Verify the retained representatives as well as expired candidates.
        # A corrupt newer representative must never evict an older good copy.
        verified = validate_backup(path)
        candidates.append((path, moment, verified["bundle_sha256"]))
    keep = {latest}
    today = now.date()
    this_week = today - timedelta(days=today.weekday())
    this_month = today.year * 12 + today.month - 1
    weeks, months = {}, {}
    for path, moment, _ in sorted(candidates, key=lambda item: (item[1], item[0].name), reverse=True):
        day = moment.date()
        if moment > now:
            keep.add(path)
            continue
        if 0 <= (today - day).days < 14:
            keep.add(path)
        week = day - timedelta(days=day.weekday())
        if timedelta(0) <= this_week - week < timedelta(weeks=8):
            weeks.setdefault(week, path)
        month = day.year * 12 + day.month - 1
        if 0 <= this_month - month < 12:
            months.setdefault(month, path)
    keep.update(weeks.values())
    keep.update(months.values())
    expired = [(path, checksum) for path, _, checksum in candidates if path not in keep]
    if not expired:
        return 0
    # Validate the entire removal set before the first deletion, then retain
    # the exact plan and per-file completion facts for interrupted runs.
    for path, checksum in expired:
        _retention_path(root, path)
        require(digest(path) == checksum, "備份在清理前已改變，未清理備份。")
    directory = nas_directory(root, "_retention")
    journal = directory / (now.strftime("%Y%m%d_%H%M%S_") + uuid4().hex + ".json")
    receipt = {"format":"nas-backup-retention/v1", "status":"planned", "time":now.isoformat(),
        "policy":{"days":14, "weeks":8, "months":12},
        "latest":str(latest.relative_to(root)),
        "planned":[{"file":str(path.relative_to(root)), "sha256":checksum} for path, checksum in expired],
        "removed":[]}
    save(journal, receipt)
    for path, checksum in expired:
        _retention_path(root, path)
        require(digest(path) == checksum, "備份在清理前已改變，已停止後續清理。")
        path.unlink()
        receipt["removed"].append(str(path.relative_to(root)))
        save(journal, receipt)
    receipt["status"] = "completed"
    save(journal, receipt)
    return len(expired)


def record_backup_result(settings, status, *, message=None, created_at=None):
    private_directory(LOCAL_STATUS.parent)
    previous = json.loads(LOCAL_STATUS.read_text(encoding="utf-8")) if LOCAL_STATUS.is_file() else {}
    target = f"{settings['host']}:{settings['port']}"
    last_success = previous.get("last_success") if previous.get("target") == target else None
    save(LOCAL_STATUS, {"status": status, "time": datetime.now(timezone.utc).isoformat(),
         "message": message, "target": target, "last_success": created_at if status == "passed" else last_success})


def backup_status():
    result = {"enabled": False, "time": "18:00", "version": 0, "last_backup": None, "last_result": None,
              "configured": False, "storage_ready": False, "storage_message": "備份位置尚未設定。",
              "disaster_recovery_ready": False}
    if SCHEDULE.is_file():
        saved = json.loads(SCHEDULE.read_text(encoding="utf-8"))
        result.update({key: saved[key] for key in ("enabled", "time")})
        result["version"] = saved.get("version", 0)
        result["enabled"] = bool(result["enabled"] and registered_backup_enabled())
    try:
        settings = load_settings()
        result["configured"] = True
        if LOCAL_STATUS.is_file():
            data = json.loads(LOCAL_STATUS.read_text(encoding="utf-8"))
            if data.get("target") == f"{settings['host']}:{settings['port']}":
                result["last_result"] = {key: data.get(key) for key in ("status", "time", "message")}
                result["last_backup"] = data.get("last_success")
        try:
            destination_ready(settings)
            result["storage_ready"] = True
            result["storage_message"] = "備份區目前可讀取；備份時會再驗證寫入。"
            latest = next(available_backups(settings), None)
            if latest:
                result["last_backup"] = latest[1]["created_at"]
        except (OSError, MaintenanceBlocked):
            result["storage_message"] = "NAS 備份區目前無法使用，備份不會改存本機。"
    except (OSError, ValueError, MaintenanceBlocked):
        pass
    return result


def select_backup_file(settings):
    require(os.name == "nt", "備份檔案選擇視窗須在已登入桌面的 Windows 電腦操作。")
    initial = "'" + str(settings["backup_root"]).replace("'", "''") + "'"
    script = "\n".join([
        "$ErrorActionPreference='Stop'",
        "[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)",
        "Add-Type -AssemblyName System.Windows.Forms",
        "$dialog=New-Object System.Windows.Forms.OpenFileDialog",
        "$owner=New-Object System.Windows.Forms.Form",
        "try {",
        "  $owner.TopMost=$true",
        "  $owner.Opacity=0",
        "  $owner.ShowInTaskbar=$false",
        "  $owner.StartPosition='CenterScreen'",
        "  $owner.Show()",
        "  $dialog.Title='選擇要復原的資料庫備份'",
        "  $dialog.Filter='資料庫備份 (*.zip;*.sql.gz)|*.zip;*.sql.gz'",
        "  $dialog.CheckFileExists=$true",
        "  $dialog.Multiselect=$false",
        "  $dialog.RestoreDirectory=$true",
        f"  $dialog.InitialDirectory={initial}",
        "  if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {",
        "    [Console]::Write($dialog.FileName)",
        "  }",
        "} finally { $dialog.Dispose(); $owner.Dispose() }",
    ])
    result = run_windows_powershell(script, timeout=None, sta=True)
    require(result.returncode == 0, "無法開啟備份檔案選擇視窗，請確認使用已登入桌面的 Windows 帳號。")
    selected = result.stdout.strip()
    require(selected, "已取消，資料庫不變。")
    return Path(selected)


def choose_backup(settings):
    try:
        destination_ready(settings)
        choices = list(available_backups(settings))[:30]
    except (OSError, MaintenanceBlocked):
        choices = []
    if not choices:
        print(f"預設備份位置找不到可用備份：{settings['backup_root']}")
        print("將開啟檔案選擇視窗，請選取 .zip 或舊版 .sql.gz 備份檔；選取舊版 .sql.gz 時需保留校驗檔與成功紀錄。")
        return select_backup_file(settings)
    paths = [item[0] for item in choices]
    require(paths, "指定位置沒有完整且已完成的備份。")
    for index, (path, info) in enumerate(choices, 1):
        print(f"{index}. {path.parent.name}／{path.name}（{info['database']}）")
    selection = input("請輸入要復原的備份編號（直接 Enter 取消）：").strip()
    require(selection.isdigit() and 1 <= int(selection) <= min(len(paths), 30), "已取消，資料庫不變。")
    return paths[int(selection) - 1]


def format_maintenance_error(error: Exception, settings: dict | None = None) -> str:
    """提供清晰且具排查指引的維護錯誤診斷訊息。"""
    if isinstance(error, MaintenanceBlocked):
        return f"[環境與設定檢查未通過] {error}"

    if isinstance(error, pymysql.MySQLError):
        args = error.args
        errno = args[0] if args and isinstance(args[0], int) else None
        detail = args[1] if len(args) > 1 else str(error)
        host = settings.get("host", "127.0.0.1") if settings else "127.0.0.1"
        port = settings.get("port", 3306) if settings else 3306
        user = settings.get("runtime", {}).get("DB_USER", "root") if settings else "root"
        database = settings.get("database", "union_db") if settings else "union_db"

        if errno in (2002, 2003):
            return (
                f"[連線失敗 (MySQL 錯誤碼 {errno})]\n"
                f"無法連線至 MySQL 伺服器 ({host}:{port})。\n"
                f"可能原因與建議排查：\n"
                f"  1. MySQL 服務尚未啟動。若使用 Docker，請確認 Docker 容器已啟動 (例如: docker start mysql_db)；\n"
                f"  2. 若為 Windows 系統服務或 NAS，請確認 MySQL 服務運作中且防火牆允許通訊埠 {port}；\n"
                f"  3. 請確認 .env 中的 DB_HOST 與 DB_PORT 設定正確。"
            )
        if errno == 1045:
            return (
                f"[帳號驗證失敗 (MySQL 錯誤碼 1045)]\n"
                f"登入 MySQL 伺服器失敗 (使用者: '{user}', 目標: {host}:{port})。\n"
                f"可能原因：密碼或使用者名稱錯誤。\n"
                f"建議排查：請檢查 .env 中的 DB_USER 與 DB_PASSWORD 是否與實際 MySQL 密碼相符。"
            )
        if errno == 1049:
            return (
                f"[資料庫不存在 (MySQL 錯誤碼 1049)]\n"
                f"MySQL 伺服器上找不到指定的資料庫 '{database}'。\n"
                f"建議排查：請檢查 .env 中的 DB_DATABASE 設定，或確認資料庫是否已建立。"
            )
        return f"[MySQL 資料庫錯誤 (錯誤碼 {errno})]: {detail}"

    if isinstance(error, FileNotFoundError):
        fn = getattr(error, "filename", "") or str(error)
        return (
            f"[找不到執行工具]\n"
            f"系統找不到指定檔案或命令工具: {fn}\n"
            f"建議排查：若為 mysql 或 mysqldump，請確認已放置於專案 tools/mysql/ 目錄下，或安裝並加入系統 PATH。"
        )

    err_name = type(error).__name__
    return f"[資料庫維護未完成 ({err_name})]: {error}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("backup", "upgrade", "restore", "protect-account-receipts"))
    parser.add_argument("--environment-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--settings-file", type=Path, default=SETTINGS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--backup-file", type=Path)
    parser.add_argument("--time", default="18:00")
    parser.add_argument("--install-daily", action="store_true")
    args = parser.parse_args(argv)
    settings = None
    cleanup_warning = None
    try:
        require(not args.scheduled or args.mode == "backup", "排程只允許備份，不能自動升級或復原。")
        require(not args.install_daily or args.mode == "backup", "只有備份腳本可以設定排程。")
        settings = load_settings(args.environment_file, args.settings_file)
        settings["scheduled_backup"] = args.mode == "backup" and args.scheduled
        if args.mode == "protect-account-receipts":
            require_account_receipt_conversion_target(settings)
        if args.dry_run:
            if args.mode != "protect-account-receipts":
                for executable in (("mysqldump",) if args.mode == "backup" else ("mysql", "mysqldump")):
                    reader(settings).client_prefix(executable)
            print("設定與工具檢查通過；未連線、未變更資料庫。")
            return 0
        if args.install_daily:
            configure_daily_backup(args.time, environment_file=args.environment_file, settings_file=args.settings_file)
            print(f"已設定每日 {args.time} 備份。電腦須開機並登入 Windows。")
            return 0
        print(f"NAS：{settings['host']}:{settings['port']}　資料庫：{settings['database']}")
        if args.mode == "protect-account-receipts":
            database = settings["database"]
            count = protect_account_receipts(reader(settings), database, apply=False)
            print(f"需轉換的帳號指紋數：{count}。")
            if not count:
                return 0
            answer = input(f"確認已停止管理服務後，輸入 PROTECT {database} 開始轉換：").strip()
            if answer != f"PROTECT {database}":
                print("已取消，資料庫不變。")
                return 0
            config = writer(settings)
            with maintenance_lock(config):
                converted = protect_account_receipts(config, database, apply=True)
            print(f"收據轉換完成，已核對無未保護的帳號收據。轉換筆數：{converted}。")
            return 0
        if args.mode == "backup" and not args.scheduled:
            print("1. 立即備份\n2. 設定每日備份（預設 18:00）\n直接 Enter 取消")
            answer = input("請選擇：").strip().strip("\ufeff")
            if answer == "2":
                at = input("每日備份時間（Enter 使用 18:00）：").strip() or "18:00"
                configure_daily_backup(at, environment_file=args.environment_file, settings_file=args.settings_file)
                print(f"已設定每日 {at} 備份。電腦須開機並登入 Windows。")
                return 0
            if answer != "1":
                print("已取消。")
                return 0
        if args.mode in {"upgrade", "restore"}:
            print("開始內部資料庫維護，請保持工會系統與背景服務停止。")
        if args.mode == "restore":
            selected_backup = args.backup_file
            if selected_backup is None and not restore_has_pending_cleanup(settings):
                selected_backup = choose_backup(settings)
            path = restore(settings, selected_backup)
            print(f"同名資料庫復原與清理完成。請重新啟動工會系統，再確認登入與資料。紀錄：{path}")
            return 0
        config = reader(settings) if args.mode == "backup" else writer(settings)
        destination_ready(settings, create=True)
        with maintenance_lock(config):
            if args.mode == "backup":
                path = backup(settings)
                if args.scheduled:
                    validate_backup(path)  # Backup success must precede best-effort retention.
                    try:
                        removed = retain_scheduled_backups(settings, path)
                        print(f"滾動保存完成，清理 {removed} 份過期排程備份。")
                    except Exception as cleanup_error:
                        # Cleanup is secondary to the verified backup. Keep its
                        # failure separate so a good restore point stays passed.
                        try:
                            root = destination_ready(settings)
                            _retention_path(root, path)
                            folder = nas_directory(root, "_retention")
                            save(folder / (uuid4().hex + ".json"), {
                                "format":"nas-backup-retention/v1", "status":"failed",
                                "time":backup_time().isoformat(), "latest":str(path.relative_to(root)),
                                "error_type":type(cleanup_error).__name__})
                        except Exception:
                            pass  # An unavailable NAS cannot accept a failure receipt.
                        cleanup_warning = "備份已完成，過期備份清理未完成；請通知維護人員。"
                        print(cleanup_warning)
            elif args.mode == "upgrade":
                path = upgrade(settings)
        if args.mode == "backup":
            record_backup_result(settings, "passed", message=cleanup_warning,
                                 created_at=read_backup_receipt(path)["created_at"])
            print(f"備份成功，儲存位置：{path}")
        elif path is not None:
            print(f"副本驗證與設定切換完成。請重新啟動工會系統，再確認登入與資料。紀錄：{path}")
        return 0
    except RestoreCleanupPending as error:
        print(str(error))
        return 2
    except (EOFError, KeyboardInterrupt):
        print("已停止；若操作已開始，請保留紀錄並通知維護人員，不要重複執行。")
        return 2
    except Exception as error:
        if args.mode == "restore" and not isinstance(error, MaintenanceBlocked):
            message = "復原未完成。請保留備份及本次進度，由維護人員核對連線、權限或操作結果。"
        else:
            message = format_maintenance_error(error, settings)
        if args.mode == "backup" and settings is not None and not args.dry_run:
            try:
                record_backup_result(settings, "failed", message=message)
            except Exception:
                pass
        print(message)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

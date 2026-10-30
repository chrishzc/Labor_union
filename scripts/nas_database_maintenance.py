"""Windows NAS SQL backup, candidate upgrade and disaster restore; no SSH/reset.

The three launchers share this transport. Canonical migration still owns schema,
backfills and preservation checks. Operational databases are never dropped.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import dotenv_values
import pymysql

from scripts import migrate_preserved_database_additive_schema as migration

SETTINGS = ROOT / ".env.nas-maintenance"
SCHEDULE = ROOT / "scratch/nas_database_maintenance/schedule.json"
TASK_NAME = "LaborUnion-NAS-Database-Backup"
IDENTIFIER = re.compile(r"[A-Za-z0-9_]{1,64}\Z")
# The NAS IO adapter below mirrors this CLI revision's receipt/verification
# orchestration. A future artifact must be reviewed, not silently skipped.
SUPPORTED_POLICY_SHA256 = "2d2ddfebf56f6ed092cd856a97ba47d2dd46b216ee45d992064e20d7c4cb65ab"


class MaintenanceBlocked(RuntimeError):
    """Safe Chinese operator message; never include provider error text."""


class ScheduleConflict(MaintenanceBlocked):
    pass


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
        os.chmod(temporary, 0o600)
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run_windows_powershell(command):
    # A parent PowerShell 7 can export an incompatible module search path to
    # Windows PowerShell 5. Use that child's own built-in module defaults.
    environment = {key: value for key, value in os.environ.items() if key.casefold() != "psmodulepath"}
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", command],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment,
                          timeout=30, check=False)


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
        require(shutil.which(executable), "找不到 MySQL 維護工具；請維護人員安裝 MySQL 8 的 mysql 與 mysqldump。")
        return [executable, *options]

    def run_manifest_backfill(self, backfill, mode, candidate, plan_path, backup_path, receipt_path):
        # This is an IO adapter for the existing policy library. No source
        # connection is exposed to it; the hash-checked manifest remains SSOT.
        require(candidate == self.candidate and candidate.startswith("lu_nas_"), "資料轉換只能作用於本次 NAS 副本。")
        if backfill.backfill_id == "twins-payroll-rate-snapshots-v1":
            return False  # Its canonical CLI already accepts an explicit remote target.
        require(backfill.backfill_id == "subsidy-period-policy-v1", "此版本包含尚未支援的資料轉換；已保留原庫，請交由維護人員處理。")
        require(backfill.artifact.sha256 == SUPPORTED_POLICY_SHA256, "資料轉換版本已變更，請維護人員更新 NAS 升級工具。")
        from scripts import migrate_subsidy_period_policy as policy
        require(backfill.artifact.relative_path == "scripts/migrate_subsidy_period_policy.py", "資料轉換來源不符。")
        require(digest(ROOT / backfill.artifact.relative_path) == backfill.artifact.sha256, "資料轉換檔案驗證失敗。")
        connection = self.connect(candidate)
        try:
            changes = policy.plan(connection)
            pending, pending_cases = {}, []
            if mode == "apply":
                expected = json.loads(plan_path.read_text(encoding="utf-8"))
                require(backup_path.is_file() and backup_path.stat().st_size > 0, "缺少副本轉換前備份。")
                require(expected["database"] == candidate and expected["changes"] == changes, "資料轉換預覽已過期。")
                pending = policy.apply(connection, changes, pending_cases=pending_cases) or {}
            if mode == "verify":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT policy_key FROM client_subsidy_policy_migrations WHERE policy_key=%s", (policy.POLICY,))
                    require(cursor.fetchone(), "資料轉換尚未完成。")
                    cursor.execute("SELECT COUNT(*) n FROM client_subsidy_identity_label_changes change_row JOIN clients client "
                                   "ON client.id=change_row.client_id WHERE client.identity_status<>change_row.after_identity")
                    require(not cursor.fetchone()["n"], "資料轉換核對失敗。")
            if mode in {"verify", "dry-run"}:
                pending_cases = policy.pending_refund_cases(connection)
                pending = {code: sum(item["reason"] == code for item in pending_cases)
                           for code in policy.PENDING_SOURCE_CODES if any(item["reason"] == code for item in pending_cases)}
            # Detailed business cases belong to the existing canonical receipt,
            # never console/UI output.
            save(receipt_path, {"contract": backfill.receipt_contract, "mode": mode, "database": candidate,
                 "receipt_status": {"apply": "committed", "verify": "verified", "dry-run": "planned"}[mode],
                 "changes": changes if mode == "dry-run" else [], "changed_count": len(changes),
                 "pending_source_codes": pending, "pending_cases": pending_cases,
                 "dataset_fingerprint": hashlib.sha256(json.dumps(changes, ensure_ascii=False, sort_keys=True).encode()).hexdigest()})
        finally:
            connection.close()
        return True


def load_settings(environment_file=ROOT / ".env", settings_file=SETTINGS):
    environment_file, settings_file = Path(environment_file).resolve(), Path(settings_file).resolve()
    require(environment_file.is_file() and settings_file.is_file(),
            "尚未設定 NAS 維護資料；請維護人員依操作說明準備 .env.nas-maintenance。")
    runtime = dotenv_values(environment_file, encoding="utf-8", interpolate=False)
    values = dotenv_values(settings_file, encoding="utf-8", interpolate=False)
    require(values.get("NAS_MAINTENANCE_ENABLED") == "1", "NAS 維護尚未啟用，未連線或變更資料庫。")
    require((runtime.get("DEPLOYMENT_PROFILE") or "").lower() != "nas",
            "此工具供電腦執行程式的部署使用；舊 NAS 多帳號部署請由原維護工具處理。")
    host = (runtime.get("DB_HOST") or "").strip()
    try:
        address = ipaddress.ip_address(host.strip("[]"))
        require(not address.is_loopback and not address.is_unspecified, "這是 NAS 專用工具，不能操作本機開發資料庫。")
    except ValueError:
        pass
    require(host and host.casefold().rstrip(".") not in {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"},
            "這是 NAS 專用工具，不能操作本機開發資料庫。")
    require(host == values.get("NAS_EXPECTED_HOST"), "NAS 位址與已登記的維護目標不同，已停止。")
    port = int(runtime.get("DB_PORT") or "3306")
    require(1 <= port <= 65535 and port == int(values.get("NAS_EXPECTED_PORT") or "3306"), "NAS 連線埠與維護目標不同。")
    database = runtime.get("DB_DATABASE") or ""
    require(IDENTIFIER.fullmatch(database) and (database == "union_db" or database.startswith("lu_nas_")), "不是核准的 NAS 業務資料庫。")
    for key in ("APP_ENV", *(key for key in runtime if key.startswith("DB_"))):
        require(key not in os.environ or os.environ[key] == runtime.get(key), "目前執行環境與設定檔不同，已停止，請維護人員確認。")
    required = ("NAS_BACKUP_USER", "NAS_BACKUP_PASSWORD", "NAS_MAINTENANCE_USER", "NAS_MAINTENANCE_PASSWORD")
    require(all(values.get(key) for key in required), "缺少備份或升級維護帳號，請維護人員設定。")
    require(values["NAS_BACKUP_USER"] != values["NAS_MAINTENANCE_USER"], "備份與升級必須使用不同帳號。")
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
    backup_dir = Path(values.get("NAS_BACKUP_DIR") or ROOT / "backups")
    require(backup_dir.is_absolute(), "備份位置請填寫完整路徑。")
    return {"host": host, "port": port, "database": database, "tls": tls, "tls_files": files,
            "ssl_mode": {"disabled": "DISABLED", "verify_ca": "VERIFY_CA", "verify_identity": "VERIFY_IDENTITY"}[mode],
            "environment_file": environment_file, "settings_file": settings_file,
            "backup_root": backup_dir / "labor_union_nas", "values": values, "runtime": runtime}


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
        yield
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
                definitions.append(migration._normalize_database_qualifiers(sql, (database, *equivalent_databases)))
            result["definitions_sha256"] = hashlib.sha256(json.dumps(definitions, ensure_ascii=False).encode()).hexdigest()
            cursor.execute("SELECT default_character_set_name AS charset,default_collation_name AS collation FROM information_schema.schemata WHERE schema_name=%s", (database,))
            result.update(cursor.fetchone())
            return result
    finally:
        connection.close()


def backup(settings):
    print("正在備份資料，完成前請勿關閉視窗。", flush=True)
    config, database = reader(settings), settings["database"]
    config.client_prefix("mysqldump")
    root = private_directory(settings["backup_root"])
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
    directory = private_directory(root / (".partial-" + identifier))
    before = schema_inventory(config, database)
    identity = migration.server_identity(config, database)
    command = migration._mysql_base(config, "mysqldump") + ["--single-transaction", "--quick", "--skip-lock-tables",
        "--no-tablespaces", "--set-gtid-purged=OFF", "--routines", "--events", "--triggers", "--hex-blob", database]
    path = directory / "database.sql"
    with path.open("xb") as output:
        os.chmod(path, 0o600)
        completed = subprocess.run(command, stdout=output, stderr=subprocess.DEVNULL,
                                   env=migration._client_environment(config), timeout=7200, check=False)
        output.flush()
        os.fsync(output.fileno())
    require(completed.returncode == 0 and path.stat().st_size, "備份未完成；已保留先前的成功備份，請通知維護人員。")
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 2048))
        require(b"-- Dump completed on " in stream.read(), "備份內容不完整，未標記為成功。")
    require(schema_inventory(config, database) == before and migration.server_identity(config, database) == identity,
            "備份期間資料庫結構或目標改變，未標記為成功。")
    receipt = {"format": "nas-sql-backup/v1", "status": "completed", "created_at": datetime.now(timezone.utc).isoformat(),
               "database": database, "host": config.host, "port": config.port, "server": identity["server"],
               "sha256": digest(path), "size": path.stat().st_size, "inventory": before}
    save(directory / "receipt.json", receipt)
    final = root / identifier
    directory.rename(final)
    return final


def validate_backup(directory):
    directory = Path(directory).resolve()
    require(not directory.name.startswith(".partial-"), "這份備份尚未完成，不能復原。")
    require((directory / "receipt.json").is_file() and (directory / "database.sql").is_file(), "找不到完整的備份與驗證紀錄。")
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    require(receipt.get("format") == "nas-sql-backup/v1" and receipt.get("status") == "completed", "不是有效的 NAS 資料庫備份。")
    require(digest(directory / "database.sql") == receipt["sha256"] and (directory / "database.sql").stat().st_size == receipt["size"],
            "備份檢查碼不符，已停止；原資料庫不變。")
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


def prepare_runtime_access(settings, candidate):
    runtime = settings["runtime"]
    require(runtime.get("DB_USER") and runtime.get("DB_PASSWORD"), "缺少工會系統原有的連線帳號。")
    _copy_schema_access(settings, candidate, ConnectionConfig(settings, user=runtime["DB_USER"], password=runtime["DB_PASSWORD"]))
    _copy_schema_access(settings, candidate, reader(settings))


def _copy_schema_access(settings, candidate, probe):
    """Copy only the existing runtime account's schema grant to the new schema.

    Passwords/global privileges/source grants are never changed. Fine-grained
    or role-based policies need their existing permission owner, not a guess.
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
            for grant in grants:
                match = re.match(r"^GRANT ([A-Z_, ]+) ON `((?:``|[^`])+)`\.\* TO ", grant)
                scope = match[2].replace("``", "`") if match else ""
                if not partial_revokes:
                    scope = re.sub(r"\\(.)", r"\1", scope)
                if match and scope == settings["database"]:
                    privileges.update(item.strip() for item in match[1].split(","))
            allowed = {"ALL PRIVILEGES", "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "REFERENCES", "INDEX", "ALTER",
                       "CREATE TEMPORARY TABLES", "LOCK TABLES", "EXECUTE", "CREATE VIEW", "SHOW VIEW", "CREATE ROUTINE", "ALTER ROUTINE", "EVENT", "TRIGGER"}
            require(privileges and privileges <= allowed, "原帳號使用特殊權限配置，未切換；請由維護人員沿用原權限政策。")
            target_scope = candidate if partial_revokes else candidate.replace("_", r"\_")
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


def upgrade(settings):
    print("正在核對資料庫版本，原資料庫不會被清空。", flush=True)
    source, candidate = settings["database"], new_candidate("upgrade")
    read, write = reader(settings), writer(settings, candidate)
    for executable in ("mysql", "mysqldump"):
        write.client_prefix(executable)
    # Unknown backfills stop before source backup or candidate writes.
    require(all(item.backfill_id in {"subsidy-period-policy-v1", "twins-payroll-rate-snapshots-v1"} for item in migration.RELEASE_MANIFEST.backfills),
            "新版包含尚未支援的資料轉換，請交由維護人員處理。")
    require(all(item.artifact.sha256 == SUPPORTED_POLICY_SHA256 for item in migration.RELEASE_MANIFEST.backfills
                if item.backfill_id == "subsidy-period-policy-v1"), "資料轉換版本已變更，請維護人員更新 NAS 升級工具。")
    original_env_digest = digest(settings["environment_file"])
    config = migration.SeparateDatabaseConfig(migration.DatabaseDescriptor("source-read", source, read),
              migration.DatabaseDescriptor("candidate-write", candidate, write))
    plan = migration.build_plan(config, source, candidate)
    require(plan["status"] == "ready" and not plan["candidate_exists"], "升級預檢未通過，原資料庫不變。")
    directory = backup(settings)
    # Canonical restore requires its own backup receipt, bound to the exact dump.
    info = validate_backup(directory)
    require_event_scheduler_safe(write, info)
    save(directory / "backup.receipt.json", {"kind": "source_backup", "created_at": info["created_at"],
         "database": source, "server": info["server"], "sha256": info["sha256"], "size": info["size"], "exit_code": 0})
    migration.write_receipt(directory / "plan.json", plan)
    operation = directory / "operation.json"
    migration.restore_candidate(config, source, candidate, directory / "database.sql", directory / "backup.receipt.json", operation)
    schema_inventory(write, candidate, (source,), reject_source_references=True)
    print("備份已完成，正在升級副本並核對資料；請勿關閉視窗。", flush=True)
    migration.apply_schema(config, source, candidate, directory / "plan.json", operation)
    print("正在進行最後的完整資料驗證。", flush=True)
    result = migration.verify_candidate(config, source, candidate, operation)
    require(result.get("status") == "verified", "副本驗證未通過，未切換資料庫。")
    prepare_runtime_access(settings, candidate)
    # Reuse the canonical fresh-read/data-fingerprint/config switch guard.
    require(digest(settings["environment_file"]) == original_env_digest, "連線設定已改變，未切換資料庫。")
    migration.switch_environment(settings["environment_file"], source, candidate, operation,
                                 directory / "switch.json", config=config,
                                 environment_writer=lambda path, payload: replace_runtime_file(path, payload, original_env_digest))
    return directory


def restore(settings, directory):
    directory = Path(directory).resolve()
    require(directory.is_relative_to(settings["backup_root"].resolve()),
            "請將要復原的備份先交由維護人員放入專用備份資料夾，再從清單選擇。")
    require(not (directory / "database.sql").is_symlink() and not (directory / "receipt.json").is_symlink(),
            "備份檔案不能是符號連結。")
    info = validate_backup(directory)
    print("備份檢查通過，正在建立並驗證復原副本；原庫保留。", flush=True)
    candidate = new_candidate("restore")
    config = writer(settings, candidate)
    config.client_prefix("mysql")
    require_event_scheduler_safe(config, info)
    original_env_digest = digest(settings["environment_file"])
    # The source may be absent/corrupt. Recovery only needs a working server.
    require(not migration.database_exists(config, candidate), "復原副本已存在，請維護人員確認。")
    run = private_directory(settings["backup_root"] / ("restore-" + candidate))
    save(run / "operation.json", {"status": "prepared", "candidate": candidate, "backup_sha256": info["sha256"]})
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            charset, collation = info["inventory"]["charset"], info["inventory"]["collation"]
            require(IDENTIFIER.fullmatch(charset) and IDENTIFIER.fullmatch(collation), "備份的資料庫字元集設定無效。")
            cursor.execute(f"CREATE DATABASE `{candidate}` CHARACTER SET {charset} COLLATE {collation}")
    finally:
        connection.close()
    with (Path(directory) / "database.sql").open("rb") as source:
        completed = subprocess.run(migration._mysql_base(config, "mysql") + [candidate], stdin=source,
             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=migration._client_environment(config), timeout=7200, check=False)
    require(completed.returncode == 0, "復原匯入失敗，未切換；原庫、備份與副本皆保留。")
    require(schema_inventory(config, candidate, (info["database"],), reject_source_references=True) == info["inventory"], "復原物件核對失敗，未切換資料庫。")
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            for table in info["inventory"]["tables"]:
                if table["kind"] != "BASE TABLE":
                    continue
                name = table["name"].replace("`", "``")
                cursor.execute(f"CHECK TABLE `{name}`")
                results = cursor.fetchall()
                require(results and all(row["Msg_type"] != "error" for row in results) and any(row["Msg_text"] == "OK" for row in results),
                        "復原資料表檢查失敗，未切換資料庫。")
    finally:
        connection.close()
    from scripts import update_local_database as updater
    current = updater.build_additive_preview(config, candidate, run)
    require(current.get("status") == "current", "備份已匯入副本，但與目前程式版本不同，尚未切換；請維護人員完成版本核對。")
    updater.require_current_database(current)
    prepare_runtime_access(settings, candidate)
    switch_runtime(settings, candidate, original_env_digest, run)
    return run


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
    private_directory(settings["backup_root"])
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


def backup_status():
    result = {"enabled": False, "time": "18:00", "version": 0, "last_backup": None, "last_result": None}
    if SCHEDULE.is_file():
        saved = json.loads(SCHEDULE.read_text(encoding="utf-8"))
        result.update({key: saved[key] for key in ("enabled", "time")})
        result["version"] = saved.get("version", 0)
        result["enabled"] = bool(result["enabled"] and registered_backup_enabled())
    try:
        settings = load_settings()
        backups = sorted(settings["backup_root"].glob("*/receipt.json"), reverse=True)
        for path in backups:
            if path.parent.name.startswith(".partial-"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") == "completed":
                result["last_backup"] = data["created_at"]
                break
        path = settings["backup_root"] / "last-result.json"
        if path.is_file():
            result["last_result"] = json.loads(path.read_text(encoding="utf-8"))
        result["configured"] = True
    except (OSError, ValueError, MaintenanceBlocked):
        result["configured"] = False
    return result


def choose_backup(settings):
    paths = [p.parent for p in sorted(settings["backup_root"].glob("*/receipt.json"), reverse=True)
             if not p.parent.name.startswith(".partial-")]
    require(paths, "目前沒有已完成的備份。")
    for index, path in enumerate(paths[:30], 1):
        info = json.loads((path / "receipt.json").read_text(encoding="utf-8"))
        print(f"{index}. {info['created_at']}（{info['database']}）")
    selection = input("請輸入要復原的備份編號（直接 Enter 取消）：").strip()
    require(selection.isdigit() and 1 <= int(selection) <= min(len(paths), 30), "已取消，資料庫不變。")
    return paths[int(selection) - 1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("backup", "upgrade", "restore"))
    parser.add_argument("--environment-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--settings-file", type=Path, default=SETTINGS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--backup-directory", type=Path)
    parser.add_argument("--time", default="18:00")
    parser.add_argument("--install-daily", action="store_true")
    args = parser.parse_args(argv)
    settings = None
    try:
        require(not args.scheduled or args.mode == "backup", "排程只允許備份，不能自動升級或復原。")
        require(not args.install_daily or args.mode == "backup", "只有備份腳本可以設定排程。")
        settings = load_settings(args.environment_file, args.settings_file)
        if args.dry_run:
            for executable in (("mysqldump",) if args.mode == "backup" else ("mysql", "mysqldump")):
                reader(settings).client_prefix(executable)
            print("設定與工具檢查通過；未連線、未變更資料庫。")
            return 0
        if args.install_daily:
            configure_daily_backup(args.time, environment_file=args.environment_file, settings_file=args.settings_file)
            print(f"已設定每日 {args.time} 備份。電腦須開機並登入 Windows。")
            return 0
        print(f"NAS：{settings['host']}:{settings['port']}　資料庫：{settings['database']}")
        if args.mode == "backup" and not args.scheduled:
            print("1. 立即備份\n2. 設定每日備份（預設 18:00）\n直接 Enter 取消")
            answer = input("請選擇：").strip()
            if answer == "2":
                at = input("每日備份時間（Enter 使用 18:00）：").strip() or "18:00"
                configure_daily_backup(at, environment_file=args.environment_file, settings_file=args.settings_file)
                print(f"已設定每日 {at} 備份。電腦須開機並登入 Windows。")
                return 0
            if answer != "1":
                print("已取消。")
                return 0
        if args.mode in {"upgrade", "restore"}:
            print("請先關閉工會系統與背景服務，並確認所有使用者已停止操作。")
            print("此操作保留原資料庫；驗證副本成功後才切換設定。")
            if input("已停止服務且要繼續，請輸入「確認」：").strip() != "確認":
                print("已取消，資料庫不變。")
                return 0
        config = reader(settings) if args.mode == "backup" else writer(settings)
        with maintenance_lock(config):
            if args.mode == "backup":
                path = backup(settings)
            elif args.mode == "upgrade":
                path = upgrade(settings)
            else:
                path = restore(settings, args.backup_directory or choose_backup(settings))
        if args.mode == "backup":
            save(settings["backup_root"] / "last-result.json", {"status": "passed", "time": datetime.now(timezone.utc).isoformat()})
            print(f"備份成功，儲存位置：{path}")
        else:
            print(f"副本驗證與設定切換完成。請重新啟動工會系統，再確認登入與資料。紀錄：{path}")
        return 0
    except (EOFError, KeyboardInterrupt):
        print("已停止；若操作已開始，請保留紀錄並通知維護人員，不要重複執行。")
        return 2
    except Exception as error:
        message = str(error) if isinstance(error, MaintenanceBlocked) else "操作未完成；請保留備份與紀錄，通知維護人員確認。"
        if args.mode == "backup" and settings is not None:
            try:
                private_directory(settings["backup_root"])
                save(settings["backup_root"] / "last-result.json", {"status": "failed", "time": datetime.now(timezone.utc).isoformat(), "message": message})
            except Exception:
                pass
        print(message)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

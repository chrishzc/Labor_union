"""Initialize NAS union_db with explicit confirmation for creation or test resets."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
from time import monotonic
from uuid import uuid4

from dotenv import dotenv_values
import pymysql

from scripts.schema_assembly import load_schema_assembly
from scripts.sql_statements import split_sql
from scripts.verify_validation_schema_manifest import (
    expected_database_objects, load_manifest, selected_schema_parts,
    verify_database_objects, verify_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_ROOT = ROOT / "scratch" / "nas_schema_initialization"
RESET_READ_TIMEOUT = 600
RESET_LOCK_WAIT_TIMEOUT = 15
DATABASE_CONTROL = re.compile(r"^(?:USE\b|(?:CREATE|DROP|ALTER)\s+(?:DATABASE|SCHEMA)\b)", re.I)
BASE_CONTROLS = {
    "DROP DATABASE IF EXISTS union_db",
    "CREATE DATABASE union_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
    "USE union_db",
}


class InitializationBlocked(RuntimeError):
    """An operator-facing failure containing no provider error or credentials."""


class _NonEmptyDatabase(InitializationBlocked):
    """Reject initialization, then explain existing schema through read-only checks."""


class _MissingDatabase(InitializationBlocked):
    """Offer explicit creation only from the interactive entry point."""


def _mysql_reason(error):
    number = error.args[0] if isinstance(error, pymysql.MySQLError) and error.args and isinstance(error.args[0], int) else None
    reasons = {
        1044: "帳號沒有目標資料庫的存取權限",
        1045: "MySQL 拒絕登入，請確認帳號、密碼及允許連線的來源",
        1049: "目標資料庫不存在，請先在 NAS 建立 union_db",
        1007: "目標資料庫已被其他程序建立，已停止，不會覆蓋或繼續初始化",
        1050: "資料表已存在，初始化已停止，不會覆蓋",
        1064: "MySQL 無法解析這條指令，請確認伺服器版本相容性",
        1142: "帳號缺少執行這項操作的資料庫權限",
        1205: "等待其他連線釋放鎖逾時；請停止使用此資料庫的服務並結束交易，再確認資料庫現況",
        1227: "帳號缺少 MySQL 要求的管理或物件權限",
        1290: "MySQL 伺服器設定禁止這項操作，請確認唯讀等限制",
        1419: "binary log 設定與帳號權限不允許建立觸發器",
        2003: "無法連線 NAS MySQL，請確認服務、連線位址、防火牆及 TLS 設定",
        2006: "MySQL 連線已中斷",
        2013: "等待 MySQL 回應逾時或連線中斷",
    }
    if number is not None:
        return f"{reasons.get(number, 'MySQL 拒絕執行操作')} (MySQL errno: {number})"
    if isinstance(error, InitializationBlocked):
        return str(error)
    if getattr(error, "code", None) == "schema_update_required":
        return "現有資料庫結構尚未符合目前程式版本，不能視為初始化成功"
    return f"檢查未能完成 ({type(error).__name__})"


def _schema_scope_matches(scope, database, partial_revokes):
    if scope == "*.*":
        return True
    pattern = scope[1:-3].replace("``", "`")
    if partial_revokes:
        return pattern == database
    expression, index = "", 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\" and index + 1 < len(pattern):
            index += 1
            expression += re.escape(pattern[index])
        else:
            expression += {"%": ".*", "_": "."}.get(character, re.escape(character))
        index += 1
    return re.fullmatch(expression, database) is not None


def _effective_privileges(grants, database, partial_revokes, required):
    global_grants, schema_grants, revoked = set(), set(), set()
    for grant in grants:
        match = re.match(r"^(GRANT|REVOKE) ([A-Z_, ]+) ON (\*\.\*|`(?:``|[^`])+`\.\*) (?:TO|FROM) ", grant)
        if not match:
            continue
        command, privileges, scope = match.groups()
        if not _schema_scope_matches(scope, database, partial_revokes):
            continue
        privileges = {value.strip() for value in privileges.split(",")}
        if "ALL PRIVILEGES" in privileges:
            privileges = set(required) | ({"SUPER"} if scope == "*.*" else set())
        if command == "REVOKE":
            revoked.update(privileges)
        elif scope == "*.*":
            global_grants.update(privileges)
        else:
            schema_grants.update(privileges)
    return (global_grants - revoked) | schema_grants, global_grants


def _active_role_clause(roles):
    if roles == "NONE":
        return ""
    if not roles:
        raise InitializationBlocked("無法確認目前啟用角色的權限，尚未寫入資料庫")
    # Re-quote parsed identifiers, never execute server-returned SQL text.
    pair = re.compile(r"\s*`((?:``|[^`])*)`@`((?:``|[^`])*)`\s*(,|$)")
    remaining, quoted = roles, []
    while remaining:
        match = pair.match(remaining)
        if not match:
            raise InitializationBlocked("無法確認目前啟用角色的權限，尚未寫入資料庫")
        name, host, separator = match.groups()
        name, host = name.replace("``", "`"), host.replace("``", "`")
        quoted.append("`" + name.replace("`", "``") + "`@`" + host.replace("`", "``") + "`")
        remaining = remaining[match.end():]
        if separator == "," and not remaining:
            raise InitializationBlocked("無法確認目前啟用角色的權限，尚未寫入資料庫")
    return " USING " + ",".join(quoted)


def _require_server_ready(cursor, database, plan, *, reset=False):
    cursor.execute("SELECT VERSION() AS mysql_version, @@version_comment AS version_comment")
    server = cursor.fetchone()
    version = re.match(r"(\d+)\.(\d+)\.(\d+)", str(server["mysql_version"]))
    if ("mariadb" in (str(server["mysql_version"]) + str(server["version_comment"])).lower()
            or not version or tuple(map(int, version.groups())) < (8, 0, 16)):
        raise InitializationBlocked("版本不相容：初始化需要 MySQL 8.0.16 以上，不支援 MariaDB；尚未寫入資料庫")
    cursor.execute("SELECT @@read_only AS read_only, @@super_read_only AS super_read_only, @@log_bin AS log_bin, @@log_bin_trust_function_creators AS trust_function_creators, @@partial_revokes AS partial_revokes, CURRENT_ROLE() AS active_roles")
    capabilities = cursor.fetchone()
    if capabilities["read_only"] or capabilities["super_read_only"]:
        raise InitializationBlocked("NAS MySQL 處於唯讀模式，尚未寫入資料庫")
    cursor.execute("SELECT support AS support FROM information_schema.engines WHERE engine='InnoDB'")
    engine = cursor.fetchone()
    if not engine or engine["support"] not in {"YES", "DEFAULT"}:
        raise InitializationBlocked("NAS MySQL 未啟用 InnoDB，尚未寫入資料庫")
    required = {"CREATE", "SELECT", "INSERT", "REFERENCES"}
    if reset:
        required.add("DROP")
    if plan["expected"].get("views"):
        # Current final SQL uses CREATE OR REPLACE VIEW; MySQL requires DROP
        # for that view even though this entry never drops a database/table.
        required.update({"CREATE VIEW", "SHOW VIEW", "DROP"})
    if plan["expected"].get("triggers"):
        required.add("TRIGGER")
    cursor.execute("SHOW GRANTS FOR CURRENT_USER" + _active_role_clause(capabilities["active_roles"]))
    grants = [next(iter(row.values())) for row in cursor.fetchall()]
    privileges, global_privileges = _effective_privileges(
        grants, database,
        bool(capabilities["partial_revokes"]), required,
    )
    missing = required - privileges
    if not reset and "DROP" in missing and plan["expected"].get("views"):
        view_drops = set()
        for grant in grants:
            match = re.match(r"^GRANT ([A-Z_, ]+) ON `((?:``|[^`])+)`\.`((?:``|[^`])+)` TO ", grant)
            if match:
                permissions, schema, view = match.groups()
                if schema.replace("``", "`") == database and {"DROP", "ALL PRIVILEGES"} & {value.strip() for value in permissions.split(",")}:
                    view_drops.add(view.replace("``", "`"))
        if plan["expected"]["views"] <= view_drops:
            missing.remove("DROP")
    if missing:
        raise InitializationBlocked("初始化前檢查失敗：缺少資料庫權限 " + ", ".join(sorted(missing)) + "；尚未寫入資料庫")
    if (plan["expected"].get("triggers") and capabilities["log_bin"]
            and not capabilities["trust_function_creators"] and "SUPER" not in global_privileges):
        raise InitializationBlocked("NAS 的 binary log 設定禁止目前帳號建立觸發器：缺少 SUPER 且 log_bin_trust_function_creators=0；請管理者確認設定，尚未寫入資料庫")
    return ".".join(version.groups())


def _preflight_metadata(config, *, missing=False):
    from scripts.check_runtime_database import ReadOnlyRuntimeConfig, updater
    try:
        updater.migration._local_ordered_upgrade_entries()
    except Exception:
        raise InitializationBlocked("本機版本驗證檔案缺漏或不一致，請更新完整專案；尚未寫入資料庫") from None
    readonly = ReadOnlyRuntimeConfig(config)
    if missing:
        # The canonical queries filter information_schema by target name. Use
        # the same query oracle without selecting a database that is absent.
        class ServerMetadataConfig:
            def connect(self, database=None, *, timeout_seconds=None):
                return readonly.connect(timeout_seconds=timeout_seconds)
        readonly_config = ServerMetadataConfig()
    else:
        readonly_config = readonly
    updater.migration._schema_snapshot(readonly_config, config["database"])


def load_configuration(path: Path = ROOT / ".env") -> dict:
    if not path.is_file():
        raise InitializationBlocked("Missing .env")
    values = dotenv_values(path, encoding="utf-8")
    required = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_DATABASE")
    if any(not values.get(key) for key in required):
        raise InitializationBlocked("Set DB_HOST, DB_USER, DB_PASSWORD and DB_DATABASE in .env")
    if values.get("APP_ENV", "").strip().lower() != "development":
        raise InitializationBlocked(".env must set APP_ENV=development")
    if values["DB_DATABASE"] != "union_db":
        raise InitializationBlocked("NAS initialization only accepts DB_DATABASE=union_db")
    # Refuse a different runtime target rather than initialize a database the API
    # would not use. Values are never included in the diagnostic.
    effective_values = {"DB_PORT": "3306", "DB_SSL_MODE": "disabled",
                        "DB_SSL_CA": "", "DB_SSL_CERT": "", "DB_SSL_KEY": "", **values}
    for key, value in effective_values.items():
        if (key.startswith("DB_") or key == "APP_ENV") and key in os.environ:
            if os.environ[key] != value:
                raise InitializationBlocked(f"Process {key} conflicts with .env; clear the override")
    host = values["DB_HOST"].strip()
    try:
        local = ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        local = host.casefold().rstrip(".") == "localhost"
    if not host or local or host in {"0.0.0.0", "::"}:
        raise InitializationBlocked("DB_HOST must identify the NAS, not a local server")
    port = int(values.get("DB_PORT") or "3306")
    if not 1 <= port <= 65535:
        raise InitializationBlocked("DB_PORT must be between 1 and 65535")
    settings = {
        "host": host, "port": port, "user": values["DB_USER"],
        "password": values["DB_PASSWORD"], "database": "union_db", "charset": "utf8mb4",
    }
    mode = (values.get("DB_SSL_MODE") or "disabled").strip().lower()
    if mode not in {"disabled", "verify_ca", "verify_identity"}:
        raise InitializationBlocked("Invalid DB_SSL_MODE")
    if mode != "disabled":
        if not all(values.get(key) for key in ("DB_SSL_CA", "DB_SSL_CERT", "DB_SSL_KEY")):
            raise InitializationBlocked("MySQL mTLS requires DB_SSL_CA, DB_SSL_CERT and DB_SSL_KEY")
        settings["ssl"] = {
            "ca": values["DB_SSL_CA"], "cert": values["DB_SSL_CERT"],
            "key": values["DB_SSL_KEY"], "check_hostname": mode == "verify_identity",
        }
    return settings


def source_schema_plan():
    """Historical assembly used only to regenerate and verify the compact baseline."""
    assembly = load_schema_assembly()
    manifest = load_manifest()
    if verify_manifest(manifest) or tuple(selected_schema_parts(manifest)) != assembly.active_artifact_paths:
        raise InitializationBlocked("Canonical schema manifest verification failed")
    steps, base_views, removed = [], [], set()
    part_digest = hashlib.sha256()
    for path in (assembly.base_schema_path, *assembly.active_artifact_paths):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if path == assembly.base_schema_path:
            if digest != manifest["base_schema"]["sha256"]:
                raise InitializationBlocked("Captured base schema digest does not match manifest")
        else:
            part_digest.update(f"{path.name}:{digest}\n".encode("utf-8"))
        for ordinal, sql in enumerate(split_sql(raw.decode("utf-8")), 1):
            if DATABASE_CONTROL.match(sql):
                if path != assembly.base_schema_path or sql not in BASE_CONTROLS:
                    raise InitializationBlocked("Unexpected database control statement in canonical schema")
                removed.add(sql)
                continue
            step = {"artifact": path.name, "ordinal": ordinal, "sql": sql}
            if path == assembly.base_schema_path and re.match(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", sql, re.I):
                base_views.append(step)
            else:
                steps.append(step)
    if removed != BASE_CONTROLS:
        raise InitializationBlocked("Canonical base database controls have changed")
    if part_digest.hexdigest() != manifest["schema_parts"]["ordered_digest_sha256"]:
        raise InitializationBlocked("Captured schema part digests do not match manifest")
    return {
        "assembly_id": assembly.assembly_id, "release_id": manifest["release_id"],
        "schema_parts": [path.name for path in assembly.active_artifact_paths],
        "steps": steps + base_views, "expected": expected_database_objects(manifest),
    }


def schema_plan():
    """Load the generated final schema, never replay historical upgrade steps."""
    from scripts.compact_fresh_schema import load_compact_plan
    try:
        return load_compact_plan()
    except (OSError, ValueError, KeyError) as error:
        raise InitializationBlocked(
            "Compact fresh schema verification failed; regenerate the baseline from current sources"
        ) from error


def _database_identity(cursor, database):
    cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
    identity = cursor.fetchone()
    if not identity or identity["database_name"] != database or not identity["server"]:
        raise InitializationBlocked("Connected database identity does not match target")
    return identity


def _require_empty(cursor, database):
    identity = _database_identity(cursor, database)
    for table, field in (
        ("tables", "table_schema"), ("routines", "routine_schema"), ("events", "event_schema"),
    ):
        cursor.execute(f"SELECT 1 FROM information_schema.{table} WHERE {field}=%s LIMIT 1", (database,))
        if cursor.fetchone():
            raise _NonEmptyDatabase("Database is not empty; initialization stopped without schema writes")
    return identity


def _require_missing(cursor, database):
    identity = _database_identity(cursor, None)
    cursor.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name=%s", (database,))
    if cursor.fetchone():
        raise InitializationBlocked("目標資料庫已存在，建庫流程停止，不會覆蓋或初始化；請重新進入唯讀預檢")
    return identity


def _journal(path, event):
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _verify_current(config):
    from scripts.check_runtime_database import ReadOnlyRuntimeConfig, updater
    preview = updater.build_additive_preview(ReadOnlyRuntimeConfig(config), config["database"], updater.DEFAULT_RECEIPT_ROOT)
    updater.require_current_database(preview)


def initialize(config, plan, *, apply=False, reset=False, confirm_reset=None,
               create_missing=False, confirm_create=None, receipt_root=RECEIPT_ROOT):
    """The CLI validates NAS union_db; engine tests inject an owned lu_test_* target."""
    if reset and (not apply or confirm_reset is None):
        raise InitializationBlocked("清空資料庫必須經互動確認，不接受直接重設")
    if create_missing and (reset or not apply or confirm_create is None):
        raise InitializationBlocked("建立缺少的資料庫必須獨立經互動確認")
    settings = dict(config)
    settings.update(autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                    connect_timeout=5, read_timeout=RESET_READ_TIMEOUT if reset or create_missing else 30, write_timeout=30)
    if create_missing:
        settings.pop("database", None)
    if not apply:
        settings["init_command"] = "SET SESSION TRANSACTION READ ONLY"
    try:
        connection = pymysql.connect(**settings)
    except pymysql.MySQLError as error:
        if error.args and error.args[0] == 1049:
            raise _MissingDatabase("目標資料庫不存在 (MySQL errno: 1049)；互動模式可確認建立並初始化 union_db，尚未寫入資料庫") from None
        raise InitializationBlocked("連線預檢失敗：" + _mysql_reason(error)) from None
    journal_path = None
    completed = 0
    phase = "preflight"
    reset_operation = None
    reset_completed = []
    try:
        with connection.cursor() as cursor:
            if apply:
                cursor.execute("SELECT GET_LOCK(%s, 0) AS acquired", ("nas_schema_init:" + config["database"],))
                if cursor.fetchone().get("acquired") != 1:
                    raise InitializationBlocked("Another schema initializer holds the database lock")
            check_target = _require_missing if create_missing else (_database_identity if reset else _require_empty)
            metadata_options = {"missing": True} if create_missing else {}
            identity = check_target(cursor, config["database"])
            version = _require_server_ready(cursor, config["database"], plan, reset=reset)
            _preflight_metadata(config, **metadata_options)
            # Metadata checks can take time. Re-read the target immediately
            # before admitting writes, including after the Windows confirmation.
            identity = check_target(cursor, config["database"])
            result = {
                "status": "ready", "database": config["database"], "server": identity["server"],
                "assembly_id": plan["assembly_id"], "release_id": plan["release_id"],
                "statement_count": len(plan["steps"]), "system_seed_policy": "canonical_schema_only",
                "mysql_version": version, "preflight": "passed",
            }
            if not apply:
                return result
            if reset:
                cursor.execute("SELECT 1 FROM information_schema.key_column_usage WHERE referenced_table_schema=%s AND table_schema<>%s LIMIT 1", (config["database"], config["database"]))
                if cursor.fetchone():
                    raise InitializationBlocked("其他資料庫有外鍵參照目標資料庫，為避免影響其他資料庫，尚未清空")
                cursor.execute("SELECT default_character_set_name AS charset, default_collation_name AS collation FROM information_schema.schemata WHERE schema_name=%s", (config["database"],))
                defaults = cursor.fetchone()
                if not defaults or any(not re.fullmatch(r"[a-zA-Z0-9_]+", str(defaults[key])) for key in ("charset", "collation")):
                    raise InitializationBlocked("無法確認目標資料庫的字元集與定序，尚未清空")
            if reset or create_missing:
                if create_missing:
                    defaults = {"charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"}
                confirm = confirm_create if create_missing else confirm_reset
                if not confirm({**result, "host": config["host"], "port": config.get("port", 3306)}):
                    return {"status": "cancelled", "database": config["database"], "writes": "not_run"}
                # Keep the same connection and initialization lock across confirmation.
                # Recheck permissions/settings before the first database DDL.
                _require_server_ready(cursor, config["database"], plan, reset=reset)
                _preflight_metadata(config, **metadata_options)
                if check_target(cursor, config["database"]) != identity:
                    raise InitializationBlocked("確認後連線目標已改變，尚未清空")
            directory = Path(receipt_root) / uuid4().hex
            directory.mkdir(parents=True, exist_ok=False)
            journal_path = directory / "journal.jsonl"
            _journal(journal_path, {"event": "started", **result})
            if reset or create_missing:
                phase = "reset_database" if reset else "create_database"
                # Bound metadata-lock waiting without cutting off slow NAS DDL.
                cursor.execute(f"SET SESSION lock_wait_timeout={RESET_LOCK_WAIT_TIMEOUT}")
                target = "`" + config["database"].replace("`", "``") + "`"
                control_steps = [("drop_database", f"DROP DATABASE {target}")] if reset else []
                control_steps.extend([
                    ("create_database", f"CREATE DATABASE {target} CHARACTER SET {defaults['charset']} COLLATE {defaults['collation']}"),
                    ("select_database", f"USE {target}"),
                ])
                label = "Reset" if reset else "Create"
                event_prefix = "reset" if reset else "create"
                for operation, sql in control_steps:
                    reset_operation = operation
                    evidence = {"operation": operation, "statement_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest()}
                    _journal(journal_path, {"event": f"{event_prefix}_prepared", **evidence})
                    print(f"[Info] {label} operation: {operation}; waiting for MySQL response (up to {RESET_READ_TIMEOUT}s; each metadata lock wait up to {RESET_LOCK_WAIT_TIMEOUT}s). Do not close or rerun.", flush=True)
                    started = monotonic()
                    cursor.execute(sql)
                    reset_completed.append(operation)
                    _journal(journal_path, {"event": f"{event_prefix}_applied", **evidence})
                    print(f"[Done] {label} operation: {operation}; elapsed: {monotonic() - started:.1f}s.", flush=True)
                _require_empty(cursor, config["database"])
                if create_missing:
                    phase = "created_database_preflight"
                    _preflight_metadata(config)
                    _require_empty(cursor, config["database"])
                print(f"[Info] Database ready. Applying {len(plan['steps'])} schema statements...", flush=True)
            phase = "statements"
            for step in plan["steps"]:
                evidence = {
                    "artifact": step["artifact"], "ordinal": step["ordinal"],
                    "statement_sha256": hashlib.sha256(step["sql"].encode("utf-8")).hexdigest(),
                }
                _journal(journal_path, {"event": "prepared", **evidence})
                cursor.execute(step["sql"])
                completed += 1
                _journal(journal_path, {"event": "applied", **evidence})
            phase = "objects"
            # The existing object verifier consumes positional rows, unlike the
            # mapping rows used by target/lock admission above.
            with connection.cursor(pymysql.cursors.Cursor) as verification_cursor:
                if verify_database_objects(verification_cursor, config["database"], plan["expected"]):
                    raise InitializationBlocked("Canonical database object verification failed")
        # Use the same descriptor/current gate as the NAS runtime launcher.
        phase = "current_schema"
        _verify_current(config)
        result.update(status="passed", schema="current", journal=str(journal_path))
        _journal(journal_path, {"event": "passed", **result})
        return result
    except Exception as error:
        if journal_path is None and isinstance(error, _NonEmptyDatabase):
            try:
                _verify_current(config)
            except Exception as verification_error:
                detail = "現有結構尚未通過完整版本查核：" + _mysql_reason(verification_error)
            else:
                detail = "現有結構已通過完整版本查核；不需要重新初始化，可直接啟動服務"
            raise _NonEmptyDatabase(f"{error}. {detail}。未修改資料庫，不會自動清空或重跑。") from None
        if journal_path is not None:
            errno = error.args[0] if isinstance(error, pymysql.MySQLError) and error.args and isinstance(error.args[0], int) else None
            _journal(journal_path, {"event": "failed_partial", "phase": phase,
                                   "completed_statements": completed, "mysql_errno": errno,
                                   "error_type": type(error).__name__,
                                   "reset_operation": reset_operation if phase in {"reset_database", "create_database"} else None,
                                   "reset_completed": reset_completed})
            reset_detail = ""
            if phase in {"reset_database", "create_database"}:
                reset_detail = (
                    f"{'Reset' if reset else 'Create'} operation: {reset_operation or 'configure_lock_wait'}; "
                    f"last confirmed: {reset_completed[-1] if reset_completed else 'none'}. "
                )
                if errno in {2006, 2013}:
                    reset_detail += "連線已中斷，目前操作是否完成未知，MySQL 可能仍在執行；先確認 NAS 資料庫現況，勿立即重跑操作。 "
            summary = (
                "All schema statements completed, but verification failed"
                if completed == len(plan["steps"])
                else "Initialization failed before all schema statements completed"
            )
            raise InitializationBlocked(
                f"{summary}; DDL may be committed. "
                f"Phase: {phase}; completed: {completed}/{len(plan['steps'])}; "
                f"MySQL errno: {errno if errno is not None else 'unavailable'}. "
                f"{reset_detail}"
                f"Reason: {_mysql_reason(error)}. "
                f"No automatic cleanup or retry. Journal: {journal_path}"
            ) from None
        if not isinstance(error, InitializationBlocked):
            raise InitializationBlocked("初始化前檢查未通過，尚未寫入資料庫：" + _mysql_reason(error)) from None
        raise
    finally:
        # Closing also releases the session-owned initialization lock.
        connection.close()


def _answer(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _confirm_reset(target):
    print(f"\n[WARNING] Target: {target['host']}:{target['port']} / {target['database']} (server: {target['server']})")
    print("This will DELETE and RECREATE this entire database, including ALL tables, views, routines, events and data.")
    print("This cannot be undone. Stop applications and other database writers before continuing.")
    expected = "RESET " + target["database"]
    return _answer(f"Type {expected} exactly to clear and reinitialize, or press Enter to cancel: ") == expected


def _confirm_create(target):
    print(f"\n[Info] Target: {target['host']}:{target['port']} / {target['database']} (server: {target['server']})")
    print("The database is missing. This will CREATE it and initialize the complete schema and required system data.")
    return _answer("Press Y then Enter to create and initialize, or N then Enter to cancel: ").upper() == "Y"


def _interactive_initialize(config, plan):
    try:
        preview = initialize(config, plan)
    except _MissingDatabase as error:
        print(str(error))
        return initialize(config, plan, apply=True, create_missing=True, confirm_create=_confirm_create)
    except _NonEmptyDatabase as error:
        print(str(error))
        answer = _answer("Press R then Enter to reset this test database, or N then Enter to cancel: ")
        if answer.upper() != "R":
            return {"status": "cancelled", "writes": "not_run"}
        return initialize(config, plan, apply=True, reset=True, confirm_reset=_confirm_reset)
    print(json.dumps(preview, ensure_ascii=False))
    if _answer("Press Y then Enter to initialize, or N then Enter to cancel: ").upper() != "Y":
        return {"status": "cancelled", "writes": "not_run"}
    print("[Info] Initializing NAS schema. All preflight checks will be repeated before writing...")
    return initialize(config, plan, apply=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="initialize the existing empty union_db")
    mode.add_argument("--dry-run", action="store_true", help="validate config and canonical SQL without connecting")
    mode.add_argument("--interactive", action="store_true", help="confirm initialization, missing database creation or test database reset")
    args = parser.parse_args(argv)
    try:
        config = load_configuration()
        plan = schema_plan()
        if args.dry_run:
            result = {"status": "configured", "connection": "not_run", "statement_count": len(plan["steps"]),
                      "schema_parts": plan["schema_parts"], "assembly_id": plan["assembly_id"]}
        elif args.interactive:
            result = _interactive_initialize(config, plan)
        else:
            result = initialize(config, plan, apply=args.apply)
    except InitializationBlocked as error:
        result = {"status": "blocked", "error": str(error)}
    except Exception:
        result = {"status": "blocked", "error": "NAS initialization failed; check .env, MySQL permissions, TLS and canonical schema"}
    print(json.dumps(result, ensure_ascii=False))
    if args.interactive:
        if result["status"] == "passed":
            print("[Done] NAS schema initialization completed.")
        elif result["status"] == "cancelled":
            print("[Cancelled] No database changes were requested.")
    return 1 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Initialize an existing, empty NAS union_db from the canonical schema assembly."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
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
DATABASE_CONTROL = re.compile(r"^(?:USE\b|(?:CREATE|DROP|ALTER)\s+(?:DATABASE|SCHEMA)\b)", re.I)
BASE_CONTROLS = {
    "DROP DATABASE IF EXISTS union_db",
    "CREATE DATABASE union_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci",
    "USE union_db",
}


class InitializationBlocked(RuntimeError):
    """An operator-facing failure containing no provider error or credentials."""


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


def schema_plan():
    """Freeze validated SQL in memory before any connection or mutation."""
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


def _require_empty(cursor, database):
    cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
    identity = cursor.fetchone()
    if not identity or identity["database_name"] != database or not identity["server"]:
        raise InitializationBlocked("Connected database identity does not match target")
    for table, field in (
        ("tables", "table_schema"), ("routines", "routine_schema"), ("events", "event_schema"),
    ):
        cursor.execute(f"SELECT 1 FROM information_schema.{table} WHERE {field}=%s LIMIT 1", (database,))
        if cursor.fetchone():
            raise InitializationBlocked("Database is not empty; initialization stopped without schema writes")
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


def initialize(config, plan, *, apply=False, receipt_root=RECEIPT_ROOT):
    """The CLI validates NAS union_db; engine tests inject an owned lu_test_* target."""
    settings = dict(config)
    settings.update(autocommit=True, cursorclass=pymysql.cursors.DictCursor,
                    connect_timeout=5, read_timeout=30, write_timeout=30)
    if not apply:
        settings["init_command"] = "SET SESSION TRANSACTION READ ONLY"
    connection = pymysql.connect(**settings)
    journal_path = None
    completed = 0
    phase = "preflight"
    try:
        with connection.cursor() as cursor:
            if apply:
                cursor.execute("SELECT GET_LOCK(%s, 0) AS acquired", ("nas_schema_init:" + config["database"],))
                if cursor.fetchone().get("acquired") != 1:
                    raise InitializationBlocked("Another schema initializer holds the database lock")
            identity = _require_empty(cursor, config["database"])
            result = {
                "status": "ready", "database": config["database"], "server": identity["server"],
                "assembly_id": plan["assembly_id"], "release_id": plan["release_id"],
                "statement_count": len(plan["steps"]), "system_seed_policy": "canonical_schema_only",
            }
            if not apply:
                return result
            directory = Path(receipt_root) / uuid4().hex
            directory.mkdir(parents=True, exist_ok=False)
            journal_path = directory / "journal.jsonl"
            _journal(journal_path, {"event": "started", **result})
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
        if journal_path is not None:
            errno = error.args[0] if isinstance(error, pymysql.MySQLError) and error.args and isinstance(error.args[0], int) else None
            _journal(journal_path, {"event": "failed_partial", "phase": phase,
                                   "completed_statements": completed, "mysql_errno": errno,
                                   "error_type": type(error).__name__})
            raise InitializationBlocked(
                f"Initialization failed; DDL may be committed. No automatic cleanup or retry. Journal: {journal_path}"
            ) from None
        raise
    finally:
        # Closing also releases the session-owned initialization lock.
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="initialize the existing empty union_db")
    mode.add_argument("--dry-run", action="store_true", help="validate config and canonical SQL without connecting")
    args = parser.parse_args(argv)
    try:
        config = load_configuration()
        plan = schema_plan()
        if args.dry_run:
            result = {"status": "configured", "connection": "not_run", "statement_count": len(plan["steps"]),
                      "schema_parts": plan["schema_parts"], "assembly_id": plan["assembly_id"]}
        else:
            result = initialize(config, plan, apply=args.apply)
    except InitializationBlocked as error:
        result = {"status": "blocked", "error": str(error)}
    except Exception:
        result = {"status": "blocked", "error": "NAS initialization failed; check .env, MySQL permissions, TLS and canonical schema"}
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

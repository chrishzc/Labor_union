"""Read-only MySQL readiness for the development runtime, including NAS targets."""

from __future__ import annotations

import argparse
import json
import os

import pymysql

from infrastructure.mysql.mysql_adapter import _database_config_from_environment
from scripts import update_local_database as updater


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class RuntimeDatabaseBlocked(RuntimeError):
    """A bounded message that never includes connection credentials."""


class ReadOnlyRuntimeConfig:
    """Use the application's connection settings for canonical schema reads."""

    def __init__(self, settings: dict) -> None:
        self._settings = dict(settings)
        self.host = settings["host"]
        self.port = settings["port"]

    def connect(self, database=None, *, timeout_seconds=None):
        settings = dict(self._settings)
        settings.pop("database", None)
        if database is not None:
            settings["database"] = database
        timeout = min(float(timeout_seconds or 5), 30)
        return pymysql.connect(
            **settings,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=timeout,
            read_timeout=timeout,
            write_timeout=timeout,
            init_command="SET SESSION TRANSACTION READ ONLY",
        )


def configured_database(*, require_remote=False):
    # mysql_adapter loads .env with the same process-over-file precedence as API.
    if os.getenv("APP_ENV", "development").strip().lower() not in {
        "development", "local", "test", "testing",
    }:
        raise RuntimeDatabaseBlocked("development launcher requires APP_ENV=development")
    if any(not os.getenv(key, "").strip() for key in (
        "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_DATABASE",
    )):
        raise RuntimeDatabaseBlocked("set DB_HOST, DB_USER, DB_PASSWORD and DB_DATABASE in .env")
    settings = _database_config_from_environment()
    host = settings["host"].strip().casefold().rstrip(".")
    if not host or host in {"0.0.0.0", "::"}:
        raise RuntimeDatabaseBlocked("DB_HOST must identify a MySQL server")
    if require_remote and host in LOCAL_HOSTS:
        raise RuntimeDatabaseBlocked("NAS launcher requires a remote DB_HOST, not localhost")
    database = settings["database"]
    if (
        not updater.migration.IDENTIFIER.fullmatch(database)
        or len(database) > 64
        or database.casefold() in updater.migration.LOCAL_ADDITIVE_SYSTEM_DATABASES
    ):
        raise RuntimeDatabaseBlocked("DB_DATABASE must name an application database")
    if not 1 <= settings["port"] <= 65535:
        raise RuntimeDatabaseBlocked("DB_PORT must be between 1 and 65535")
    return ReadOnlyRuntimeConfig(settings), database


def check_database(*, dry_run=False, require_remote=False):
    config, database = configured_database(require_remote=require_remote)
    if dry_run:
        return {"status": "configured", "connection": "not_run", "schema": "not_run"}
    preview = updater.build_additive_preview(
        config, database, updater.DEFAULT_RECEIPT_ROOT,
    )
    if preview.get("status") != "current":
        raise RuntimeDatabaseBlocked(
            "MySQL schema is not current; provision or upgrade the NAS test database separately"
        )
    updater.require_current_database(preview)
    return {"status": "passed", "connection": "passed", "schema": "current"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = check_database(
            dry_run=args.dry_run,
            require_remote=os.getenv("RUNTIME_DATABASE_TARGET") == "nas",
        )
    except RuntimeDatabaseBlocked as error:
        result = {"status": "blocked", "error": str(error)}
    except Exception:
        # Driver/provider errors may contain user names, paths or credentials.
        result = {"status": "blocked", "error": "MySQL readiness failed; check connection, permissions, TLS and schema"}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"configured", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

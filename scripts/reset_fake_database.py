"""Rebuild local ``union_db`` from the current canonical schema assembly."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pymysql

from infrastructure.mysql.mysql_adapter import DB_CONFIG
from scripts.init_db import DB_CONFIG as SERVER_CONFIG
from scripts.init_db import load_schema_paths
from scripts.schema_assembly import SchemaAssembly, load_schema_assembly
from scripts.sql_statements import split_sql
from scripts.verify_validation_schema_manifest import (
    DEFAULT_MANIFEST_PATH,
    expected_database_objects,
    load_manifest,
    selected_schema_parts,
    verify_database_objects,
    verify_manifest,
)


class FakeDatabaseResetError(RuntimeError):
    """Raised when the destructive local reset contract cannot be satisfied."""


def validate_target(config=None, environment=None) -> None:
    config = DB_CONFIG if config is None else config
    env = environment if environment is not None else os.environ
    host = str(config.get("host", "")).strip().lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise FakeDatabaseResetError("local MySQL only")
    if config.get("database") != "union_db":
        raise FakeDatabaseResetError("database must be union_db")
    profiles = [
        str(env.get(key, "")).strip().lower()
        for key in ("APP_ENV", "ENV", "FLASK_ENV")
        if str(env.get(key, "")).strip()
    ]
    if any("prod" in profile for profile in profiles):
        raise FakeDatabaseResetError("production environment refused")
    if not profiles or any(
        profile not in {"development", "dev", "local", "test", "testing", "validation"}
        for profile in profiles
    ):
        raise FakeDatabaseResetError("development environment required")


def _canonical_bootstrap_contract() -> tuple[SchemaAssembly, dict[str, object]]:
    """Validate every hash-locked input before any destructive connection is made."""
    try:
        assembly = load_schema_assembly()
        manifest = load_manifest(DEFAULT_MANIFEST_PATH)
        errors = verify_manifest(manifest)
        if errors:
            raise ValueError("; ".join(errors))
        manifest_paths = tuple(selected_schema_parts(manifest))
        if manifest_paths != assembly.active_artifact_paths:
            raise ValueError("validation manifest differs from canonical schema assembly")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FakeDatabaseResetError(f"canonical schema preflight failed: {exc}") from exc
    return assembly, manifest


def _partition_base_statements(path: Path) -> tuple[list[str], list[str]]:
    statements = split_sql(path.read_text(encoding="utf-8"))
    views = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("CREATE OR REPLACE VIEW")
    ]
    return [statement for statement in statements if statement not in views], views


def rebuild_schema(
    assembly: SchemaAssembly,
    manifest: dict[str, object],
    connection_factory=pymysql.connect,
) -> dict[str, Any]:
    """Destructively create current schema and verify its declared database objects."""
    base_statements, base_views = _partition_base_statements(assembly.base_schema_path)
    connection = connection_factory(**SERVER_CONFIG)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET NAMES utf8mb4")
            for statement in base_statements:
                cursor.execute(statement)
            cursor.execute("USE `union_db`")
            loaded_parts = load_schema_paths(cursor, assembly.active_artifact_paths)
            for statement in base_views:
                cursor.execute(statement)
            errors = verify_database_objects(
                cursor,
                "union_db",
                expected_database_objects(manifest),
            )
            if errors:
                raise FakeDatabaseResetError(
                    "canonical schema postcheck failed: " + "; ".join(errors)
                )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if isinstance(exc, FakeDatabaseResetError):
            raise
        raise FakeDatabaseResetError(
            "canonical schema reset failed; DROP may already have taken effect"
        ) from exc
    finally:
        connection.close()
    return {
        "assembly_id": assembly.assembly_id,
        "base_statement_count": len(base_statements),
        "schema_parts": loaded_parts,
        "base_view_count": len(base_views),
        "schema_postcheck": "pass",
        "business_fixture_rows_loaded": 0,
    }


def reset(
    apply: bool = False,
    confirm_database: str | None = None,
    *,
    connection_factory=pymysql.connect,
) -> dict[str, Any]:
    validate_target()
    assembly, manifest = _canonical_bootstrap_contract()
    schema_parts = list(assembly.active_artifact_paths)
    preview = {
        "target": {
            "host": DB_CONFIG["host"],
            "port": DB_CONFIG["port"],
            "database": "union_db",
        },
        "mode": "canonical_empty_database",
        "assembly_id": assembly.assembly_id,
        "schema_part_count": len(schema_parts),
        "terminal_schema_artifact": schema_parts[-1].name,
        "business_fixture": "none",
        "system_seed_policy": "canonical_schema_declared_only",
    }
    if not apply:
        return {"status": "preview", "side_effects": "none", **preview}
    if confirm_database != "union_db":
        raise FakeDatabaseResetError("apply requires --confirm-database union_db")
    schema_report = rebuild_schema(
        assembly,
        manifest,
        connection_factory=connection_factory,
    )
    return {"status": "completed", **preview, "schema_report": schema_report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database")
    arguments = parser.parse_args(argv)
    try:
        result = reset(arguments.apply, arguments.confirm_database)
    except FakeDatabaseResetError as exc:
        print(
            json.dumps(
                {"status": "blocked", "error": str(exc), "code": "database_reset_blocked"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

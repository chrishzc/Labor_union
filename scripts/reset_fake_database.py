"""Canonical local MySQL schema reset runner.

The module keeps two explicit destructive surfaces: disposable ``lu_test_*``
targets require a target-matching backup, while the operator-only ``union_db``
route requires an exact ``RESET`` discard confirmation.  Both routes require
a prior dry-run plan and a terminal receipt.  Dry-run, verify, and replay paths
do not open a database connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import pymysql

from infrastructure.mysql.mysql_adapter import DB_CONFIG
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
    """Raised when the disposable reset contract cannot be satisfied."""


_TARGET_PATTERN = re.compile(r"lu_test_[a-z0-9_]+\Z")
_OPERATOR_TARGET = "union_db"
_LOCAL_PROFILES = frozenset(
    {"development", "dev", "local", "test", "testing", "validation"}
)


def validate_target(
    config: dict[str, object] | None = None,
    environment: dict[str, str] | None = None,
    target_database: str | None = None,
    host: str | None = None,
) -> str:
    """Validate explicit target, configured identity, and local authority."""
    config = DB_CONFIG if config is None else config
    environment = os.environ if environment is None else environment
    target = str(target_database or "").strip()
    configured_database = str(config.get("database") or "").strip()
    configured_host = str(config.get("host") or "").strip()
    requested_host = str(host if host is not None else configured_host).strip()
    if not target:
        raise FakeDatabaseResetError("explicit --target-database is required")
    if target != _OPERATOR_TARGET and not _TARGET_PATTERN.fullmatch(target):
        raise FakeDatabaseResetError(
            "target database must be union_db or an explicitly named "
            "lu_test_* database"
        )
    if configured_database != target:
        raise FakeDatabaseResetError(
            "target database must exactly match configured DB_DATABASE"
        )
    if requested_host.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise FakeDatabaseResetError("destructive reset requires local MySQL host")
    if not configured_host or requested_host != configured_host:
        raise FakeDatabaseResetError("target host must exactly match configured DB_HOST")
    configured_environment = str(environment.get("APP_ENV") or "").strip().lower()
    if not configured_environment:
        configured_environment = str(environment.get("ENV") or "").strip().lower()
    if configured_environment in {"prod", "production"}:
        raise FakeDatabaseResetError("production environment is not permitted")
    if configured_environment not in _LOCAL_PROFILES:
        raise FakeDatabaseResetError("development or validation environment required")
    return target


def _canonical_bootstrap_contract(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> tuple[SchemaAssembly, dict[str, object]]:
    """Validate hash-locked schema inputs before any connection is opened."""
    try:
        assembly = load_schema_assembly()
        manifest = load_manifest(manifest_path)
        errors = verify_manifest(manifest)
        if errors:
            raise ValueError("; ".join(errors))
        if tuple(selected_schema_parts(manifest)) != assembly.active_artifact_paths:
            raise ValueError("validation manifest differs from canonical schema assembly")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FakeDatabaseResetError(f"canonical schema preflight failed: {exc}") from exc
    return assembly, manifest


def _base_schema_for(path: Path, database: str) -> str:
    """Render the canonical base schema for one validated local target."""
    source = path.read_text(encoding="utf-8")
    if database == _OPERATOR_TARGET:
        return source
    if not _TARGET_PATTERN.fullmatch(database):
        raise FakeDatabaseResetError(
            "base schema requires union_db or a disposable lu_test_* target"
        )
    return source.replace("union_db", database)


def _partition_base_statements(
    path: Path, database: str | None = None
) -> tuple[list[str], list[str]]:
    source = path.read_text(encoding="utf-8")
    if database is not None:
        source = _base_schema_for(path, database)
    statements = split_sql(source)
    views = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("CREATE OR REPLACE VIEW")
    ]
    return [statement for statement in statements if statement not in views], views


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plan_payload(
    assembly: SchemaAssembly,
    manifest: dict[str, object],
    target_database: str,
    config: dict[str, object],
) -> dict[str, object]:
    base_statements, base_views = _partition_base_statements(
        assembly.base_schema_path, target_database
    )
    payload: dict[str, object] = {
        "mode": "dry-run",
        "runner": "scripts.reset_fake_database",
        "target_database": target_database,
        "host": str(config.get("host") or ""),
        "port": int(config.get("port") or 3306),
        "assembly_id": assembly.assembly_id,
        "release_id": manifest["release_id"],
        "base_schema_sha256": _sha256_bytes(assembly.base_schema_path),
        "base_statement_count": len(base_statements),
        "view_count": len(base_views),
        "schema_parts": [path.name for path in assembly.active_artifact_paths],
        "schema_part_sha256": [
            _sha256_bytes(path) for path in assembly.active_artifact_paths
        ],
        "business_fixture_rows_loaded": 0,
        "system_seed_policy": "canonical_schema_declared_only",
    }
    payload["plan_fingerprint"] = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _read_json(path: Path, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FakeDatabaseResetError(f"{description} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise FakeDatabaseResetError(f"{description} must contain a JSON object")
    return payload


def _validate_backup(
    path_value: str | Path | None, target_database: str
) -> dict[str, object]:
    if not path_value:
        raise FakeDatabaseResetError("--apply requires --backup-receipt")
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise FakeDatabaseResetError("backup receipt does not exist or is empty")
    data = path.read_bytes()
    header = data[: 1_048_576]
    if not header.startswith((b"-- MySQL dump", b"-- MariaDB dump")):
        raise FakeDatabaseResetError("backup receipt is not a MySQL dump")
    markers = (
        f"Current Database: `{target_database}`".encode("utf-8"),
        f"USE `{target_database}`".encode("utf-8"),
        f"Database: {target_database}".encode("utf-8"),
    )
    if not any(marker in header for marker in markers):
        raise FakeDatabaseResetError(
            "backup receipt does not identify the target database"
        )
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "target_database": target_database,
    }


def _read_prior_plan(
    path_value: str | Path | None, expected: dict[str, object]
) -> dict[str, object]:
    if not path_value:
        raise FakeDatabaseResetError(
            "--apply requires --plan-receipt from a prior --dry-run"
        )
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FakeDatabaseResetError("dry-run plan receipt does not exist")
    plan = _read_json(path, "dry-run plan receipt")
    if plan.get("mode") != "dry-run":
        raise FakeDatabaseResetError("plan receipt is not a dry-run receipt")
    for field, value in expected.items():
        if plan.get(field) != value:
            raise FakeDatabaseResetError(f"schema bootstrap plan drift detected in {field}")
    return plan


def _identity_value(identity: object, key: str) -> object:
    if isinstance(identity, dict):
        return identity.get(key)
    return None


def _server_config(config: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in config.items() if key != "database"}


def _check_connected_identity(
    config: dict[str, object],
    target_database: str,
    connection_factory: Callable[..., Any] = pymysql.connect,
) -> dict[str, object]:
    connection = connection_factory(**_server_config(config))
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT DATABASE() AS database_name, @@hostname AS server, @@port AS port"
            )
            identity = cursor.fetchone()
        if not identity:
            raise FakeDatabaseResetError("connected MySQL identity is unavailable")
        connected_database = _identity_value(identity, "database_name")
        if connected_database not in (None, target_database):
            raise FakeDatabaseResetError(
                "connected database identity does not match target"
            )
        server = str(_identity_value(identity, "server") or "").strip()
        if not server:
            raise FakeDatabaseResetError("connected MySQL server identity is unavailable")
        connected_port = _identity_value(identity, "port")
        configured_port = config.get("port")
        if connected_port is not None and configured_port is not None:
            if int(connected_port) != int(configured_port):
                raise FakeDatabaseResetError("connected MySQL port does not match configured DB_PORT")
        return {
            "database": connected_database,
            "server": server,
            "port": connected_port,
        }
    finally:
        connection.close()


def rebuild_schema(
    assembly: SchemaAssembly,
    manifest: dict[str, object],
    target_database: str,
    *,
    config: dict[str, object] | None = None,
    connection_factory: Callable[..., Any] = pymysql.connect,
) -> dict[str, object]:
    """Drop/create one explicit disposable target and verify declared objects."""
    config = DB_CONFIG if config is None else config
    base_statements, base_views = _partition_base_statements(
        assembly.base_schema_path, target_database
    )
    connection = connection_factory(**_server_config(config))
    committed = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET NAMES utf8mb4")
            for statement in base_statements:
                cursor.execute(statement)
            cursor.execute(f"USE `{target_database}`")
            loaded_parts = load_schema_paths(cursor, assembly.active_artifact_paths)
            for statement in base_views:
                cursor.execute(statement)
            errors = verify_database_objects(
                cursor, target_database, expected_database_objects(manifest)
            )
            if errors:
                raise FakeDatabaseResetError(
                    "canonical schema postcheck failed: " + "; ".join(errors)
                )
        connection.commit()
        committed = True
    except Exception as exc:
        if not committed:
            try:
                connection.rollback()
            except Exception:
                pass
        if isinstance(exc, FakeDatabaseResetError):
            raise
        raise FakeDatabaseResetError(
            "canonical schema reset failed; MySQL DDL may already have taken effect"
        ) from exc
    finally:
        connection.close()
    return {
        "assembly_id": assembly.assembly_id,
        "target_database": target_database,
        "base_statement_count": len(base_statements),
        "schema_parts": loaded_parts,
        "base_view_count": len(base_views),
        "schema_postcheck": "pass",
        "business_fixture_rows_loaded": 0,
    }


def _receipt_identity(path_value: str | Path | None, target: str) -> dict[str, object]:
    if not path_value:
        raise FakeDatabaseResetError("--verify/--replay requires --receipt-path")
    path = Path(path_value).expanduser().resolve()
    receipt = _read_json(path, "terminal receipt")
    if receipt.get("target_database") != target:
        raise FakeDatabaseResetError("terminal receipt belongs to another target")
    if receipt.get("receipt_status") != "committed":
        raise FakeDatabaseResetError("terminal receipt is not committed")
    receipt["receipt_path"] = str(path)
    return receipt


def reset(
    apply: bool = False,
    confirm_database: str | None = None,
    *,
    confirm_apply: str | None = None,
    target_database: str | None = None,
    plan_receipt: str | Path | None = None,
    backup_receipt: str | Path | None = None,
    receipt_path: str | Path | None = None,
    verify: bool = False,
    replay: bool = False,
    operator_reset: bool = False,
    config: dict[str, object] | None = None,
    environment: dict[str, str] | None = None,
    connection_factory: Callable[..., Any] = pymysql.connect,
) -> dict[str, object]:
    config = DB_CONFIG if config is None else config
    target = validate_target(config, environment, target_database)
    if operator_reset and target != _OPERATOR_TARGET:
        raise FakeDatabaseResetError(
            "operator reset is restricted to union_db"
        )
    if target == _OPERATOR_TARGET and not operator_reset:
        raise FakeDatabaseResetError(
            "union_db requires the explicit operator reset route"
        )
    assembly, manifest = _canonical_bootstrap_contract()
    plan = _plan_payload(assembly, manifest, target, config)
    if verify or replay:
        terminal = _receipt_identity(receipt_path, target)
        terminal["status"] = "verified" if verify else "replayed"
        return terminal
    if not apply:
        result = {"status": "preview", "side_effects": "none", **plan}
        if plan_receipt:
            resolved = Path(plan_receipt).expanduser().resolve()
            _write_json(resolved, plan)
            result["plan_receipt"] = str(resolved)
        return result
    expected_confirmation = "RESET" if operator_reset else f"APPLY {target}"
    if confirm_database != target and confirm_database is not None:
        raise FakeDatabaseResetError(
            "apply requires exact --confirm-database target"
        )
    if confirm_apply is not None and confirm_apply != expected_confirmation:
        raise FakeDatabaseResetError(
            f"--confirm-apply must exactly equal '{expected_confirmation}'"
        )
    if confirm_apply is None and confirm_database is None:
        raise FakeDatabaseResetError(
            f"apply requires exact confirmation '{expected_confirmation}'"
        )
    if operator_reset and confirm_apply != "RESET":
        raise FakeDatabaseResetError(
            "operator reset requires exact RESET confirmation"
        )
    if not receipt_path:
        raise FakeDatabaseResetError(
            "--apply requires --receipt-path for terminal receipt"
        )
    _read_prior_plan(plan_receipt, plan)
    backup = (
        {
            "policy": "explicit_discard_confirmed",
            "target_database": target,
        }
        if operator_reset
        else _validate_backup(backup_receipt, target)
    )
    identity = _check_connected_identity(config, target, connection_factory)
    report = rebuild_schema(
        assembly,
        manifest,
        target,
        config=config,
        connection_factory=connection_factory,
    )
    receipt = {
        **plan,
        "status": "completed",
        "receipt_status": "committed",
        "connected_identity": identity,
        "backup_receipt": backup,
        "schema_report": report,
        "verify": "pass",
        "replay_key": plan["plan_fingerprint"],
    }
    resolved = Path(receipt_path).expanduser().resolve()
    _write_json(resolved, receipt)
    receipt["receipt_path"] = str(resolved)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--operator-reset", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Plan only (the default).")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--confirm-database")
    parser.add_argument("--confirm-apply")
    parser.add_argument("--plan-receipt", type=Path)
    parser.add_argument("--backup-receipt", type=Path)
    parser.add_argument("--receipt-path", type=Path)
    args = parser.parse_args(argv)
    if args.dry_run and (args.apply or args.verify or args.replay):
        parser.error("--dry-run cannot be combined with --apply, --verify, or --replay")
    if sum(bool(value) for value in (args.apply, args.verify, args.replay)) > 1:
        parser.error("--apply, --verify, and --replay are mutually exclusive")
    try:
        result = reset(
            apply=args.apply,
            confirm_database=args.confirm_database,
            confirm_apply=args.confirm_apply,
            target_database=args.target_database,
            plan_receipt=args.plan_receipt,
            backup_receipt=args.backup_receipt,
            receipt_path=args.receipt_path,
            verify=args.verify,
            replay=args.replay,
            operator_reset=args.operator_reset,
        )
    except (FakeDatabaseResetError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": "database_reset_blocked",
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

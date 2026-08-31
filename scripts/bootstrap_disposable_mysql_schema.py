"""
File: bootstrap_disposable_mysql_schema.py
Description: 以唯一 schema assembly 建立並驗證隔離的 disposable MySQL schema。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.reset_fake_database import split_sql
from scripts.init_db import load_schema_paths
from scripts.verify_validation_schema_manifest import (
    DEFAULT_MANIFEST_PATH,
    expected_database_objects,
    load_manifest,
    verify_database_objects,
    verify_manifest,
    selected_schema_parts,
)
from scripts.verification_gate_report import build_gate_report


SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def _require_disposable_database(database: str, confirmation: str) -> str:
    target = database.strip()
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", target):
        raise ValueError("database must start with lu_test_")
    if confirmation != target:
        raise ValueError("confirmation must exactly match database")
    return target


def _base_schema_for(database: str) -> str:
    source = SCHEMA_PATH.read_text(encoding="utf-8")
    return source.replace("union_db", database)


def _partition_base_statements(database: str) -> tuple[list[str], list[str]]:
    statements = split_sql(_base_schema_for(database))
    views = [statement for statement in statements if statement.lstrip().upper().startswith("CREATE OR REPLACE VIEW")]
    return [statement for statement in statements if statement not in views], views


def _connect(arguments):
    return pymysql.connect(
        host=arguments.host,
        port=arguments.port,
        user=arguments.user,
        password=arguments.password,
        charset="utf8mb4",
        autocommit=False,
    )


def _dry_run_payload(arguments, manifest: dict[str, object]) -> dict[str, object]:
    database = _require_disposable_database(arguments.database, arguments.confirm_database)
    statements, views = _partition_base_statements(database)
    maximum_part = getattr(arguments, "max_schema_part", None)
    selected_parts = [
        str(path)
        for path in selected_schema_parts(manifest)
        if maximum_part is None or int(re.match(r"^(\d+)", path.name).group(1)) <= maximum_part
    ]
    if getattr(arguments, "base_only", False):
        selected_parts = []
    payload = {
        "mode": "dry-run",
        "database": database,
        "release_id": manifest["release_id"],
        "base_statement_count": len(statements),
        "schema_parts": selected_parts,
        "view_count": len(views),
    }
    payload["plan_fingerprint"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload


def _require_configured_host(host: str) -> None:
    configured = os.getenv("DB_HOST", "").strip()
    if not configured:
        raise RuntimeError("DB_HOST must be configured explicitly")
    if host.strip() != configured:
        raise RuntimeError("--host must exactly match configured DB_HOST")


def _check_connected_identity(arguments, database: str) -> None:
    _require_configured_host(arguments.host)
    connection = _connect(arguments)
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, @@hostname AS server")
            identity = cursor.fetchone()
        if identity and identity.get("database_name") not in (None, database):
            raise RuntimeError("connected database identity does not match target")
        if not identity or not str(identity.get("server") or "").strip():
            raise RuntimeError("connected MySQL server identity is unavailable")
    finally:
        connection.close()


def _verified_manifest(manifest_path: Path) -> dict[str, object]:
    manifest = load_manifest(manifest_path)
    errors = verify_manifest(manifest)
    if errors:
        raise RuntimeError("validation schema manifest failed: " + "; ".join(errors))
    return manifest


def _require_validation_gate() -> None:
    errors = _schema_bootstrap_gate_errors(build_gate_report())
    if errors:
        raise RuntimeError(
            "schema bootstrap contract gate failed before database creation: "
            + "; ".join(errors)
        )


def _schema_bootstrap_gate_errors(gate: dict[str, object]) -> list[str]:
    """Require schema prerequisites, not receipts the fresh database must create."""
    error_groups = gate.get("errors")
    if not isinstance(error_groups, dict):
        return ["verification gate report is malformed"]
    required_groups = ("baseline", "scenarios", "field_authority")
    return [
        f"{group}: {error}"
        for group in required_groups
        for error in error_groups.get(group, [])
    ]


def _require_absent_database(cursor, database: str) -> None:
    cursor.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
        (database,),
    )
    if cursor.fetchone() is not None:
        raise RuntimeError("disposable database already exists; refusing to overwrite it")


def _load_schema_parts_through(cursor, maximum_part: int, manifest) -> list[str]:
    selected: list[Path] = []
    for path in selected_schema_parts(manifest):
        match = re.match(r"^(\d+)", path.name)
        if match and int(match.group(1)) <= maximum_part:
            selected.append(path)
    return load_schema_paths(cursor, selected)


def bootstrap(arguments) -> dict[str, object]:
    database = _require_disposable_database(
        arguments.database,
        arguments.confirm_database,
    )
    _require_validation_gate()
    manifest = _verified_manifest(Path(getattr(arguments, "manifest", DEFAULT_MANIFEST_PATH)))
    connection = _connect(arguments)
    try:
        with connection.cursor() as cursor:
            _require_absent_database(cursor, database)
            statements, views = _partition_base_statements(database)
            for statement in statements:
                cursor.execute(statement)
            cursor.execute(f"USE `{database}`")
            maximum_part = getattr(arguments, "max_schema_part", None)
            if getattr(arguments, "base_only", False):
                parts = []
            elif maximum_part is not None:
                parts = _load_schema_parts_through(cursor, maximum_part, manifest)
            else:
                parts = load_schema_paths(cursor, selected_schema_parts(manifest))
            for view in views:
                cursor.execute(view)
            _verify_complete_schema(cursor, database, arguments, manifest)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "database": database,
        "release_id": manifest["release_id"],
        "base_statement_count": len(statements),
        "schema_parts": parts,
        "view_count": len(views),
    }


def _verify_complete_schema(cursor, database: str, arguments, manifest: dict[str, object]) -> None:
    if getattr(arguments, "base_only", False):
        return
    if getattr(arguments, "max_schema_part", None) is not None:
        return
    errors = verify_database_objects(cursor, database, expected_database_objects(manifest))
    if errors:
        raise RuntimeError("validation schema postcheck failed: " + "; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "1234"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the disposable schema after an explicit dry-run and confirmation.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only (the default).")
    parser.add_argument("--confirm-apply")
    parser.add_argument("--receipt-path", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--base-only",
        action="store_true",
        help="Create only db/schema.sql for a pre-migration rehearsal baseline",
    )
    parser.add_argument(
        "--max-schema-part",
        type=int,
        help="Apply only schema parts whose leading number is at most this value",
    )
    arguments = parser.parse_args()
    if arguments.apply and arguments.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        parser.error("production environment is not permitted for disposable schema bootstrap")
    manifest = _verified_manifest(Path(getattr(arguments, "manifest", DEFAULT_MANIFEST_PATH)))
    if not arguments.apply:
        _require_validation_gate()
        payload = _dry_run_payload(arguments, manifest)
        if arguments.receipt_path:
            arguments.receipt_path.parent.mkdir(parents=True, exist_ok=True)
            arguments.receipt_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    expected = f"APPLY {arguments.database}"
    if arguments.confirm_apply != expected:
        parser.error(f"--confirm-apply must exactly equal {expected!r}")
    if not arguments.receipt_path or not arguments.receipt_path.is_file():
        parser.error("--apply requires --receipt-path from a prior --dry-run")
    try:
        prior = json.loads(arguments.receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(f"--receipt-path is not a valid dry-run receipt: {exc}")
    if prior.get("mode") != "dry-run" or prior.get("database") != arguments.database:
        parser.error("--receipt-path belongs to another disposable schema target")
    current = _dry_run_payload(arguments, manifest)
    if prior.get("plan_fingerprint") != current["plan_fingerprint"]:
        parser.error("schema bootstrap plan drift detected; rerun the dry-run")
    _check_connected_identity(arguments, arguments.database)
    payload = bootstrap(arguments)
    payload["mode"] = "apply"
    payload["receipt_status"] = "committed"
    arguments.receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

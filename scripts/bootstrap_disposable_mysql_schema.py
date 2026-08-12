"""Bootstrap only an explicitly confirmed disposable MySQL schema."""

from __future__ import annotations

import argparse
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
from scripts.init_db import _schema_part_sort_key, load_schema_parts
from scripts.verify_validation_schema_manifest import (
    DEFAULT_MANIFEST_PATH,
    expected_database_objects,
    load_manifest,
    verify_database_objects,
    verify_manifest,
)
from scripts.verification_gate_report import build_gate_report


SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"
SCHEMA_PARTS_PATH = PROJECT_ROOT / "db" / "schema_parts"


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
    required_groups = ("baseline", "scenarios", "fixtures", "field_authority")
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


def _load_schema_parts_through(cursor, maximum_part: int) -> list[str]:
    selected: list[Path] = []
    for path in SCHEMA_PARTS_PATH.glob("*.sql"):
        match = re.match(r"^(\d+)", path.name)
        if match and int(match.group(1)) <= maximum_part:
            selected.append(path)
    loaded: list[str] = []
    for path in sorted(selected, key=_schema_part_sort_key):
        try:
            for statement in split_sql(path.read_text(encoding="utf-8")):
                cursor.execute(statement)
        except Exception as exc:
            raise RuntimeError(
                f"載入 schema part 失敗：{path.name}: {exc}"
            ) from exc
        loaded.append(path.name)
    return loaded


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
                parts = _load_schema_parts_through(cursor, maximum_part)
            else:
                parts = load_schema_parts(cursor, SCHEMA_PARTS_PATH)
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
    print(json.dumps(bootstrap(arguments), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

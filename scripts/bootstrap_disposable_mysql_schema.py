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
from scripts.init_db import load_schema_parts


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


def _load_schema_parts_through(cursor, maximum_part: int) -> list[str]:
    selected: list[tuple[int, Path]] = []
    for path in SCHEMA_PARTS_PATH.glob("*.sql"):
        match = re.match(r"^(\d+)", path.name)
        if match and int(match.group(1)) <= maximum_part:
            selected.append((int(match.group(1)), path))
    loaded: list[str] = []
    for _, path in sorted(selected, key=lambda item: (item[0], item[1].name)):
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
    connection = _connect(arguments)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
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
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {"database": database, "base_statement_count": len(statements), "schema_parts": parts, "view_count": len(views)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", ""))
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
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

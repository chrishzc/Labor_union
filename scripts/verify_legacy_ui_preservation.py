"""Verify preserved legacy roots remain unchanged after target-only scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.plan_legacy_ui_dataset_integration import (
    PRESERVED_ROOT_TABLES,
    SOURCE_DATABASE,
)


_TARGET_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")


def verify(arguments) -> dict[str, object]:
    target = _require_target_database(arguments.database)
    connection = pymysql.connect(
        host=arguments.host,
        port=arguments.port,
        user=arguments.user,
        password=arguments.password,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        tables = _verify_tables(connection, target)
    finally:
        connection.close()
    return {
        "contract": "labor-union-legacy-ui-preservation-immutability/v1",
        "source_database": SOURCE_DATABASE,
        "target_database": target,
        "tables": tables,
        "valid": all(table["passed"] for table in tables),
    }


def _require_target_database(database: str) -> str:
    if not _TARGET_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")
    return database


def _verify_tables(connection, target: str) -> list[dict[str, object]]:
    with connection.cursor() as cursor:
        return [
            _verify_table(cursor, table_name, target)
            for table_name in PRESERVED_ROOT_TABLES
        ]


def _verify_table(cursor, table_name: str, target: str) -> dict[str, object]:
    columns = _shared_columns(cursor, table_name, target)
    keys = _primary_key_columns(cursor, table_name)
    source_rows = _table_rows(cursor, SOURCE_DATABASE, table_name, columns)
    target_rows = _table_rows(cursor, target, table_name, columns)
    comparison = compare_preserved_rows(source_rows, target_rows, keys, columns)
    return {"table": table_name, **comparison}


def compare_preserved_rows(source_rows, target_rows, keys, columns) -> dict[str, object]:
    source_by_key = {_row_key(row, keys): row for row in source_rows}
    target_by_key = {_row_key(row, keys): row for row in target_rows}
    target_subset = [target_by_key[key] for key in source_by_key if key in target_by_key]
    source_digest = _row_digest(source_rows, columns, keys)
    target_digest = _row_digest(target_subset, columns, keys)
    return {
        "source_row_count": len(source_rows),
        "target_matched_row_count": len(target_subset),
        "source_digest": source_digest,
        "target_digest": target_digest,
        "passed": len(source_rows) == len(target_subset) and source_digest == target_digest,
    }


def _shared_columns(cursor, table_name: str, target: str) -> tuple[str, ...]:
    source = set(_column_names(cursor, SOURCE_DATABASE, table_name))
    target_columns = _column_names(cursor, target, table_name)
    return tuple(column for column in target_columns if column in source)


def _primary_key_columns(cursor, table_name: str) -> tuple[str, ...]:
    cursor.execute(
        "SELECT column_name FROM information_schema.key_column_usage "
        "WHERE table_schema=%s AND table_name=%s AND constraint_name='PRIMARY' "
        "ORDER BY ordinal_position",
        (SOURCE_DATABASE, table_name),
    )
    keys = tuple(str(_field(row, "column_name")) for row in cursor.fetchall())
    if not keys:
        raise RuntimeError(f"preserved root table has no primary key: {table_name}")
    return keys


def _column_names(cursor, database: str, table_name: str) -> tuple[str, ...]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (database, table_name),
    )
    return tuple(str(_field(row, "column_name")) for row in cursor.fetchall())


def _table_rows(cursor, database: str, table_name: str, columns):
    names = ",".join(f"`{column}`" for column in columns)
    cursor.execute(f"SELECT {names} FROM `{database}`.`{table_name}`")
    return cursor.fetchall()


def _row_key(row, keys) -> tuple[object, ...]:
    return tuple(row[key] for key in keys)


def _field(row, expected_name: str):
    for name, value in row.items():
        if str(name).lower() == expected_name:
            return value
    raise KeyError(expected_name)


def _row_digest(rows, columns, keys) -> str:
    normalized = [
        {column: row[column] for column in columns}
        for row in sorted(rows, key=lambda row: _row_key(row, keys))
    ]
    payload = json.dumps(normalized, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=3306, type=int)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="1234")
    result = verify(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

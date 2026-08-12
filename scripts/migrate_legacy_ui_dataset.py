"""Copy the preserved v5 dataset into an empty current validation schema."""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable
import json
import os
from pathlib import Path
import re
import sys

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.plan_legacy_ui_dataset_integration import (
    SOURCE_DATABASE,
    classify_table,
    preserved_root_tables,
    require_target_database,
    root_digest,
    source_column_actions,
)
from scripts.rebuild_legacy_ui_dataset_projections import rebuild_preserved_root_projections


_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
_BOOTSTRAP_BASELINE_TABLES = frozenset(
    {"government_payers", "payroll_rate_policies"}
)


def copy_statement(
    source_database: str,
    target_database: str,
    table_name: str,
    shared_columns: Iterable[str],
) -> str:
    columns = tuple(shared_columns)
    _require_identifiers(source_database, target_database, table_name, *columns)
    target_columns = ",".join(_quote(column) for column in columns)
    expressions = ",".join(
        _source_expression(table_name, column) for column in columns
    )
    prefix = "INSERT IGNORE" if table_name in _BOOTSTRAP_BASELINE_TABLES else "INSERT"
    return f"{prefix} INTO {_qualified(target_database, table_name)} ({target_columns}) SELECT {expressions} FROM {_qualified(source_database, table_name)}"


def migrate(connection, target_database: str) -> dict[str, object]:
    target = require_target_database(target_database)
    with connection.cursor() as cursor:
        source_tables = _table_names(cursor, SOURCE_DATABASE)
        target_tables = _table_names(cursor, target)
        _require_target_schema(source_tables, target_tables)
        _require_empty_target(cursor, target, target_tables)
        table_columns = _shared_column_contracts(cursor, source_tables, target)
    connection.begin()
    try:
        with connection.cursor() as cursor:
            root_tables = _preserved_root_tables(source_tables)
            _require_no_unclassified_source_rows(cursor, source_tables)
            for table_name in root_tables:
                cursor.execute(
                    copy_statement(
                        SOURCE_DATABASE,
                        target,
                        table_name,
                        table_columns[table_name],
                    )
                )
            _verify_row_counts(cursor, root_tables, target)
            _verify_foreign_keys(cursor, target)
            source_digest = root_digest(
                cursor,
                SOURCE_DATABASE,
                {table: table_columns[table] for table in root_tables},
            )
            target_digest = root_digest(
                cursor,
                target,
                {table: table_columns[table] for table in root_tables},
            )
            if source_digest != target_digest:
                raise RuntimeError("preservation source-target digest mismatch")
            projection_rebuild = rebuild_preserved_root_projections(connection, target)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "contract": "labor-union-legacy-ui-preservation/v1",
        "source_database": SOURCE_DATABASE,
        "target_database": target,
        "copied_tables": len(root_tables),
        "copied_rows": _total_rows(connection, target, root_tables),
        "source_root_digest": source_digest,
        "target_root_digest": target_digest,
        "projection_rebuild": projection_rebuild,
        "projection_rebuild_required": False,
    }


def preflight(connection, target_database: str) -> dict[str, object]:
    """Read preservation inputs without copying roots or rebuilding projections."""
    target = require_target_database(target_database)
    with connection.cursor() as cursor:
        source_tables = _table_names(cursor, SOURCE_DATABASE)
        target_tables = _table_names(cursor, target)
        _require_target_schema(source_tables, target_tables)
        table_columns = _shared_column_contracts(cursor, source_tables, target)
        root_tables = _preserved_root_tables(source_tables)
        unresolved_tables = _unclassified_source_tables(cursor, source_tables)
        source_digest = root_digest(
            cursor,
            SOURCE_DATABASE,
            {table: table_columns[table] for table in root_tables},
        )
        target_is_empty = _target_is_empty(cursor, target, target_tables)
    report = _preflight_report(
        target,
        root_tables,
        table_columns,
        source_digest,
        target_is_empty,
    )
    if unresolved_tables:
        return _blocked_preflight_report(report, unresolved_tables)
    return report


def _preflight_report(target, root_tables, table_columns, source_digest, target_is_empty):
    return {
        "contract": "labor-union-legacy-ui-preservation-preflight/v1",
        "source_database": SOURCE_DATABASE,
        "target_database": target,
        "copied_tables": len(root_tables),
        "root_tables": list(root_tables),
        "source_root_digest": source_digest,
        "shared_column_counts": {
            table: len(table_columns[table]) for table in root_tables
        },
        "target_is_empty": target_is_empty,
        "migration_permitted": target_is_empty,
        "blocker_code": None if target_is_empty else "target_not_empty",
        "dry_run": True,
    }


def _blocked_preflight_report(report, unresolved_tables):
    return {
        **report,
        "migration_permitted": False,
        "blocker_code": "unclassified_source_tables",
        "unclassified_source_tables": list(unresolved_tables),
    }


def _source_expression(table_name: str, column_name: str) -> str:
    if table_name == "system_alerts" and column_name == "details":
        return (
            "JSON_MERGE_PATCH(COALESCE(`details`,JSON_OBJECT()),"
            "JSON_OBJECT('_legacy',JSON_OBJECT("
            "'description',`description`,'event_type',`event_type`))) AS `details`"
        )
    return _quote(column_name)


def _preserved_root_tables(source_tables: Iterable[str]) -> tuple[str, ...]:
    return preserved_root_tables(source_tables)


def _require_no_unclassified_source_rows(cursor, source_tables: Iterable[str]) -> None:
    unresolved = _unclassified_source_tables(cursor, source_tables)
    if unresolved:
        raise RuntimeError(
            "preservation migration requires an explicit root allowlist: "
            + ",".join(unresolved)
        )


def _unclassified_source_tables(cursor, source_tables: Iterable[str]) -> list[str]:
    return [
        table for table in source_tables
        if classify_table(table) == "legacy_unresolved"
        and _row_count(cursor, SOURCE_DATABASE, table)
    ]


def _require_target_schema(source_tables, target_tables) -> None:
    missing = sorted(set(source_tables) - set(target_tables))
    if missing:
        raise RuntimeError("target schema lacks source tables: " + ",".join(missing))


def _require_empty_target(cursor, target_database: str, target_tables) -> None:
    if not _target_is_empty(cursor, target_database, target_tables):
        raise RuntimeError("target must be empty before preservation migration")
    _verify_bootstrap_policy_baseline(cursor, target_database)


def _target_is_empty(cursor, target_database: str, target_tables) -> bool:
    return not any(
        table_name not in _BOOTSTRAP_BASELINE_TABLES
        and _row_count(cursor, target_database, table_name)
        for table_name in target_tables
    )


def _verify_bootstrap_policy_baseline(cursor, target_database: str) -> None:
    cursor.execute(
        "SELECT policy_version,policy_kind,hourly_rate_ntd,effective_from,effective_until "
        f"FROM {_qualified(SOURCE_DATABASE, 'payroll_rate_policies')}"
    )
    source_rows = {(_policy_key(row)): _policy_values(row) for row in cursor.fetchall()}
    cursor.execute(
        "SELECT policy_version,policy_kind,hourly_rate_ntd,effective_from,effective_until "
        f"FROM {_qualified(target_database, 'payroll_rate_policies')}"
    )
    target_rows = {(_policy_key(row)): _policy_values(row) for row in cursor.fetchall()}
    conflicting = [
        key for key in source_rows.keys() & target_rows.keys()
        if source_rows[key] != target_rows[key]
    ]
    if conflicting:
        raise RuntimeError("bootstrap payroll policy differs from preserved source")


def _policy_key(row) -> tuple[object, object]:
    return row[0], row[1]


def _policy_values(row) -> tuple[object, ...]:
    return tuple(row[2:])


def _shared_column_contracts(cursor, source_tables, target_database: str):
    contracts: dict[str, tuple[str, ...]] = {}
    for table_name in source_tables:
        source_columns = _column_names(cursor, SOURCE_DATABASE, table_name)
        target_columns = _column_names(cursor, target_database, table_name)
        source_only = sorted(set(source_columns) - set(target_columns))
        actions = source_column_actions(table_name, source_only)
        blockers = [name for name, action in actions.items() if action == "unmapped_blocker"]
        if blockers:
            raise RuntimeError(
                f"unmapped source columns for {table_name}: " + ",".join(blockers)
            )
        contracts[table_name] = tuple(
            column for column in target_columns if column in set(source_columns)
        )
    return contracts


def _verify_row_counts(cursor, source_tables, target_database: str) -> None:
    mismatches = [
        table_name
        for table_name in source_tables
        if table_name not in _BOOTSTRAP_BASELINE_TABLES
        and _row_count(cursor, SOURCE_DATABASE, table_name)
        != _row_count(cursor, target_database, table_name)
    ]
    if mismatches:
        raise RuntimeError("preservation row-count mismatch: " + ",".join(mismatches))
    _verify_bootstrap_policy_baseline(cursor, target_database)


def _verify_foreign_keys(cursor, target_database: str) -> None:
    constraints = _foreign_key_columns(cursor, target_database)
    invalid = [
        name
        for name, columns in constraints.items()
        if _foreign_key_orphan_count(cursor, target_database, columns)
    ]
    if invalid:
        raise RuntimeError("preservation foreign-key mismatch: " + ",".join(invalid))


def _foreign_key_columns(cursor, database: str):
    cursor.execute(
        "SELECT constraint_name,table_name,column_name,referenced_table_name,"
        "referenced_column_name,ordinal_position "
        "FROM information_schema.key_column_usage WHERE table_schema=%s "
        "AND referenced_table_name IS NOT NULL ORDER BY constraint_name,ordinal_position",
        (database,),
    )
    grouped = defaultdict(list)
    for row in cursor.fetchall():
        grouped[str(row[0])].append(tuple(str(value) for value in row[1:5]))
    return dict(grouped)


def _foreign_key_orphan_count(cursor, database: str, columns) -> int:
    child_table, _, parent_table, _ = columns[0]
    joins = " AND ".join(
        f"child.{_quote(child_column)}=parent.{_quote(parent_column)}"
        for _, child_column, _, parent_column in columns
    )
    populated = " AND ".join(
        f"child.{_quote(child_column)} IS NOT NULL"
        for _, child_column, _, _ in columns
    )
    statement = (
        f"SELECT COUNT(*) FROM {_qualified(database, child_table)} child "
        f"LEFT JOIN {_qualified(database, parent_table)} parent ON {joins} "
        f"WHERE {populated} AND parent.{_quote(columns[0][3])} IS NULL"
    )
    cursor.execute(statement)
    return int(cursor.fetchone()[0])


def _total_rows(connection, database: str, tables) -> int:
    with connection.cursor() as cursor:
        return sum(_row_count(cursor, database, table) for table in tables)


def _table_names(cursor, database: str) -> list[str]:
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",
        (database,),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _column_names(cursor, database: str, table_name: str) -> list[str]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (database, table_name),
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _row_count(cursor, database: str, table_name: str) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {_qualified(database, table_name)}")
    return int(cursor.fetchone()[0])


def _qualified(database: str, table_name: str) -> str:
    _require_identifiers(database, table_name)
    return f"{_quote(database)}.{_quote(table_name)}"


def _quote(identifier: str) -> str:
    _require_identifiers(identifier)
    return f"`{identifier}`"


def _require_identifiers(*identifiers: str) -> None:
    if any(not _IDENTIFIER.fullmatch(identifier) for identifier in identifiers):
        raise ValueError("invalid SQL identifier")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("DB_USER", "root"))
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "1234"))
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    if arguments.confirm_database != arguments.database:
        raise ValueError("confirmation must exactly match target database")
    connection = pymysql.connect(
        host=arguments.host, port=arguments.port, user=arguments.user,
        password=arguments.password, charset="utf8mb4",
    )
    try:
        result = preflight(connection, arguments.database) if arguments.dry_run else migrate(connection, arguments.database)
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("migration_permitted", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())

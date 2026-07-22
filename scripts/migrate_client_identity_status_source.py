"""Safely retire the legacy order eligibility column after all consumers migrate.

The default mode is a read-only audit.  MySQL DDL is atomic but implicitly
committed, so --apply records the pre-DDL table definition and never claims a
transaction rollback after the column has been removed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any

import pymysql
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
LEGACY_COLUMN = "subsidy_" + "eligibility"
SOURCE_DIRECTORIES = ("api", "db", "scripts", "services", "ui")
SOURCE_SUFFIXES = {".py", ".sql"}
CANONICAL_VIEW_NAME = "v_order_details"


def database_config() -> dict[str, Any]:
    """Load the project's MySQL configuration without opening a connection."""
    load_dotenv(ROOT / ".env")
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "1234"),
        "database": os.getenv("DB_DATABASE", "union_db"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }


def find_legacy_source_references(project_root: str | Path = ROOT) -> list[dict[str, Any]]:
    """Return every application/SQL consumer still mentioning the retired field."""
    root = Path(project_root).resolve()
    own_source = Path(__file__).resolve()
    own_relative_path = Path("scripts") / Path(__file__).name
    references: list[dict[str, Any]] = []
    for directory in SOURCE_DIRECTORIES:
        source_dir = root / directory
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.rglob("*")):
            if (
                path.suffix not in SOURCE_SUFFIXES
                or not path.is_file()
                or path.resolve() == own_source
                or path.relative_to(root) == own_relative_path
            ):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                references.append({"path": path.relative_to(root).as_posix(), "line": None, "reason": "not_utf8"})
                continue
            for line_number, line in enumerate(lines, start=1):
                if LEGACY_COLUMN in line:
                    references.append({"path": path.relative_to(root).as_posix(), "line": line_number})
    return references


def _scalar(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone() or {}
    return int(_metadata_value(row, "count") or 0)


def _metadata_value(row: Any, expected_key: str) -> Any:
    """Read DictCursor metadata regardless of the server's column-key casing."""
    if not isinstance(row, dict):
        return None
    expected = expected_key.casefold()
    for key, value in row.items():
        if str(key).casefold() == expected:
            return value
    return None


def _column_exists(cursor: Any) -> bool:
    return bool(_scalar(
        cursor,
        """SELECT COUNT(*) AS count FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = 'orders' AND column_name = %s""",
        (LEGACY_COLUMN,),
    ))


def _affected_views(cursor: Any) -> list[dict[str, str]]:
    cursor.execute(
        """SELECT table_name, view_definition FROM information_schema.views
           WHERE table_schema = DATABASE() AND view_definition LIKE %s
           ORDER BY table_name""",
        (f"%{LEGACY_COLUMN}%",),
    )
    views: list[dict[str, str]] = []
    for row in cursor.fetchall():
        table_name = _metadata_value(row, "table_name")
        view_definition = _metadata_value(row, "view_definition")
        if not table_name or view_definition is None:
            raise RuntimeError("information_schema.views metadata is missing table_name or view_definition")
        views.append({"table_name": str(table_name), "view_definition": str(view_definition)})
    return views


def _database_prechecks(connection: Any) -> dict[str, Any]:
    """Inspect only; no order, client, finance, or assignment record is changed."""
    with connection.cursor() as cursor:
        order_count = _scalar(cursor, "SELECT COUNT(*) AS count FROM orders")
        missing_identity_count = _scalar(
            cursor,
            """SELECT COUNT(*) AS count FROM clients
               WHERE identity_status IS NULL OR TRIM(identity_status) = ''""",
        )
        unlinked_order_count = _scalar(
            cursor,
            """SELECT COUNT(*) AS count FROM orders o
               LEFT JOIN clients c ON c.id = o.client_id
               WHERE c.id IS NULL""",
        )
        orders_with_missing_identity = _scalar(
            cursor,
            """SELECT COUNT(*) AS count FROM orders o
               JOIN clients c ON c.id = o.client_id
               WHERE c.identity_status IS NULL OR TRIM(c.identity_status) = ''""",
        )
        affected_views = _affected_views(cursor)
        dependent_routine_count = _scalar(
            cursor,
            """SELECT COUNT(*) AS count FROM information_schema.routines
               WHERE routine_schema = DATABASE() AND routine_definition LIKE %s""",
            (f"%{LEGACY_COLUMN}%",),
        )
        return {
            "orders_count": order_count,
            "clients_missing_identity_status": missing_identity_count,
            "orders_without_client": unlinked_order_count,
            "orders_with_missing_client_identity_status": orders_with_missing_identity,
            "legacy_column_exists": _column_exists(cursor),
            "database_views_still_using_legacy_column": len(affected_views),
            "database_routines_still_using_legacy_column": dependent_routine_count,
        }


def _blocked_reasons(
    source_references: list[dict[str, Any]],
    database: dict[str, Any],
    *,
    discard_fake_data: bool = False,
) -> list[str]:
    reasons: list[str] = []
    if source_references:
        reasons.append("application_or_sql_sources_still_reference_legacy_column")
    if database["clients_missing_identity_status"] and not discard_fake_data:
        reasons.append("clients_have_missing_identity_status")
    if database["orders_without_client"]:
        reasons.append("orders_are_not_linked_to_clients")
    if database["orders_with_missing_client_identity_status"] and not discard_fake_data:
        reasons.append("orders_are_not_linked_to_nonempty_client_identity_status")
    if database["database_views_still_using_legacy_column"] and not discard_fake_data:
        reasons.append("database_views_still_reference_legacy_column")
    if database["database_routines_still_using_legacy_column"]:
        reasons.append("database_routines_still_reference_legacy_column")
    return reasons


def _show_create_table(cursor: Any) -> str:
    cursor.execute("SHOW CREATE TABLE orders")
    row = cursor.fetchone() or {}
    create_statement = _metadata_value(row, "create table")
    if create_statement is not None:
        return str(create_statement)
    raise RuntimeError("SHOW CREATE TABLE orders returned no table definition")


def _show_create_view(cursor: Any, view_name: str) -> str:
    cursor.execute(f"SHOW CREATE VIEW `{view_name}`")
    row = cursor.fetchone() or {}
    create_statement = _metadata_value(row, "create view")
    if create_statement is not None:
        return str(create_statement)
    raise RuntimeError(f"SHOW CREATE VIEW returned no definition for {view_name}")


def _canonical_v_order_details_statement() -> str:
    """Load the version-controlled identity-status view definition verbatim."""
    schema_path = ROOT / "db" / "schema.sql"
    try:
        schema = schema_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read canonical schema at {schema_path}") from exc
    match = re.search(
        rf"(?ims)^CREATE\s+OR\s+REPLACE\s+VIEW\s+`?{CANONICAL_VIEW_NAME}`?\s+AS\b.*?;",
        schema,
    )
    if not match:
        raise RuntimeError(f"canonical schema does not define {CANONICAL_VIEW_NAME}")
    statement = match.group(0).strip()
    if LEGACY_COLUMN in statement or "c.identity_status" not in statement:
        raise RuntimeError(f"canonical {CANONICAL_VIEW_NAME} is not identity-status based")
    return statement


def _rebuild_known_views_from_canonical(cursor: Any, view_backups: list[dict[str, str]]) -> None:
    """Rebuild only the explicitly supported view from its checked-in definition."""
    unknown_views = [item["view_name"] for item in view_backups if item["view_name"] != CANONICAL_VIEW_NAME]
    if unknown_views:
        raise RuntimeError("unknown affected views cannot be rebuilt safely: " + ", ".join(unknown_views))
    if not view_backups:
        return
    statement = _canonical_v_order_details_statement()
    cursor.execute(statement)
    view_backups[0]["rebuilt_statement"] = statement


def run_migration(
    connection: Any,
    *,
    apply: bool = False,
    discard_fake_data: bool = False,
    project_root: str | Path = ROOT,
) -> dict[str, Any]:
    """Build an audit manifest and, only when safe and explicit, execute MySQL DDL."""
    if discard_fake_data and not apply:
        raise ValueError("discard_fake_data requires apply=True")
    source_references = find_legacy_source_references(project_root)
    database = _database_prechecks(connection)
    blocked_reasons = _blocked_reasons(source_references, database, discard_fake_data=discard_fake_data)
    manifest: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "force_mode": {
            "discard_fake_data": discard_fake_data,
            "identity_gaps": {
                "clients_missing_identity_status": database["clients_missing_identity_status"],
                "orders_with_missing_client_identity_status": database["orders_with_missing_client_identity_status"],
            },
        },
        "source_references": source_references,
        "database_prechecks": database,
        "blocked_reasons": blocked_reasons,
        "schema_before": None,
        "ddl": {"executed": False, "statement": None},
        "postcheck": None,
    }

    if blocked_reasons:
        return manifest
    if not database["legacy_column_exists"]:
        manifest["postcheck"] = {"status": "already_removed", "legacy_column_exists": False}
        return manifest
    if not apply:
        manifest["postcheck"] = {"status": "would_remove", "legacy_column_exists": True}
        return manifest

    with connection.cursor() as cursor:
        manifest["schema_before"] = _show_create_table(cursor)
        view_backups = []
        if discard_fake_data:
            for view in _affected_views(cursor):
                create_statement = _show_create_view(cursor, view["table_name"])
                view_backups.append({
                    "view_name": view["table_name"],
                    "view_definition_before": create_statement,
                })
            _rebuild_known_views_from_canonical(cursor, view_backups)
        manifest["force_mode"]["view_rebuilds"] = view_backups
        ddl = f"ALTER TABLE orders DROP COLUMN `{LEGACY_COLUMN}`"
        try:
            cursor.execute(ddl)
            manifest["ddl"] = {"executed": True, "statement": ddl, "transactional": False}
        except Exception as exc:
            manifest["ddl"] = {"executed": False, "statement": ddl, "error": str(exc), "transactional": False}
            manifest["postcheck"] = {"status": "ddl_failed_no_rollback_claimed"}
            return manifest

    post_database = _database_prechecks(connection)
    post_reasons = _blocked_reasons(
        find_legacy_source_references(project_root), post_database, discard_fake_data=discard_fake_data
    )
    column_removed = not post_database["legacy_column_exists"]
    manifest["postcheck"] = {
        "status": "passed" if column_removed and not post_reasons else "failed_no_rollback_claimed",
        "legacy_column_exists": post_database["legacy_column_exists"],
        "blocked_reasons": post_reasons,
        "database": post_database,
    }
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and retire the legacy order eligibility column.")
    parser.add_argument("--apply", action="store_true", help="Execute DROP COLUMN only after all prechecks pass.")
    parser.add_argument(
        "--discard-fake-data", action="store_true",
        help="With --apply only, permit blank fake identities and rebuild affected views before DDL.",
    )
    parser.add_argument("--project-root", default=str(ROOT), help="Project root used for consumer-source audit.")
    args = parser.parse_args(argv)
    try:
        connection = pymysql.connect(**database_config())
        try:
            manifest = run_migration(
                connection,
                apply=args.apply,
                discard_fake_data=args.discard_fake_data,
                project_root=args.project_root,
            )
        finally:
            connection.close()
    except Exception as exc:
        print(json.dumps({"mode": "apply" if args.apply else "dry-run", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if not manifest["blocked_reasons"] and manifest["postcheck"]["status"] in {"passed", "would_remove", "already_removed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

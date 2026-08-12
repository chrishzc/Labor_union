"""Safely project orders.lifecycle_version through the existing order view.

The default mode is read-only. MySQL view DDL implicitly commits, so apply
mode records the complete original definition for manual recovery and never
claims that failed postchecks were rolled back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

import pymysql
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "db" / "schema_parts" / "999_v_order_details_view.sql"
VIEW_NAME = "v_order_details"
_FORBIDDEN_SQL = re.compile(
    r"\b(?:DROP\s+(?:DATABASE|TABLE)|CREATE\s+DATABASE|TRUNCATE|"
    r"DELETE|UPDATE|INSERT|ALTER\s+TABLE)\b",
    re.IGNORECASE,
)


def database_config() -> dict[str, Any]:
    """Load the configured target without opening a connection."""
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


def _metadata_value(row: Any, expected_key: str) -> Any:
    if not isinstance(row, Mapping):
        raise RuntimeError("metadata query must return a mapping row")
    expected = expected_key.casefold()
    matches = [
        value
        for key, value in row.items()
        if str(key).casefold() == expected
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"metadata row must contain exactly one {expected_key!r} field"
        )
    return matches[0]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _without_line_comments(sql: str) -> str:
    return "\n".join(
        line.split("--", 1)[0] for line in sql.replace("\r\n", "\n").splitlines()
    )


def _normalized_view_query(statement: str) -> str:
    """Normalize a CREATE VIEW statement for semantic idempotency checks."""
    uncommented = _without_line_comments(statement).strip().rstrip(";")
    match = re.search(
        rf"(?is)\bVIEW\s+`?{re.escape(VIEW_NAME)}`?\s+AS\s+(SELECT\b.*)\Z",
        uncommented,
    )
    if not match:
        raise RuntimeError(f"cannot extract {VIEW_NAME} SELECT definition")
    query = match.group(1).replace("`", "")
    return " ".join(query.split()).casefold()


def _semantic_hash(statement: str) -> str:
    return _sha256(_normalized_view_query(statement))


def canonical_view_statement(
    schema_path: str | Path = SCHEMA_PATH,
) -> str:
    """Extract the single version-controlled CREATE OR REPLACE VIEW."""
    path = Path(schema_path)
    try:
        schema = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read canonical schema: {path}") from exc
    matches = list(
        re.finditer(
            rf"(?ims)^CREATE\s+OR\s+REPLACE\s+VIEW\s+`?"
            rf"{re.escape(VIEW_NAME)}`?\s+AS\b.*?;",
            schema,
        )
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"canonical schema must contain exactly one {VIEW_NAME} statement"
        )
    statement = matches[0].group(0).strip()
    uncommented = _without_line_comments(statement)
    if _FORBIDDEN_SQL.search(uncommented):
        raise RuntimeError("canonical view statement contains forbidden SQL")
    if uncommented.rstrip().rstrip(";").find(";") >= 0:
        raise RuntimeError("canonical view definition contains multiple statements")
    if len(re.findall(r"\bo\.lifecycle_version\b", uncommented)) != 1:
        raise RuntimeError(
            "canonical view must project o.lifecycle_version exactly once"
        )
    select_list = re.search(
        r"(?is)\bAS\s+SELECT\b(.*?)\bFROM\s+orders\s+o\b",
        uncommented,
    )
    if not select_list or not re.search(
        r"(?:^|,)\s*o\.lifecycle_version"
        r"(?:\s+AS\s+lifecycle_version)?\s*(?:,|$)",
        select_list.group(1),
        re.IGNORECASE,
    ):
        raise RuntimeError(
            "o.lifecycle_version must be a direct top-level view projection"
        )
    _normalized_view_query(statement)
    return statement


def _identity(cursor: Any) -> dict[str, str]:
    cursor.execute(
        "SELECT DATABASE() AS database_name, @@hostname AS server_hostname"
    )
    row = cursor.fetchone()
    database_name = _metadata_value(row, "database_name")
    server_hostname = _metadata_value(row, "server_hostname")
    if not isinstance(database_name, str) or not database_name:
        raise RuntimeError("target database identity is missing")
    if not isinstance(server_hostname, str) or not server_hostname:
        raise RuntimeError("target server identity is missing")
    return {
        "database": database_name,
        "server": server_hostname,
    }


def _show_create_view(cursor: Any) -> str:
    cursor.execute(f"SHOW CREATE VIEW `{VIEW_NAME}`")
    statement = _metadata_value(cursor.fetchone(), "Create View")
    if not isinstance(statement, str) or not statement.strip():
        raise RuntimeError("SHOW CREATE VIEW returned no definition")
    _normalized_view_query(statement)
    return statement.strip()


def _columns(cursor: Any) -> list[str]:
    cursor.execute(
        """SELECT column_name
           FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = %s
           ORDER BY ordinal_position""",
        (VIEW_NAME,),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, (list, tuple)):
        raise RuntimeError("view column metadata must be a row sequence")
    columns = []
    for row in rows:
        value = _metadata_value(row, "column_name")
        if not isinstance(value, str) or not value:
            raise RuntimeError("view column metadata contains an invalid name")
        columns.append(value)
    if not columns or len(columns) != len(set(columns)):
        raise RuntimeError("view columns are empty or duplicated")
    return columns


def _source_column_exists(cursor: Any) -> bool:
    cursor.execute(
        """SELECT COUNT(*) AS count
           FROM information_schema.columns
           WHERE table_schema = DATABASE()
             AND table_name = 'orders'
             AND column_name = 'lifecycle_version'"""
    )
    value = _metadata_value(cursor.fetchone(), "count")
    if isinstance(value, bool):
        raise RuntimeError("source column count returned bool")
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("source column count returned a non-integer") from exc
    if count not in {0, 1} or count != value:
        raise RuntimeError("source column count must be zero or one")
    return count == 1


def _count(cursor: Any, sql: str) -> int:
    cursor.execute(sql)
    value = _metadata_value(cursor.fetchone(), "count")
    if isinstance(value, bool):
        raise RuntimeError("count query returned bool")
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("count query returned a non-integer") from exc
    if count < 0 or count != value:
        raise RuntimeError("count query returned a non-canonical integer")
    return count


def _view_row_count(cursor: Any) -> int:
    return _count(cursor, f"SELECT COUNT(*) AS count FROM `{VIEW_NAME}`")


def _value_parity_mismatch_count(cursor: Any) -> int:
    return _count(
        cursor,
        f"""SELECT COUNT(*) AS count
            FROM (
                SELECT o.case_no
                FROM orders o
                LEFT JOIN `{VIEW_NAME}` v ON v.case_no = o.case_no
                WHERE v.case_no IS NULL
                   OR NOT (v.lifecycle_version <=> o.lifecycle_version)
                UNION ALL
                SELECT v.case_no
                FROM `{VIEW_NAME}` v
                LEFT JOIN orders o ON o.case_no = v.case_no
                WHERE o.case_no IS NULL
            ) AS lifecycle_version_mismatches""",
    )


def _snapshot(cursor: Any) -> dict[str, Any]:
    statement = _show_create_view(cursor)
    return {
        "identity": _identity(cursor),
        "create_view": statement,
        "create_view_sha256": _sha256(statement),
        "semantic_sha256": _semantic_hash(statement),
        "columns": _columns(cursor),
        "row_count": _view_row_count(cursor),
        "orders_lifecycle_version_exists": _source_column_exists(cursor),
    }


def _same_preddl_target(
    before: Mapping[str, Any], recheck: Mapping[str, Any]
) -> bool:
    return all(
        before[key] == recheck[key]
        for key in (
            "identity",
            "create_view_sha256",
            "semantic_sha256",
            "columns",
            "row_count",
            "orders_lifecycle_version_exists",
        )
    )


def _validated_existing(
    cursor: Any,
    snapshot: Mapping[str, Any],
    canonical_semantic_hash: str,
) -> bool:
    if snapshot["semantic_sha256"] != canonical_semantic_hash:
        return False
    if snapshot["columns"].count("lifecycle_version") != 1:
        return False
    return _value_parity_mismatch_count(cursor) == 0


def run_migration(
    connection: Any,
    *,
    apply: bool = False,
    schema_path: str | Path = SCHEMA_PATH,
) -> dict[str, Any]:
    """Audit or replace only v_order_details on the configured target."""
    canonical = canonical_view_statement(schema_path)
    canonical_hash = _sha256(canonical)
    canonical_semantic_hash = _semantic_hash(canonical)
    with connection.cursor() as cursor:
        before = _snapshot(cursor)
        manifest: dict[str, Any] = {
            "mode": "apply" if apply else "dry-run",
            "status": None,
            "target": before["identity"],
            "before": before,
            "canonical": {
                "source": str(Path(schema_path)),
                "sha256": canonical_hash,
                "semantic_sha256": canonical_semantic_hash,
            },
            "ddl": {
                "executed": False,
                "statement_sha256": canonical_hash,
                "transactional": False,
            },
            "after": None,
            "recovery": {
                "manual_required_on_failure": True,
                "create_view": before["create_view"],
                "create_view_sha256": before["create_view_sha256"],
            },
        }

        if not before["orders_lifecycle_version_exists"]:
            manifest["status"] = "blocked_missing_orders_lifecycle_version"
            return manifest
        if _validated_existing(cursor, before, canonical_semantic_hash):
            manifest["status"] = "existing"
            manifest["after"] = before
            return manifest
        if not apply:
            manifest["status"] = "ready"
            return manifest

        recheck = _snapshot(cursor)
        if not _same_preddl_target(before, recheck):
            manifest["status"] = "blocked_preddl_fingerprint_changed"
            manifest["preddl_recheck"] = recheck
            return manifest

        try:
            cursor.execute(canonical)
            manifest["ddl"]["executed"] = True
            after = _snapshot(cursor)
            manifest["after"] = after
            mismatch_count = (
                _value_parity_mismatch_count(cursor)
                if after["columns"].count("lifecycle_version") == 1
                else None
            )
            manifest["after"]["value_parity_mismatch_count"] = mismatch_count
            checks_passed = (
                after["identity"] == before["identity"]
                and after["columns"].count("lifecycle_version") == 1
                and after["row_count"] == before["row_count"]
                and mismatch_count == 0
                and manifest["ddl"]["executed"] is True
                and manifest["ddl"]["statement_sha256"] == canonical_hash
            )
            manifest["status"] = (
                "applied" if checks_passed else "failed_no_rollback_claimed"
            )
        except Exception as exc:
            manifest["status"] = "failed_no_rollback_claimed"
            manifest["error"] = str(exc)
        return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit v_order_details and optionally project orders.lifecycle_version."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute only the canonical CREATE OR REPLACE VIEW after rechecks.",
    )
    parser.add_argument(
        "--schema-path",
        default=str(SCHEMA_PATH),
        help="Version-controlled schema.sql used as the only DDL source.",
    )
    args = parser.parse_args(argv)
    connection = None
    try:
        connection = pymysql.connect(**database_config())
        manifest = run_migration(
            connection,
            apply=args.apply,
            schema_path=args.schema_path,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry-run",
                    "status": "error",
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2
    finally:
        if connection is not None:
            connection.close()

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] in {"ready", "existing", "applied"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

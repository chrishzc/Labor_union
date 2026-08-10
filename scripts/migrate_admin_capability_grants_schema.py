"""Apply the cumulative Access, Knowledge, session, and LINE confirmation schema."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from infrastructure.mysql.mysql_adapter import get_connection
from scripts.reset_fake_database import split_sql


ROOT = Path(__file__).resolve().parents[1]
RELEASE_PARTS = (
    ROOT / "db" / "schema_parts" / "147_access_capability_grants.sql",
    ROOT / "db" / "schema_parts" / "148_knowledge_retrieval.sql",
    ROOT / "db" / "schema_parts" / "150_line_publication_confirmation_and_session_expiry.sql",
    ROOT / "db" / "schema_parts" / "151_admin_security_audit_retention.sql",
    ROOT / "db" / "schema_parts" / "152_finance_import_ingestion_attempts.sql",
)


def _has_authorization_version(cursor: Any) -> bool:
    cursor.execute("SHOW COLUMNS FROM admin_users LIKE 'authorization_version'")
    return cursor.fetchone() is not None


def migrate(connection: Any) -> str:
    with connection.cursor() as cursor:
        already_current = _has_authorization_version(cursor)
        if not already_current:
            cursor.execute(
                "ALTER TABLE admin_users ADD COLUMN authorization_version "
                "BIGINT UNSIGNED NOT NULL DEFAULT 0 "
                "COMMENT 'effective capability grant revision' AFTER enabled"
            )
        _apply_release_parts(cursor)
    connection.commit()
    return "already_current" if already_current else "migrated"


def _apply_release_parts(cursor: Any) -> None:
    for schema_part in RELEASE_PARTS:
        for statement in split_sql(schema_part.read_text(encoding="utf-8")):
            cursor.execute(statement)


def main() -> int:
    connection = get_connection()
    try:
        print(migrate(connection))
        return 0
    except Exception as error:
        connection.rollback()
        print(f"migration failed: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

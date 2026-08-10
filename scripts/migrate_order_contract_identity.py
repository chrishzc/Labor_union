"""Retire the provider-specific Orders contract column without losing facts."""

from __future__ import annotations

import sys
from typing import Any

from infrastructure.mysql.mysql_adapter import get_connection


LEGACY_COLUMN = "contract_id"
CANONICAL_COLUMN = "contract_identity"


def _order_columns(cursor: Any) -> set[str]:
    cursor.execute("SHOW COLUMNS FROM orders")
    return {str(row["Field"]) for row in cursor.fetchall()}


def retire_legacy_contract_column(cursor: Any) -> str:
    """Rename exactly the known legacy column; ambiguous states fail closed."""
    columns = _order_columns(cursor)
    legacy_exists = LEGACY_COLUMN in columns
    canonical_exists = CANONICAL_COLUMN in columns
    if not legacy_exists and canonical_exists:
        return "already_retired"
    if legacy_exists and not canonical_exists:
        cursor.execute(
            "ALTER TABLE orders RENAME COLUMN contract_id TO contract_identity"
        )
        return "renamed"
    raise RuntimeError("orders contract identity columns are absent or ambiguous")


def migrate(connection: Any) -> dict[str, str]:
    with connection.cursor() as cursor:
        outcome = retire_legacy_contract_column(cursor)
    connection.commit()
    return {"status": outcome, "canonical_column": CANONICAL_COLUMN}


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

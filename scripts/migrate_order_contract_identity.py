"""Retire the provider-specific Orders contract column without losing facts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migrate_order_details_lifecycle_version_view import canonical_view_statement


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


def rebuild_order_details_view(cursor: Any) -> None:
    cursor.execute(canonical_view_statement())


def migrate(connection: Any) -> dict[str, str]:
    """Apply this library-only step using a caller-owned connection.

    The preserve-data runner owns the candidate transaction and its receipt.
    Keeping this function free of commit/rollback/close is important because
    the legacy child executable is no longer an independent migration owner.
    """
    with connection.cursor() as cursor:
        outcome = retire_legacy_contract_column(cursor)
        if outcome == "renamed":
            rebuild_order_details_view(cursor)
    return {"status": outcome, "canonical_column": CANONICAL_COLUMN}

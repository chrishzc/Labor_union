"""Retired Finance Import diagnostic dispatch boundary.

Historical workbook diagnostics may classify and stage rows inside a transaction
that is always rolled back.  They must not post legacy payment transactions;
formal settlement is only available through the typed Finance Import workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _dispatch_row(cursor: Any, row_id: int) -> Mapping[str, Any]:
    cursor.execute(
        "SELECT id, classification_type, matched_identity_ids, "
        "resolved_counterparty_account, classification_reason, debit "
        "FROM finance_import_rows WHERE id=%s FOR UPDATE",
        (row_id,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("finance import row was not found")
    return row


def dispatch_finance_import_row(
    cursor: Any,
    finance_import_row_id: int,
    originating_batch_id: int,
) -> dict[str, Any]:
    """Report a diagnostic-only pending result without creating formal facts."""
    if not callable(getattr(cursor, "execute", None)):
        raise AssertionError("cursor must provide execute()")
    row_id = _positive_id(finance_import_row_id, "finance_import_row_id")
    _positive_id(originating_batch_id, "originating_batch_id")
    row = _dispatch_row(cursor, row_id)
    classification_type = str(row.get("classification_type") or "non_business_review")
    reason = row.get("classification_reason")
    if classification_type != "non_business_review":
        reason = "legacy_finance_import_diagnostic_dispatch_retired"
    return {
        "classification_type": classification_type,
        "result": "pending",
        "reason": reason or "non_business_review",
        "formal_references": {},
        "finance_alert_action": None,
    }

"""Read exact bank-account identity candidates used by finance classification."""

from __future__ import annotations

from collections.abc import Mapping
import unicodedata
from typing import Any


def _account(value: Any) -> str | None:
    """Normalize only Unicode representation and surrounding whitespace."""
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    return normalized or None


def _positive_id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _stable_map(candidates: dict[str, set[int]]) -> dict[str, list[int]]:
    return {
        account: sorted(candidates[account])
        for account in sorted(candidates)
    }


def load_finance_identity_maps(cursor: Any) -> dict[str, dict[str, list[int]]]:
    """Load exact unresolved-client and all-staff account candidates read-only."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    assert callable(getattr(cursor, "fetchall", None)), "cursor must provide fetchall()"

    cursor.execute(
        """SELECT cp.id AS client_payment_id, br.refund_account_no
           FROM client_payments cp
           JOIN beclass_records br ON br.query_no=cp.case_no
           WHERE cp.subsidy_return_receivable > cp.subsidy_return_refunded
             AND (
                 cp.subsidy_return_review_status IS NULL
                 OR cp.subsidy_return_review_status <> 'review_required'
             )
           ORDER BY cp.id, br.id"""
    )
    client_rows = cursor.fetchall()
    client_candidates: dict[str, set[int]] = {}
    for row in client_rows:
        if not isinstance(row, Mapping):
            raise TypeError("cursor must return mapping rows")
        account = _account(row.get("refund_account_no"))
        if account is None:
            continue
        client_payment_id = _positive_id(
            row.get("client_payment_id"), "client_payment_id"
        )
        client_candidates.setdefault(account, set()).add(client_payment_id)

    cursor.execute(
        """SELECT sba.staff_id, sba.account_no
           FROM staff_bank_accounts sba
           WHERE sba.account_no IS NOT NULL
           ORDER BY sba.staff_id, sba.id"""
    )
    staff_rows = cursor.fetchall()
    staff_candidates: dict[str, set[int]] = {}
    for row in staff_rows:
        if not isinstance(row, Mapping):
            raise TypeError("cursor must return mapping rows")
        account = _account(row.get("account_no"))
        if account is None:
            continue
        staff_id = _positive_id(row.get("staff_id"), "staff_id")
        staff_candidates.setdefault(account, set()).add(staff_id)

    return {
        "client_refund_accounts": _stable_map(client_candidates),
        "staff_accounts": _stable_map(staff_candidates),
    }

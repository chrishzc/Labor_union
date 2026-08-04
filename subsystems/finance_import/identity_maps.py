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


def load_finance_identity_maps(cursor: Any) -> dict[str, Any]:
    """Load exact unresolved-client and all-staff account candidates read-only."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    assert callable(getattr(cursor, "fetchall", None)), "cursor must provide fetchall()"

    cursor.execute(
        """SELECT order_row.client_id, br.refund_account_no
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           JOIN beclass_records br ON br.query_no=obligation.case_no
           WHERE obligation.direction='payable_to_client'
             AND obligation.obligation_type='subsidy_return'
             AND obligation.status='open'
             AND obligation.amount_due_ntd>0
           ORDER BY order_row.client_id, br.id"""
    )
    client_rows = cursor.fetchall()
    subsidy_return_candidates: dict[str, set[int]] = {}
    for row in client_rows:
        if not isinstance(row, Mapping):
            raise TypeError("cursor must return mapping rows")
        account = _account(row.get("refund_account_no"))
        if account is None:
            continue
        client_id = _positive_id(row.get("client_id"), "client_id")
        subsidy_return_candidates.setdefault(account, set()).add(client_id)

    cursor.execute(
        """SELECT order_row.client_id, br.refund_account_no
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           JOIN beclass_records br ON br.query_no=obligation.case_no
           WHERE obligation.direction='payable_to_client'
             AND obligation.status='open'
             AND obligation.amount_due_ntd>0
             AND obligation.obligation_type IN ('refund','adjustment')
           ORDER BY order_row.client_id, br.id"""
    )
    refund_rows = cursor.fetchall()
    refund_candidates: dict[str, set[int]] = {}
    for row in refund_rows:
        if not isinstance(row, Mapping):
            raise TypeError("cursor must return mapping rows")
        account = _account(row.get("refund_account_no"))
        if account is None:
            continue
        client_id = _positive_id(row.get("client_id"), "client_id")
        refund_candidates.setdefault(account, set()).add(client_id)

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
        "client_refund_accounts": _stable_map(refund_candidates),
        "client_subsidy_return_accounts": _stable_map(
            subsidy_return_candidates
        ),
        "staff_accounts": _stable_map(staff_candidates),
        "client_receipt_candidates": _client_receipt_candidates(cursor),
    }


def _client_receipt_candidates(cursor: Any) -> tuple[dict[str, Any], ...]:
    cursor.execute(
        """SELECT order_row.client_id,client.name,beclass.refund_account_no,
                  obligation.amount_due_ntd
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           JOIN clients client ON client.id=order_row.client_id
           LEFT JOIN beclass_records beclass ON beclass.query_no=order_row.case_no
           WHERE obligation.direction='receivable_from_client'
             AND obligation.status='open' AND obligation.amount_due_ntd>0
           ORDER BY order_row.client_id,obligation.obligation_identity"""
    )
    grouped: dict[int, dict[str, Any]] = {}
    for row in cursor.fetchall():
        if not isinstance(row, Mapping):
            raise TypeError("cursor must return mapping rows")
        client_id = _positive_id(row.get("client_id"), "client_id")
        candidate = grouped.setdefault(
            client_id,
            {
                "client_id": client_id,
                "name": _account(row.get("name")) or "",
                "account": _account(row.get("refund_account_no")) or "",
                "open_amounts": set(),
            },
        )
        candidate["open_amounts"].add(int(row["amount_due_ntd"]))
    return tuple(
        {
            **candidate,
            "open_amounts": tuple(sorted(candidate["open_amounts"])),
        }
        for _, candidate in sorted(grouped.items())
    )

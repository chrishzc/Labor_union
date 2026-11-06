"""
File: identity_maps.py
Description: 讀取銀行帳戶、客戶姓名及待退款義務候選，供財務分類與台新比對使用。
"""

from __future__ import annotations

from collections.abc import Mapping
import unicodedata
from typing import Any

from subsystems.client_finance.virtual_account_resolution import (
    build_client_virtual_account,
)


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
        """SELECT order_row.client_id, snapshot.bank_account AS refund_account_no
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           JOIN client_refund_recipient_snapshots snapshot
             ON snapshot.refund_obligation_identity=obligation.obligation_identity
            AND snapshot.case_no=obligation.case_no
           WHERE obligation.direction='payable_to_client'
             AND obligation.obligation_type='subsidy_return'
             AND obligation.status='open'
             AND obligation.amount_due_ntd>0
           ORDER BY order_row.client_id, obligation.obligation_identity"""
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
        """SELECT order_row.client_id, snapshot.bank_account AS refund_account_no
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           JOIN client_refund_recipient_snapshots snapshot
             ON snapshot.refund_obligation_identity=obligation.obligation_identity
            AND snapshot.case_no=obligation.case_no
           WHERE obligation.direction='payable_to_client'
             AND obligation.status='open'
             AND obligation.amount_due_ntd>0
             AND obligation.obligation_type IN ('refund','adjustment')
           ORDER BY order_row.client_id, obligation.obligation_identity"""
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

    try:
        cursor.execute(
            """SELECT obligation.case_no, obligation.staff_id
               FROM staff_obligations obligation
               WHERE obligation.direction='payable_to_staff'
                 AND obligation.status<>'cancelled'
                 AND obligation.amount_due_ntd>0
               ORDER BY obligation.staff_id, obligation.obligation_identity"""
        )
        staff_obligation_rows = cursor.fetchall()
    except Exception:
        staff_obligation_rows = ()

    try:
        cursor.execute(
            """SELECT case_no, staff_id
               FROM orders
               WHERE staff_id IS NOT NULL AND status <> '訂單取消'"""
        )
        order_staff_rows = cursor.fetchall()
    except Exception:
        order_staff_rows = ()

    try:
        cursor.execute(
            """SELECT case_no, staff_id
               FROM case_staff_assignments
               WHERE staff_id IS NOT NULL AND status='active'"""
        )
        assignment_staff_rows = cursor.fetchall()
    except Exception:
        assignment_staff_rows = ()

    all_staff_case_rows = list(staff_obligation_rows) + list(order_staff_rows) + list(assignment_staff_rows)

    try:
        cursor.execute(
            """SELECT obligation.case_no, order_row.client_id
               FROM client_obligations obligation
               JOIN orders order_row ON order_row.case_no=obligation.case_no
               WHERE obligation.direction='payable_to_client'
                 AND obligation.status='open'
                 AND obligation.amount_due_ntd>0
                 AND obligation.obligation_type IN ('refund','adjustment')
               ORDER BY order_row.client_id, obligation.obligation_identity"""
        )
        refund_obligation_rows = cursor.fetchall()
    except Exception:
        refund_obligation_rows = ()

    all_cases = {
        str(r["case_no"]) for r in all_staff_case_rows if isinstance(r, Mapping) and r.get("case_no")
    } | {
        str(r["case_no"]) for r in refund_obligation_rows if isinstance(r, Mapping) and r.get("case_no")
    }
    case_suffixes: dict[str, str] = {}
    if all_cases:
        try:
            format_strings = ",".join("%s" for _ in all_cases)
            cursor.execute(
                f"SELECT case_no, virtual_account FROM client_legacy_virtual_accounts WHERE case_no IN ({format_strings})",
                tuple(all_cases),
            )
            legacy_va = {
                str(row["case_no"]): str(row["virtual_account"])
                for row in cursor.fetchall()
                if isinstance(row, Mapping) and row.get("case_no") and row.get("virtual_account")
            }
        except Exception:
            legacy_va = {}
        for case_no in all_cases:
            va = legacy_va.get(case_no) or build_client_virtual_account(case_no)
            if va and len(va) >= 6:
                case_suffixes[case_no] = va[-6:]
            elif len(case_no) == 6 and case_no.isdigit():
                case_suffixes[case_no] = case_no

    staff_case_candidates: dict[str, set[int]] = {}
    for r in all_staff_case_rows:
        if not isinstance(r, Mapping):
            continue
        c_no = str(r.get("case_no") or "")
        suffix = case_suffixes.get(c_no)
        if suffix:
            s_id = _positive_id(r.get("staff_id"), "staff_id")
            staff_case_candidates.setdefault(suffix, set()).add(s_id)

    refund_case_candidates: dict[str, set[int]] = {}
    for r in refund_obligation_rows:
        if not isinstance(r, Mapping):
            continue
        c_no = str(r.get("case_no") or "")
        suffix = case_suffixes.get(c_no)
        if suffix:
            c_id = _positive_id(r.get("client_id"), "client_id")
            refund_case_candidates.setdefault(suffix, set()).add(c_id)

    return {
        "client_refund_accounts": _stable_map(refund_candidates),
        "client_subsidy_return_accounts": _stable_map(
            subsidy_return_candidates
        ),
        "staff_accounts": _stable_map(staff_candidates),
        "client_receipt_candidates": _client_receipt_candidates(cursor),
        "staff_case_suffixes": _stable_map(staff_case_candidates),
        "client_refund_case_suffixes": _stable_map(refund_case_candidates),
        "all_client_names": _all_client_names(cursor),
        "taishin_client_refund_candidates": _client_refund_name_candidates(cursor),
        "all_staff_names": _all_staff_names(cursor),
        "staff_payout_candidates": _staff_payout_candidates(cursor),
    }


def _all_staff_names(cursor: Any) -> tuple[str, ...]:
    try:
        cursor.execute("SELECT DISTINCT name FROM staff WHERE name IS NOT NULL AND name <> ''")
        names = []
        for row in cursor.fetchall():
            if isinstance(row, Mapping) and row.get("name"):
                normalized = _account(row.get("name"))
                if normalized:
                    names.append(normalized)
        return tuple(sorted(set(names), key=len, reverse=True))
    except Exception:
        return ()


def _staff_payout_candidates(cursor: Any) -> tuple[dict[str, Any], ...]:
    try:
        cursor.execute(
            """SELECT obligation.staff_id, staff.name, obligation.case_no,
                      obligation.obligation_identity,
                      COALESCE(projection.balance_ntd, obligation.amount_due_ntd) AS amount_due_ntd,
                      obligation.due_date
               FROM staff_obligations obligation
               JOIN staff staff ON staff.id=obligation.staff_id
               LEFT JOIN staff_payable_projections projection
                 ON projection.obligation_identity=obligation.obligation_identity
               WHERE obligation.direction='payable_to_staff'
                 AND obligation.status<>'cancelled'
                 AND obligation.amount_due_ntd>0
                 AND (projection.status IS NULL OR projection.status IN ('payable','partially_paid'))
               ORDER BY obligation.staff_id, obligation.obligation_identity"""
        )
        results = []
        for row in cursor.fetchall():
            if not isinstance(row, Mapping):
                continue
            staff_id = _positive_id(row.get("staff_id"), "staff_id")
            name = _account(row.get("name")) or ""
            due_date = row.get("due_date")
            due_date_str = (
                due_date.isoformat()
                if hasattr(due_date, "isoformat")
                else (str(due_date) if due_date else None)
            )
            results.append(
                {
                    "staff_id": staff_id,
                    "name": name,
                    "case_no": str(row.get("case_no") or ""),
                    "obligation_identity": str(row.get("obligation_identity") or ""),
                    "amount_due_ntd": int(row.get("amount_due_ntd") or 0),
                    "due_date": due_date_str,
                }
            )
        return tuple(results)
    except Exception:
        return ()


def _all_client_names(cursor: Any) -> tuple[str, ...]:
    try:
        cursor.execute("SELECT DISTINCT name FROM clients WHERE name IS NOT NULL AND name <> ''")
        names = []
        for row in cursor.fetchall():
            if isinstance(row, Mapping) and row.get("name"):
                normalized = _account(row.get("name"))
                if normalized:
                    names.append(normalized)
        return tuple(sorted(set(names), key=len, reverse=True))
    except Exception:
        return ()


def _client_refund_name_candidates(cursor: Any) -> tuple[dict[str, Any], ...]:
    try:
        cursor.execute(
            """SELECT order_row.client_id, client.name, obligation.case_no,
                      obligation.obligation_identity, obligation.amount_due_ntd,
                      obligation.due_date
               FROM client_obligations obligation
               JOIN orders order_row ON order_row.case_no=obligation.case_no
               JOIN clients client ON client.id=order_row.client_id
               WHERE obligation.direction='payable_to_client'
                 AND obligation.status='open' AND obligation.amount_due_ntd>0
               ORDER BY order_row.client_id, obligation.obligation_identity"""
        )
        results = []
        for row in cursor.fetchall():
            if not isinstance(row, Mapping):
                continue
            client_id = _positive_id(row.get("client_id"), "client_id")
            name = _account(row.get("name")) or ""
            due_date = row.get("due_date")
            due_date_str = (
                due_date.isoformat()
                if hasattr(due_date, "isoformat")
                else (str(due_date) if due_date else None)
            )
            results.append(
                {
                    "client_id": client_id,
                    "name": name,
                    "case_no": str(row.get("case_no") or ""),
                    "obligation_identity": str(row.get("obligation_identity") or ""),
                    "amount_due_ntd": int(row.get("amount_due_ntd") or 0),
                    "due_date": due_date_str,
                }
            )
        return tuple(results)
    except Exception:
        return ()


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

"""
File: identity_maps.py
Description: 讀取銀行帳戶、既有案件虛擬帳號與服務人員／客戶候選，供財務流水分類使用。
"""

from __future__ import annotations

from collections.abc import Mapping
import unicodedata
from typing import Any

from domains.finance_import.cancellation_code import sinopac_memo_case_suffixes
from domains.finance_import.transaction_classifier import extract_name_from_row_text
from subsystems.client_finance.virtual_account_resolution import (
    build_effective_formula_account,
    resolve_client_virtual_account_suffix,
    uses_imported_case_virtual_account,
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
        """SELECT order_row.client_id, snapshot.bank_account AS refund_account_no,
                  obligation.status, obligation.amount_due_ntd
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           JOIN client_refund_recipient_snapshots snapshot
             ON snapshot.refund_obligation_identity=obligation.obligation_identity
            AND snapshot.case_no=obligation.case_no
           WHERE obligation.direction='payable_to_client'
             AND obligation.status<>'cancelled'
             AND obligation.obligation_type IN ('refund','adjustment')
           ORDER BY order_row.client_id, obligation.obligation_identity"""
    )
    refund_rows = cursor.fetchall()
    refund_candidates: dict[str, set[int]] = {}
    refund_identity_candidates: dict[str, set[int]] = {}
    for row in refund_rows:
        if not isinstance(row, Mapping):
            raise TypeError("cursor must return mapping rows")
        account = _account(row.get("refund_account_no"))
        if account is None:
            continue
        client_id = _positive_id(row.get("client_id"), "client_id")
        refund_identity_candidates.setdefault(account, set()).add(client_id)
        if row["status"] == "open" and int(row["amount_due_ntd"]) > 0:
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

    receipt_candidates = _client_receipt_candidates(cursor)
    known_virtual_accounts, known_case_suffixes, client_case_suffixes, case_suffixes = _known_case_virtual_accounts(cursor)

    cursor.execute(
        """SELECT obligation.case_no, obligation.staff_id
           FROM staff_obligations obligation
           WHERE obligation.direction='payable_to_staff'
             AND obligation.status<>'cancelled'
             AND obligation.amount_due_ntd>0
           ORDER BY obligation.staff_id, obligation.obligation_identity"""
    )
    staff_obligation_rows = cursor.fetchall()

    cursor.execute(
        """SELECT case_no, staff_id
           FROM orders
           WHERE staff_id IS NOT NULL AND status <> '訂單取消'"""
    )
    order_staff_rows = cursor.fetchall()

    cursor.execute(
        """SELECT case_no, staff_id
           FROM case_staff_assignments
           WHERE staff_id IS NOT NULL AND status IN ('planned','active','completed')"""
    )
    assignment_staff_rows = cursor.fetchall()

    all_staff_case_rows = list(staff_obligation_rows) + list(order_staff_rows) + list(assignment_staff_rows)

    cursor.execute(
        """SELECT obligation.case_no, order_row.client_id
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           WHERE obligation.direction='payable_to_client'
             AND obligation.status<>'cancelled'
             AND obligation.obligation_type IN ('refund','adjustment')
           ORDER BY order_row.client_id, obligation.obligation_identity"""
    )
    refund_obligation_rows = cursor.fetchall()

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

    staff_name_identities = _staff_name_identities(cursor)
    client_name_identities = load_client_name_identities(cursor)
    return {
        "client_refund_accounts": _stable_map(refund_candidates),
        "client_refund_identity_accounts": _stable_map(refund_identity_candidates),
        "client_subsidy_return_accounts": _stable_map(
            subsidy_return_candidates
        ),
        "staff_accounts": _stable_map(staff_candidates),
        "client_receipt_candidates": receipt_candidates,
        "staff_case_suffixes": _stable_map(staff_case_candidates),
        "client_refund_case_suffixes": _stable_map(refund_case_candidates),
        "all_client_names": tuple(client_name_identities),
        "client_name_identities": client_name_identities,
        "taishin_client_refund_candidates": _client_refund_name_candidates(cursor),
        "all_staff_names": tuple(name for name, identities in staff_name_identities.items() for _ in identities),
        "staff_name_identities": staff_name_identities,
        "staff_payout_candidates": _staff_payout_candidates(cursor),
        "known_virtual_accounts": known_virtual_accounts,
        "known_case_suffixes": known_case_suffixes,
        "client_case_suffixes": client_case_suffixes,
    }


def _known_case_virtual_accounts(
    cursor: Any,
) -> tuple[frozenset[str], frozenset[str], dict[str, list[int]], dict[str, str]]:
    cursor.execute("SELECT case_no,client_id FROM orders WHERE case_no IS NOT NULL")
    order_rows = tuple(cursor.fetchall())
    existing_cases = {
        str(row["case_no"])
        for row in order_rows
        if isinstance(row, Mapping) and row.get("case_no")
    }

    cursor.execute(
        "SELECT case_no, virtual_account FROM client_legacy_virtual_accounts "
        "WHERE case_no IS NOT NULL AND virtual_account IS NOT NULL"
    )
    legacy_rows = list(cursor.fetchall())

    va_to_cases: dict[str, set[str]] = {}
    imported_by_case: dict[str, set[str]] = {}
    for row in legacy_rows:
        if isinstance(row, Mapping) and row.get("case_no") and row.get("virtual_account"):
            case_no = str(row["case_no"])
            virtual_account = str(row["virtual_account"]).strip()
            if virtual_account and uses_imported_case_virtual_account(case_no):
                va_to_cases.setdefault(virtual_account, set()).add(case_no)
                imported_by_case.setdefault(case_no, set()).add(virtual_account)

    valid_virtual_accounts = {
        va for va, cases in va_to_cases.items()
        if len(cases) == 1 and len(imported_by_case[next(iter(cases))]) == 1
    }
    formula_to_cases: dict[str, set[str]] = {}
    for case_no in existing_cases:
        built = build_effective_formula_account(case_no)
        if built and built not in va_to_cases:
            formula_to_cases.setdefault(built, set()).add(case_no)
    valid_virtual_accounts.update(
        va for va, cases in formula_to_cases.items() if len(cases) == 1
    )
    known_suffixes = frozenset(
        va[-6:] for va in valid_virtual_accounts if len(va) >= 6
    )
    clients = {str(row['case_no']): row.get('client_id') for row in order_rows}
    suffix_clients: dict[str, set[int]] = {}
    case_suffixes: dict[str, str] = {}
    for account in valid_virtual_accounts:
        cases = va_to_cases.get(account) or formula_to_cases.get(account, set())
        for case in cases:
            case_suffixes[case] = account[-6:]
            if clients.get(case) is not None:
                suffix_clients.setdefault(account[-6:], set()).add(int(clients[case]))
    return frozenset(valid_virtual_accounts), known_suffixes, _stable_map(suffix_clients), case_suffixes


def _staff_name_identities(cursor: Any) -> dict[str, tuple[int, ...]]:
    cursor.execute("SELECT id,name FROM staff WHERE name IS NOT NULL AND name <> ''")
    names: dict[str, set[int]] = {}
    for row in cursor.fetchall():
        if isinstance(row, Mapping) and row.get("name"):
            normalized = _account(row.get("name"))
            if normalized:
                names.setdefault(normalized, set()).add(_positive_id(row["id"], "staff_id"))
    return {name: tuple(sorted(names[name])) for name in sorted(names, key=len, reverse=True)}


def _staff_payout_candidates(cursor: Any) -> tuple[dict[str, Any], ...]:
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


def load_client_name_identities(cursor: Any, *, lock=False) -> dict[str, tuple[int, ...]]:
    cursor.execute("SELECT id,name FROM clients WHERE name IS NOT NULL AND name <> ''" + (" FOR UPDATE" if lock else ""))
    names: dict[str, set[int]] = {}
    for row in cursor.fetchall():
        if isinstance(row, Mapping) and row.get("name"):
            normalized = _account(row.get("name"))
            if normalized:
                names.setdefault(normalized, set()).add(_positive_id(row["id"], "client_id"))
    return {name: tuple(sorted(names[name])) for name in sorted(names, key=len, reverse=True)}


def resolve_taishin_client_memo_case(cursor: Any, memo: str | None, names, *, lock=False, match_month=None) -> str | None:
    suffixes = sinopac_memo_case_suffixes(memo)
    if len(suffixes) > 1:
        return None
    name = extract_name_from_row_text({'memo': memo}, tuple(names))
    client_ids = names.get(name, ())
    if suffixes:
        resolution = resolve_client_virtual_account_suffix(cursor, next(iter(suffixes)))
        if resolution['result'] != 'resolved':
            return None
        case_no = resolution['case_no']
        if not client_ids:
            return case_no
        cursor.execute('SELECT client_id FROM orders WHERE case_no=%s' + (' FOR UPDATE' if lock else ''), (case_no,))
        return case_no if any(int(row['client_id']) in client_ids for row in cursor.fetchall()) else None
    if len(client_ids) > 1 and match_month is not None:
        return match_month(cursor, client_ids)
    if len(client_ids) != 1:
        return None
    cursor.execute('SELECT case_no FROM orders WHERE client_id=%s LIMIT 2' + (' FOR UPDATE' if lock else ''), client_ids)
    cases = cursor.fetchall()
    return str(cases[0]['case_no']) if len(cases) == 1 else None


def _client_refund_name_candidates(cursor: Any) -> tuple[dict[str, Any], ...]:
    cursor.execute(
        """SELECT order_row.client_id, client.name, obligation.case_no,
                  obligation.obligation_identity, obligation.obligation_type, obligation.amount_due_ntd,
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
                "obligation_type": row.get("obligation_type"),
                "amount_due_ntd": int(row.get("amount_due_ntd") or 0),
                "due_date": due_date_str,
            }
        )
    return tuple(results)


def _client_receipt_candidates(cursor: Any) -> tuple[dict[str, Any], ...]:
    cursor.execute(
        """SELECT order_row.client_id,client.name,beclass.refund_account_no,
                  obligation.amount_due_ntd
           FROM client_obligations obligation
           JOIN orders order_row ON order_row.case_no=obligation.case_no
           JOIN clients client ON client.id=order_row.client_id
           LEFT JOIN beclass_records beclass ON beclass.bound_case_no=order_row.case_no
               OR (beclass.bound_case_no IS NULL AND beclass.query_no=order_row.case_no)
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

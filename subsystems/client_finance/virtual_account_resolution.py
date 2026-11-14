"""Resolve a Client Finance virtual account to its canonical case identity."""

from __future__ import annotations

from typing import Any
import re

from domains.client_finance.virtual_account import allows_case_account_edit, allows_historical_non_citizen_account


_VIRTUAL_ACCOUNT_PREFIX = "99781699"
_VIRTUAL_ACCOUNT_PATTERN = re.compile(rf"^{_VIRTUAL_ACCOUNT_PREFIX}([0-9]{{3}})([0-9]{{3}})$")
_FIRST_FORMULA_YEAR = "116"


def build_client_virtual_account(case_no: object) -> str | None:
    """Build the per-case Client Finance collection account."""
    normalized = str(case_no) if case_no is not None else ""
    non_citizen = re.fullmatch(r"A([0-9]{3})([0-9]{3})", normalized)
    if non_citizen:
        year, case_sequence = non_citizen.groups()
        account_sequence = int(case_sequence) + 500
        if int(case_sequence) < 1 or account_sequence > 999:
            return None
        return f"{_VIRTUAL_ACCOUNT_PREFIX}{year}{account_sequence:03d}"
    if len(normalized) != 9 or not normalized.isascii() or not normalized.isdigit():
        return None
    sequence = int(normalized[3:])
    if sequence > 999:
        return None
    return f"{_VIRTUAL_ACCOUNT_PREFIX}{normalized[:3]}{sequence:03d}"


def uses_imported_case_virtual_account(case_no: object) -> bool:
    normalized = str(case_no) if case_no is not None else ""
    return re.fullmatch(r"[0-9]{9}", normalized) is not None and normalized[:3] < _FIRST_FORMULA_YEAR


def build_effective_formula_account(case_no: object, *, has_imported_account: bool = False) -> str | None:
    if uses_imported_case_virtual_account(case_no) or (has_imported_account and allows_historical_non_citizen_account(case_no)):
        return None
    return build_client_virtual_account(case_no)


def _imported_accounts(cursor: Any, case_no: str) -> set[str]:
    cursor.execute(
        "SELECT DISTINCT virtual_account FROM client_legacy_virtual_accounts "
        "WHERE case_no = %s ORDER BY virtual_account",
        (case_no,),
    )
    return {
        str(row.get("virtual_account") if isinstance(row, dict) else row[0])
        for row in cursor.fetchall()
    }


def resolve_case_virtual_account(cursor: Any, case_no: object) -> dict[str, str | None]:
    """Project the account source selected by the canonical case number."""
    normalized = str(case_no) if case_no is not None else ""
    imported = _imported_accounts(cursor, normalized) if allows_case_account_edit(normalized) else set()
    if len(imported) > 1:
        return {"result": "pending", "virtual_account": None, "reason": "imported_account_not_unique"}
    if imported:
        account = next(iter(imported))
        resolved = resolve_client_virtual_account(cursor, account)
        if resolved["case_no"] != normalized:
            return {"result": "pending", "virtual_account": None, "reason": "case_not_unique"}
        return {"result": "resolved", "virtual_account": account, "reason": None}
    if uses_imported_case_virtual_account(normalized):
        return {"result": "pending", "virtual_account": None, "reason": "imported_account_missing"}
    built = build_effective_formula_account(normalized)
    if built is None:
        return {"result": "pending", "virtual_account": None, "reason": "case_not_representable"}
    if resolve_client_virtual_account(cursor, built)["case_no"] != normalized:
        return {"result": "pending", "virtual_account": None, "reason": "case_not_unique"}
    return {"result": "resolved", "virtual_account": built, "reason": None}


def resolve_formula_case_virtual_account(cursor: Any, case_no: str) -> str | None:
    """Display the formula source independently from an imported account."""
    built = build_effective_formula_account(case_no)
    if built is None:
        return None
    resolved = _resolve_account(cursor, built, include_candidates=False, show_formula=True)
    return built if resolved["case_no"] == case_no else None


def _pending(reason: str) -> dict[str, str | None]:
    return {"result": "pending", "case_no": None, "reason": reason}


def resolve_client_virtual_account_suffix(cursor: Any, suffix: object, *, include_candidates=False) -> dict[str, Any]:
    """Use the canonical account resolver for a six-digit bank memo reference."""
    if not isinstance(suffix, str) or re.fullmatch(r"[0-9]{6}", suffix) is None:
        return _pending("invalid_virtual_account_format")
    account = _VIRTUAL_ACCOUNT_PREFIX + suffix
    if include_candidates:
        return resolve_client_virtual_account(cursor, account, include_candidates=True)
    return resolve_client_virtual_account(cursor, account)


def resolve_client_virtual_account(cursor: Any, cancellation_code: Any, *, include_candidates=False) -> dict[str, Any]:
    """Resolve imported mappings first; use the formula only when none exist."""
    return _resolve_account(cursor, cancellation_code, include_candidates=include_candidates, show_formula=False)


def resolve_imported_virtual_account(
    cursor: Any, account: str, *, include_candidates: bool = False,
) -> dict[str, Any] | None:
    """Resolve a canonical account from registered mappings alone."""
    cursor.execute(
        "SELECT CASE WHEN EXISTS (SELECT 1 FROM client_legacy_virtual_accounts other "
        "WHERE other.case_no=mapping.case_no AND other.virtual_account<>mapping.virtual_account) "
        "THEN NULL ELSE mapping.case_no END AS case_no "
        "FROM client_legacy_virtual_accounts mapping WHERE mapping.virtual_account = %s "
        "AND ((LENGTH(mapping.case_no)=9 AND mapping.case_no < '" + _FIRST_FORMULA_YEAR + "') "
        "OR (LENGTH(mapping.case_no)=7 AND SUBSTR(mapping.case_no,1,1)='A' "
        "AND SUBSTR(mapping.case_no,2,3) < '" + _FIRST_FORMULA_YEAR + "')) ORDER BY mapping.case_no",
        (account,),
    )
    imported_candidates = {
        row.get("case_no") if isinstance(row, dict) else row[0]
        for row in cursor.fetchall()
    }
    if imported_candidates:
        if None in imported_candidates or len(imported_candidates) != 1:
            pending = _pending("case_not_unique")
            if include_candidates:
                pending["candidate_cases"] = tuple(sorted(str(case) for case in imported_candidates if case is not None))
            return pending
        return {
            "result": "resolved",
            "case_no": str(next(iter(imported_candidates))),
            "reason": None,
        }
    return None


def _resolve_account(cursor: Any, cancellation_code: Any, *, include_candidates: bool, show_formula: bool) -> dict[str, Any]:
    if not isinstance(cancellation_code, str):
        return _pending("invalid_virtual_account_format")

    match = _VIRTUAL_ACCOUNT_PATTERN.fullmatch(cancellation_code)
    if match is None:
        return _pending("invalid_virtual_account_format")

    imported = resolve_imported_virtual_account(cursor, cancellation_code, include_candidates=include_candidates)
    if imported is not None:
        return imported
    roc_year, sequence = match.groups()
    generated_case_no = f"{roc_year}{int(sequence):06d}"
    formula_candidates = set()
    if not uses_imported_case_virtual_account(generated_case_no):
        formula_candidates.add(generated_case_no)
    if int(sequence) > 500:
        non_citizen_case_no = f"A{roc_year}{int(sequence) - 500:03d}"
        formula_candidates.add(non_citizen_case_no)
    if not formula_candidates:
        return _pending("case_not_found")
    if len(formula_candidates) == 2:
        cursor.execute("SELECT case_no FROM orders WHERE case_no IN (%s,%s)",
                       (generated_case_no, non_citizen_case_no))
    else:
        formula_case = next(iter(formula_candidates))
        query = "SELECT case_no FROM orders WHERE case_no = %s"
        if allows_historical_non_citizen_account(formula_case) and not show_formula:
            query += (
                " AND NOT EXISTS (SELECT 1 FROM client_legacy_virtual_accounts mapping"
                " WHERE mapping.case_no=orders.case_no)"
            )
        cursor.execute(query, (formula_case,))
    generated_matches = cursor.fetchall()
    candidates = {
        str(row.get("case_no") if isinstance(row, dict) else row[0])
        for row in generated_matches
        if str(row.get("case_no") if isinstance(row, dict) else row[0]) in formula_candidates
    }
    if not candidates:
        return _pending("case_not_found")
    if len(candidates) != 1:
        pending = _pending("case_not_unique")
        if include_candidates:
            pending["candidate_cases"] = tuple(sorted(candidates))
        return pending
    return {"result": "resolved", "case_no": next(iter(candidates)), "reason": None}


__all__ = [
    "build_client_virtual_account",
    "build_effective_formula_account",
    "resolve_case_virtual_account",
    "resolve_client_virtual_account",
    "resolve_client_virtual_account_suffix",
    "resolve_formula_case_virtual_account",
    "resolve_imported_virtual_account",
    "uses_imported_case_virtual_account",
]

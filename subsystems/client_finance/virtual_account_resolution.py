"""Resolve a Client Finance virtual account to its canonical case identity."""

from __future__ import annotations

from typing import Any
import re


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


def build_effective_formula_account(case_no: object) -> str | None:
    if uses_imported_case_virtual_account(case_no):
        return None
    return build_client_virtual_account(case_no)


def resolve_case_virtual_account(cursor: Any, case_no: object) -> dict[str, str | None]:
    """Project the account source selected by the canonical case number."""
    normalized = str(case_no) if case_no is not None else ""
    if not uses_imported_case_virtual_account(normalized):
        built = build_effective_formula_account(normalized)
        if built is None:
            return {"result": "pending", "virtual_account": None, "reason": "case_not_representable"}
        resolved = resolve_client_virtual_account(cursor, built)
        if resolved["case_no"] != normalized:
            return {"result": "pending", "virtual_account": None, "reason": "case_not_unique"}
        return {"result": "resolved", "virtual_account": built, "reason": None}
    cursor.execute(
        "SELECT DISTINCT virtual_account FROM client_legacy_virtual_accounts "
        "WHERE case_no = %s ORDER BY virtual_account",
        (normalized,),
    )
    imported = {
        str(row.get("virtual_account") if isinstance(row, dict) else row[0])
        for row in cursor.fetchall()
    }
    if len(imported) > 1:
        return {"result": "pending", "virtual_account": None, "reason": "imported_account_not_unique"}
    if imported:
        account = next(iter(imported))
        resolved = resolve_client_virtual_account(cursor, account)
        if resolved["case_no"] != normalized:
            return {"result": "pending", "virtual_account": None, "reason": "case_not_unique"}
        return {"result": "resolved", "virtual_account": account, "reason": None}
    return {"result": "pending", "virtual_account": None, "reason": "imported_account_missing"}


def _pending(reason: str) -> dict[str, str | None]:
    return {"result": "pending", "case_no": None, "reason": reason}


def resolve_client_virtual_account_suffix(cursor: Any, suffix: object) -> dict[str, str | None]:
    """Use the canonical account resolver for a six-digit bank memo reference."""
    if not isinstance(suffix, str) or re.fullmatch(r"[0-9]{6}", suffix) is None:
        return _pending("invalid_virtual_account_format")
    return resolve_client_virtual_account(cursor, _VIRTUAL_ACCOUNT_PREFIX + suffix)


def resolve_client_virtual_account(cursor: Any, cancellation_code: Any) -> dict[str, str | None]:
    """Resolve imported mappings first; use the formula only when none exist."""
    if not isinstance(cancellation_code, str):
        return _pending("invalid_virtual_account_format")

    match = _VIRTUAL_ACCOUNT_PATTERN.fullmatch(cancellation_code)
    if match is None:
        return _pending("invalid_virtual_account_format")

    roc_year, sequence = match.groups()
    generated_case_no = f"{roc_year}{int(sequence):06d}"
    assert len(generated_case_no) == 9 and generated_case_no.isascii() and generated_case_no.isdigit()
    cursor.execute(
        "SELECT CASE WHEN EXISTS (SELECT 1 FROM client_legacy_virtual_accounts other "
        "WHERE other.case_no=mapping.case_no AND other.virtual_account<>mapping.virtual_account) "
        "THEN NULL ELSE mapping.case_no END AS case_no "
        "FROM client_legacy_virtual_accounts mapping WHERE mapping.virtual_account = %s "
        "AND LENGTH(mapping.case_no)=9 AND mapping.case_no < '" + _FIRST_FORMULA_YEAR + "' ORDER BY mapping.case_no",
        (cancellation_code,),
    )
    imported_candidates = {
        row.get("case_no") if isinstance(row, dict) else row[0]
        for row in cursor.fetchall()
    }
    if imported_candidates:
        if None in imported_candidates or len(imported_candidates) != 1:
            return _pending("case_not_unique")
        return {
            "result": "resolved",
            "case_no": str(next(iter(imported_candidates))),
            "reason": None,
        }
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
        cursor.execute("SELECT case_no FROM orders WHERE case_no = %s", (next(iter(formula_candidates)),))
    generated_matches = cursor.fetchall()
    candidates = {
        str(row.get("case_no") if isinstance(row, dict) else row[0])
        for row in generated_matches
        if str(row.get("case_no") if isinstance(row, dict) else row[0]) in formula_candidates
    }
    if not candidates:
        return _pending("case_not_found")
    if len(candidates) != 1:
        return _pending("case_not_unique")
    return {"result": "resolved", "case_no": next(iter(candidates)), "reason": None}


__all__ = [
    "build_client_virtual_account",
    "build_effective_formula_account",
    "resolve_case_virtual_account",
    "resolve_client_virtual_account",
    "resolve_client_virtual_account_suffix",
    "uses_imported_case_virtual_account",
]

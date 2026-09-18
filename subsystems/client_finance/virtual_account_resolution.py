"""Resolve a Client Finance virtual account to its canonical case identity."""

from __future__ import annotations

from typing import Any
import re


_VIRTUAL_ACCOUNT_PATTERN = re.compile(r"^99781699([0-9]{3})([0-9]{3})$")


def build_client_virtual_account(case_no: object) -> str | None:
    """Build the per-case Client Finance collection account."""
    normalized = str(case_no) if case_no is not None else ""
    if len(normalized) != 9 or not normalized.isascii() or not normalized.isdigit():
        return None
    sequence = int(normalized[3:])
    if sequence > 999:
        return None
    return f"99781699{normalized[:3]}{sequence:03d}"


def resolve_case_virtual_account(cursor: Any, case_no: object) -> dict[str, str | None]:
    """Project one case account with imported mappings taking precedence."""
    normalized = str(case_no) if case_no is not None else ""
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
        return {"result": "resolved", "virtual_account": next(iter(imported)), "reason": None}
    built = build_client_virtual_account(normalized)
    if built is None:
        return {"result": "pending", "virtual_account": None, "reason": "case_not_representable"}
    return {"result": "resolved", "virtual_account": built, "reason": None}


def _pending(reason: str) -> dict[str, str | None]:
    return {"result": "pending", "case_no": None, "reason": reason}


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
        "SELECT case_no FROM client_legacy_virtual_accounts WHERE virtual_account = %s ORDER BY case_no",
        (cancellation_code,),
    )
    imported_candidates = {
        str(row.get("case_no") if isinstance(row, dict) else row[0])
        for row in cursor.fetchall()
    }
    if imported_candidates:
        if len(imported_candidates) != 1:
            return _pending("case_not_unique")
        return {
            "result": "resolved",
            "case_no": next(iter(imported_candidates)),
            "reason": None,
        }
    cursor.execute("SELECT case_no FROM orders WHERE case_no = %s", (generated_case_no,))
    generated_matches = cursor.fetchall()
    candidates = {
        str(row.get("case_no") if isinstance(row, dict) else row[0])
        for row in generated_matches
        if str(row.get("case_no") if isinstance(row, dict) else row[0]) == generated_case_no
    }
    if not candidates:
        return _pending("case_not_found")
    if len(candidates) != 1:
        return _pending("case_not_unique")
    return {"result": "resolved", "case_no": next(iter(candidates)), "reason": None}


__all__ = [
    "build_client_virtual_account",
    "resolve_case_virtual_account",
    "resolve_client_virtual_account",
]

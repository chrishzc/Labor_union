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


def _pending(reason: str) -> dict[str, str | None]:
    return {"result": "pending", "case_no": None, "reason": reason}


def resolve_client_virtual_account(cursor: Any, cancellation_code: Any) -> dict[str, str | None]:
    """Resolve a current or legacy account only when one distinct case exists."""
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
    candidates = {
        str(row.get("case_no") if isinstance(row, dict) else row[0])
        for row in cursor.fetchall()
    }
    cursor.execute("SELECT case_no FROM orders WHERE case_no = %s", (generated_case_no,))
    generated_matches = cursor.fetchall()
    candidates.update(
        str(row.get("case_no") if isinstance(row, dict) else row[0])
        for row in generated_matches
        if str(row.get("case_no") if isinstance(row, dict) else row[0]) == generated_case_no
    )
    if not candidates:
        return _pending("case_not_found")
    if len(candidates) != 1:
        return _pending("case_not_unique")
    return {"result": "resolved", "case_no": next(iter(candidates)), "reason": None}


__all__ = ["build_client_virtual_account", "resolve_client_virtual_account"]

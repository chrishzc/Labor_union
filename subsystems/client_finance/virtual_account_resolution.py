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
    """Resolve the embedded ROC-year and sequence only when one case exists."""
    if not isinstance(cancellation_code, str):
        return _pending("invalid_virtual_account_format")

    match = _VIRTUAL_ACCOUNT_PATTERN.fullmatch(cancellation_code)
    if match is None:
        return _pending("invalid_virtual_account_format")

    roc_year, sequence = match.groups()
    case_no = f"{roc_year}{int(sequence):06d}"
    assert len(case_no) == 9 and case_no.isascii() and case_no.isdigit()
    cursor.execute("SELECT case_no FROM orders WHERE case_no = %s", (case_no,))
    matches = cursor.fetchall()
    if not matches:
        return _pending("case_not_found")
    if len(matches) != 1:
        return _pending("case_not_unique")

    row = matches[0]
    stored_case_no = row.get("case_no") if isinstance(row, dict) else row[0]
    if str(stored_case_no) != case_no:
        return _pending("case_not_unique")
    return {"result": "resolved", "case_no": case_no, "reason": None}


__all__ = ["build_client_virtual_account", "resolve_client_virtual_account"]

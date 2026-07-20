"""Resolve a Sinopac client virtual account to one existing order."""

from __future__ import annotations

import re
from typing import Any


_VIRTUAL_ACCOUNT_PATTERN = re.compile(r"^99781699([0-9]{3})([0-9]{3})$")


def _pending(reason: str) -> dict[str, Any]:
    return {"result": "pending", "case_no": None, "reason": reason}


def resolve_client_virtual_account(cursor: Any, cancellation_code: str) -> dict[str, Any]:
    """Return the unique canonical case number encoded by a virtual account.

    The bank suffix consists of a three-digit ROC year and a three-digit
    sequence.  Canonical case numbers preserve the year and expand that
    sequence to six digits before the database lookup.
    """
    if not isinstance(cancellation_code, str):
        return _pending("invalid_virtual_account_format")

    match = _VIRTUAL_ACCOUNT_PATTERN.fullmatch(cancellation_code)
    if match is None:
        return _pending("invalid_virtual_account_format")

    roc_year, sequence = match.groups()
    case_no = f"{roc_year}{int(sequence):06d}"
    assert len(case_no) == 9 and case_no.isascii() and case_no.isdigit()

    cursor.execute(
        "SELECT case_no FROM orders WHERE case_no = %s",
        (case_no,),
    )
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

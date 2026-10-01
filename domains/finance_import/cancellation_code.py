"""Project complete Sinopac account references without changing bank facts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_VALID_CANCELLATION_CODE = re.compile(r"99781699[0-9]{6}")
_SINOPAC_ACCOUNT_REFERENCE = re.compile(r"([0-9]+)(?:\s*[^\W\d_][^\d]*)?")


def extract_sinopac_account_reference(value: object) -> str | None:
    """Accept one complete numeric account, optionally followed by a name."""
    if not isinstance(value, str):
        return None
    match = _SINOPAC_ACCOUNT_REFERENCE.fullmatch(value.strip())
    return match.group(1) if match is not None else None


def _valid_cancellation_code(value: object) -> str | None:
    if isinstance(value, str) and _VALID_CANCELLATION_CODE.fullmatch(value):
        return value
    return None


def resolve_finance_cancellation_code(row: Mapping[str, Any]) -> dict[str, str | None]:
    if row.get("format_id") == "sinopac":
        references = row.get("bank_references")
        account = extract_sinopac_account_reference(
            references.get("銷帳編號") if isinstance(references, Mapping) else None
        )
        code = _valid_cancellation_code(account)
        return {
            "cancellation_code": code,
            "source": "sinopac_bank_reference" if code is not None else "none",
        }
    canonical = row.get("cancellation_code")
    if row.get("format_id") == "legacy":
        canonical = extract_sinopac_account_reference(canonical)
    canonical_code = _valid_cancellation_code(canonical)
    if canonical_code is not None:
        return {"cancellation_code": canonical_code, "source": "canonical"}
    return {"cancellation_code": None, "source": "none"}


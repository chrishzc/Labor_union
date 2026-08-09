"""Resolve a validated finance cancellation code from normalized bank facts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_VALID_CANCELLATION_CODE = re.compile(r"99781699[0-9]{6}")


def _valid_cancellation_code(value: object) -> str | None:
    if isinstance(value, str) and _VALID_CANCELLATION_CODE.fullmatch(value):
        return value
    return None


def resolve_finance_cancellation_code(row: Mapping[str, Any]) -> dict[str, str | None]:
    canonical_code = _valid_cancellation_code(row.get("cancellation_code"))
    if canonical_code is not None:
        return {"cancellation_code": canonical_code, "source": "canonical"}
    bank_references = row.get("bank_references")
    if row.get("format_id") == "sinopac" and isinstance(bank_references, Mapping):
        fallback_code = _valid_cancellation_code(bank_references.get("銷帳編號"))
        if fallback_code is not None:
            return {"cancellation_code": fallback_code, "source": "sinopac_raw_fallback"}
    return {"cancellation_code": None, "source": "none"}


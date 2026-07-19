"""Stable cross-file fingerprints for normalized finance transactions."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import unicodedata
from typing import Any

from scripts.imports.finance_normalized_row import validate_normalized_row


_BANK_SOURCE = {
    "legacy": "sinopac",
    "sinopac": "sinopac",
    "taishin": "taishin",
}
_FINGERPRINT_FIELDS = (
    "bank_source",
    "source_bank_account",
    "transaction_date",
    "transaction_time",
    "direction",
    "debit",
    "credit",
    "balance",
    "summary",
    "memo",
    "cancellation_code",
)

assert len(_FINGERPRINT_FIELDS) == 11


def _text(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return " ".join(normalized.split())


def _amount(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0.00"
    return format(value, ".2f")


def build_dedup_fingerprint(normalized_row: dict[str, Any]) -> str:
    """Return a lowercase SHA-256 fingerprint of stable transaction fields."""
    row = validate_normalized_row(normalized_row)
    values = (
        _BANK_SOURCE[row["format_id"]],
        _text(row["source_bank_account"]),
        _text(row["transaction_date"]),
        _text(row["transaction_time"]),
        row["direction"],
        _amount(row["debit"]),
        _amount(row["credit"]),
        _amount(row["balance"]),
        _text(row["summary"]),
        _text(row["memo"]),
        _text(row["cancellation_code"]),
    )
    assert len(values) == len(_FINGERPRINT_FIELDS)
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

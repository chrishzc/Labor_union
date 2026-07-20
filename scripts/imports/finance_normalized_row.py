"""Validation contract for normalized finance statement rows."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
import math
import re
from typing import Any


REQUIRED_FIELDS = frozenset({
    "format_id",
    "source_file",
    "source_bank_account",
    "sheet_name",
    "source_row",
    "source_reference",
    "transaction_date",
    "transaction_time",
    "posting_date",
    "value_date",
    "debit",
    "credit",
    "direction",
    "balance",
    "currency",
    "summary",
    "memo",
    "counterparty_name",
    "counterparty_account",
    "cancellation_code",
    "bank_references",
    "warnings",
    "raw_payload",
})

FORMAT_IDS = frozenset({"legacy", "taishin", "sinopac"})
DIRECTIONS = frozenset({"incoming", "outgoing", "unknown"})
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_TIME_PATTERN = re.compile(r"\d{2}:\d{2}:\d{2}\Z")
_OPTIONAL_TEXT_FIELDS = (
    "source_bank_account",
    "currency",
    "summary",
    "memo",
    "counterparty_name",
    "counterparty_account",
    "cancellation_code",
)

assert len(REQUIRED_FIELDS) == 23 and "header_row" not in REQUIRED_FIELDS


def _is_optional_string(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value != "")


def _is_iso_date(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_iso_time(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not _TIME_PATTERN.fullmatch(value):
        return False
    try:
        return time.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _is_json_safe_scalar(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and math.isfinite(value)


def validate_normalized_row(row: dict) -> dict:
    """Validate one normalized bank row and return the original object unchanged."""
    if not isinstance(row, dict):
        raise ValueError("row: must be a dict")

    errors: list[str] = []
    fields = set(row)
    missing = sorted(REQUIRED_FIELDS - fields)
    unexpected = sorted(fields - REQUIRED_FIELDS)
    if missing:
        errors.append(f"fields: missing {', '.join(missing)}")
    if unexpected:
        errors.append(f"fields: unexpected {', '.join(unexpected)}")
    if missing:
        raise ValueError("normalized row validation failed: " + "; ".join(errors))

    if row["format_id"] not in FORMAT_IDS:
        errors.append("format_id: must be legacy, taishin, or sinopac")
    for field in ("source_file", "sheet_name"):
        if not isinstance(row[field], str) or not row[field]:
            errors.append(f"{field}: must be a non-empty string")
    if isinstance(row["source_row"], bool) or not isinstance(row["source_row"], int) or row["source_row"] < 1:
        errors.append("source_row: must be an Excel one-based integer")
    if row["source_reference"] is not None:
        errors.append("source_reference: must be None until bank reference priority is defined")

    for field in ("transaction_date", "posting_date", "value_date"):
        if not _is_iso_date(row[field]):
            errors.append(f"{field}: must be ISO YYYY-MM-DD or None")
    if not _is_iso_time(row["transaction_time"]):
        errors.append("transaction_time: must be ISO HH:MM:SS or None")

    for field in ("debit", "credit", "balance"):
        if row[field] is not None and not isinstance(row[field], Decimal):
            errors.append(f"{field}: must be Decimal or None")
    for field in _OPTIONAL_TEXT_FIELDS:
        if not _is_optional_string(row[field]):
            errors.append(f"{field}: must be a non-empty string or None")

    bank_references = row["bank_references"]
    if not isinstance(bank_references, dict):
        errors.append("bank_references: must be a dict")
    else:
        for key, value in bank_references.items():
            if not isinstance(key, str) or not key:
                errors.append("bank_references: keys must be non-empty strings")
                break
            if not _is_optional_string(value):
                errors.append(f"bank_references.{key}: must be a non-empty string or None")

    warnings = row["warnings"]
    if not isinstance(warnings, list) or any(not isinstance(item, str) or not item for item in warnings):
        errors.append("warnings: must be an array of non-empty strings")
        warning_set: set[str] = set()
    else:
        warning_set = set(warnings)
        if len(warning_set) != len(warnings):
            errors.append("warnings: values must not be duplicated")

    raw_payload = row["raw_payload"]
    if not isinstance(raw_payload, dict):
        errors.append("raw_payload: must be a dict")
    else:
        for key, value in raw_payload.items():
            if not isinstance(key, str):
                errors.append("raw_payload: keys must use original string headers")
                break
            if not _is_json_safe_scalar(value):
                errors.append(f"raw_payload.{key}: must be a JSON-safe scalar")

    direction = row["direction"]
    if direction not in DIRECTIONS:
        errors.append("direction: must be incoming, outgoing, or unknown")
    debit = row["debit"]
    credit = row["credit"]
    if (debit is None or isinstance(debit, Decimal)) and (credit is None or isinstance(credit, Decimal)):
        debit_positive = debit is not None and debit > 0
        credit_positive = credit is not None and credit > 0
        if debit_positive ^ credit_positive:
            expected_direction = "outgoing" if debit_positive else "incoming"
            if direction != expected_direction:
                errors.append(f"direction: must be {expected_direction} for the positive amount side")
        else:
            required_warning = "direction_ambiguous" if debit_positive and credit_positive else "direction_missing"
            if direction != "unknown":
                errors.append("direction: must be unknown unless exactly one amount side is positive")
            if required_warning not in warning_set:
                errors.append(f"warnings: must include {required_warning}")

    if errors:
        raise ValueError("normalized row validation failed: " + "; ".join(errors))
    return row

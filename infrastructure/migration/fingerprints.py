"""Deterministic database row fingerprints."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Any


def fingerprint_full_rows(
    columns: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> str:
    canonical_columns = tuple(columns)
    _validate_columns(canonical_columns)
    row_digests = sorted(
        hashlib.sha256(_canonical_row(canonical_columns, row)).digest()
        for row in rows
    )
    digest = hashlib.sha256()
    digest.update(_length_prefixed(_canonical_json(canonical_columns)))
    for row_digest in row_digests:
        digest.update(_length_prefixed(row_digest))
    return digest.hexdigest()


def _validate_columns(columns: tuple[str, ...]) -> None:
    if not columns:
        raise ValueError("full-row fingerprint requires columns")
    if len(columns) != len(set(columns)):
        raise ValueError("full-row fingerprint columns must be unique")
    if any(not isinstance(column, str) or not column for column in columns):
        raise ValueError("full-row fingerprint columns must be non-empty text")


def _canonical_row(
    columns: tuple[str, ...],
    row: Mapping[str, Any],
) -> bytes:
    if set(row) != set(columns):
        raise ValueError("row shape does not match fingerprint columns")
    return _canonical_json([_canonical_value(row[column]) for column in columns])


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.hex()}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, timedelta):
        return {
            "type": "timedelta",
            "value": _timedelta_microseconds(value),
        }
    if isinstance(value, (date, datetime, time)):
        return {"type": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, float):
        return {"type": "float", "value": value.hex()}
    raise TypeError(f"unsupported fingerprint value: {type(value).__name__}")


def _timedelta_microseconds(value: timedelta) -> int:
    seconds_per_day = 86_400
    microseconds_per_second = 1_000_000
    return (
        value.days * seconds_per_day * microseconds_per_second
        + value.seconds * microseconds_per_second
        + value.microseconds
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _length_prefixed(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value

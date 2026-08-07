"""Small validation helpers for immutable shared-kernel values."""

from __future__ import annotations

from typing import Any

_SHA256_HEX_LENGTH = 64


def require_canonical_text(value: Any, field_name: str, maximum_length: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be canonical non-empty text")
    if len(value) > maximum_length:
        raise ValueError(f"{field_name} exceeds maximum length")
    return value


def require_nonnegative_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return value


def require_positive_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def require_sha256_hex(value: Any, field_name: str) -> str:
    value = require_canonical_text(value, field_name, _SHA256_HEX_LENGTH)
    if len(value) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be lowercase SHA-256 hex")
    return value

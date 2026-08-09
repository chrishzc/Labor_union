"""Canonical bounded JSON helpers for LINE domain payloads."""

from __future__ import annotations

import json
from typing import Mapping

from shared_kernel.validation import require_canonical_text

LINE_PAYLOAD_MAXIMUM_LENGTH = 65_535


def canonical_line_payload_json(payload: Mapping[str, object]) -> str:
    if not isinstance(payload, Mapping):
        raise TypeError("LINE payload must be a mapping")
    canonical = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    validate_canonical_line_payload_json(canonical)
    return canonical


def validate_canonical_line_payload_json(payload_json: str) -> None:
    require_canonical_text(
        payload_json,
        "LINE payload JSON",
        LINE_PAYLOAD_MAXIMUM_LENGTH,
    )
    parsed = json.loads(payload_json, parse_constant=_reject_json_constant)
    if not isinstance(parsed, dict):
        raise ValueError("LINE payload JSON must be an object")
    if canonical_line_payload_json_without_validation(parsed) != payload_json:
        raise ValueError("LINE payload JSON must be canonical")


def canonical_line_payload_json_without_validation(
    payload: Mapping[str, object],
) -> str:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"LINE payload JSON contains unsupported constant {value}")


__all__ = [
    "LINE_PAYLOAD_MAXIMUM_LENGTH",
    "canonical_line_payload_json",
    "validate_canonical_line_payload_json",
]

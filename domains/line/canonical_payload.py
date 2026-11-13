"""Canonical bounded JSON helpers for LINE domain payloads."""

from __future__ import annotations

import json
from typing import Mapping

from shared_kernel.validation import require_canonical_text

LINE_PAYLOAD_MAXIMUM_LENGTH = 65_535
LINE_CONFIRMATION_WITH_RESUMES_MAXIMUM_LENGTH = 5_500_000


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
        LINE_CONFIRMATION_WITH_RESUMES_MAXIMUM_LENGTH,
    )
    parsed = json.loads(payload_json, parse_constant=_reject_json_constant)
    if not isinstance(parsed, dict):
        raise ValueError("LINE payload JSON must be an object")
    if canonical_line_payload_json_without_validation(parsed) != payload_json:
        raise ValueError("LINE payload JSON must be canonical")
    if len(payload_json) > LINE_PAYLOAD_MAXIMUM_LENGTH:
        # Only the private PNG bytes are exempt from the normal message cap.
        documents = parsed.get("_table_documents")
        pictures = documents[3:] if isinstance(documents, list) else ()
        if (
            parsed.get("type") == "flex"
            and 1 <= len(pictures) <= 4
            and all(isinstance(item, dict) and set(item) == {"url", "png"}
                    and isinstance(item["url"], str) and len(item["url"]) <= 2000
                    and isinstance(item["png"], str) and len(item["png"]) <= 1_333_336
                    for item in pictures)
        ):
            payload_json = canonical_line_payload_json_without_validation({
                **parsed, "_table_documents": documents[:3],
            })
        require_canonical_text(payload_json, "LINE payload JSON", LINE_PAYLOAD_MAXIMUM_LENGTH)


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

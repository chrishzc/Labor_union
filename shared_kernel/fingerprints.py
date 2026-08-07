"""Deterministic canonical payload fingerprints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from shared_kernel.validation import require_sha256_hex


@dataclass(frozen=True, slots=True)
class PreviewFingerprint:
    value: str

    def __post_init__(self) -> None:
        require_sha256_hex(self.value, "preview fingerprint")


def _normalize_mapping(value: Mapping[Any, Any], path: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{path} keys must be strings")
        normalized[key] = _normalize_payload(item, f"{path}.{key}")
    return normalized


def _normalize_sequence(value: Sequence[Any], path: str) -> list[Any]:
    return [
        _normalize_payload(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _normalize_payload(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return _normalize_mapping(value, path)
    if isinstance(value, (list, tuple)):
        return _normalize_sequence(value, path)
    raise TypeError(f"{path} contains a non-canonical value")


def fingerprint_payload(payload: Mapping[str, Any]) -> PreviewFingerprint:
    normalized = _normalize_mapping(payload, "payload")
    canonical_json = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return PreviewFingerprint(digest)

"""
File: staff_historical_adoption.py
Description: 依歷史報名時間決定 Staff 可更新 scalar 覆寫或保守補值與衝突欄位。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


PROTECTED_STAFF_FIELDS = frozenset(
    {"id", "identity_card", "line_user_id", "status", "created_at", "updated_at", "has_massage_cert", "care_babies"}
)
_SOURCE_SNAPSHOT_TIME_FIELD = "registered_at"


@dataclass(frozen=True, slots=True)
class StaffScalarMerge:
    patch: Mapping[str, object]
    conflict_fields: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint
    source_is_newer: bool


def plan_staff_scalar_merge(existing: Mapping[str, object], historical: Mapping[str, object]) -> StaffScalarMerge:
    source_is_newer = _source_snapshot_is_newer(existing, historical)
    patch: dict[str, object] = {}
    conflicts: list[str] = []
    for field, incoming in historical.items():
        if field in PROTECTED_STAFF_FIELDS or _blank(incoming):
            continue
        if field == _SOURCE_SNAPSHOT_TIME_FIELD and not source_is_newer:
            _fill_blank_field(existing, patch, field, incoming)
            continue
        current = existing.get(field)
        if source_is_newer and _canonical(current) != _canonical(incoming):
            patch[field] = incoming
            continue
        if _blank(current):
            patch[field] = incoming
            continue
        if _canonical(current) != _canonical(incoming):
            conflicts.append(field)
    preview = fingerprint_payload(
        {
            "existing": {field: _canonical(existing.get(field)) for field in sorted(historical)},
            "historical": {field: _canonical(value) for field, value in sorted(historical.items())},
        }
    )
    return StaffScalarMerge(
        patch,
        tuple(sorted(conflicts)),
        preview,
        source_is_newer,
    )


def _fill_blank_field(existing, patch, field, incoming) -> None:
    if _blank(existing.get(field)):
        patch[field] = incoming


def _source_snapshot_is_newer(existing, historical) -> bool:
    current = _timestamp(existing.get(_SOURCE_SNAPSHOT_TIME_FIELD))
    incoming = _timestamp(historical.get(_SOURCE_SNAPSHOT_TIME_FIELD))
    return current is not None and incoming is not None and incoming > current


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _canonical(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.strip() if isinstance(value, str) else value


__all__ = ["PROTECTED_STAFF_FIELDS", "StaffScalarMerge", "plan_staff_scalar_merge"]

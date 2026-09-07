"""Pure contract for Staff's six canonical case-preference relations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_positive_integer

RelationKey = Literal[
    "service_regions",
    "service_periods",
    "cooking_skills",
    "holiday_availability",
    "rest_schedule",
    "baby_types",
]

RELATION_KEYS: tuple[RelationKey, ...] = (
    "service_regions", "service_periods", "cooking_skills",
    "holiday_availability", "rest_schedule", "baby_types",
)
RELATION_SPECS: dict[RelationKey, tuple[str, str, str]] = {
    "service_regions": ("staff_regions", "region_name", "custom_region_detail"),
    "service_periods": ("staff_time_slots", "slot_name", "custom_slot_detail"),
    "cooking_skills": ("staff_cooking_skills", "skill_name", "custom_skill_detail"),
    "holiday_availability": ("staff_holiday_availability", "holiday_name", "custom_holiday_detail"),
    "rest_schedule": ("staff_weekly_rest", "rest_type", "custom_rest_detail"),
    "baby_types": ("staff_baby_types", "baby_type", "custom_baby_detail"),
}

# Transportation is a seventh canonical fact and remains read-only/source_not_ready.
READ_ONLY_RELATION_SPECS = {
    "transportation": ("staff_transportation", "vehicle_type", None),
}
ALL_RELATION_KEYS = (*RELATION_KEYS, "transportation")


class CasePreferenceManualError(ValueError):
    """A six-relation manual contract cannot be formed."""


@dataclass(frozen=True, slots=True)
class RelationValue:
    value: str
    detail: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.value, "relation value", 50)
        if self.detail is not None:
            require_canonical_text(self.detail, "relation detail", 100)

    def canonical_payload(self) -> dict[str, str | None]:
        return {"value": self.value, "detail": self.detail}


Relations = dict[RelationKey, tuple[RelationValue, ...]]


@dataclass(frozen=True, slots=True)
class CasePreferenceManualSnapshot:
    staff_id: int
    relations: Relations
    snapshot_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class CasePreferenceManualPreview:
    staff_id: int
    before: Relations
    after: Relations
    snapshot_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint


def normalize_relations(raw: Mapping[str, Sequence[object]]) -> Relations:
    if not isinstance(raw, Mapping) or set(raw) != set(RELATION_KEYS):
        raise CasePreferenceManualError("staff_case_preference_relation_keys_invalid")
    result: Relations = {}
    for key in RELATION_KEYS:
        values = raw[key]
        if not isinstance(values, (list, tuple)):
            raise CasePreferenceManualError("staff_case_preference_relation_values_invalid")
        parsed: list[RelationValue] = []
        seen: set[str] = set()
        for item in values:
            if isinstance(item, RelationValue):
                candidate = item
            elif isinstance(item, Mapping):
                value = item.get("value")
                detail = item.get("detail")
                if not isinstance(value, str) or (detail is not None and not isinstance(detail, str)):
                    raise CasePreferenceManualError("staff_case_preference_relation_value_invalid")
                candidate = RelationValue(value.strip(), None if detail is None else detail.strip() or None)
            else:
                raise CasePreferenceManualError("staff_case_preference_relation_value_invalid")
            if candidate.value in seen:
                raise CasePreferenceManualError("staff_case_preference_relation_duplicate")
            seen.add(candidate.value)
            parsed.append(candidate)
        result[key] = tuple(sorted(parsed, key=lambda item: (item.value, item.detail or "")))
    return result


def snapshot_fingerprint(staff_id: int, relations: Relations) -> PreviewFingerprint:
    require_positive_integer(staff_id, "staff_id")
    return fingerprint_payload({"staff_id": staff_id, "relations": _relations_payload(relations)})


def preview_fingerprint(staff_id: int, before: Relations, after: Relations, snapshot: PreviewFingerprint) -> PreviewFingerprint:
    return fingerprint_payload({
        "staff_id": staff_id,
        "before": _relations_payload(before),
        "after": _relations_payload(after),
        "snapshot_fingerprint": snapshot.value,
    })


def _relations_payload(relations: Relations) -> dict[str, list[dict[str, str | None]]]:
    return {key: [item.canonical_payload() for item in relations[key]] for key in RELATION_KEYS}


__all__ = [
    "ALL_RELATION_KEYS", "CasePreferenceManualError", "CasePreferenceManualPreview",
    "CasePreferenceManualSnapshot", "READ_ONLY_RELATION_SPECS", "RELATION_KEYS",
    "RELATION_SPECS", "RelationKey", "RelationValue", "Relations",
    "normalize_relations", "preview_fingerprint", "snapshot_fingerprint",
]

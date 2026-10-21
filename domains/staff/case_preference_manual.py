"""Pure contract for Staff's six canonical case-preference relations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
import re

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

# Staff-owned manual choices. Regions are Hsinchu City's three districts and
# Hsinchu County's thirteen townships/cities; unchanged imported facts stay valid.
RELATION_OPTIONS: dict[RelationKey, tuple[str, ...]] = {
    "service_regions": ("東區", "北區", "香山區", "竹北市", "竹東鎮", "新埔鎮", "關西鎮", "湖口鄉", "新豐鄉", "芎林鄉", "橫山鄉", "北埔鄉", "寶山鄉", "峨眉鄉", "尖石鄉", "五峰鄉"),
    "service_periods": ("4小時", "8小時", "24小時"),
    "cooking_skills": ("葷食", "素食", "其他"),
    "holiday_availability": ("年節農曆過年初一", "年節農曆過年初二", "年節農曆過年初三", "端午節", "中秋節", "國定假日必休", "其他"),
    "rest_schedule": ("週休一日", "週休二日", "連續服務"),
    "baby_types": ("單胞胎", "雙胞胎", "其他"),
}
RELATION_OPTIONS = {key: tuple(value for value in values if value != "其他") for key, values in RELATION_OPTIONS.items()}


def canonical_service_period(hours: int, start: str, end: str, end_day_offset: int) -> str:
    """Staff slot identity carries its exact, validated window, never a note."""
    if type(hours) is not int or hours not in (4, 8, 24):
        raise CasePreferenceManualError("staff_case_preference_service_hours_invalid")
    if start is None or end is None or end_day_offset is None:
        raise CasePreferenceManualError("staff_case_preference_time_required")
    if type(end_day_offset) is not int or end_day_offset not in (0, 1):
        raise CasePreferenceManualError("staff_case_preference_time_invalid")
    def minutes(value):
        if not isinstance(value, str) or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value) is None:
            raise CasePreferenceManualError("staff_case_preference_time_invalid")
        hour, minute = value.split(":")
        return int(hour) * 60 + int(minute)
    span = minutes(end) + end_day_offset * 1440 - minutes(start)
    required = hours * 60 + (30 if hours == 8 else 0)
    if span != required:
        raise CasePreferenceManualError("staff_case_preference_time_duration_mismatch")
    return f"{hours}小時({start}-{'次日' if end_day_offset else ''}{end})"


def service_period_fields(value: str, detail: str | None = None) -> dict[str, object]:
    """Project the Staff slot fact into typed clock fields for its consumers."""
    fields = {"service_hours": None, "start_time": None, "end_time": None, "end_day_offset": None}
    match = re.fullmatch(r"(4|8|24)小時\(([0-9]{2}:[0-9]{2})-(次日)?([0-9]{2}:[0-9]{2})\)", value)
    if match:
        hours, start, next_day, end = match.groups()
        offset = int(bool(next_day))
        try:
            canonical_service_period(int(hours), start, end, offset)
        except CasePreferenceManualError:
            return fields
        return {"service_hours": int(hours), "start_time": start, "end_time": end, "end_day_offset": offset}
    legacy = {"4小時(上午8:30-12:30)": ("08:30", "12:30"), "4小時(下午13:00-17:00)": ("13:00", "17:00")}
    if value in legacy:
        start, end = legacy[value]
        return {"service_hours": 4, "start_time": start, "end_time": end, "end_day_offset": 0}
    text = detail if value == "其他" else value
    hours = re.fullmatch(r"([1-9][0-9]*)小時", text or "")
    if hours and int(hours.group(1)) <= 24:
        fields["service_hours"] = int(hours.group(1))
    return fields


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
                if key == "service_periods" and any(item.get(field) is not None for field in ("start_time", "end_time", "end_day_offset")):
                    proposed_window = {field: item.get(field) for field in ("service_hours", "start_time", "end_time", "end_day_offset")}
                    if service_period_fields(value, detail) != proposed_window:
                        value = canonical_service_period(item.get("service_hours"), item.get("start_time"), item.get("end_time"), item.get("end_day_offset"))
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


def validate_proposed_relations(before: Relations, after: Relations) -> None:
    """Check new selections; preserve existing legacy facts without rewriting them."""
    if before["service_periods"] != after["service_periods"]:
        windows = set()
        for item in after["service_periods"]:
            fields = service_period_fields(item.value)
            if fields["start_time"] is not None:
                identity = tuple(fields.values())
                if identity in windows:
                    raise CasePreferenceManualError("staff_case_preference_relation_duplicate")
                windows.add(identity)
    for key in RELATION_KEYS:
        current_values = {item.value for item in before[key]}
        current_details = {item.value: item.detail for item in before[key]}
        for item in after[key]:
            if item in before[key]:
                continue
            if item.detail is not None:
                raise CasePreferenceManualError("staff_case_preference_detail_not_editable")
            if item.value in current_details and current_details[item.value] != item.detail:
                raise CasePreferenceManualError("staff_case_preference_detail_not_editable")
            if key == "service_periods":
                if service_period_fields(item.value)["start_time"] is None:
                    raise CasePreferenceManualError("staff_case_preference_time_required")
                continue
            if item.value not in RELATION_OPTIONS[key] and item.value not in current_values:
                raise CasePreferenceManualError("staff_case_preference_option_invalid")


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
    "RELATION_OPTIONS", "validate_proposed_relations",
    "canonical_service_period", "service_period_fields",
]

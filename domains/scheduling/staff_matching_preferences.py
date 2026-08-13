"""Scheduling-owned staff matching preference rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class PreferenceValueKind(str, Enum):
    INTEGER_RANGE = "integer_range"
    INTEGER_SET = "integer_set"


class PreferenceComparisonOperator(str, Enum):
    RANGE_WITH_TOLERANCE = "range_with_tolerance"
    CONTAINS_INTEGER = "contains_integer"


@dataclass(frozen=True, slots=True)
class StaffPreferenceDefinition:
    preference_key: str
    display_name: str
    value_kind: PreferenceValueKind
    is_filterable: bool
    order_fact_key: str | None
    comparison_operator: PreferenceComparisonOperator | None
    active: bool = True

    def __post_init__(self) -> None:
        _require_key(self.preference_key)
        _require_text(self.display_name, "display_name", 100)
        _validate_filter_semantics(self)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "active": self.active,
            "comparison_operator": _enum_value(self.comparison_operator),
            "display_name": self.display_name,
            "is_filterable": self.is_filterable,
            "order_fact_key": self.order_fact_key,
            "preference_key": self.preference_key,
            "value_kind": self.value_kind.value,
        }


@dataclass(frozen=True, slots=True)
class IntegerRangePreference:
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        _require_positive_integer(self.minimum, "minimum")
        _require_positive_integer(self.maximum, "maximum")
        if self.minimum > self.maximum:
            raise ValueError("preference_range_invalid")

    def canonical_payload(self) -> dict[str, object]:
        return {"maximum": self.maximum, "minimum": self.minimum}


@dataclass(frozen=True, slots=True)
class IntegerSetPreference:
    values: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("preference_integer_set_required")
        for value in self.values:
            _require_positive_integer(value, "values")
        if self.values != tuple(sorted(set(self.values))):
            raise ValueError("preference_integer_set_not_canonical")

    def canonical_payload(self) -> dict[str, object]:
        return {"values": list(self.values)}


PreferenceValue = IntegerRangePreference | IntegerSetPreference


def parse_preference_value(
    definition: StaffPreferenceDefinition,
    payload: Mapping[str, Any],
) -> PreferenceValue:
    if definition.value_kind is PreferenceValueKind.INTEGER_RANGE:
        _require_exact_keys(payload, {"maximum", "minimum"})
        return IntegerRangePreference(payload["minimum"], payload["maximum"])
    _require_exact_keys(payload, {"values"})
    raw_values = payload["values"]
    if not isinstance(raw_values, list):
        raise ValueError("preference_integer_set_invalid")
    return IntegerSetPreference(tuple(raw_values))


def preference_matches(
    definition: StaffPreferenceDefinition,
    value: PreferenceValue,
    required_integer: int,
    *,
    tolerance: int = 0,
) -> bool:
    _require_positive_integer(required_integer, "required_integer")
    _require_nonnegative_integer(tolerance, "tolerance")
    if definition.comparison_operator is PreferenceComparisonOperator.RANGE_WITH_TOLERANCE:
        if not isinstance(value, IntegerRangePreference):
            raise ValueError("preference_value_kind_mismatch")
        return value.minimum - tolerance <= required_integer <= value.maximum + tolerance
    if definition.comparison_operator is PreferenceComparisonOperator.CONTAINS_INTEGER:
        if not isinstance(value, IntegerSetPreference):
            raise ValueError("preference_value_kind_mismatch")
        return required_integer in value.values
    raise ValueError("preference_not_filterable")


def _validate_filter_semantics(definition: StaffPreferenceDefinition) -> None:
    if not definition.is_filterable:
        if definition.order_fact_key is not None or definition.comparison_operator is not None:
            raise ValueError("non_filterable_preference_has_filter_semantics")
        return
    _require_text(definition.order_fact_key, "order_fact_key", 64)
    expected = {
        PreferenceValueKind.INTEGER_RANGE: PreferenceComparisonOperator.RANGE_WITH_TOLERANCE,
        PreferenceValueKind.INTEGER_SET: PreferenceComparisonOperator.CONTAINS_INTEGER,
    }[definition.value_kind]
    if definition.comparison_operator is not expected:
        raise ValueError("preference_comparison_operator_invalid")
    supported = {
        (
            PreferenceValueKind.INTEGER_RANGE,
            "service_days",
            PreferenceComparisonOperator.RANGE_WITH_TOLERANCE,
        ),
        (
            PreferenceValueKind.INTEGER_SET,
            "service_hours_per_day",
            PreferenceComparisonOperator.CONTAINS_INTEGER,
        ),
    }
    semantics = (
        definition.value_kind,
        definition.order_fact_key,
        definition.comparison_operator,
    )
    if semantics not in supported:
        raise ValueError("preference_filter_semantics_unsupported")


def _require_key(value: Any) -> None:
    text = _require_text(value, "preference_key", 64)
    if not text.replace("_", "").isalnum() or text.lower() != text:
        raise ValueError("preference_key_invalid")


def _require_text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{field}_invalid")
    return value.strip()


def _require_positive_integer(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field}_invalid")


def _require_nonnegative_integer(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field}_invalid")


def _require_exact_keys(payload: Mapping[str, Any], expected: set[str]) -> None:
    if set(payload) != expected:
        raise ValueError("preference_value_shape_invalid")


def _enum_value(value: Enum | None) -> str | None:
    return None if value is None else str(value.value)


SYSTEM_PREFERENCE_DEFINITIONS = (
    StaffPreferenceDefinition(
        "preferred_service_days",
        "希望服務天數",
        PreferenceValueKind.INTEGER_RANGE,
        True,
        "service_days",
        PreferenceComparisonOperator.RANGE_WITH_TOLERANCE,
    ),
    StaffPreferenceDefinition(
        "daily_service_hours",
        "每日服務時數",
        PreferenceValueKind.INTEGER_SET,
        True,
        "service_hours_per_day",
        PreferenceComparisonOperator.CONTAINS_INTEGER,
    ),
)

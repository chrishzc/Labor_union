"""Allowlisted, typed predicates for the read-only client roster."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Literal


RegistryFilterField = Literal[
    "case_no", "name", "phone", "district", "multi_birth_count", "order_status",
    "service_type", "requires_cooking", "service_days", "planned_start_date",
    "deposit_due_date", "first_due_date", "second_due_date",
    "subsidy_return_due_date", "staff_payment_due_date",
]
FIELD_KINDS = {
    "case_no": "text", "name": "text", "phone": "text", "district": "text",
    "multi_birth_count": "text", "order_status": "text", "service_type": "text",
    "requires_cooking": "boolean", "service_days": "number",
    "planned_start_date": "date", "deposit_due_date": "date", "first_due_date": "date",
    "second_due_date": "date", "subsidy_return_due_date": "date",
    "staff_payment_due_date": "date",
}
RegistryFilterOperator = Literal["in", "not_in", "contains", "starts_with", "equals", "gt", "lt", "between", "blank"]


@dataclass(frozen=True, slots=True)
class RegistryColumnFilter:
    field: RegistryFilterField
    operator: RegistryFilterOperator
    values: tuple[str | None, ...] = ()


@dataclass(frozen=True, slots=True)
class RegistryFilterOptions:
    values: tuple[str | None, ...]
    next_offset: int | None


def normalize_column_filters(filters: tuple[RegistryColumnFilter, ...]) -> tuple[RegistryColumnFilter, ...]:
    if len(filters) > len(FIELD_KINDS):
        raise ValueError("client_registry_column_filters_invalid")
    seen = set()
    for predicate in filters:
        kind = FIELD_KINDS.get(predicate.field)
        if kind is None or predicate.field in seen:
            raise ValueError("client_registry_filter_field_invalid")
        seen.add(predicate.field)
        allowed = {"in", "not_in", "equals", "blank"}
        allowed |= {"contains", "starts_with"} if kind == "text" else set()
        allowed |= {"gt", "lt", "between"} if kind in {"number", "date"} else set()
        if predicate.operator not in allowed:
            raise ValueError("client_registry_filter_operator_invalid")
        values = predicate.values
        if len(values) > 200 or (predicate.operator == "blank" and values):
            raise ValueError("client_registry_filter_values_invalid")
        if predicate.operator not in {"in", "not_in", "blank"}:
            if len(values) != (2 if predicate.operator == "between" else 1) or None in values:
                raise ValueError("client_registry_filter_values_invalid")
        for value in values:
            if value is None:
                continue
            if not isinstance(value, str) or not value or len(value) > 100:
                raise ValueError("client_registry_filter_values_invalid")
            if kind == "boolean" and value not in {"true", "false"}:
                raise ValueError("client_registry_filter_values_invalid")
            if kind == "number" and (not value.isascii() or not value.isdecimal() or int(value) < 1):
                raise ValueError("client_registry_filter_values_invalid")
            if kind == "date":
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError
                except ValueError as error:
                    raise ValueError("client_registry_filter_values_invalid") from error
        if predicate.operator == "between":
            lower, upper = values
            reversed_range = int(lower) > int(upper) if kind == "number" else lower > upper
            if reversed_range:
                raise ValueError("client_registry_filter_range_invalid")
    return filters


def parse_column_filters(payload: str | None) -> tuple[RegistryColumnFilter, ...]:
    if payload is None:
        return ()
    try:
        raw = json.loads(payload)
        if not isinstance(raw, list) or len(raw) > len(FIELD_KINDS):
            raise ValueError
        predicates = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"field", "operator", "values"}:
                raise ValueError
            if not isinstance(item["field"], str) or not isinstance(item["operator"], str) or not isinstance(item["values"], list):
                raise ValueError
            predicates.append(RegistryColumnFilter(item["field"], item["operator"], tuple(item["values"])))
        return normalize_column_filters(tuple(predicates))
    except (ValueError, TypeError) as error:
        raise ValueError("client_registry_column_filters_invalid") from error

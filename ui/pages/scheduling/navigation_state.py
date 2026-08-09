"""One-shot scheduling deep-link state without Streamlit dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping


@dataclass(frozen=True, slots=True)
class StaffCalendarSelection:
    label: str
    year: int | None
    month: int | None
    note: str | None


def apply_one_time_default(
    state: MutableMapping[str, Any],
    *,
    enabled: bool,
    navigation_value: str,
) -> None:
    if not enabled:
        return
    event_token = state.get("matching_center_plan_navigation_token")
    if not isinstance(event_token, str) or not event_token:
        return
    consumed_token_key = "matching_center_consumed_plan_navigation_token"
    if state.get(consumed_token_key) == event_token:
        return
    state[consumed_token_key] = event_token
    state["matching_center_sub_nav"] = navigation_value


def consume_staff_calendar_selection(
    state: MutableMapping[str, Any],
    staff_options: Mapping[str, int],
) -> StaffCalendarSelection | None:
    staff_id = state.get("pending_staff_calendar_staff_id")
    if staff_id is None:
        return None
    label = next(
        (
            label
            for label, option_staff_id in staff_options.items()
            if option_staff_id == staff_id
        ),
        None,
    )
    if label is None:
        return None
    state.pop("pending_staff_calendar_staff_id", None)
    return StaffCalendarSelection(
        label=label,
        year=_optional_integer(state.pop("pending_staff_calendar_year", None)),
        month=_optional_integer(state.pop("pending_staff_calendar_month", None)),
        note=state.pop("pending_staff_calendar_note", None),
    )


def clear_staff_calendar_navigation(state: MutableMapping[str, Any]) -> None:
    for key in (
        "pending_staff_calendar_staff_id",
        "pending_staff_calendar_year",
        "pending_staff_calendar_month",
        "pending_staff_calendar_note",
    ):
        state.pop(key, None)


def staff_option_label(staff: Mapping[str, Any]) -> str:
    staff_id = int(staff["id"])
    name = str(staff.get("name") or "未命名")
    phone = str(staff.get("phone") or "無電話")
    return f"{name} ({phone}) · #{staff_id}"


def _optional_integer(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("calendar navigation value must be an integer")
    return int(value)


__all__ = [
    "StaffCalendarSelection",
    "apply_one_time_default",
    "clear_staff_calendar_navigation",
    "consume_staff_calendar_selection",
    "staff_option_label",
]

"""Pure validation rules for multi-caregiver service date intervals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any


def _normalize_date(value: Any, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO date") from exc
    raise ValueError(f"{field_name} is required and must be an ISO date")


def validate_non_overlapping_assignment_interval(
    candidate_start_date: date | str,
    candidate_end_date: date | str,
    existing_assignments: Iterable[Mapping[str, Any]],
    candidate_assignment_id: int | None = None,
) -> tuple[date, date]:
    """Return a valid inclusive interval or raise ``ValueError``.

    Existing assignments must belong to one case and expose ``id``, ``status``,
    ``assigned_start_date``, and ``assigned_end_date``.  Cancelled assignments
    and the assignment being edited do not reserve dates.
    """

    candidate_start = _normalize_date(candidate_start_date, "candidate_start_date")
    candidate_end = _normalize_date(candidate_end_date, "candidate_end_date")
    if candidate_start > candidate_end:
        raise ValueError("candidate_start_date must not be after candidate_end_date")

    for assignment in existing_assignments:
        assignment_id = assignment.get("id")
        if assignment_id == candidate_assignment_id:
            continue
        if assignment.get("status") == "cancelled":
            continue

        try:
            existing_start = _normalize_date(
                assignment.get("assigned_start_date"),
                f"assignment {assignment_id} assigned_start_date",
            )
            existing_end = _normalize_date(
                assignment.get("assigned_end_date"),
                f"assignment {assignment_id} assigned_end_date",
            )
        except ValueError as exc:
            raise ValueError(
                f"assignment {assignment_id} has incomplete service dates and requires review"
            ) from exc

        if existing_start > existing_end:
            raise ValueError(f"assignment {assignment_id} has an invalid service date range")
        if candidate_start <= existing_end and candidate_end >= existing_start:
            raise ValueError(f"service date range overlaps assignment {assignment_id}")

    return candidate_start, candidate_end

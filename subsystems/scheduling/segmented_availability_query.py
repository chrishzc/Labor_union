"""Segmented caregiver availability search service.

Pure helpers for constraints/combination enumeration remain in
`caregiver_segment_availability_service.py`. This module only owns DB loading,
date normalization and data shaping.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from domains.scheduling.waiting_deposit_lock import (
    WaitingDepositOccupancyKind,
    WaitingDepositSegment,
    project_waiting_deposit_occupancy,
)
from subsystems.scheduling.segmented_availability import (
    derive_segment_availability,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.segmented_availability_repository import (
    MySqlSegmentedAvailabilityFactsRepository,
    SegmentedAvailabilityFactsPort,
)


def _as_optional_date(value: Any, field_name: str) -> date:
    """Normalize date-like input coming from caller/database boundary fields."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError(f"{field_name} must be a date")
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a date") from exc
    raise ValueError(f"{field_name} must be a date")


def _expand_assignment_days(
    assignment: Dict[str, Any],
    window_start: date,
    window_end: date,
) -> list[Dict[str, Any]]:
    assignment_id = assignment["id"]
    staff_id = assignment["staff_id"]
    start = _as_optional_date(assignment["assigned_start_date"], "case_staff_assignments.assigned_start_date")
    end = _as_optional_date(assignment["assigned_end_date"], "case_staff_assignments.assigned_end_date")

    if start > end:
        raise ValueError("case_staff_assignments.assigned_start_date cannot be after assigned_end_date")

    cursor = start
    segment_start = max(start, window_start)
    segment_end = min(end, window_end)
    if segment_start > segment_end:
        return []

    blocked: list[dict[str, Any]] = []
    while cursor <= segment_end:
        if cursor >= segment_start:
            blocked.append(
                {
                    "assignment_id": int(assignment_id),
                    "staff_id": int(staff_id),
                    "work_date": cursor.isoformat(),
                    "reason_code": "assignment",
                }
            )
        cursor = cursor + timedelta(days=1)

    return blocked


def search_segmented_caregiver_availability(
    case_no: str,
    segment_count: int,
    segment_drafts: List[dict],
    as_of: Any,
    facts_port: SegmentedAvailabilityFactsPort | None = None,
) -> Dict[str, Any]:
    """Search for segmented caregiver availability for a single case."""
    if not case_no:
        raise ValueError("case_no is required")
    if not isinstance(segment_count, int) or isinstance(segment_count, bool) or segment_count not in (1, 2, 3, 4):
        raise ValueError("segment_count must be 1, 2, 3, or 4")

    # Ensure `as_of` comes from caller and is a valid date representation.
    _as_optional_date(as_of, "as_of")

    if not isinstance(segment_drafts, list):
        raise ValueError("segment_drafts must be a list")

    facts = facts_port or MySqlSegmentedAvailabilityFactsRepository(get_connection)
    loaded_facts = facts.load_case_facts(case_no)
    order_row = loaded_facts["order"]
    if not order_row:
        raise ValueError("case not found")
    if order_row["status"] != "洽談中":
        raise ValueError("case is not in negotiation stage")

    planned_start = _as_optional_date(order_row["start_date"], "planned_start_date")
    planned_end = _as_optional_date(order_row["end_date"], "planned_end_date")
    if planned_start > planned_end:
        raise ValueError("planned_start_date cannot be after planned_end_date")

    candidate_rows = loaded_facts["staff_rows"]
    candidate_staff_ids = [row["id"] for row in candidate_rows if row is not None and "id" in row]
    assignments = loaded_facts["assignments"]

    assignment_schedule_days: list[dict[str, Any]] = []
    for assignment in assignments:
        assignment_schedule_days.extend(_expand_assignment_days(assignment, planned_start, planned_end))
    for row in loaded_facts["schedule_rows"]:
        assignment_schedule_days.append(
            {
                "assignment_id": row["assignment_id"],
                "staff_id": row["staff_id"],
                "work_date": _as_optional_date(row["work_date"], "staff_schedule.work_date").isoformat(),
                "reason_code": "schedule",
            }
        )
    for row in loaded_facts["legacy_schedule_rows"]:
        assignment_schedule_days.append(
            {
                "staff_id": row["staff_id"],
                "work_date": _as_optional_date(row["work_date"], "staff_schedule.work_date").isoformat(),
                "assignment_id": None,
            }
        )
    for row in loaded_facts["buffer_rows"]:
        assignment_schedule_days.append(
            {
                "assignment_id": row["assignment_id"],
                "staff_id": row["staff_id"],
                "work_date": _as_optional_date(
                    row["buffer_date"], "scheduling_buffer_days.buffer_date"
                ).isoformat(),
                "reason_code": "assignment",
            }
        )

    active_lock_days = [
        {
            "staff_id": row["staff_id"],
            "lock_date": _as_optional_date(
                row["lock_date"], "caregiver_availability_lock_days.lock_date"
            ).isoformat(),
            "active_marker": row["active_marker"],
        }
        for row in loaded_facts["active_lock_rows"]
    ]
    active_lock_days.extend(
        _active_waiting_buffer_days(
            loaded_facts["waiting_buffer_rows"], planned_start, planned_end
        )
    )

    required_service_dates = _required_service_dates(
        loaded_facts.get("confirmed_service_dates") or [], planned_start, planned_end
    )
    result = derive_segment_availability(
        planned_start_date=planned_start.isoformat(),
        planned_end_date=planned_end.isoformat(),
        segment_count=segment_count,
        segment_drafts=segment_drafts,
        candidate_staff_ids=candidate_staff_ids,
        assignment_schedule_days=assignment_schedule_days,
        active_lock_days=active_lock_days,
    )
    return {
        "case_no": order_row["case_no"],
        "planned_start_date": result["validated_input"]["planned_start_date"],
        "planned_end_date": result["validated_input"]["planned_end_date"],
        "feasibility": "complete" if result["complete_combinations"] else "partial",
        "complete_combinations": result["complete_combinations"],
        "segment_candidates": result["segment_candidates"],
        "candidate_options": _candidate_options(result["segment_candidates"], candidate_rows,
                                                  required_service_dates, segment_drafts,
                                                  int(order_row.get("scheduling_version") or 0)),
        "conflicts": result["conflicts"],
    }


def _required_service_dates(confirmed_rows, planned_start, planned_end):
    if confirmed_rows:
        return tuple(_as_optional_date(row["service_date"], "confirmed_service_date") for row in confirmed_rows)
    return tuple(planned_start + timedelta(days=offset)
                 for offset in range((planned_end - planned_start).days + 1))


def _candidate_options(candidate_rows, staff_rows, required_service_dates, segment_drafts,
                       scheduling_version):
    staff_names = {
        int(row["id"]): str(row.get("name") or "")
        for row in staff_rows
        if row and row.get("id") is not None
    }
    options = {}
    for candidate in candidate_rows:
        key = (int(candidate["segment_index"]), int(candidate["staff_id"]))
        option = options.setdefault(
            key,
            {
                "segment_index": key[0],
                "staff_id": key[1],
                "staff_name": staff_names.get(key[1], ""),
                "coverage_day_count": 0,
                "available_ranges": [],
            },
        )
        start_date = _as_optional_date(candidate["start_date"], "candidate.start_date")
        end_date = _as_optional_date(candidate["end_date"], "candidate.end_date")
        option["available_ranges"].append(
            {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        )
    return [_coverage_view(options[key], required_service_dates, segment_drafts,
                           scheduling_version) for key in sorted(options)]


def _coverage_view(option, required_service_dates, segment_drafts, scheduling_version):
    supported = tuple(service_date for service_date in required_service_dates
                      if any(_as_optional_date(interval["start_date"], "range.start") <= service_date <=
                             _as_optional_date(interval["end_date"], "range.end")
                             for interval in option["available_ranges"]))
    draft = segment_drafts[option["segment_index"]] if option["segment_index"] < len(segment_drafts) else {}
    segment_start = _as_optional_date(draft.get("start_date"), "segment.start") if draft.get("start_date") else required_service_dates[0]
    segment_end = _as_optional_date(draft.get("end_date"), "segment.end") if draft.get("end_date") else required_service_dates[-1]
    required_segment = tuple(day for day in required_service_dates if segment_start <= day <= segment_end)
    supported_segment = set(supported)
    uncovered = tuple(day for day in required_segment if day not in supported_segment)
    return {
        **option,
        "coverage_day_count": len(supported),
        "case_period_start": required_service_dates[0].isoformat(),
        "case_period_end": required_service_dates[-1].isoformat(),
        "required_service_dates": [day.isoformat() for day in required_service_dates],
        "supported_service_dates": [day.isoformat() for day in supported],
        "supported_ranges": _date_ranges(supported),
        "supported_day_count": len(supported),
        "required_day_count": len(required_service_dates),
        "full_case_coverage": len(supported) == len(required_service_dates),
        "selected_segment_start": segment_start.isoformat(),
        "selected_segment_end": segment_end.isoformat(),
        "full_selected_segment_coverage": not uncovered,
        "uncovered_segment_dates": [day.isoformat() for day in uncovered],
        "source_scheduling_version": scheduling_version,
    }


def _date_ranges(dates):
    if not dates:
        return []
    ranges, start, previous = [], dates[0], dates[0]
    for current in dates[1:]:
        if current == previous + timedelta(days=1):
            previous = current
            continue
        ranges.append({"start_date": start.isoformat(), "end_date": previous.isoformat(),
                       "service_day_count": (previous - start).days + 1})
        start = previous = current
    ranges.append({"start_date": start.isoformat(), "end_date": previous.isoformat(),
                   "service_day_count": (previous - start).days + 1})
    return ranges


def _active_waiting_buffer_days(rows, window_start, window_end):
    buffer_days = []
    for row in rows:
        segment = WaitingDepositSegment(
            int(row["segment_id"]),
            int(row["staff_id"]),
            _as_optional_date(
                row["assigned_start_date"],
                "matching_plan_segment.assigned_start_date",
            ),
            _as_optional_date(
                row["assigned_end_date"],
                "matching_plan_segment.assigned_end_date",
            ),
        )
        occupancy = project_waiting_deposit_occupancy((segment,))
        buffer_days.extend(
            {
                "staff_id": item.staff_id,
                "lock_date": item.occupancy_date.isoformat(),
                "active_marker": 1,
            }
            for item in occupancy
            if item.kind is WaitingDepositOccupancyKind.BUFFER
            and window_start <= item.occupancy_date <= window_end
        )
    return buffer_days

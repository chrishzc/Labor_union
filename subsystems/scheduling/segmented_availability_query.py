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
        **{key: result[key] for key in ["complete_combinations", "segment_candidates", "conflicts"]},
    }

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

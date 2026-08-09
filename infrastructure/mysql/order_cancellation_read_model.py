"""Strict MySQL readers for the Orders Cancellation transaction."""

from __future__ import annotations

from typing import Any, TypedDict

from domains.orders.cancellation import (
    CancellationAssignmentFacts,
    CancellationOrderFacts,
    CancellationSchedulingFacts,
)
from subsystems.scheduling.occupancy_mutex import lock_staff_occupancy_mutex
from subsystems.orders.cancellation_workflow import CancellationWorkflowFacts

from .order_terms_read_model import (
    _assemble_facts,
    preflight_staff_ids,
    select_order,
    select_scheduling_aggregate,
)


class CaregiverOptionRow(TypedDict):
    staff_id: int
    display_name: str


def list_active_caregiver_options(cursor: Any) -> tuple[CaregiverOptionRow, ...]:
    cursor.execute(
        "SELECT id,name FROM staff WHERE status='active' ORDER BY id",
        (),
    )
    return tuple(_caregiver_option(row) for row in cursor.fetchall())


def _caregiver_option(row) -> CaregiverOptionRow:
    display_name = row["name"]
    if (
        not isinstance(display_name, str)
        or not display_name
        or display_name != display_name.strip()
    ):
        raise ValueError("staff_display_name_invalid")
    return {"staff_id": int(row["id"]), "display_name": display_name}


def load_cancellation_preview_facts(
    cursor: Any,
    case_no: str,
    requested_staff_ids: tuple[int, ...],
) -> CancellationWorkflowFacts:
    _require_canonical_staff_ids(requested_staff_ids)
    _require_active_staff(cursor, requested_staff_ids, lock=False)
    order_row = select_order(cursor, case_no, lock=False)
    aggregate_row = select_scheduling_aggregate(cursor, case_no, lock=False)
    return _assemble_cancellation_facts(
        cursor, order_row, aggregate_row, lock=False
    )


def load_cancellation_locked_facts(
    cursor: Any,
    case_no: str,
    preflight_staff_ids: tuple[int, ...],
) -> CancellationWorkflowFacts:
    _require_canonical_staff_ids(preflight_staff_ids)
    order_row = select_order(cursor, case_no, lock=True)
    aggregate_row = select_scheduling_aggregate(cursor, case_no, lock=True)
    _lock_staff(cursor, preflight_staff_ids)
    return _assemble_cancellation_facts(
        cursor, order_row, aggregate_row, lock=True
    )


def cancellation_preflight_staff_ids(
    cursor: Any,
    case_no: str,
    requested_staff_ids: tuple[int, ...],
) -> tuple[int, ...]:
    _require_canonical_staff_ids(requested_staff_ids)
    current_ids = preflight_staff_ids(cursor, case_no)
    return tuple(sorted(set(current_ids).union(requested_staff_ids)))


def _assemble_cancellation_facts(
    cursor, order_row, aggregate_row, *, lock
):
    terms_facts = _assemble_facts(cursor, order_row, aggregate_row, lock=lock)
    assignments = _load_cancellation_assignments(
        cursor, aggregate_row, lock=lock
    )
    return _cancellation_facts(
        terms_facts, assignments, terms_facts.payroll
    )


# Kept cohesive because this is the single row-to-Domain assembly boundary.
def _cancellation_facts(terms_facts, assignments, payroll):
    order = terms_facts.order
    lifecycle = terms_facts.lifecycle
    return CancellationWorkflowFacts(
        CancellationOrderFacts(
            order.case_no,
            order.version,
            order.terms.service_days,
            order.terms.service_hours_per_day,
            lifecycle.actual_start_date,
            lifecycle.actual_start_date is not None,
            order.service_data_locked,
        ),
        order.terms,
        CancellationSchedulingFacts(
            order.case_no,
            terms_facts.scheduling.aggregate_version,
            terms_facts.scheduling.generation_number,
            assignments,
        ),
        terms_facts.client_finance,
        payroll,
        lifecycle,
    )


def _load_cancellation_assignments(cursor, aggregate_row, *, lock):
    cursor.execute(
        _CANCELLATION_ASSIGNMENTS_SQL + _lock_clause(lock),
        (aggregate_row["effective_generation_id"],),
    )
    rows = tuple(cursor.fetchall())
    return _cancellation_assignments(rows)


def _cancellation_assignments(rows):
    grouped: dict[int, dict[str, object]] = {}
    for row in rows:
        assignment_id = int(row["assignment_id"])
        grouped.setdefault(assignment_id, _assignment_root(row))
        if row["work_date"] is not None:
            grouped[assignment_id]["service_dates"].append(row["work_date"])
    return tuple(_cancellation_assignment(value) for value in grouped.values())


def _assignment_root(row):
    return {
        "assignment_id": int(row["assignment_id"]),
        "staff_id": int(row["staff_id"]),
        "sequence": int(row["assignment_sequence"]),
        "service_dates": [],
    }


def _cancellation_assignment(value):
    return CancellationAssignmentFacts(
        value["assignment_id"],
        value["staff_id"],
        value["sequence"],
        tuple(value["service_dates"]),
    )


def _lock_staff(cursor, staff_ids) -> None:
    locked_ids = tuple(lock_staff_occupancy_mutex(cursor, list(staff_ids)))
    if locked_ids != staff_ids:
        raise ValueError("scheduling_staff_not_found")
    _require_active_staff(cursor, staff_ids, lock=False)


def _require_active_staff(cursor, staff_ids, *, lock) -> None:
    if not staff_ids:
        return
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        f"SELECT id FROM staff WHERE id IN ({placeholders}) "
        f"AND status='active' ORDER BY id{_lock_clause(lock)}",
        staff_ids,
    )
    locked_ids = tuple(int(row["id"]) for row in cursor.fetchall())
    if locked_ids != staff_ids:
        raise ValueError("scheduling_staff_not_found")


def _require_canonical_staff_ids(staff_ids) -> None:
    if staff_ids != tuple(sorted(set(staff_ids))):
        raise ValueError("staff ids must be canonical")
    if any(isinstance(value, bool) or value <= 0 for value in staff_ids):
        raise ValueError("staff ids must be positive integers")


def _lock_clause(lock: bool) -> str:
    return " FOR UPDATE" if lock else ""


_CANCELLATION_ASSIGNMENTS_SQL = (
    "SELECT a.id AS assignment_id,a.staff_id,a.assignment_sequence,"
    "s.work_date FROM case_staff_assignments a "
    "LEFT JOIN staff_schedule s ON s.assignment_id=a.id "
    "AND s.generation_id=a.generation_id AND s.effective_marker=1 "
    "AND s.is_work_day=1 WHERE a.generation_id=%s "
    "AND a.status NOT IN ('cancelled','replaced') "
    "ORDER BY a.assignment_sequence,a.id,s.work_date,s.id"
)

__all__ = [
    "CaregiverOptionRow",
    "cancellation_preflight_staff_ids",
    "list_active_caregiver_options",
    "load_cancellation_locked_facts",
    "load_cancellation_preview_facts",
]

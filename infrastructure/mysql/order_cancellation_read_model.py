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
    _load_client_finance,
    _load_payroll,
    _load_lifecycle,
    _order_facts,
    _select_generation,
    _select_assignments,
    _select_schedules,
    _lock_dated_occupancy,
    _validate_scheduling_aggregate_state,
    _SCHEDULING_AGGREGATE_SQL,
    preflight_staff_ids,
    select_order,
)


class CaregiverOptionRow(TypedDict):
    staff_id: int
    display_name: str


def list_active_caregiver_options(cursor: Any) -> tuple[CaregiverOptionRow, ...]:
    """Backward-compatible active-only caregiver query."""

    cursor.execute(
        "SELECT id,name FROM staff WHERE status='active' ORDER BY id",
        (),
    )
    return tuple(_caregiver_option(row) for row in cursor.fetchall())


def list_caregiver_options(
    cursor: Any,
    case_no: str,
) -> tuple[CaregiverOptionRow, ...]:
    """Include inactive staff only when this historical case proves the pairing."""

    if not _historical_cancellation_origin(cursor, case_no):
        return list_active_caregiver_options(cursor)
    cursor.execute(
        "SELECT s.id,s.name,MAX(CASE WHEN a.id IS NULL THEN 0 ELSE 1 END) "
        "AS historical_evidence FROM staff s "
        "LEFT JOIN case_staff_assignments a ON a.staff_id=s.id "
        "AND a.case_no=%s AND a.generation_id IS NULL "
        "AND a.status='completed' "
        "WHERE s.status='active' OR a.id IS NOT NULL "
        "GROUP BY s.id,s.name ORDER BY historical_evidence DESC,s.id",
        (case_no,),
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
    order_row = select_order(cursor, case_no, lock=False)
    historical_origin = _historical_cancellation_origin(cursor, case_no)
    _require_selectable_staff(
        cursor,
        case_no,
        requested_staff_ids,
        historical_origin=historical_origin,
    )
    aggregate_row = _select_cancellation_aggregate(cursor, case_no, lock=False)
    return _assemble_cancellation_facts(
        cursor,
        order_row,
        aggregate_row,
        lock=False,
        historical_origin=historical_origin,
    )


def load_cancellation_locked_facts(
    cursor: Any,
    case_no: str,
    preflight_staff_ids: tuple[int, ...],
) -> CancellationWorkflowFacts:
    _require_canonical_staff_ids(preflight_staff_ids)
    order_row = select_order(cursor, case_no, lock=True)
    aggregate_row = _select_cancellation_aggregate(cursor, case_no, lock=True)
    historical_origin = _historical_cancellation_origin(cursor, case_no)
    _lock_staff(
        cursor,
        preflight_staff_ids,
        case_no=case_no,
        historical_origin=historical_origin,
    )
    return _assemble_cancellation_facts(
        cursor,
        order_row,
        aggregate_row,
        lock=True,
        historical_origin=historical_origin,
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
    cursor,
    order_row,
    aggregate_row,
    *,
    lock,
    historical_origin=None,
):
    case_no = str(order_row["case_no"])
    if aggregate_row is None:
        cursor.execute("SELECT id FROM scheduling_generations WHERE case_no=%s" + _lock_clause(lock), (case_no,))
        if cursor.fetchone() is not None:
            raise ValueError("cancellation_scheduling_facts_inconsistent")
    generation = _select_generation(cursor, aggregate_row, lock) if aggregate_row else None
    assignment_rows = _select_assignments(cursor, generation, lock)
    schedule_rows = _select_schedules(cursor, generation, lock)
    assignments = _load_cancellation_assignments(cursor, aggregate_row, lock=lock) if aggregate_row else ()
    finance_present, payroll_present = _validate_cancellation_owner_presence(cursor, case_no, lock)
    if assignments and not (finance_present and payroll_present):
        raise ValueError("cancellation_financial_roots_inconsistent")
    if aggregate_row is None and payroll_present:
        raise ValueError("cancellation_scheduling_facts_inconsistent")
    finance = _load_client_finance(cursor, order_row, schedule_rows, lock) if finance_present else None
    payroll = _load_payroll(cursor, order_row, assignment_rows, lock) if payroll_present else None
    lifecycle = _load_lifecycle(cursor, order_row, lock)
    order = _order_facts(order_row)
    if lock and generation is not None:
        _lock_dated_occupancy(cursor, generation)
    if historical_origin is None:
        historical_origin = _historical_cancellation_origin(cursor, case_no)
    return CancellationWorkflowFacts(
        CancellationOrderFacts(
            case_no, order.version, order.terms.service_days,
            order.terms.service_hours_per_day, lifecycle.actual_start_date,
            lifecycle.actual_start_date is not None and bool(assignments),
            order.service_data_locked,
        ),
        order.terms,
        CancellationSchedulingFacts(
            case_no,
            int(aggregate_row["aggregate_version"]) if aggregate_row else None,
            int(generation["generation_number"]) if generation else (0 if aggregate_row else None),
            assignments,
        ),
        finance, payroll, lifecycle, historical_origin,
    )


def _select_cancellation_aggregate(cursor, case_no, *, lock):
    cursor.execute(_SCHEDULING_AGGREGATE_SQL + _lock_clause(lock), (case_no,))
    row = cursor.fetchone()
    if row is not None:
        _validate_scheduling_aggregate_state(row)
    return row


def _validate_cancellation_owner_presence(cursor, case_no, lock):
    """Absence is legal; partial roots or orphan financial history are not."""
    def exists(table, column="case_no"):
        cursor.execute(f"SELECT {column} FROM {table} WHERE case_no=%s" + _lock_clause(lock), (case_no,))
        return cursor.fetchone() is not None

    finance = exists("client_finance_accounts")
    if finance != exists("client_payment_terms"):
        raise ValueError("invalid_client_finance_facts")
    if not finance and any(exists(table) for table in ("client_obligations", "client_obligation_events", "client_ledger_entries")):
        raise ValueError("invalid_client_finance_facts")
    payroll = exists("payroll_case_accounts")
    if payroll != exists("case_payroll_rate_policy_snapshots"):
        raise ValueError("invalid_payroll_facts")
    if not payroll and any(exists(table) for table in ("staff_obligations", "staff_obligation_events")):
        raise ValueError("invalid_payroll_facts")
    return finance, payroll


def _historical_cancellation_origin(cursor, case_no) -> bool:
    cursor.execute(
        "SELECT "
        "EXISTS(SELECT 1 FROM order_lifecycle_control_state s "
        "WHERE s.case_no=%s AND s.control_type='cancellation' "
        "AND s.control_key='order_cancelled' AND s.state='active' "
        "AND s.reason LIKE 'historical_order_adoption:%%') "
        "AS historical_control_active,"
        "EXISTS(SELECT 1 FROM order_cancellation_events c "
        "WHERE c.case_no=%s) AS canonical_cancellation_exists",
        (case_no, case_no),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("historical_cancellation_origin_readback_missing")
    return bool(row["historical_control_active"]) and not bool(
        row["canonical_cancellation_exists"]
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


def _lock_staff(
    cursor,
    staff_ids,
    *,
    case_no=None,
    historical_origin=False,
) -> None:
    if not staff_ids:
        return
    locked_ids = tuple(lock_staff_occupancy_mutex(cursor, list(staff_ids)))
    if locked_ids != staff_ids:
        raise ValueError("scheduling_staff_not_found")
    if historical_origin and not isinstance(case_no, str):
        raise ValueError("historical cancellation case number is required")
    _require_selectable_staff(
        cursor,
        case_no,
        staff_ids,
        historical_origin=historical_origin,
    )


def _require_selectable_staff(
    cursor,
    case_no,
    staff_ids,
    *,
    historical_origin,
) -> None:
    if not staff_ids:
        return
    placeholders = ",".join("%s" for _ in staff_ids)
    if historical_origin:
        cursor.execute(
            f"SELECT s.id FROM staff s WHERE s.id IN ({placeholders}) "
            "AND (s.status='active' OR EXISTS(SELECT 1 "
            "FROM case_staff_assignments a WHERE a.case_no=%s "
            "AND a.staff_id=s.id AND a.generation_id IS NULL "
            "AND a.status='completed')) ORDER BY s.id",
            (*staff_ids, case_no),
        )
    else:
        cursor.execute(
            f"SELECT id FROM staff WHERE id IN ({placeholders}) "
            "AND status='active' ORDER BY id",
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
    "list_caregiver_options",
    "load_cancellation_locked_facts",
    "load_cancellation_preview_facts",
]

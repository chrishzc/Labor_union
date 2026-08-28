"""
File: historical_orders_scheduling_completion_read_adapter.py
Description: 以單一唯讀快照組合 Orders 完成事件與 Scheduling 正式服務根事實。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_completion_oracle import (
    HistoricalOrdersCompletionReadback,
)


_CASE_NUMBER_MAXIMUM_LENGTH = 50
_SIGNED_BIGINT_MAXIMUM = 9_223_372_036_854_775_807
_ACTIVE_ASSIGNMENT_STATUSES = frozenset({"planned", "active", "completed"})
_EXCLUDED_ASSIGNMENT_STATUSES = frozenset({"cancelled", "replaced"})


# One statement gives all branches the same statement-level consistent read
# without changing the caller connection's transaction state.
_CURRENT_CASE_READ_SQL = """
SELECT 'order' AS row_kind,
       o.case_no, o.lifecycle_version, o.status, o.actual_start_date,
       o.service_days, o.service_start_time, o.service_end_time,
       o.service_end_day_offset,
       NULL AS completion_event_id, NULL AS completion_case_no,
       NULL AS completion_after_status, NULL AS completion_expected_version,
       NULL AS aggregate_case_no, NULL AS aggregate_version,
       NULL AS effective_generation_id,
       NULL AS generation_id, NULL AS generation_case_no,
       NULL AS generation_resulting_aggregate_version,
       NULL AS generation_status, NULL AS generation_effective_marker,
       NULL AS assignment_id, NULL AS assignment_case_no,
       NULL AS assignment_generation_id, NULL AS assignment_staff_id,
       NULL AS assignment_status, NULL AS assignment_start_date,
       NULL AS assignment_end_date,
       NULL AS schedule_id, NULL AS schedule_case_no,
       NULL AS schedule_generation_id, NULL AS schedule_assignment_id,
       NULL AS schedule_staff_id, NULL AS work_date,
       NULL AS schedule_effective_marker, NULL AS schedule_is_work_day
FROM orders o
WHERE o.case_no=%s
UNION ALL
SELECT 'completion',
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       e.id, e.case_no, e.after_status, e.expected_version,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL
FROM order_lifecycle_state_events e
WHERE e.case_no=%s AND e.after_status='訂單完成'
UNION ALL
SELECT 'aggregate',
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL,
       a.case_no, a.aggregate_version, a.effective_generation_id,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM scheduling_aggregates a
WHERE a.case_no=%s
UNION ALL
SELECT 'generation',
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       g.id, g.case_no, g.resulting_aggregate_version,
       g.status, g.effective_marker,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM scheduling_generations g
WHERE g.case_no=%s
UNION ALL
SELECT 'assignment',
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL,
       a.id, a.case_no, a.generation_id, a.staff_id, a.status,
       a.assigned_start_date, a.assigned_end_date,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM case_staff_assignments a
WHERE a.case_no=%s
UNION ALL
SELECT 'schedule',
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, s.id, s.case_no, s.generation_id,
       s.assignment_id, s.staff_id, s.work_date,
       s.effective_marker, s.is_work_day
FROM staff_schedule s
WHERE s.case_no=%s
"""


class MySqlHistoricalOrdersSchedulingCompletionReadAdapter:
    """Read current Orders/Scheduling roots without lock or caller transaction effects."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalOrdersCompletionReadback | None:
        """Return one case readback from a single statement-level snapshot."""

        require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if for_update is not False:
            raise ValueError("historical completion read adapter is read-only")
        with self._connection.cursor() as cursor:
            cursor.execute(_CURRENT_CASE_READ_SQL, (case_no,) * 6)
            rows = _mapping_rows(cursor.fetchall(), "Orders/Scheduling current roots")
        if not any(row.get("row_kind") == "order" for row in rows):
            return None
        if any(
            not isinstance(row.get("row_kind"), str)
            or row.get("row_kind")
            not in {"order", "completion", "aggregate", "generation", "assignment", "schedule"}
            for row in rows
        ):
            raise ValueError("Orders/Scheduling current roots contain an unknown row kind")
        orders = tuple(row for row in rows if row.get("row_kind") == "order")
        if len(orders) != 1:
            raise ValueError("Orders current root is duplicated")
        completion = tuple(row for row in rows if row.get("row_kind") == "completion")
        aggregate = tuple(row for row in rows if row.get("row_kind") == "aggregate")
        generations = tuple(row for row in rows if row.get("row_kind") == "generation")
        assignments = tuple(row for row in rows if row.get("row_kind") == "assignment")
        schedules = tuple(row for row in rows if row.get("row_kind") == "schedule")
        return _build_readback(
            case_no,
            orders[0],
            completion,
            aggregate,
            generations,
            assignments,
            schedules,
        )


def _build_readback(
    case_no: str,
    order: Mapping[str, Any],
    completion_rows: tuple[Mapping[str, Any], ...],
    aggregate_rows: tuple[Mapping[str, Any], ...],
    generation_rows: tuple[Mapping[str, Any], ...],
    assignment_rows: tuple[Mapping[str, Any], ...],
    schedule_rows: tuple[Mapping[str, Any], ...],
) -> HistoricalOrdersCompletionReadback:
    blockers: list[str] = []
    _check_case_identity(order, case_no, "Orders")
    lifecycle_version = _required_nonnegative_int(
        order.get("lifecycle_version"), "Orders lifecycle version"
    )
    status = _status(order.get("status"))
    required_days = _required_positive_int(
        order.get("service_days"), "required service day count"
    )
    actual_start_date = _optional_date(
        order.get("actual_start_date"),
        "actual start date",
        blockers,
        "orders.actual_start_date",
    )
    service_time_complete = _service_time_complete(order, blockers)

    completion_identity = _completion_identity(
        case_no, lifecycle_version, completion_rows, blockers
    )
    aggregate, generation, assignments, schedules = _current_scheduling_rows(
        case_no,
        aggregate_rows,
        generation_rows,
        assignment_rows,
        schedule_rows,
        blockers,
    )
    service_dates, service_identity = _official_service_facts(
        case_no,
        lifecycle_version,
        required_days,
        aggregate,
        generation,
        assignments,
        schedules,
        blockers,
    )
    aggregate_version = None
    if aggregate is not None:
        aggregate_version = _required_nonnegative_int(
            aggregate.get("aggregate_version"), "Scheduling aggregate version"
        )
    return HistoricalOrdersCompletionReadback(
        case_no=case_no,
        lifecycle_version=lifecycle_version,
        canonical_status=status,
        completion_lineage_identity=completion_identity,
        actual_start_date=actual_start_date,
        official_service_fact_identity=service_identity,
        official_service_dates=tuple(service_dates),
        required_service_day_count=required_days,
        service_time_tuple_complete=service_time_complete,
        # The statement completed and returned the owner snapshot. Known
        # semantic gaps stay actionable through ``integrity_blockers``; only a
        # transport/query failure makes the readback unavailable.
        readback_available=True,
        integrity_blockers=tuple(sorted(set(blockers))),
    )


def _completion_identity(
    case_no: str,
    lifecycle_version: int,
    rows: tuple[Mapping[str, Any], ...],
    blockers: list[str],
) -> str | None:
    if not rows:
        blockers.append("orders.completion_lineage_missing")
        return None
    eligible = tuple(
        row
        for row in rows
        if row.get("completion_expected_version") == lifecycle_version - 1
    )
    if len(eligible) > 1:
        blockers.append("orders.completion_lineage_duplicate")
        return None
    if not eligible:
        blockers.append("orders.completion_lineage_version_mismatch")
        return None
    row = eligible[0]
    _check_case_identity(
        row,
        case_no,
        "Orders completion lineage",
        blockers,
        field="completion_case_no",
    )
    if row.get("completion_case_no") != case_no:
        return None
    event_id = row.get("completion_event_id")
    expected_version = row.get("completion_expected_version")
    if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id <= 0:
        blockers.append("orders.completion_event_identity_invalid")
        return None
    if event_id > _SIGNED_BIGINT_MAXIMUM:
        blockers.append("orders.completion_event_identity_invalid")
        return None
    if row.get("completion_after_status") != OrderLifecycleStatus.COMPLETED.value:
        blockers.append("orders.completion_event_status_invalid")
        return None
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
        blockers.append("orders.completion_expected_version_invalid")
        return None
    if expected_version + 1 != lifecycle_version:
        blockers.append("orders.completion_lineage_version_mismatch")
        return None
    return f"orders-completion-event:{case_no}:{event_id}"


def _current_scheduling_rows(
    case_no: str,
    aggregate_rows: tuple[Mapping[str, Any], ...],
    generation_rows: tuple[Mapping[str, Any], ...],
    assignment_rows: tuple[Mapping[str, Any], ...],
    schedule_rows: tuple[Mapping[str, Any], ...],
    blockers: list[str],
) -> tuple[
    Mapping[str, Any] | None,
    Mapping[str, Any] | None,
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
]:
    if not aggregate_rows:
        blockers.append("scheduling.aggregate_missing")
        return None, None, (), ()
    if len(aggregate_rows) != 1:
        blockers.append("scheduling.aggregate_duplicate")
        return None, None, (), ()
    aggregate = aggregate_rows[0]
    _check_case_identity(aggregate, case_no, "Scheduling aggregate", blockers, field="aggregate_case_no")
    effective_id = aggregate.get("effective_generation_id")
    if effective_id is None:
        blockers.append("scheduling.effective_generation_missing")
        return aggregate, None, (), ()
    if not _is_positive_database_identity(effective_id):
        blockers.append("scheduling.effective_generation_identity_invalid")
        return aggregate, None, (), ()
    matching_generations = tuple(
        row for row in generation_rows if row.get("generation_id") == effective_id
    )
    if len(matching_generations) != 1:
        blockers.append("scheduling.effective_generation_missing" if not matching_generations else "scheduling.effective_generation_duplicate")
        return aggregate, None, (), ()
    generation = matching_generations[0]
    _check_case_identity(generation, case_no, "Scheduling generation", blockers, field="generation_case_no")
    if (
        generation.get("generation_status") != "effective"
        or not _is_binary_flag(generation.get("generation_effective_marker"))
        or generation.get("generation_effective_marker") != 1
    ):
        blockers.append("scheduling.effective_generation_invalid")
    aggregate_version = aggregate.get("aggregate_version")
    if generation.get("generation_resulting_aggregate_version") != aggregate_version:
        blockers.append("scheduling.generation_version_mismatch")

    current_assignments = tuple(
        row
        for row in assignment_rows
        if row.get("assignment_generation_id") == effective_id
    )
    current_schedules = tuple(
        row
        for row in schedule_rows
        if row.get("schedule_generation_id") == effective_id
    )
    for row in assignment_rows:
        if (
            row.get("assignment_generation_id") == effective_id
            and (
                not isinstance(row.get("assignment_status"), str)
                or row.get("assignment_status") not in _EXCLUDED_ASSIGNMENT_STATUSES
            )
        ):
            _check_case_identity(row, case_no, "Scheduling assignment", blockers, field="assignment_case_no")
    excluded_assignment_ids = {
        row.get("assignment_id")
        for row in current_assignments
        if isinstance(row.get("assignment_status"), str)
        and row.get("assignment_status") in _EXCLUDED_ASSIGNMENT_STATUSES
        and _is_positive_database_identity(row.get("assignment_id"))
    }
    excluded_assignment_ids.difference_update(
        row.get("assignment_id")
        for row in current_assignments
        if isinstance(row.get("assignment_status"), str)
        and row.get("assignment_status") in _ACTIVE_ASSIGNMENT_STATUSES
        and _is_positive_database_identity(row.get("assignment_id"))
    )
    for row in schedule_rows:
        schedule_assignment_id = row.get("schedule_assignment_id")
        if (
            row.get("schedule_generation_id") == effective_id
            and (
                not _is_positive_database_identity(schedule_assignment_id)
                or schedule_assignment_id not in excluded_assignment_ids
            )
        ):
            _check_case_identity(row, case_no, "Scheduling service schedule", blockers, field="schedule_case_no")
    if not any(
        isinstance(row.get("assignment_status"), str)
        and row.get("assignment_status") in _ACTIVE_ASSIGNMENT_STATUSES
        for row in current_assignments
    ):
        blockers.append("scheduling.assignments_missing")
    if not current_schedules:
        blockers.append("scheduling.official_service_dates_missing")
    return aggregate, generation, current_assignments, current_schedules


def _official_service_facts(
    case_no: str,
    lifecycle_version: int,
    required_days: int,
    aggregate: Mapping[str, Any] | None,
    generation: Mapping[str, Any] | None,
    assignments: tuple[Mapping[str, Any], ...],
    schedules: tuple[Mapping[str, Any], ...],
    blockers: list[str],
) -> tuple[list[date], str | None]:
    starting_blocker_count = len(blockers)
    assignment_index: dict[int, Mapping[str, Any]] = {}
    assignments_by_id: dict[int, Mapping[str, Any]] = {}
    for row in assignments:
        assignment_status = row.get("assignment_status")
        # Replaced/cancelled rows are retained as lineage, but current readers
        # exclude them from official ownership and service-day facts.
        if isinstance(assignment_status, str) and assignment_status in _EXCLUDED_ASSIGNMENT_STATUSES:
            assignment_id = row.get("assignment_id")
            if (
                _is_positive_database_identity(assignment_id)
            ):
                assignments_by_id.setdefault(assignment_id, row)
            continue
        assignment_id = row.get("assignment_id")
        if not _is_positive_database_identity(assignment_id):
            blockers.append("scheduling.assignment_identity_invalid")
            continue
        assignments_by_id[assignment_id] = row
        previous = assignment_index.get(assignment_id)
        if previous is not None:
            blockers.append(
                "scheduling.assignment_identity_duplicate"
                if dict(previous) == dict(row)
                else "scheduling.assignment_identity_conflict"
            )
        if not isinstance(assignment_status, str) or assignment_status not in _ACTIVE_ASSIGNMENT_STATUSES:
            blockers.append("scheduling.assignment_status_invalid")
            continue
        assignment_staff_id = row.get("assignment_staff_id")
        if (
            not _is_positive_database_identity(assignment_staff_id)
        ):
            blockers.append("scheduling.assignment_staff_identity_invalid")
            continue
        try:
            assignment_start = _as_date(
                row.get("assignment_start_date"), "assignment start date"
            )
            assignment_end = _as_date(
                row.get("assignment_end_date"), "assignment end date"
            )
        except (TypeError, ValueError):
            blockers.append("scheduling.assignment_service_period_invalid")
            continue
        if assignment_start > assignment_end:
            blockers.append("scheduling.assignment_service_period_invalid")
            continue
        assignment_index.setdefault(assignment_id, row)
    official: list[Mapping[str, Any]] = []
    schedule_ids: set[int] = set()
    for row in schedules:
        assignment_id = row.get("schedule_assignment_id")
        assignment = (
            assignments_by_id.get(assignment_id)
            if _is_positive_database_identity(assignment_id)
            else None
        )
        if (
            assignment is not None
            and isinstance(assignment.get("assignment_status"), str)
            and assignment.get("assignment_status") in _EXCLUDED_ASSIGNMENT_STATUSES
        ):
            # The schedule is historical with respect to the effective
            # generation's current owner and must not affect dates, identity,
            # or duplicate checks.
            continue
        schedule_id = row.get("schedule_id")
        if not _is_positive_database_identity(schedule_id):
            blockers.append("scheduling.schedule_identity_invalid")
        elif schedule_id in schedule_ids:
            blockers.append("scheduling.schedule_identity_duplicate")
        else:
            schedule_ids.add(schedule_id)
        schedule_staff_id = row.get("schedule_staff_id")
        if (
            not _is_positive_database_identity(schedule_staff_id)
        ):
            blockers.append("scheduling.schedule_staff_identity_invalid")
        if (
            not _is_positive_database_identity(assignment_id)
            or assignment_id not in assignment_index
        ):
            blockers.append("scheduling.official_service_owner_inconsistent")
        elif (
            not _is_positive_database_identity(schedule_staff_id)
            or schedule_staff_id
            != assignment_index[assignment_id].get("assignment_staff_id")
        ):
            blockers.append("scheduling.official_service_owner_inconsistent")
        effective_marker = row.get("schedule_effective_marker")
        is_work_day = row.get("schedule_is_work_day")
        if not _is_binary_flag(effective_marker):
            blockers.append("scheduling.schedule_effective_marker_invalid")
            continue
        if not _is_binary_flag(is_work_day):
            blockers.append("scheduling.schedule_work_day_marker_invalid")
            continue
        if effective_marker != 1:
            if is_work_day == 1:
                blockers.append("scheduling.schedule_effective_marker_invalid")
            continue
        if is_work_day != 1:
            continue
        try:
            value = _as_date(row.get("work_date"), "official service date")
        except (TypeError, ValueError):
            blockers.append("scheduling.official_service_date_invalid")
            continue
        if (
            _is_positive_database_identity(assignment_id)
            and assignment_id in assignment_index
        ):
            assignment_start = _as_date(
                assignment_index[assignment_id].get("assignment_start_date"),
                "assignment start date",
            )
            assignment_end = _as_date(
                assignment_index[assignment_id].get("assignment_end_date"),
                "assignment end date",
            )
            if value < assignment_start or value > assignment_end:
                blockers.append("scheduling.official_service_date_outside_assignment")
        official.append(row)
    sorted_official = sorted(
        official,
        key=lambda item: (
            _as_date(item["work_date"], "official service date"),
            item.get("schedule_id")
            if isinstance(item.get("schedule_id"), int)
            and not isinstance(item.get("schedule_id"), bool)
            else 0,
        ),
    )
    dates = [_as_date(item["work_date"], "official service date") for item in sorted_official]
    if len(dates) != len(set(dates)):
        blockers.append("scheduling.official_service_dates_duplicated")
    unique_dates = list(dict.fromkeys(dates))
    if len(unique_dates) != required_days:
        blockers.append("scheduling.official_service_day_count_mismatch")
    if (
        aggregate is None
        or generation is None
        or not assignment_index
        or not official
        or generation.get("generation_status") != "effective"
        or not _is_binary_flag(generation.get("generation_effective_marker"))
        or generation.get("generation_effective_marker") != 1
        or generation.get("generation_resulting_aggregate_version")
        != aggregate.get("aggregate_version")
        or any(
            row.get("assignment_case_no") != case_no
            for row in assignments
            if not isinstance(row.get("assignment_status"), str)
            or row.get("assignment_status") not in _EXCLUDED_ASSIGNMENT_STATUSES
        )
        or any(row.get("schedule_case_no") != case_no for row in official)
        or len(blockers) != starting_blocker_count
    ):
        return unique_dates, None
    payload = {
        "case_no": case_no,
        "order_lifecycle_version": lifecycle_version,
        "scheduling_aggregate_version": aggregate.get("aggregate_version"),
        "generation_id": generation.get("generation_id"),
        "assignments": tuple(
            (row.get("assignment_id"), row.get("assignment_case_no"), row.get("assignment_generation_id"), row.get("assignment_staff_id"), row.get("assignment_status"), _date_text(row.get("assignment_start_date")), _date_text(row.get("assignment_end_date")))
            for row in sorted(assignment_index.values(), key=lambda item: item.get("assignment_id", 0))
        ),
        "official_schedules": tuple(
            (row.get("schedule_id"), row.get("schedule_case_no"), row.get("schedule_generation_id"), row.get("schedule_assignment_id"), row.get("schedule_staff_id"), _date_text(row.get("work_date")))
            for row in sorted_official
        ),
    }
    return unique_dates, f"scheduling-official-service:{fingerprint_payload(payload).value}"


def _service_time_complete(order: Mapping[str, Any], blockers: list[str]) -> bool:
    values = (order.get("service_start_time"), order.get("service_end_time"), order.get("service_end_day_offset"))
    if any(value is None for value in values):
        blockers.append("scheduling.service_time_terms_incomplete")
        return False
    if not _is_mysql_time_of_day(values[0]) or not _is_mysql_time_of_day(values[1]):
        blockers.append("scheduling.service_time_terms_invalid")
        return False
    if type(values[2]) is not int or values[2] not in (0, 1):
        blockers.append("scheduling.service_time_terms_invalid")
        return False
    return True


def _is_mysql_time_of_day(value: Any) -> bool:
    if isinstance(value, time):
        return True
    if not isinstance(value, timedelta):
        return False
    return timedelta(0) <= value < timedelta(days=1)


def _is_binary_flag(value: Any) -> bool:
    return type(value) is int and value in (0, 1)


def _is_positive_database_identity(value: Any) -> bool:
    return (
        type(value) is int
        and 0 < value <= _SIGNED_BIGINT_MAXIMUM
    )


def _status(value: Any) -> OrderLifecycleStatus:
    try:
        return OrderLifecycleStatus(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Orders canonical status is invalid") from error


def _required_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} is invalid")
    return value


def _required_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} is invalid")
    return value


def _optional_date(value: Any, label: str, blockers: list[str], blocker: str) -> date | None:
    if value is None:
        blockers.append(f"{blocker}_missing")
        return None
    try:
        return _as_date(value, label)
    except (TypeError, ValueError):
        blockers.append(f"{blocker}_invalid")
        return None


def _as_date(value: Any, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    raise ValueError(f"{label} is invalid")


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    result = value.isoformat() if hasattr(value, "isoformat") else value
    return result if isinstance(result, str) else None


def _check_case_identity(
    row: Mapping[str, Any],
    case_no: str,
    label: str,
    blockers: list[str] | None = None,
    *,
    field: str = "case_no",
) -> None:
    value = row.get(field)
    if value != case_no:
        if blockers is not None:
            blockers.append(f"{label.lower().replace(' ', '_')}_case_identity_mismatch")
            return
        raise ValueError(f"{label} case identity mismatch")


def _mapping_rows(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{label} readback is invalid")
    rows = tuple(value)
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError(f"{label} readback requires mapping rows")
    return rows


__all__ = ["MySqlHistoricalOrdersSchedulingCompletionReadAdapter"]

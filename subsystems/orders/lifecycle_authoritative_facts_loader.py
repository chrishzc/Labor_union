"""Load locked Orders facts before one lifecycle transition is decided."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from subsystems.orders.lifecycle_authoritative_facts import (
    CANONICAL_LIFECYCLE_TRIGGERS,
    CANONICAL_ORDER_STATUSES,
)

_TAIPEI = ZoneInfo("Asia/Taipei")
_ACTIVE_ASSIGNMENT_STATUSES = frozenset({"active", "planned", "completed"})


@dataclass(frozen=True)
class ClientDepositLifecycleFacts:
    reconciled: bool
    settlement_identity: str | None
    settlement_date: date | None
    blockers: tuple[str, ...] = ()


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, date):
        raise TypeError(f"{field} must be a date or None")
    return value


def _optional_time(value: object, field: str) -> time | None:
    if value is None:
        return None
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        if seconds < 0 or seconds >= 86_400:
            raise ValueError(f"{field} must be a same-day MySQL TIME")
        return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)
    if not isinstance(value, time):
        raise TypeError(f"{field} must be a time or None")
    return value


def _taipei_instant(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TypeError("evaluation_at must be a timezone-aware datetime")
    return value.astimezone(_TAIPEI)


def _reload_locked_order(cursor: Any, envelope: object, case_no: str) -> Mapping[str, Any]:
    cursor.execute("SELECT case_no, status, lifecycle_version, service_days, cancel_reason, actual_start_date, actual_end_date, service_start_time, service_end_time, service_end_day_offset FROM orders WHERE case_no = %s FOR UPDATE", (case_no,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("locked order no longer exists")
    order = _mapping(row, "locked order")
    if order.get("case_no") != case_no:
        raise ValueError("locked order identity differs from command envelope")
    if order.get("lifecycle_version") != getattr(envelope, "lifecycle_version", None):
        raise ValueError("locked order lifecycle_version drifted")
    return order


def _canonical_control_rows(cursor: Any, case_no: str) -> list[Mapping[str, Any]]:
    cursor.execute("SELECT control_type, control_key, scope, state, current_event_id, release_policy, expires_at_utc, confirmed_start_date, deposit_settlement_identity_hash, reason, changed_by FROM order_lifecycle_control_state WHERE case_no = %s ORDER BY control_type, control_key FOR UPDATE", (case_no,))
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TypeError("control state rows must be a sequence")
    return [_mapping(row, f"control_rows[{index}]") for index, row in enumerate(rows)]


def _load_deposit_ledger(cursor: Any, case_no: str) -> tuple[bool, str | None, date | None, list[str]]:
    cursor.execute(
        "SELECT settlement_state,settlement_identity,updated_at "
        "FROM client_deposit_settlement_projection "
        "WHERE case_no=%s FOR UPDATE",
        (case_no,),
    )
    row = cursor.fetchone()
    if row is None:
        return False, None, None, ["enter_service.deposit_settlement_missing"]
    projection = _mapping(row, "deposit settlement projection")
    state = projection.get("settlement_state")
    identity = projection.get("settlement_identity")
    if state == "unsettled" and identity is None:
        return False, None, None, []
    if state != "settled" or not isinstance(identity, str) or len(identity) != 64:
        return False, None, None, ["enter_service.deposit_settlement_inconsistent"]
    settlement_date = _optional_date(projection.get("updated_at"), "deposit settlement updated_at")
    if settlement_date is None:
        return False, None, None, ["enter_service.deposit_settlement_inconsistent"]
    return True, identity, settlement_date, []


def _control_facts(rows: list[Mapping[str, Any]], *, current_status: str, actual_start_date: date | None, deposit_reconciled: bool, settlement_identity: str | None, settlement_date: date | None) -> tuple[bool, str | None, bool, dict[str, list[str]]]:
    cancellation, reason, reconfirmed = current_status == "訂單取消", None, False
    blockers: dict[str, list[str]] = {"enter_service": [], "auto_complete": []}
    for row in rows:
        control_type, state = row.get("control_type"), row.get("state")
        if state != "active":
            continue
        scope = row.get("scope")
        if scope in blockers:
            blockers[scope].append(f"{scope}.{row.get('control_key')}_active")
        if control_type == "cancellation":
            cancellation, reason = True, _required_text(row.get("reason"), "cancellation reason")
        if control_type == "actual_start_reconfirmation":
            required = row.get("confirmed_start_date")
            reconfirmed = actual_start_date is not None and deposit_reconciled and settlement_identity is not None and settlement_date is not None and required == actual_start_date
    if cancellation:
        blockers["enter_service"].append("enter_service.order_cancelled")
    return cancellation, reason, reconfirmed, blockers


def _load_effective_completion_facts(
    cursor: Any,
    case_no: str,
    service_day_count: int,
    actual_end_date: date | None,
) -> tuple[int | None, tuple[date, ...], list[str]]:
    generation_id = _lock_effective_generation_id(cursor, case_no)
    if generation_id is None:
        return None, (), ["auto_complete.effective_generation_missing"]
    assignments = _lock_effective_assignments(cursor, generation_id)
    schedules = _lock_effective_service_schedules(cursor, case_no, generation_id)
    return generation_id, _official_dates(schedules), _completion_root_blockers(
        assignments,
        schedules,
        service_day_count,
        actual_end_date,
    )


def _lock_effective_generation_id(cursor: Any, case_no: str) -> int | None:
    cursor.execute(
        "SELECT effective_generation_id FROM scheduling_aggregates "
        "WHERE case_no=%s FOR UPDATE",
        (case_no,),
    )
    aggregate = cursor.fetchone()
    if aggregate is None:
        return None
    generation_value = _mapping(aggregate, "scheduling aggregate").get(
        "effective_generation_id"
    )
    if generation_value is None:
        return None
    if isinstance(generation_value, bool) or not isinstance(generation_value, int):
        raise ValueError("effective scheduling generation identity is invalid")
    cursor.execute(
        "SELECT id FROM scheduling_generations "
        "WHERE id=%s AND case_no=%s AND status='effective' "
        "AND effective_marker=1 FOR UPDATE",
        (generation_value, case_no),
    )
    generation = cursor.fetchone()
    if generation is None:
        return None
    return int(_mapping(generation, "effective scheduling generation")["id"])


def _lock_effective_assignments(cursor: Any, generation_id: int) -> tuple[Mapping[str, Any], ...]:
    cursor.execute(
        "SELECT id,status FROM case_staff_assignments "
        "WHERE generation_id=%s ORDER BY id FOR UPDATE",
        (generation_id,),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence):
        raise TypeError("effective assignment rows must be a sequence")
    return tuple(_mapping(row, f"effective_assignment[{index}]") for index, row in enumerate(rows))


def _lock_effective_service_schedules(
    cursor: Any,
    case_no: str,
    generation_id: int,
) -> tuple[Mapping[str, Any], ...]:
    cursor.execute(
        "SELECT id,assignment_id,work_date FROM staff_schedule "
        "WHERE case_no=%s AND generation_id=%s AND effective_marker=1 "
        "AND is_work_day=1 ORDER BY work_date,id FOR UPDATE",
        (case_no, generation_id),
    )
    rows = cursor.fetchall()
    if not isinstance(rows, Sequence):
        raise TypeError("effective service schedule rows must be a sequence")
    return tuple(_mapping(row, f"effective_service_schedule[{index}]") for index, row in enumerate(rows))


def _official_dates(schedules: tuple[Mapping[str, Any], ...]) -> tuple[date, ...]:
    return tuple(_optional_date(row.get("work_date"), "official service date") for row in schedules if row.get("work_date") is not None)


def _completion_root_blockers(
    assignments: tuple[Mapping[str, Any], ...],
    schedules: tuple[Mapping[str, Any], ...],
    service_day_count: int,
    actual_end_date: date | None,
) -> list[str]:
    assignment_ids = {row.get("id") for row in assignments}
    dates = _official_dates(schedules)
    blockers: list[str] = []
    if not assignments or any(row.get("status") not in _ACTIVE_ASSIGNMENT_STATUSES for row in assignments):
        blockers.append("auto_complete.effective_assignment_facts_inconsistent")
    if not schedules:
        blockers.append("auto_complete.official_service_days_missing")
    if any(row.get("assignment_id") not in assignment_ids for row in schedules):
        blockers.append("auto_complete.official_service_owner_inconsistent")
    if len(dates) != len(set(dates)):
        blockers.append("auto_complete.official_service_days_duplicated")
    if len(dates) != service_day_count:
        blockers.append("auto_complete.official_service_day_count_mismatch")
    if dates and actual_end_date != max(dates):
        blockers.append("auto_complete.actual_end_date_drift")
    return blockers


def _completion_instant(actual_end_date: date | None, start: time | None, end: time | None, offset: object) -> tuple[datetime | None, list[str]]:
    if actual_end_date is None:
        return None, ["auto_complete.actual_end_date_missing"]
    if start is None and end is None and offset is None:
        return datetime.combine(actual_end_date, time.max, _TAIPEI), []
    if start is None or end is None or offset not in {0, 1}:
        return None, ["auto_complete.service_time_terms_incomplete"]
    return datetime.combine(actual_end_date + timedelta(days=offset), end, _TAIPEI), []


def load_order_lifecycle_authoritative_facts(cursor: Any, command_envelope: object, trigger_event: str, evaluation_at: datetime, manual_correction_target: str | None = None, deposit_facts: ClientDepositLifecycleFacts | None = None) -> dict[str, Any]:
    """Read the lock-held root facts; this function never commits or mutates."""
    if not callable(getattr(cursor, "execute", None)):
        raise TypeError("cursor must provide execute()")
    if getattr(command_envelope, "cursor", None) is not cursor:
        raise ValueError("command envelope belongs to another cursor")
    case_no = _required_text(getattr(command_envelope, "case_no", None), "case_no")
    if trigger_event not in CANONICAL_LIFECYCLE_TRIGGERS:
        raise ValueError("trigger_event is not canonical")
    if manual_correction_target is not None and (trigger_event != "manual_correction" or manual_correction_target not in CANONICAL_ORDER_STATUSES):
        raise ValueError("manual_correction_target requires a typed correction command")
    if trigger_event == "manual_correction" and manual_correction_target is None:
        raise ValueError("manual correction requires a canonical target")
    order = _reload_locked_order(cursor, command_envelope, case_no); status = order.get("status")
    if status not in CANONICAL_ORDER_STATUSES: raise ValueError("command envelope current_status is not canonical")
    evaluation = _taipei_instant(evaluation_at); actual_start = _optional_date(order.get("actual_start_date"), "actual_start_date"); actual_end = _optional_date(order.get("actual_end_date"), "actual_end_date")
    controls = _canonical_control_rows(cursor, case_no)
    deposit = deposit_facts or ClientDepositLifecycleFacts(*_load_deposit_ledger(cursor, case_no))
    service_days = _nonnegative_int(order.get("service_days"), "service_days")
    if service_days < 1:
        raise ValueError("service_days must be positive")
    generation_id, official_dates, completion_blockers = _load_effective_completion_facts(
        cursor,
        case_no,
        service_days,
        actual_end,
    )
    completion, time_blockers = _completion_instant(actual_end, _optional_time(order.get("service_start_time"), "service_start_time"), _optional_time(order.get("service_end_time"), "service_end_time"), order.get("service_end_day_offset"))
    cancellation, reason, reconfirmed, blockers = _control_facts(controls, current_status=status, actual_start_date=actual_start, deposit_reconciled=deposit.reconciled, settlement_identity=deposit.settlement_identity, settlement_date=deposit.settlement_date)
    blockers["enter_service"].extend(deposit.blockers); blockers["auto_complete"].extend(completion_blockers + time_blockers)
    facts = {"cancellation":cancellation,"cancellation_reason":reason,"deposit_reconciled":deposit.reconciled,"deposit_settlement_identity":deposit.settlement_identity,"actual_start_date":actual_start.isoformat() if actual_start else None,"actual_end_date":actual_end.isoformat() if actual_end else None,"evaluation_at":evaluation.isoformat(),"completion_instant":completion.isoformat() if completion else None,"completion_facts_consistent":not completion_blockers and not time_blockers,"actual_start_reconfirmed":reconfirmed,"effective_scheduling_generation_id":generation_id,"official_service_dates":tuple(value.isoformat() for value in official_dates),"transition_blockers":{key:tuple(sorted(set(value))) for key,value in blockers.items()},"manual_correction_target":manual_correction_target}
    return {"locked_order":dict(order), "authoritative_facts":facts, "existing_event":getattr(command_envelope, "existing_lifecycle_event", None)}

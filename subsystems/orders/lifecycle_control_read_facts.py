"""
File: subsystems/orders/lifecycle_control_read_facts.py
Description: 唯讀載入訂單生命週期控制事實，接受待補件但不賦予後續流程資格。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
import json
from typing import Any, Literal

_CANONICAL_STATUSES = frozenset({"待補件", "洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"})


class OrderLifecycleControlReadNotFoundError(LookupError):
    """Raised when the requested order does not exist."""


@dataclass(frozen=True)
class ActualStartControlReadFacts:
    state: Literal["active", "cleared"] | None
    current_event_id: int | None
    required_date: str | None
    required_settlement_identity: str | None


@dataclass(frozen=True)
class OrderLifecycleControlReadFacts:
    case_no: str
    lifecycle_version: int
    canonical_status: str
    current_actual_start_date: str | None
    actual_start_control: ActualStartControlReadFacts
    deposit_reconciled: bool
    deposit_settlement_identity: str | None
    deposit_settlement_date: str | None
    deposit_blockers: tuple[str, ...]


def _canonical_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    return value


def _rows(value: object, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{field} must be a sequence")
    return [_mapping(row, f"{field}[{index}]") for index, row in enumerate(value)]


def _iso_date(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        raise ValueError(f"{field} must be a date")
    return value.isoformat()


def _payload_object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, str):
        raise ValueError("control payload_snapshot must be JSON")
    try:
        return _mapping(json.loads(value), "control payload_snapshot")
    except json.JSONDecodeError as error:
        raise ValueError("control payload_snapshot must be JSON") from error


def _load_actual_start_control(cursor: Any, case_no: str) -> ActualStartControlReadFacts:
    cursor.execute("SELECT current_state.state, current_state.current_event_id,\n                  control_event.action, control_event.payload_snapshot\n           FROM order_lifecycle_control_state AS current_state\n           JOIN order_lifecycle_control_events AS control_event\n             ON control_event.id = current_state.current_event_id\n            AND control_event.case_no = current_state.case_no\n            AND control_event.control_type = current_state.control_type\n            AND control_event.control_key = current_state.control_key\n           WHERE current_state.case_no = %s\n             AND current_state.control_type = 'actual_start_reconfirmation'\n             AND current_state.control_key = 'actual_start_reconfirmation'", (case_no,))
    value = cursor.fetchone()
    if value is None:
        return ActualStartControlReadFacts(None, None, None, None)
    row = _mapping(value, "actual-start control")
    state, action = row.get("state"), row.get("action")
    if state not in {"active", "cleared"}: raise ValueError("actual-start control state is unsupported")
    if (state, action) not in {("active", "activate"), ("cleared", "clear")}:
        raise ValueError("actual-start control event does not match projection")
    event_id = _positive_int(row.get("current_event_id"), "current_event_id")
    payload = _payload_object(row.get("payload_snapshot"))
    if state == "active":
        return ActualStartControlReadFacts(state, event_id, _iso_date(payload.get("actual_start_date"), "required actual_start_date"), _canonical_text(payload.get("deposit_settlement_identity"), "required deposit_settlement_identity"))
    value = payload.get("deposit_settlement_identity")
    return ActualStartControlReadFacts(state, event_id, _iso_date(payload.get("original_actual_start_date"), "original actual_start_date", optional=True), None if value is None else _canonical_text(value, "confirmed deposit_settlement_identity"))


def _load_deposit_settlement(cursor: Any, case_no: str) -> tuple[bool, str | None, str | None, tuple[str, ...]]:
    cursor.execute(
        "SELECT settlement_state,settlement_identity,updated_at "
        "FROM client_deposit_settlement_projection WHERE case_no=%s",
        (case_no,),
    )
    row = cursor.fetchone()
    if row is None:
        return False, None, None, ("enter_service.deposit_settlement_missing",)
    projection = _mapping(row, "deposit settlement projection")
    state = projection.get("settlement_state")
    identity = projection.get("settlement_identity")
    updated_at = projection.get("updated_at")
    if state == "unsettled" and identity is None:
        return False, None, None, ()
    if state != "settled" or not isinstance(identity, str) or len(identity) != 64:
        return False, None, None, ("enter_service.deposit_settlement_inconsistent",)
    if not isinstance(updated_at, datetime):
        return False, None, None, ("enter_service.deposit_settlement_inconsistent",)
    return True, identity, updated_at.date().isoformat(), ()


def load_order_lifecycle_control_read_facts(cursor: Any, case_no: str, as_of: datetime) -> OrderLifecycleControlReadFacts:
    """Load one bounded, non-locking canonical control-read snapshot."""
    if not callable(getattr(cursor, "execute", None)): raise TypeError("cursor must provide execute")
    if not callable(getattr(cursor, "fetchone", None)): raise TypeError("cursor must provide fetchone")
    if not callable(getattr(cursor, "fetchall", None)): raise TypeError("cursor must provide fetchall")
    case_no = _canonical_text(case_no, "case_no")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None: raise TypeError("as_of must be a timezone-aware datetime")
    if as_of.utcoffset() is None: raise ValueError("as_of must have a valid UTC offset")
    cursor.execute("SELECT case_no, status, lifecycle_version, actual_start_date\n           FROM orders\n           WHERE case_no = %s", (case_no,))
    order_value = cursor.fetchone()
    if order_value is None: raise OrderLifecycleControlReadNotFoundError(f"order {case_no} does not exist")
    order = _mapping(order_value, "order")
    if order.get("case_no") != case_no: raise ValueError("order identity differs from case_no")
    status = order.get("status")
    if status not in _CANONICAL_STATUSES: raise ValueError("order status is not canonical")
    control = _load_actual_start_control(cursor, case_no)
    reconciled, identity, settlement_date, blockers = _load_deposit_settlement(cursor, case_no)
    return OrderLifecycleControlReadFacts(case_no, _nonnegative_int(order.get("lifecycle_version"), "lifecycle_version"), str(status), _iso_date(order.get("actual_start_date"), "actual_start_date", optional=True), control, reconciled, identity, settlement_date, tuple(sorted(set(blockers))))

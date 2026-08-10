"""Expose the side-effect-free Orders lifecycle control read projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.business_time import current_business_instant
from subsystems.orders.lifecycle_control_read_facts import (
    OrderLifecycleControlReadNotFoundError,
    load_order_lifecycle_control_read_facts,
)

_INACTIVE_BLOCKER = "enter_service.actual_start_reconfirmation_inactive"


@dataclass(frozen=True)
class ActualStartReconfirmationControlState:
    state: Literal["not_required", "active", "cleared"]
    required_date: str | None
    current_actual_start_date: str | None
    blockers: tuple[str, ...]
    can_reconfirm: bool


@dataclass(frozen=True)
class OrderLifecycleControlState:
    case_no: str
    lifecycle_version: int
    canonical_status: str
    actual_start_reconfirmation: ActualStartReconfirmationControlState


def get_order_lifecycle_control_state(case_no: str) -> OrderLifecycleControlState:
    """Return one immutable, side-effect-free canonical control snapshot."""
    evaluation_at = current_business_instant()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            facts = load_order_lifecycle_control_read_facts(cursor=cursor, case_no=case_no, as_of=evaluation_at)
    finally:
        connection.close()
    control = facts.actual_start_control
    state = "not_required" if control.state is None else control.state
    blockers = list(facts.deposit_blockers)
    if state != "active": blockers.append(_INACTIVE_BLOCKER)
    if facts.canonical_status == "訂單取消": blockers.append("enter_service.order_cancelled")
    if facts.current_actual_start_date is None: blockers.append("enter_service.actual_start_date_missing")
    if state == "active" and control.required_date != facts.current_actual_start_date: blockers.append("enter_service.actual_start_date_changed")
    if state == "active" and control.required_settlement_identity != facts.deposit_settlement_identity: blockers.append("enter_service.deposit_settlement_identity_changed")
    canonical_blockers = tuple(sorted(set(blockers)))
    actual_start = ActualStartReconfirmationControlState(state, control.required_date, facts.current_actual_start_date, canonical_blockers, state == "active" and facts.deposit_reconciled and facts.canonical_status != "訂單取消" and facts.current_actual_start_date is not None and not canonical_blockers)
    return OrderLifecycleControlState(facts.case_no, facts.lifecycle_version, facts.canonical_status, actual_start)


__all__ = ["ActualStartReconfirmationControlState", "OrderLifecycleControlReadNotFoundError", "OrderLifecycleControlState", "get_order_lifecycle_control_state", "load_order_lifecycle_control_read_facts"]

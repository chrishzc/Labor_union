"""
File: subsystems/orders/order_lifecycle_command_envelope.py
Description: 鎖定訂單生命週期命令事實，待補件案件一律拒絕進入後續命令。
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import re

_CANONICAL_STATUSES = frozenset({
    "待補件", "洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消",
    "歷史訂單－未服務", "歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成",
})
_CONTROL_TYPES = frozenset({"cancellation", "actual_start_reconfirmation", "human_hold"})
_CONTROL_SCOPES = frozenset({"order", "enter_service", "auto_complete"})
_CONTROL_STATES = frozenset({"active", "cleared"})
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_ORDER_KEYS = frozenset({"case_no", "status", "lifecycle_version", "service_days", "cancel_reason", "actual_start_date", "actual_end_date", "service_start_time", "service_end_time", "service_end_day_offset"})
_CONTROL_STATE_KEYS = frozenset({"control_type", "control_key", "scope", "state", "current_event_id", "release_policy", "expires_at_utc", "confirmed_start_date", "deposit_settlement_identity_hash", "reason", "changed_by"})
_CONTROL_EVENT_KEYS = frozenset({"id", "case_no", "control_type", "control_key", "scope", "action", "actor", "reason", "expected_version", "idempotency_key", "payload_hash", "payload_snapshot"})
_LIFECYCLE_EVENT_KEYS = frozenset({"id", "case_no", "trigger_event", "before_status", "after_status", "actor", "business_date", "expected_version", "idempotency_key", "facts_snapshot"})


@dataclass(frozen=True)
class OrderLifecycleCommandEnvelope:
    cursor: Any
    case_no: str
    current_status: str
    lifecycle_version: int
    service_days: int
    cancel_reason: str | None
    actual_start_date: object
    actual_end_date: object
    service_start_time: object
    service_end_time: object
    service_end_day_offset: int | None
    idempotency_key: str
    request_expected_version: int
    control_states: tuple[Mapping[str, object], ...]
    existing_control_event: Mapping[str, object] | None
    existing_lifecycle_event: Mapping[str, object] | None


def _required_text(value: object, field: str) -> str:
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


def _exact_mapping(value: object, keys: frozenset[str], field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping")
    if set(value) != keys:
        raise ValueError(f"{field} has an unexpected row shape")
    return value


def _optional_exact_mapping(value: object, keys: frozenset[str], field: str) -> Mapping[str, object] | None:
    return None if value is None else _exact_mapping(value, keys, field)


def _freeze_row(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _validate_control_state(row: Mapping[str, object]) -> None:
    control_type, control_key = row["control_type"], _required_text(row["control_key"], "control_key")
    scope, state = row["scope"], row["state"]
    if control_type not in _CONTROL_TYPES: raise ValueError("control state has unsupported control_type")
    if scope not in _CONTROL_SCOPES: raise ValueError("control state has unsupported scope")
    if state not in _CONTROL_STATES: raise ValueError("control state has unsupported state")
    _positive_int(row["current_event_id"], "current_event_id")
    _required_text(row["reason"], "control state reason")
    _required_text(row["changed_by"], "control state changed_by")
    policy, expires, confirmed, settlement = (row[key] for key in ("release_policy", "expires_at_utc", "confirmed_start_date", "deposit_settlement_identity_hash"))
    if settlement is not None and (not isinstance(settlement, str) or not _HASH_PATTERN.fullmatch(settlement)):
        raise ValueError("control state settlement hash is not canonical")
    if control_type == "cancellation":
        if (control_key, scope, policy, expires, confirmed, settlement) != ("order_cancelled", "order", None, None, None, None):
            raise ValueError("cancellation control projection is inconsistent")
        return
    if control_type == "actual_start_reconfirmation":
        valid = control_key == "actual_start_reconfirmation" and scope == "enter_service" and policy is None and expires is None
        valid = valid and ((state == "active" and confirmed is None and settlement is None) or (state == "cleared" and confirmed is not None and settlement is not None))
        if not valid: raise ValueError("actual-start control projection is inconsistent")
        return
    valid = scope in {"enter_service", "auto_complete"} and confirmed is None and settlement is None and policy in {"manual", "expires_at"}
    valid = valid and ((policy == "manual" and expires is None) or (policy == "expires_at" and expires is not None))
    if not valid: raise ValueError("human-hold control projection is inconsistent")


def _validate_order_row(
    row: Mapping[str, object],
    case_no: str,
    *,
    allow_incomplete_order: bool = False,
) -> tuple[str, int, int]:
    if type(allow_incomplete_order) is not bool:
        raise TypeError("allow_incomplete_order must be a bool")
    if row["case_no"] != case_no: raise ValueError("locked order identity differs from case_no")
    status = row["status"]
    if status not in _CANONICAL_STATUSES: raise ValueError("locked order status is not canonical")
    if status == "待補件" and not allow_incomplete_order: raise ValueError("pending-completion order cannot enter lifecycle commands")
    version = _nonnegative_int(row["lifecycle_version"], "lifecycle_version")
    raw_service_days = row["service_days"]
    if allow_incomplete_order and raw_service_days is None:
        service_days = 0
    elif allow_incomplete_order:
        service_days = _nonnegative_int(raw_service_days, "service_days")
    else:
        service_days = _positive_int(raw_service_days, "service_days")
    if row["cancel_reason"] is not None and not isinstance(row["cancel_reason"], str): raise TypeError("cancel_reason must be a string or None")
    terms = (row["service_start_time"], row["service_end_time"], row["service_end_day_offset"])
    if not allow_incomplete_order and not all(value is None for value in terms) and any(value is None for value in terms): raise ValueError("order service time terms are partially populated")
    offset = row["service_end_day_offset"]
    if offset is not None and (isinstance(offset, bool) or not isinstance(offset, int) or offset not in {0, 1}): raise ValueError("service_end_day_offset must be 0, 1, or None")
    return str(status), version, service_days


def _validate_control_event(row: Mapping[str, object], *, case_no: str, idempotency_key: str) -> None:
    _positive_int(row["id"], "existing control event id")
    if row["case_no"] != case_no or row["idempotency_key"] != idempotency_key: raise ValueError("existing control event identity differs")
    if row["control_type"] not in _CONTROL_TYPES: raise ValueError("existing control event type is unsupported")
    _required_text(row["control_key"], "existing control event key")
    if row["scope"] not in _CONTROL_SCOPES: raise ValueError("existing control event scope is unsupported")
    if row["action"] not in {"activate", "clear"}: raise ValueError("existing control event action is unsupported")
    _nonnegative_int(row["expected_version"], "control event expected_version")
    if not isinstance(row["payload_hash"], str) or not _HASH_PATTERN.fullmatch(row["payload_hash"]): raise ValueError("existing control event payload hash is not canonical")


def _validate_lifecycle_event(row: Mapping[str, object], *, case_no: str, idempotency_key: str) -> int:
    _positive_int(row["id"], "existing lifecycle event id")
    if row["case_no"] != case_no or row["idempotency_key"] != idempotency_key: raise ValueError("existing lifecycle event identity differs")
    if row["before_status"] not in _CANONICAL_STATUSES or row["after_status"] not in _CANONICAL_STATUSES: raise ValueError("existing lifecycle event status is not canonical")
    _required_text(row["trigger_event"], "existing lifecycle trigger")
    _required_text(row["actor"], "existing lifecycle actor")
    return _nonnegative_int(row["expected_version"], "existing lifecycle expected_version")


def lock_order_lifecycle_command_envelope(
    cursor: Any,
    case_no: str,
    expected_version: int,
    idempotency_key: str,
    *,
    allow_incomplete_order: bool = False,
) -> OrderLifecycleCommandEnvelope:
    """Lock canonical aggregate rows without owning the caller transaction."""
    if not callable(getattr(cursor, "execute", None)): raise TypeError("cursor must provide execute()")
    if not callable(getattr(cursor, "fetchone", None)) or not callable(getattr(cursor, "fetchall", None)): raise TypeError("cursor must provide fetchone() and fetchall()")
    case_no = _required_text(case_no, "case_no")
    request_expected_version = _nonnegative_int(expected_version, "expected_version")
    idempotency_key = _required_text(idempotency_key, "idempotency_key")
    if type(allow_incomplete_order) is not bool:
        raise TypeError("allow_incomplete_order must be a bool")
    cursor.execute("SELECT case_no, status, lifecycle_version, service_days, cancel_reason,\n                  actual_start_date, actual_end_date, service_start_time,\n                  service_end_time, service_end_day_offset\n           FROM orders\n           WHERE case_no = %s\n           FOR UPDATE", (case_no,))
    order_value = cursor.fetchone()
    if order_value is None: raise ValueError("order does not exist")
    order = _exact_mapping(order_value, _ORDER_KEYS, "locked order")
    current_status, lifecycle_version, service_days = _validate_order_row(
        order, case_no, allow_incomplete_order=allow_incomplete_order
    )
    cursor.execute("SELECT control_type, control_key, scope, state, current_event_id,\n                  release_policy, expires_at_utc, confirmed_start_date,\n                  deposit_settlement_identity_hash, reason, changed_by\n           FROM order_lifecycle_control_state\n           WHERE case_no = %s\n           ORDER BY control_type, control_key\n           FOR UPDATE", (case_no,))
    state_values = cursor.fetchall()
    if not isinstance(state_values, Sequence) or isinstance(state_values, (str, bytes)): raise TypeError("control state query must return a sequence")
    control_states, identities = [], []
    for index, value in enumerate(state_values):
        row = _exact_mapping(value, _CONTROL_STATE_KEYS, f"control_states[{index}]")
        _validate_control_state(row)
        identity = (str(row["control_type"]), str(row["control_key"]))
        if identity in identities: raise ValueError("control state identity is duplicated")
        identities.append(identity); control_states.append(_freeze_row(row))
    if identities != sorted(identities): raise ValueError("control states are not in canonical order")
    cursor.execute("SELECT id, case_no, control_type, control_key, scope, action,\n                  actor, reason, expected_version, idempotency_key,\n                  payload_hash, payload_snapshot\n           FROM order_lifecycle_control_events\n           WHERE case_no = %s AND idempotency_key = %s\n           FOR UPDATE", (case_no, idempotency_key))
    control_event = _optional_exact_mapping(cursor.fetchone(), _CONTROL_EVENT_KEYS, "existing control event")
    if control_event is not None: _validate_control_event(control_event, case_no=case_no, idempotency_key=idempotency_key)
    cursor.execute("SELECT id, case_no, trigger_event, before_status, after_status,\n                  actor, business_date, expected_version, idempotency_key,\n                  facts_snapshot\n           FROM order_lifecycle_state_events\n           WHERE case_no = %s AND idempotency_key = %s\n           FOR UPDATE", (case_no, idempotency_key))
    lifecycle_event = _optional_exact_mapping(cursor.fetchone(), _LIFECYCLE_EVENT_KEYS, "existing lifecycle event")
    if lifecycle_event is None:
        if control_event is not None: raise ValueError("control idempotency event has no lifecycle decision event")
        if request_expected_version != lifecycle_version: raise ValueError("expected_version differs from locked lifecycle_version")
    else:
        persisted_expected_version = _validate_lifecycle_event(lifecycle_event, case_no=case_no, idempotency_key=idempotency_key)
        if request_expected_version != persisted_expected_version or lifecycle_version != persisted_expected_version + 1 or current_status != lifecycle_event["after_status"]: raise ValueError("lifecycle replay aggregate identity differs")
    if control_event is not None:
        if control_event["expected_version"] != request_expected_version: raise ValueError("control replay expected_version differs")
        matching_state = next((row for row in control_states if row["control_type"] == control_event["control_type"] and row["control_key"] == control_event["control_key"]), None)
        if matching_state is None or matching_state["current_event_id"] != control_event["id"]: raise ValueError("control replay projection is partial or stale")
    return OrderLifecycleCommandEnvelope(cursor, case_no, current_status, lifecycle_version, service_days, order["cancel_reason"], order["actual_start_date"], order["actual_end_date"], order["service_start_time"], order["service_end_time"], order["service_end_day_offset"], idempotency_key, request_expected_version, tuple(control_states), None if control_event is None else _freeze_row(control_event), None if lifecycle_event is None else _freeze_row(lifecycle_event))

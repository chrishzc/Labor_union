"""Append idempotent Orders lifecycle-control events and projections."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Literal, Mapping, TypeAlias

OrderLifecycleControlCommand: TypeAlias = "CancellationControlCommand | ActualStartReconfirmationRequiredCommand | ActualStartReconfirmationConfirmedCommand | HumanHoldActivateCommand | HumanHoldReleaseCommand"

class OrderLifecycleControlConflict(ValueError): pass
class OrderLifecycleControlConcurrencyError(RuntimeError): pass
class OrderLifecycleControlStateError(ValueError): pass

@dataclass(frozen=True)
class CancellationControlCommand:
    action: Literal["activate", "clear"]; actor: str; reason: str; expected_version: int; idempotency_key: str
@dataclass(frozen=True)
class ActualStartReconfirmationRequiredCommand:
    actor: str; reason: str; expected_version: int; idempotency_key: str; actual_start_date: date | str; deposit_settlement_identity: str
@dataclass(frozen=True)
class ActualStartReconfirmationConfirmedCommand:
    actor: str; reason: str; expected_version: int; idempotency_key: str; original_actual_start_date: date | str; new_actual_start_date: date | str; deposit_settlement_identity: str; preview_request_hash: str; assignment_apply_receipt: Mapping[str, object]
@dataclass(frozen=True)
class HumanHoldActivateCommand:
    control_key: str; scope: Literal["enter_service", "auto_complete"]; actor: str; reason: str; expected_version: int; idempotency_key: str; release_policy: Literal["manual", "expires_at"]; expires_at: datetime | None = None
@dataclass(frozen=True)
class HumanHoldReleaseCommand:
    control_key: str; scope: Literal["enter_service", "auto_complete"]; actor: str; reason: str; expected_version: int; idempotency_key: str

@dataclass(frozen=True)
class OrderLifecycleControlProjection:
    case_no: str; control_type: str; control_key: str; scope: str; state: Literal["active", "cleared"]; current_event_id: int; release_policy: str | None; expires_at_utc: datetime | None; confirmed_start_date: str | None; deposit_settlement_identity_hash: str | None; reason: str; changed_by: str
@dataclass(frozen=True)
class OrderLifecycleControlResult:
    outcome: Literal["created", "existing"]; event_id: int; projection: OrderLifecycleControlProjection
@dataclass(frozen=True)
class _NormalizedCommand:
    control_type: str; control_key: str; scope: str; action: str; actor: str; reason: str; expected_version: int; idempotency_key: str; payload: Mapping[str, object]; state: Literal["active", "cleared"]; release_policy: str | None; expires_at_utc: datetime | None; confirmed_start_date: str | None; deposit_settlement_identity_hash: str | None

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

def _text(value: object, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > maximum: raise OrderLifecycleControlStateError(f"{field} must be a bounded canonical string")
    return value
def _nonnegative(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0: raise OrderLifecycleControlStateError(f"{field} must be a non-negative integer")
    return value
def _date(value: object, field: str) -> str:
    if isinstance(value, datetime): value = value.date()
    if isinstance(value, date): return value.isoformat()
    if isinstance(value, str):
        try: return date.fromisoformat(value).isoformat()
        except ValueError: pass
    raise OrderLifecycleControlStateError(f"{field} must be an ISO date")
def _hash(value: object, field: str) -> str:
    value = _text(value, field, 64)
    if not _SHA256_RE.fullmatch(value): raise OrderLifecycleControlStateError(f"{field} must be a SHA-256 hex digest")
    return value
def _canonical_json(value: object, field: str) -> str:
    if not isinstance(value, Mapping): raise OrderLifecycleControlStateError(f"{field} must be a mapping")
    try: return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error: raise OrderLifecycleControlStateError(f"{field} must be JSON-safe") from error
def _utc_expiry(value: object, policy: str) -> tuple[datetime | None, str | None]:
    if policy == "manual":
        if value is not None: raise OrderLifecycleControlStateError("manual hold must not expire")
        return None, None
    if policy != "expires_at" or not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None: raise OrderLifecycleControlStateError("expires_at hold requires a timezone-aware expiry")
    instant = value.astimezone(timezone.utc)
    return instant, instant.isoformat()

def _normalize_command(command: OrderLifecycleControlCommand, actual_start: object, *, validate_current_actual_start_date: bool = True) -> _NormalizedCommand:
    if not isinstance(command, (CancellationControlCommand, ActualStartReconfirmationRequiredCommand, ActualStartReconfirmationConfirmedCommand, HumanHoldActivateCommand, HumanHoldReleaseCommand)): raise TypeError("command must be a typed order lifecycle control command")
    actor, reason, version, key = _text(command.actor, "actor", 100), _text(command.reason, "reason", 1000), _nonnegative(command.expected_version, "expected_version"), _text(command.idempotency_key, "idempotency_key", 255)
    if isinstance(command, CancellationControlCommand):
        if command.action not in {"activate", "clear"}: raise OrderLifecycleControlStateError("cancellation action is unsupported")
        return _NormalizedCommand("cancellation", "order_cancelled", "order", command.action, actor, reason, version, key, {}, "active" if command.action == "activate" else "cleared", None, None, None, None)
    if isinstance(command, ActualStartReconfirmationRequiredCommand):
        actual = _date(command.actual_start_date, "actual_start_date")
        if validate_current_actual_start_date and actual != _date(actual_start, "command_envelope.actual_start_date"): raise OrderLifecycleControlConflict("required reconfirmation date must match the locked actual_start_date")
        settlement = _text(command.deposit_settlement_identity, "deposit_settlement_identity", 128)
        return _NormalizedCommand("actual_start_reconfirmation", "actual_start_reconfirmation", "enter_service", "activate", actor, reason, version, key, {"actual_start_date": actual, "deposit_settlement_identity": settlement}, "active", None, None, None, None)
    if isinstance(command, ActualStartReconfirmationConfirmedCommand):
        original, new = _date(command.original_actual_start_date, "original_actual_start_date"), _date(command.new_actual_start_date, "new_actual_start_date")
        if validate_current_actual_start_date and original != _date(actual_start, "command_envelope.actual_start_date"): raise OrderLifecycleControlConflict("original_actual_start_date must match the locked aggregate")
        settlement = _text(command.deposit_settlement_identity, "deposit_settlement_identity", 128)
        payload = {"original_actual_start_date": original, "new_actual_start_date": new, "deposit_settlement_identity": settlement, "preview_request_hash": _hash(command.preview_request_hash, "preview_request_hash"), "assignment_apply_receipt": json.loads(_canonical_json(command.assignment_apply_receipt, "assignment_apply_receipt"))}
        return _NormalizedCommand("actual_start_reconfirmation", "actual_start_reconfirmation", "enter_service", "clear", actor, reason, version, key, payload, "cleared", None, None, new, hashlib.sha256(settlement.encode()).hexdigest())
    control_key, scope = _text(command.control_key, "control_key", 100), command.scope
    if control_key in {"order_cancelled", "actual_start_reconfirmation"}: raise OrderLifecycleControlStateError("human hold control_key is reserved")
    if scope not in {"enter_service", "auto_complete"}: raise OrderLifecycleControlStateError("human hold scope is unsupported")
    if isinstance(command, HumanHoldReleaseCommand): return _NormalizedCommand("human_hold", control_key, scope, "clear", actor, reason, version, key, {}, "cleared", None, None, None, None)
    expiry, expiry_payload = _utc_expiry(command.expires_at, command.release_policy)
    return _NormalizedCommand("human_hold", control_key, scope, "activate", actor, reason, version, key, {"release_policy": command.release_policy, "expires_at_utc": expiry_payload}, "active", command.release_policy, expiry, None, None)

def _projection(command: _NormalizedCommand, case_no: str, event_id: int) -> OrderLifecycleControlProjection:
    return OrderLifecycleControlProjection(case_no, command.control_type, command.control_key, command.scope, command.state, event_id, command.release_policy, command.expires_at_utc, command.confirmed_start_date, command.deposit_settlement_identity_hash, command.reason, command.actor)

def apply_order_lifecycle_control_command(cursor: object, command_envelope: object, command: OrderLifecycleControlCommand) -> OrderLifecycleControlResult:
    """Append one typed control event and CAS its current projection."""
    if getattr(command_envelope, "cursor", None) is not cursor: raise ValueError("cursor must be the command envelope cursor")
    case_no, envelope_key = _text(getattr(command_envelope, "case_no", None), "case_no"), _text(getattr(command_envelope, "idempotency_key", None), "command_envelope.idempotency_key", 255)
    request_version, current_version = _nonnegative(getattr(command_envelope, "request_expected_version", None), "command_envelope.request_expected_version"), _nonnegative(getattr(command_envelope, "lifecycle_version", None), "command_envelope.lifecycle_version")
    normalized = _normalize_command(command, getattr(command_envelope, "actual_start_date", None), validate_current_actual_start_date=getattr(command_envelope, "existing_control_event", None) is None)
    if normalized.idempotency_key != envelope_key: raise OrderLifecycleControlConflict("idempotency_key must match the command envelope")
    if normalized.expected_version != request_version: raise OrderLifecycleControlConflict("expected_version must match the command envelope")
    payload_json = _canonical_json(normalized.payload, "control payload"); payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    existing = getattr(command_envelope, "existing_control_event", None)
    if existing is not None:
        expected = {"case_no":case_no,"control_type":normalized.control_type,"control_key":normalized.control_key,"scope":normalized.scope,"action":normalized.action,"actor":normalized.actor,"reason":normalized.reason,"expected_version":normalized.expected_version,"idempotency_key":normalized.idempotency_key,"payload_hash":payload_hash}
        for field, value in expected.items():
            if existing.get(field) != value: raise OrderLifecycleControlConflict(f"idempotency conflict in control event field {field}")
        if existing.get("payload_snapshot") != payload_json: raise OrderLifecycleControlConflict("idempotency conflict in control event payload_snapshot")
        event_id = _nonnegative(existing.get("id"), "existing control event id")
        return OrderLifecycleControlResult("existing", event_id, _projection(normalized, case_no, event_id))
    if getattr(command_envelope, "existing_lifecycle_event", None) is not None: raise OrderLifecycleControlConflict("lifecycle event exists without its required control event")
    if request_version != current_version: raise OrderLifecycleControlConcurrencyError("request expected version differs from locked aggregate version")
    cursor.execute("INSERT INTO order_lifecycle_control_events (case_no, control_type, control_key, scope, action, actor, reason, expected_version, idempotency_key, payload_hash, payload_snapshot) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (case_no, normalized.control_type, normalized.control_key, normalized.scope, normalized.action, normalized.actor, normalized.reason, normalized.expected_version, normalized.idempotency_key, payload_hash, payload_json))
    if getattr(cursor, "rowcount", None) != 1: raise OrderLifecycleControlConcurrencyError("control event append did not affect exactly one row")
    event_id = _nonnegative(getattr(cursor, "lastrowid", None), "inserted control event id")
    current = next((row for row in getattr(command_envelope, "control_states", ()) if row["control_type"] == normalized.control_type and row["control_key"] == normalized.control_key), None)
    if current is None:
        if normalized.action != "activate": raise OrderLifecycleControlStateError("a new control projection must be activated")
        cursor.execute("INSERT INTO order_lifecycle_control_state (case_no, control_type, control_key, scope, state, current_event_id, release_policy, expires_at_utc, confirmed_start_date, deposit_settlement_identity_hash, reason, changed_by, changed_at) SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, control_event.created_at FROM order_lifecycle_control_events AS control_event WHERE control_event.id = %s AND control_event.case_no = %s AND control_event.control_type = %s AND control_event.control_key = %s", (case_no, normalized.control_type, normalized.control_key, normalized.scope, normalized.state, event_id, normalized.release_policy, normalized.expires_at_utc, normalized.confirmed_start_date, normalized.deposit_settlement_identity_hash, normalized.reason, normalized.actor, event_id, case_no, normalized.control_type, normalized.control_key))
    else:
        if current["scope"] != normalized.scope: raise OrderLifecycleControlStateError("current control projection scope differs")
        if normalized.action == "clear" and current["state"] != "active": raise OrderLifecycleControlStateError("control clear requires an active projection")
        cursor.execute("UPDATE order_lifecycle_control_state AS current_state JOIN order_lifecycle_control_events AS control_event ON control_event.id = %s AND control_event.case_no = %s AND control_event.control_type = %s AND control_event.control_key = %s SET current_state.scope = %s, current_state.state = %s, current_state.current_event_id = %s, current_state.release_policy = %s, current_state.expires_at_utc = %s, current_state.confirmed_start_date = %s, current_state.deposit_settlement_identity_hash = %s, current_state.reason = %s, current_state.changed_by = %s, current_state.changed_at = control_event.created_at WHERE current_state.case_no = %s AND current_state.control_type = %s AND current_state.control_key = %s AND current_state.current_event_id = %s", (event_id, case_no, normalized.control_type, normalized.control_key, normalized.scope, normalized.state, event_id, normalized.release_policy, normalized.expires_at_utc, normalized.confirmed_start_date, normalized.deposit_settlement_identity_hash, normalized.reason, normalized.actor, case_no, normalized.control_type, normalized.control_key, current["current_event_id"]))
    if getattr(cursor, "rowcount", None) != 1: raise OrderLifecycleControlConcurrencyError("control projection CAS did not affect exactly one row")
    return OrderLifecycleControlResult("created", event_id, _projection(normalized, case_no, event_id))

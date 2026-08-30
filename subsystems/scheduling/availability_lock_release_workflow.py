"""Atomic release of waiting-for-deposit caregiver availability lock to unbound state."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

from subsystems.scheduling.availability_lock_helpers import normalize_plan_snapshot
from subsystems.scheduling.ports import unconfigured_connection_factory
from subsystems.scheduling.occupancy_mutex import lock_staff_occupancy_mutex
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


get_connection = unconfigured_connection_factory


def _close_once(resource: Any, state: dict[str, bool]) -> None:
    if resource is not None and not state["closed"]:
        state["closed"] = True
        try:
            resource.close()
        except BaseException:  # noqa: BLE001 - cleanup should stay best effort.
            pass


def _strict_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if value.strip() != value:
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    return value


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a positive integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _as_date(value: Any, field_name: str) -> date:
    if value.__class__ is not date:
        raise ValueError(f"{field_name} must be a date")
    return value


def _exact_row(value: Any, expected_keys: frozenset[str], field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    if set(value) != expected_keys:
        raise ValueError(f"{field_name} has unexpected keys")
    return value


def _assert_row_list(value: Any, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return value


def _normalize_request(
    case_no: Any,
    plan_id: Any,
    lock_id: Any,
    event_key: Any,
    actor: Any,
    reason: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    expected = {"case_no", "plan_id", "lock_id", "event_key", "actor", "reason"}
    if set(kwargs):
        unknown = ", ".join(sorted(kwargs.keys()))
        raise ValueError(f"unexpected request fields: {unknown}")

    return {
        "case_no": _strict_str(case_no, "case_no"),
        "plan_id": _positive_int(plan_id, "plan_id"),
        "lock_id": _positive_int(lock_id, "lock_id"),
        "event_key": _strict_str(event_key, "event_key"),
        "actor": _strict_str(actor, "actor"),
        "reason": _strict_str(reason, "reason"),
    }


def _normalize_preview_request(
    case_no: Any,
    plan_id: Any,
    lock_id: Any,
) -> dict[str, Any]:
    return {
        "case_no": _strict_str(case_no, "case_no"),
        "plan_id": _positive_int(plan_id, "plan_id"),
        "lock_id": _positive_int(lock_id, "lock_id"),
    }


def _optional_preview_fingerprint(value: Any) -> PreviewFingerprint | None:
    if value is None:
        return None
    return PreviewFingerprint(value)


def _normalize_lock_day_rows(value: Any, required_active_only: bool = True) -> list[dict[str, Any]]:
    rows = _assert_row_list(value, "lock_row_rows")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        row = _exact_row(
            row,
            frozenset(
                {
                    "segment_id",
                    "staff_id",
                    "lock_date",
                    "active_marker",
                    "released_by",
                    "released_at",
                }
            ),
            f"lock_row_rows[{index}]",
        )
        segment_id = _positive_int(row["segment_id"], f"lock_row_rows[{index}].segment_id")
        staff_id = _positive_int(row["staff_id"], f"lock_row_rows[{index}].staff_id")
        lock_date = _as_date(row["lock_date"], f"lock_row_rows[{index}].lock_date")
        active_marker = row["active_marker"]
        released_by = row["released_by"]
        released_at = row["released_at"]
        if required_active_only:
            if active_marker != 1:
                raise ValueError("lock day must be active during release preflight")
            if released_by is not None or released_at is not None:
                raise ValueError("active lock day cannot include release metadata")
        normalized.append(
            {
                "segment_id": segment_id,
                "staff_id": staff_id,
                "lock_date": lock_date,
                "active_marker": active_marker,
                "released_by": released_by,
                "released_at": released_at,
            }
        )

    normalized.sort(key=lambda item: (item["lock_date"], item["segment_id"], item["staff_id"]))
    return normalized


def _snapshot_staff_ids(lock_days: list[dict[str, Any]]) -> list[int]:
    staff_ids = sorted({row["staff_id"] for row in lock_days})
    if not 1 <= len(staff_ids) <= 4:
        raise ValueError("lock must reference one to four staff")
    return staff_ids


def _snapshot_lock_rows(lock_days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in lock_days:
        rows.append(
            {
                "segment_id": row["segment_id"],
                "staff_id": row["staff_id"],
                "lock_date": row["lock_date"].isoformat(),
            }
        )
    rows.sort(key=lambda item: (item["lock_date"], item["segment_id"], item["staff_id"]))
    return rows


def _assert_lock_rows_match(expected: list[dict[str, Any]], actual: list[dict[str, Any]], field_name: str) -> None:
    if _snapshot_lock_rows(actual) != expected:
        raise ValueError(f"{field_name} must match plan snapshot")


def _assert_lock_days_active(lock_days: list[dict[str, Any]]) -> None:
    for index, row in enumerate(lock_days):
        if row["active_marker"] != 1:
            raise ValueError(f"lock_row_rows[{index}] must be active")
        if row["released_by"] is not None or row["released_at"] is not None:
            raise ValueError(f"lock_row_rows[{index}] cannot contain release metadata")


def _assert_lock_days_released(lock_days: list[dict[str, Any]], actor: str) -> None:
    for index, row in enumerate(lock_days):
        if row["active_marker"] is not None:
            raise ValueError(f"lock_row_rows[{index}] must be released")
        if row["released_by"] != actor:
            raise ValueError(f"lock_row_rows[{index}] release actor mismatch")
        if row["released_at"] is None:
            raise ValueError(f"lock_row_rows[{index}] release timestamp missing")


def _build_release_event_payload(
    request: dict[str, Any],
    snapshot: dict[str, Any],
    expected_preview_fingerprint: PreviewFingerprint | None = None,
) -> dict[str, Any]:
    payload = {
        "case_no": request["case_no"],
        "plan_id": request["plan_id"],
        "lock_id": request["lock_id"],
        "actor": request["actor"],
        "reason": request["reason"],
        "plan_status": "proposed",
        "lock_status": "released",
        "staff_ids": list(snapshot["staff_ids"]),
        "segments": [dict(segment) for segment in snapshot["segments"]],
        "lock_rows": [dict(row) for row in snapshot["lock_rows"]],
        "case_start_date": snapshot["case_start_date"],
        "case_end_date": snapshot["case_end_date"],
    }
    if expected_preview_fingerprint is not None:
        payload["preview_fingerprint"] = expected_preview_fingerprint.value
    return payload


def _load_prelocked_rows(
    cursor: Any,
    lock_id: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cursor.execute(
        "SELECT id, plan_id, status, is_active, released_by, released_at "
        "FROM caregiver_availability_locks WHERE id = %s",
        (lock_id,),
    )
    lock_row = _exact_row(
        cursor.fetchone(),
        frozenset({"id", "plan_id", "status", "is_active", "released_by", "released_at"}),
        "lock_row",
    )
    if _positive_int(lock_row["id"], "lock_row.id") != lock_id:
        raise ValueError("lock id mismatch")
    _positive_int(lock_row["plan_id"], "lock_row.plan_id")

    cursor.execute(
        "SELECT segment_id, staff_id, lock_date, active_marker, released_by, released_at "
        "FROM caregiver_availability_lock_days WHERE lock_id = %s ORDER BY lock_date, segment_id, staff_id",
        (lock_id,),
    )
    lock_days = _normalize_lock_day_rows(cursor.fetchall(), required_active_only=False)
    if not lock_days:
        raise ValueError("lock has no days")
    if lock_row["status"] == "active":
        if lock_row["is_active"] != 1:
            raise ValueError("active lock header lifecycle mismatch")
        if lock_row["released_by"] is not None or lock_row["released_at"] is not None:
            raise ValueError("active lock header cannot include release metadata")
        _assert_lock_days_active(lock_days)
    elif lock_row["status"] == "released":
        if lock_row["is_active"] is not None:
            raise ValueError("released lock header lifecycle mismatch")
        released_by = _strict_str(lock_row["released_by"], "lock_row.released_by")
        if lock_row["released_at"] is None:
            raise ValueError("released lock timestamp missing")
        _assert_lock_days_released(lock_days, released_by)
    else:
        raise ValueError("lock is neither active nor released")
    return lock_row, lock_days


def _normalize_order_row(order_row: Any, case_no: str) -> dict[str, Any]:
    order_row = _exact_row(order_row, frozenset({"case_no", "status"}), "order_row")
    _strict_str(order_row["case_no"], "order_row.case_no")
    if order_row["case_no"] != case_no:
        raise ValueError("order case_no mismatch")
    _strict_str(order_row["status"], "order_row.status")
    return order_row


def _assert_order_row(order_row: Any, case_no: str) -> dict[str, Any]:
    order_row = _normalize_order_row(order_row, case_no)
    if order_row["status"] != "洽談中":
        raise ValueError("case is not in negotiation")
    return order_row


def _assert_plan_row(plan_row: Any, case_no: str, plan_id: int) -> dict[str, Any]:
    plan_row = _exact_row(
        plan_row,
        frozenset({"id", "case_no", "status", "is_active", "start_date", "end_date"}),
        "plan_row",
    )
    if plan_row["id"] != plan_id:
        raise ValueError("plan id mismatch")
    if plan_row["case_no"] != case_no:
        raise ValueError("plan case_no mismatch")
    _strict_str(plan_row["case_no"], "plan_row.case_no")
    if _as_date(plan_row["start_date"], "plan_row.start_date") > _as_date(plan_row["end_date"], "plan_row.end_date"):
        raise ValueError("plan start_date cannot be after end_date")
    return plan_row


def _load_plan_snapshot(cursor: Any, case_no: str, plan_id: int) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    cursor.execute(
        "SELECT id, case_no, status, is_active, start_date, end_date "
        "FROM caregiver_matching_plans WHERE id = %s AND case_no = %s FOR UPDATE",
        (plan_id, case_no),
    )
    plan_row = _assert_plan_row(cursor.fetchone(), case_no, plan_id)

    cursor.execute(
        "SELECT id, plan_id, segment_order, staff_id, assigned_start_date, assigned_end_date "
        "FROM caregiver_matching_plan_segments WHERE plan_id = %s ORDER BY segment_order FOR UPDATE",
        (plan_id,),
    )
    segment_rows = _assert_row_list(cursor.fetchall(), "plan_segment_rows")
    normalized_segments: list[dict[str, Any]] = []
    for index, row in enumerate(segment_rows):
        row = _exact_row(
            row,
            frozenset({"id", "plan_id", "segment_order", "staff_id", "assigned_start_date", "assigned_end_date"}),
            f"plan_segment_rows[{index}]",
        )
        normalized_segments.append(
            {
                "id": _positive_int(row["id"], f"plan_segment_rows[{index}].id"),
                "plan_id": _positive_int(row["plan_id"], f"plan_segment_rows[{index}].plan_id"),
                "segment_order": _positive_int(
                    row["segment_order"],
                    f"plan_segment_rows[{index}].segment_order",
                ),
                "staff_id": _positive_int(row["staff_id"], f"plan_segment_rows[{index}].staff_id"),
                "assigned_start_date": _as_date(row["assigned_start_date"], f"plan_segment_rows[{index}].assigned_start_date"),
                "assigned_end_date": _as_date(row["assigned_end_date"], f"plan_segment_rows[{index}].assigned_end_date"),
            }
        )
    snapshot = normalize_plan_snapshot(
        case_no,
        plan_id,
        {
            "id": plan_row["id"],
            "case_no": plan_row["case_no"],
            "status": plan_row["status"],
            "is_active": plan_row["is_active"],
            "start_date": plan_row["start_date"],
            "end_date": plan_row["end_date"],
        },
        normalized_segments,
    )
    return plan_row, segment_rows, snapshot


def _load_lock_rows_for_update(cursor: Any, lock_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cursor.execute(
        "SELECT id, plan_id, status, is_active, released_by, released_at "
        "FROM caregiver_availability_locks WHERE id = %s FOR UPDATE",
        (lock_id,),
    )
    lock_row = _exact_row(cursor.fetchone(), frozenset({"id", "plan_id", "status", "is_active", "released_by", "released_at"}), "lock_row")
    if _positive_int(lock_row["id"], "lock_row.id") != lock_id:
        raise ValueError("lock id mismatch")
    _positive_int(lock_row["plan_id"], "lock_row.plan_id")
    cursor.execute(
        "SELECT id, segment_id, staff_id, lock_date, active_marker, released_by, released_at "
        "FROM caregiver_availability_lock_days WHERE lock_id = %s ORDER BY lock_date, segment_id, staff_id FOR UPDATE",
        (lock_id,),
    )
    lock_days = _assert_row_list(cursor.fetchall(), "lock_days")
    normalized = []
    for index, row in enumerate(lock_days):
        row = _exact_row(
            row,
            frozenset({"id", "segment_id", "staff_id", "lock_date", "active_marker", "released_by", "released_at"}),
            f"lock_days[{index}]",
        )
        normalized.append(
            {
                "id": _positive_int(row["id"], f"lock_days[{index}].id"),
                "segment_id": _positive_int(row["segment_id"], f"lock_days[{index}].segment_id"),
                "staff_id": _positive_int(row["staff_id"], f"lock_days[{index}].staff_id"),
                "lock_date": _as_date(row["lock_date"], f"lock_days[{index}].lock_date"),
                "active_marker": row["active_marker"],
                "released_by": row["released_by"],
                "released_at": row["released_at"],
            }
        )
    if not normalized:
        raise ValueError("lock has no days")
    return lock_row, normalized


def _normalize_deposit_settlement_projection(row: Any) -> dict[str, Any]:
    fields = frozenset({
        "case_no", "deposit_obligation_identity", "settlement_state",
        "contracted_amount_ntd", "allocated_net_amount_ntd", "settlement_identity",
        "source_fingerprint", "projection_version", "latest_ledger_entry_id",
    })
    row = _exact_row(row, fields, "client_deposit_settlement_projection")
    case_no = _strict_str(row["case_no"], "client_deposit_settlement_projection.case_no")
    obligation_identity = _strict_str(
        row["deposit_obligation_identity"],
        "client_deposit_settlement_projection.deposit_obligation_identity",
    )
    settlement_state = row["settlement_state"]
    if settlement_state not in {"unsettled", "settled"}:
        raise ValueError("client_deposit_settlement_projection.settlement_state invalid")
    contracted_amount = _positive_int(
        row["contracted_amount_ntd"],
        "client_deposit_settlement_projection.contracted_amount_ntd",
    )
    allocated_amount = row["allocated_net_amount_ntd"]
    if isinstance(allocated_amount, bool) or not isinstance(allocated_amount, int):
        raise ValueError("client_deposit_settlement_projection.allocated_net_amount_ntd must be an integer")
    settlement_identity = row["settlement_identity"]
    if settlement_identity is not None:
        settlement_identity = _strict_str(
            settlement_identity,
            "client_deposit_settlement_projection.settlement_identity",
        )
    source_fingerprint = _strict_str(
        row["source_fingerprint"],
        "client_deposit_settlement_projection.source_fingerprint",
    )
    if len(source_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in source_fingerprint):
        raise ValueError("client_deposit_settlement_projection.source_fingerprint invalid")
    projection_version = _positive_int(
        row["projection_version"],
        "client_deposit_settlement_projection.projection_version",
    )
    latest_ledger_entry_id = row["latest_ledger_entry_id"]
    if latest_ledger_entry_id is not None:
        latest_ledger_entry_id = _positive_int(
            latest_ledger_entry_id,
            "client_deposit_settlement_projection.latest_ledger_entry_id",
        )
    if settlement_state == "settled":
        if allocated_amount != contracted_amount or settlement_identity is None or latest_ledger_entry_id is None:
            raise ValueError("client_deposit_settlement_projection settled state invalid")
    elif allocated_amount == contracted_amount or settlement_identity is not None:
        raise ValueError("client_deposit_settlement_projection unsettled state invalid")
    return {
        "case_no": case_no,
        "deposit_obligation_identity": obligation_identity,
        "settlement_state": settlement_state,
        "contracted_amount_ntd": contracted_amount,
        "allocated_net_amount_ntd": allocated_amount,
        "settlement_identity": settlement_identity,
        "source_fingerprint": source_fingerprint,
        "projection_version": projection_version,
        "latest_ledger_entry_id": latest_ledger_entry_id,
    }


def _assert_zero_deposit(deposit_projection: dict[str, Any]) -> None:
    if deposit_projection["allocated_net_amount_ntd"] != 0:
        raise ValueError("existing deposit net amount must be zero")


def _release_blockers(
    order_row: dict[str, Any],
    deposit_projection: dict[str, Any],
    plan_row: dict[str, Any],
    lock_row: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if order_row["status"] != "洽談中":
        blockers.append("case_not_in_negotiation")
    if deposit_projection["allocated_net_amount_ntd"] != 0:
        blockers.append("deposit_not_zero")
    if lock_row["status"] != "active" or lock_row["is_active"] != 1:
        blockers.append("lock_not_active")
    if plan_row["status"] != "accepted" or plan_row["is_active"] != 1:
        blockers.append("plan_not_accepted")
    return blockers


# Kept cohesive so the response and its fingerprint use the same blocker snapshot.
def _build_release_preview(
    request: dict[str, Any],
    order_row: dict[str, Any],
    deposit_projection: dict[str, Any],
    plan_row: dict[str, Any],
    snapshot: dict[str, Any],
    lock_row: dict[str, Any],
    lock_days: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers = _release_blockers(
        order_row,
        deposit_projection,
        plan_row,
        lock_row,
    )
    fingerprint_facts = _release_fingerprint_facts(
        request,
        order_row,
        deposit_projection,
        plan_row,
        snapshot,
        lock_row,
        lock_days,
    )
    return {
        **request,
        "service_day_count": len(lock_days),
        "staff_count": len(_snapshot_staff_ids(lock_days)),
        "apply_allowed": not blockers,
        "blockers": blockers,
        "preview_fingerprint": fingerprint_payload(fingerprint_facts).value,
    }


def _raise_release_blocker(blockers: list[str]) -> None:
    if not blockers:
        return
    messages = {
        "case_not_in_negotiation": "case is not in negotiation",
        "deposit_not_zero": "existing deposit net amount must be zero",
        "lock_not_active": "lock is not active",
        "plan_not_accepted": "plan is not accepted",
    }
    raise ValueError(messages[blockers[0]])


# Kept cohesive because the fingerprint must cover one exact authoritative snapshot.
def _release_fingerprint_facts(
    request: dict[str, Any],
    order_row: dict[str, Any],
    deposit_projection: dict[str, Any],
    plan_row: dict[str, Any],
    snapshot: dict[str, Any],
    lock_row: dict[str, Any],
    lock_days: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        **request,
        "order_status": order_row["status"],
        "deposit_settlement": deposit_projection,
        "plan_status": plan_row["status"],
        "plan_is_active": plan_row["is_active"],
        "plan_snapshot": snapshot,
        "lock_status": lock_row["status"],
        "lock_is_active": lock_row["is_active"],
        "lock_rows": _snapshot_lock_rows(lock_days),
        "lock_day_lifecycle": [
            {
                "segment_id": row["segment_id"],
                "staff_id": row["staff_id"],
                "lock_date": row["lock_date"].isoformat(),
                "active_marker": row["active_marker"],
                "released_by": row["released_by"],
                "released_at_present": row["released_at"] is not None,
            }
            for row in lock_days
        ],
    }


def _load_order_snapshot(cursor: Any, case_no: str) -> dict[str, Any]:
    cursor.execute(
        "SELECT case_no, status FROM orders WHERE case_no = %s FOR UPDATE",
        (case_no,),
    )
    return _normalize_order_row(cursor.fetchone(), case_no)


# Kept cohesive so the release decision reads one locked Client Finance projection.
def _load_deposit_settlement_projection(
    cursor: Any,
    case_no: str,
) -> dict[str, Any]:
    cursor.execute(
        "SELECT case_no, deposit_obligation_identity, settlement_state, "
        "contracted_amount_ntd, allocated_net_amount_ntd, settlement_identity, "
        "source_fingerprint, projection_version, latest_ledger_entry_id "
        "FROM client_deposit_settlement_projection WHERE case_no = %s FOR UPDATE",
        (case_no,),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("client finance deposit settlement projection missing")
    deposit_projection = _normalize_deposit_settlement_projection(row)
    if deposit_projection["case_no"] != case_no:
        raise ValueError("client finance deposit settlement case_no mismatch")
    return deposit_projection


# Kept cohesive so every Preview fact comes from one read transaction.
def preview_caregiver_availability_lock_release(
    case_no: Any,
    plan_id: Any,
    lock_id: Any,
) -> dict[str, Any]:
    request = _normalize_preview_request(case_no, plan_id, lock_id)
    connection = cursor = None
    cursor_closed = {"closed": False}
    connection_closed = {"closed": False}
    try:
        connection = get_connection()
        cursor = connection.cursor()
        lock_row, lock_days = _load_lock_rows_for_update(
            cursor,
            request["lock_id"],
        )
        order_row = _load_order_snapshot(cursor, request["case_no"])
        deposit_projection = _load_deposit_settlement_projection(
            cursor,
            request["case_no"],
        )
        plan_row, _segment_rows, snapshot = _load_plan_snapshot(
            cursor,
            request["case_no"],
            request["plan_id"],
        )
        if lock_row["plan_id"] != request["plan_id"]:
            raise ValueError("lock plan_id mismatch")
        _assert_lock_rows_match(snapshot["lock_rows"], lock_days, "lock rows")
        return _build_release_preview(
            request,
            order_row,
            deposit_projection,
            plan_row,
            snapshot,
            lock_row,
            lock_days,
        )
    finally:
        if cursor is not None:
            _close_once(cursor, cursor_closed)
        if connection is not None:
            _close_once(connection, connection_closed)


def _load_existing_event(cursor: Any, event_key: str, lock_id: int) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT id, lock_id, event_type, event_key, actor, reason, payload "
        "FROM caregiver_availability_lock_events WHERE event_key = %s FOR UPDATE",
        (event_key,),
    )
    event_row = cursor.fetchone()
    if event_row is None:
        return None
    event_row = _exact_row(event_row, frozenset({"id", "lock_id", "event_type", "event_key", "actor", "reason", "payload"}), "event_row")
    if event_row["lock_id"] != lock_id:
        raise ValueError("event key already used for another lock")
    if event_row["event_key"] != event_key:
        raise ValueError("event key lookup mismatch")
    return event_row


def _normalize_event_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("event payload must be JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("event payload must be JSON object")
    return payload


def _existing_result(
    request: dict[str, Any],
    event_row: dict[str, Any],
    snapshot: dict[str, Any],
    plan_row: dict[str, Any],
    lock_row: dict[str, Any],
    lock_days: list[dict[str, Any]],
    expected_preview_fingerprint: PreviewFingerprint | None = None,
) -> dict[str, Any]:
    if event_row["event_type"] != "lock_released":
        raise ValueError("event key already used for non-release event")
    if event_row["actor"] != request["actor"]:
        raise ValueError("event actor mismatch")
    if event_row["reason"] != request["reason"]:
        raise ValueError("event reason mismatch")
    payload = _normalize_event_payload(event_row["payload"])
    expected_payload = _build_release_event_payload(
        request,
        snapshot,
        expected_preview_fingerprint,
    )
    if payload != expected_payload:
        raise ValueError("event payload mismatch")

    if plan_row["status"] != "proposed" or plan_row["is_active"] != 1:
        raise ValueError("plan status mismatch for existing release")
    if lock_row["status"] != "released" or lock_row["is_active"] is not None:
        raise ValueError("lock status mismatch for existing release")
    if not isinstance(lock_row["released_by"], str) or not lock_row["released_by"]:
        raise ValueError("lock released_by missing")
    if lock_row["released_at"] is None:
        raise ValueError("lock released_at missing")

    _assert_lock_days_released(lock_days, request["actor"])

    return {
        "result": "existing",
        "case_no": request["case_no"],
        "plan_id": request["plan_id"],
        "lock_id": request["lock_id"],
        "plan_status": "proposed",
        "lock_status": "released",
        "lock_rows": snapshot["lock_rows"],
    }


def _run_in_application_uow(operation: Callable[[Any, Any], dict[str, Any]]) -> dict[str, Any]:
    """Run one lock mutation with an Application-owned outer transaction."""
    connection = cursor = None
    cursor_closed = {"closed": False}
    connection_closed = {"closed": False}
    unit_of_work = None
    try:
        connection = get_connection()
        unit_of_work = connection
        cursor = connection.cursor()
        result = operation(connection, cursor)
        if result.get("result") != "existing" and result.get("status") != "idempotent_replay":
            unit_of_work.commit()
        else:
            unit_of_work.rollback()
        return result
    except Exception:
        if unit_of_work is not None:
            try:
                unit_of_work.rollback()
            except BaseException:  # noqa: BLE001
                pass
        raise
    finally:
        _close_once(cursor, cursor_closed)
        _close_once(connection, connection_closed)


def release_caregiver_availability_lock(
    case_no: Any,
    plan_id: Any,
    lock_id: Any,
    event_key: Any,
    actor: Any,
    reason: Any,
    expected_preview_fingerprint: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Release one active waiting-for-deposit lock and revert plan to proposed."""

    request = _normalize_request(
        case_no=case_no,
        plan_id=plan_id,
        lock_id=lock_id,
        event_key=event_key,
        actor=actor,
        reason=reason,
        **kwargs,
    )
    expected_fingerprint = _optional_preview_fingerprint(
        expected_preview_fingerprint
    )
    return _run_in_application_uow(
        lambda connection, cursor: _release_caregiver_availability_lock_in_transaction(
            connection, cursor, request, expected_fingerprint
        )
    )


def _release_caregiver_availability_lock_in_transaction(
    connection: Any,
    cursor: Any,
    request: dict[str, Any],
    expected_fingerprint: PreviewFingerprint | None,
) -> dict[str, Any]:
    try:

        pre_lock_row, pre_lock_rows = _load_lock_rows_for_update(cursor, request["lock_id"])
        staff_ids = _snapshot_staff_ids(pre_lock_rows)
        locked_staff = lock_staff_occupancy_mutex(cursor, staff_ids)
        if locked_staff != staff_ids:
            raise ValueError("mutex result does not match lock staff")

        order_row = _load_order_snapshot(cursor, request["case_no"])
        deposit_projection = _load_deposit_settlement_projection(
            cursor,
            request["case_no"],
        )

        plan_row, _segment_rows, snapshot = _load_plan_snapshot(
            cursor, request["case_no"], request["plan_id"]
        )
        _assert_lock_rows_match(snapshot["lock_rows"], pre_lock_rows, "lock rows")
        if pre_lock_row["plan_id"] != request["plan_id"]:
            raise ValueError("lock plan_id mismatch")

        lock_row, lock_days = _load_lock_rows_for_update(cursor, request["lock_id"])
        if lock_row["plan_id"] != request["plan_id"]:
            raise ValueError("lock plan_id mismatch")
        _assert_lock_rows_match(_snapshot_lock_rows(pre_lock_rows), lock_days, "locked lock rows")
        if _snapshot_staff_ids(lock_days) != staff_ids:
            raise ValueError("locked lock staff mismatch")

        existing_event = _load_existing_event(cursor, request["event_key"], request["lock_id"])
        if existing_event is not None:
            _assert_order_row(order_row, request["case_no"])
            _assert_zero_deposit(deposit_projection)
            return _existing_result(
                request=request,
                event_row=existing_event,
                snapshot=snapshot,
                plan_row=plan_row,
                lock_row=lock_row,
                lock_days=lock_days,
                expected_preview_fingerprint=expected_fingerprint,
            )

        fresh_preview = _build_release_preview(
            _normalize_preview_request(
                request["case_no"],
                request["plan_id"],
                request["lock_id"],
            ),
            order_row,
            deposit_projection,
            plan_row,
            snapshot,
            lock_row,
            lock_days,
        )
        if (
            expected_fingerprint is not None
            and fresh_preview["preview_fingerprint"]
            != expected_fingerprint.value
        ):
            raise ValueError("stale_preview")
        _raise_release_blocker(fresh_preview["blockers"])

        _assert_lock_rows_match(snapshot["lock_rows"], lock_days, "lock_rows")
        _assert_lock_days_active(lock_days)
        payload = _build_release_event_payload(
            request,
            snapshot,
            expected_fingerprint,
        )
        cursor.execute(
            "UPDATE caregiver_availability_lock_days "
            "SET active_marker = NULL, released_by = %s, released_at = CURRENT_TIMESTAMP "
            "WHERE lock_id = %s AND active_marker = 1",
            (request["actor"], request["lock_id"]),
        )
        if cursor.rowcount != len(snapshot["lock_rows"]):
            raise ValueError("lock day update rowcount mismatch")

        cursor.execute(
            "UPDATE caregiver_availability_locks "
            "SET status = 'released', is_active = NULL, released_by = %s, released_at = CURRENT_TIMESTAMP "
            "WHERE id = %s AND plan_id = %s AND status = 'active' AND is_active = 1",
            (request["actor"], request["lock_id"], request["plan_id"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("lock header update rowcount mismatch")

        cursor.execute(
            "UPDATE caregiver_matching_plans "
            "SET status = 'proposed' "
            "WHERE id = %s AND case_no = %s AND status = 'accepted' AND is_active = 1",
            (request["plan_id"], request["case_no"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("plan lifecycle update failed")

        cursor.execute(
            "INSERT INTO caregiver_availability_lock_events "
            "(lock_id, event_type, event_key, actor, reason, payload) "
            "VALUES (%s, 'lock_released', %s, %s, %s, %s)",
            (
                request["lock_id"],
                request["event_key"],
                request["actor"],
                request["reason"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("release event insert rowcount mismatch")
        return {
            "result": "created",
            "case_no": request["case_no"],
            "plan_id": request["plan_id"],
            "lock_id": request["lock_id"],
            "plan_status": "proposed",
            "lock_status": "released",
            "lock_rows": snapshot["lock_rows"],
        }
    finally:
        pass

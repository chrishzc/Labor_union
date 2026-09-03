"""
File: availability_lock_acquisition_workflow.py
Description: 原子建立等待訂金檔期鎖；只接受精確且有效的簽約前服務承諾。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

from domains.scheduling.waiting_deposit_lock import (
    WaitingDepositOccupancyKind,
    WaitingDepositSegment,
    project_waiting_deposit_occupancy,
)
from subsystems.scheduling.availability_lock_helpers import (
    build_acquired_event_payload,
    normalize_conflicts,
    normalize_lock_acquisition_request,
    normalize_plan_snapshot,
)
from subsystems.scheduling.ports import unconfigured_connection_factory
from subsystems.scheduling.occupancy_mutex import lock_staff_occupancy_mutex
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


get_connection = unconfigured_connection_factory


def _close_once(resource: Any, closed: dict[str, bool]) -> None:
    """Close a DB resource without allowing cleanup to mask the primary error."""
    if resource is not None and not closed["value"]:
        closed["value"] = True
        try:
            resource.close()
        except BaseException:  # noqa: BLE001 - cleanup is deliberately best effort
            pass


def _one(cursor: Any, message: str) -> dict[str, Any]:
    row = cursor.fetchone()
    if not isinstance(row, dict):
        raise ValueError(message)
    return row


def _rows(cursor: Any, message: str) -> list[dict[str, Any]]:
    rows = cursor.fetchall()
    if not isinstance(rows, (list, tuple)) or any(
        not isinstance(row, dict) for row in rows
    ):
        raise ValueError(message)
    return list(rows)


def _canonical_snapshot(
    case_no: str,
    plan_id: int,
    order_row: dict[str, Any],
    plan_row: dict[str, Any],
    segment_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if set(order_row) != {"case_no", "status", "start_date", "end_date"}:
        raise ValueError("invalid order row")
    if order_row["case_no"] != case_no:
        raise ValueError("order case_no does not match request")
    if order_row["status"] not in {"洽談中", "訂單成立"}:
        raise ValueError("case is not eligible for pre-execution availability lock")
    if set(plan_row) != {"id", "case_no", "status", "is_active", "start_date", "end_date"}:
        raise ValueError("invalid matching plan row")
    if plan_row["start_date"] != order_row["start_date"] or plan_row["end_date"] != order_row["end_date"]:
        raise ValueError("plan dates do not match order")
    return normalize_plan_snapshot(case_no, plan_id, plan_row, segment_rows)


def _load_prelock_snapshot(cursor: Any, case_no: str, plan_id: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read only the plan data needed to choose the shared staff mutex."""
    cursor.execute(
        "SELECT id, case_no, status, is_active, start_date, end_date "
        "FROM caregiver_matching_plans WHERE id = %s AND case_no = %s",
        (plan_id, case_no),
    )
    plan_row = _one(cursor, "matching plan not found")
    cursor.execute(
        "SELECT id, plan_id, segment_order, staff_id, assigned_start_date, assigned_end_date "
        "FROM caregiver_matching_plan_segments WHERE plan_id = %s ORDER BY segment_order",
        (plan_id,),
    )
    return plan_row, _rows(cursor, "invalid matching plan segments")


def _lock_snapshot(cursor: Any, case_no: str, plan_id: int) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    cursor.execute(
        "SELECT case_no, status, start_date, end_date FROM orders "
        "WHERE case_no = %s FOR UPDATE",
        (case_no,),
    )
    order_row = _one(cursor, "case not found")
    cursor.execute(
        "SELECT id, case_no, status, is_active, start_date, end_date "
        "FROM caregiver_matching_plans WHERE id = %s AND case_no = %s FOR UPDATE",
        (plan_id, case_no),
    )
    plan_row = _one(cursor, "matching plan not found")
    cursor.execute(
        "SELECT id, plan_id, segment_order, staff_id, assigned_start_date, assigned_end_date "
        "FROM caregiver_matching_plan_segments WHERE plan_id = %s ORDER BY segment_order FOR UPDATE",
        (plan_id,),
    )
    return order_row, plan_row, _rows(cursor, "invalid matching plan segments")


def _require_customer_matching_acceptance(cursor: Any, plan_id: int) -> None:
    cursor.execute(
        "SELECT response_value FROM matching_response_events "
        "WHERE plan_id = %s AND response_type = 'customer_decision' "
        "ORDER BY occurred_at_utc DESC, id DESC LIMIT 1",
        (plan_id,),
    )
    row = cursor.fetchone()
    if not isinstance(row, dict) or row.get("response_value") != "accepted":
        raise ValueError("customer has not accepted the matching plan")


def _require_active_precontract_commitment(cursor: Any, plan_id: int) -> list[dict[str, Any]]:
    """A lock may reserve a signed commitment, never an unsigned proposal."""
    cursor.execute(
        "SELECT commitment.id,commitment.case_no FROM precontract_service_commitments commitment "
        "LEFT JOIN precontract_service_commitment_events terminal "
        "ON terminal.commitment_id=commitment.id "
        "WHERE commitment.matching_plan_id=%s AND terminal.id IS NULL FOR UPDATE",
        (plan_id,),
    )
    commitment = cursor.fetchone()
    if not isinstance(commitment, dict):
        raise ValueError("active staff service commitment is required")
    cursor.execute(
        "SELECT order_row.service_days,COUNT(day_row.id) AS commitment_days,"
        "COUNT(DISTINCT day_row.service_date) AS distinct_service_dates "
        "FROM orders order_row LEFT JOIN precontract_service_commitment_days day_row "
        "ON day_row.commitment_id=%s WHERE order_row.case_no=%s FOR UPDATE",
        (commitment["id"], commitment["case_no"]),
    )
    days = cursor.fetchone()
    if not isinstance(days, dict) or any(
        not isinstance(days.get(key), int)
        for key in ("service_days", "commitment_days", "distinct_service_dates")
    ) or days["service_days"] <= 0 or (
        days["commitment_days"] != days["service_days"]
        or days["distinct_service_dates"] != days["service_days"]
    ):
        raise ValueError("active staff service commitment days mismatch")
    cursor.execute(
        "SELECT matching_segment_id,staff_id,service_date "
        "FROM precontract_service_commitment_days WHERE commitment_id=%s "
        "ORDER BY matching_segment_id,staff_id,service_date FOR UPDATE",
        (commitment["id"],),
    )
    commitment_days = _rows(cursor, "invalid active staff service commitment days")
    expected = {"matching_segment_id", "staff_id", "service_date"}
    if any(
        set(row) != expected
        or isinstance(row["matching_segment_id"], bool)
        or not isinstance(row["matching_segment_id"], int)
        or row["matching_segment_id"] <= 0
        or isinstance(row["staff_id"], bool)
        or not isinstance(row["staff_id"], int)
        or row["staff_id"] <= 0
        or row["service_date"].__class__ is not date
        for row in commitment_days
    ):
        raise ValueError("invalid active staff service commitment days")
    return commitment_days


def _with_exact_commitment_lock_rows(
    snapshot: dict[str, Any], commitment_days: list[dict[str, Any]]
) -> dict[str, Any]:
    """Replace calendar-range lock rows with immutable signed service days."""
    segment_staff = {
        (row["segment_id"], row["staff_id"])
        for row in snapshot["segments"]
    }
    lock_rows = [
        {
            "segment_id": row["matching_segment_id"],
            "staff_id": row["staff_id"],
            "lock_date": row["service_date"].isoformat(),
        }
        for row in commitment_days
    ]
    if (
        len(lock_rows) != len({(row["staff_id"], row["lock_date"]) for row in lock_rows})
        or any((row["segment_id"], row["staff_id"]) not in segment_staff for row in lock_rows)
    ):
        raise ValueError("active staff service commitment does not match plan segments")
    return {
        **snapshot,
        "lock_rows": sorted(
            lock_rows,
            key=lambda row: (row["lock_date"], row["segment_id"], row["staff_id"]),
        ),
    }


def _has_client_signed_contract(cursor: Any, case_no: str, plan_id: int) -> bool:
    cursor.execute(
        "SELECT event.id FROM contract_signing_events event "
        "INNER JOIN contract_document_versions document ON document.id=event.document_version_id "
        "WHERE event.case_no=%s AND event.matching_plan_id=%s "
        "AND event.event_type='signed_received' "
        "AND document.document_scope='client_contract' "
        "ORDER BY event.id DESC LIMIT 1 FOR UPDATE",
        (case_no, plan_id),
    )
    return isinstance(cursor.fetchone(), dict)


def _require_customer_pre_execution_commitment(
    cursor: Any,
    case_no: str,
    plan_id: int,
) -> None:
    """Client signature supersedes the older matching-card acceptance gate."""
    if _has_client_signed_contract(cursor, case_no, plan_id):
        return
    _require_customer_matching_acceptance(cursor, plan_id)


def _occupancy_conflicts(cursor: Any, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Read every occupancy owner under the mutex; each result is row-level."""
    staff_ids = tuple(snapshot["staff_ids"])
    wanted_rows = _proposed_occupancy_rows(snapshot)
    dates = tuple(row["lock_date"] for row in wanted_rows)
    staff_placeholders = ", ".join(["%s"] * len(staff_ids))
    date_placeholders = ", ".join(["%s"] * len(dates))
    params = staff_ids + dates
    fixed_staff_params = _fixed_staff_params(staff_ids)
    conflicts: list[dict[str, Any]] = []
    cursor.execute(
        "SELECT assignment.id AS source_id, assignment.staff_id, "
        "assignment.assigned_start_date, assignment.assigned_end_date "
        "FROM case_staff_assignments assignment WHERE assignment.staff_id IN (" + staff_placeholders + ") "
        "AND assignment.status <> 'cancelled' "
        "AND NOT (assignment.generation_id IS NULL AND EXISTS ("
        "SELECT 1 FROM order_lifecycle_state_events restart "
        "WHERE restart.case_no=assignment.case_no "
        "AND restart.trigger_event='orders_historical_precision_restart')) FOR UPDATE",
        staff_ids,
    )
    for row in _rows(cursor, "invalid assignment occupancy row"):
        if set(row) != {"source_id", "staff_id", "assigned_start_date", "assigned_end_date"}:
            raise ValueError("invalid assignment occupancy row")
        if (
            isinstance(row["source_id"], bool)
            or not isinstance(row["source_id"], int)
            or row["source_id"] <= 0
            or isinstance(row["staff_id"], bool)
            or not isinstance(row["staff_id"], int)
            or row["staff_id"] <= 0
            or row["assigned_start_date"].__class__ is not date
            or row["assigned_end_date"].__class__ is not date
            or row["assigned_start_date"] > row["assigned_end_date"]
        ):
            raise ValueError("invalid assignment occupancy row")
        for wanted in wanted_rows:
            wanted_date = wanted["lock_date"]
            if wanted["staff_id"] == row["staff_id"] and row["assigned_start_date"] <= wanted_date <= row["assigned_end_date"]:
                conflicts.append({"staff_id": wanted["staff_id"], "lock_date": wanted_date, "source_type": "assignment", "source_id": row["source_id"]})
    cursor.execute(
        "SELECT id AS source_id, staff_id, work_date, assignment_id FROM staff_schedule "
        "WHERE staff_id IN (" + staff_placeholders + ") AND work_date IN (" + date_placeholders + ") FOR UPDATE",
        params,
    )
    for row in _rows(cursor, "invalid schedule occupancy row"):
        if set(row) != {"source_id", "staff_id", "work_date", "assignment_id"}:
            raise ValueError("invalid schedule occupancy row")
        if (
            isinstance(row["source_id"], bool)
            or not isinstance(row["source_id"], int)
            or row["source_id"] <= 0
            or isinstance(row["staff_id"], bool)
            or not isinstance(row["staff_id"], int)
            or row["staff_id"] <= 0
            or row["work_date"].__class__ is not date
        ):
            raise ValueError("invalid schedule occupancy row")
        if row["assignment_id"] is not None and (isinstance(row["assignment_id"], bool) or not isinstance(row["assignment_id"], int) or row["assignment_id"] <= 0):
            raise ValueError("invalid schedule assignment_id")
        # A NULL assignment_id is deliberately not exempt: its ownership is
        # unknown, so it is reported using the canonical schedule source type.
        conflicts.append({"staff_id": row["staff_id"], "lock_date": row["work_date"], "source_type": "schedule", "source_id": row["source_id"]})
    cursor.execute(
        "SELECT id AS source_id, staff_id, buffer_date AS lock_date "
        "FROM scheduling_buffer_days "
        "WHERE status = 'active' AND active_marker = 1 "
        "AND staff_id IN (%s, %s, %s, %s) FOR UPDATE",
        fixed_staff_params,
    )
    wanted_keys = {
        (row["staff_id"], row["lock_date"])
        for row in wanted_rows
    }
    for row in _rows(cursor, "invalid assignment buffer occupancy row"):
        _append_buffer_conflict(conflicts, row, wanted_keys)
    cursor.execute(
        "SELECT l.id FROM caregiver_availability_locks l "
        "INNER JOIN caregiver_availability_lock_days d ON d.lock_id = l.id "
        "WHERE l.status = 'active' AND l.is_active = 1 AND d.active_marker = 1 "
        "AND d.staff_id IN (" + staff_placeholders + ") AND d.lock_date IN (" + date_placeholders + ") "
        "ORDER BY l.id, d.id FOR UPDATE",
        params,
    )
    active_headers = _rows(cursor, "invalid active lock header rows")
    header_ids: list[int] = []
    for row in active_headers:
        if (
            set(row) != {"id"}
            or isinstance(row["id"], bool)
            or not isinstance(row["id"], int)
            or row["id"] <= 0
        ):
            raise ValueError("invalid active lock header rows")
        if row["id"] not in header_ids:
            header_ids.append(row["id"])
    cursor.execute(
        "SELECT d.id AS source_id, d.lock_id, d.staff_id, d.lock_date FROM caregiver_availability_lock_days d "
        "INNER JOIN caregiver_availability_locks l ON l.id = d.lock_id "
        "WHERE d.staff_id IN (" + staff_placeholders + ") AND d.lock_date IN (" + date_placeholders + ") "
        "AND l.status = 'active' AND l.is_active = 1 AND d.active_marker = 1 FOR UPDATE",
        params,
    )
    for row in _rows(cursor, "invalid active lock occupancy row"):
        if set(row) != {"source_id", "lock_id", "staff_id", "lock_date"}:
            raise ValueError("invalid active lock occupancy row")
        if (
            isinstance(row["source_id"], bool)
            or not isinstance(row["source_id"], int)
            or row["source_id"] <= 0
            or isinstance(row["lock_id"], bool)
            or not isinstance(row["lock_id"], int)
            or row["lock_id"] <= 0
            or row["lock_id"] not in header_ids
            or isinstance(row["staff_id"], bool)
            or not isinstance(row["staff_id"], int)
            or row["staff_id"] <= 0
            or row["lock_date"].__class__ is not date
        ):
            raise ValueError("invalid active lock occupancy row")
        conflicts.append({"staff_id": row["staff_id"], "lock_date": row["lock_date"], "source_type": "active_lock", "source_id": row["source_id"]})
    cursor.execute(
        "SELECT d.id AS source_id, d.lock_id, d.segment_id, d.staff_id, "
        "segment.assigned_end_date "
        "FROM caregiver_availability_lock_days d "
        "INNER JOIN caregiver_availability_locks header "
        "ON header.id = d.lock_id "
        "INNER JOIN caregiver_matching_plan_segments segment "
        "ON segment.id = d.segment_id "
        "WHERE header.status = 'active' AND header.is_active = 1 "
        "AND d.active_marker = 1 "
        "AND d.staff_id IN (%s, %s, %s, %s) "
        "ORDER BY d.lock_id, d.segment_id, d.id FOR UPDATE",
        fixed_staff_params,
    )
    active_buffers = _active_waiting_buffer_rows(
        _rows(cursor, "invalid active waiting buffer row")
    )
    _append_active_waiting_buffer_conflicts(
        conflicts,
        wanted_rows,
        active_buffers,
    )
    return normalize_conflicts(conflicts)


def _proposed_occupancy_rows(snapshot):
    service_dates_by_segment: dict[tuple[int, int], list[date]] = {}
    for row in snapshot["lock_rows"]:
        service_dates_by_segment.setdefault(
            (int(row["segment_id"]), int(row["staff_id"])), []
        ).append(date.fromisoformat(row["lock_date"]))
    segments = tuple(
        WaitingDepositSegment(
            int(row["segment_id"]),
            int(row["staff_id"]),
            date.fromisoformat(row["assigned_start_date"]),
            date.fromisoformat(row["assigned_end_date"]),
            tuple(service_dates_by_segment[(int(row["segment_id"]), int(row["staff_id"]))]),
        )
        for row in snapshot["segments"]
    )
    return tuple(
        {
            "segment_id": item.segment_id,
            "staff_id": item.staff_id,
            "lock_date": item.occupancy_date,
            "lock_kind": item.kind.value,
        }
        for item in project_waiting_deposit_occupancy(segments)
    )


def _fixed_staff_params(staff_ids: tuple[int, ...]) -> tuple[int, int, int, int]:
    if not 1 <= len(staff_ids) <= 4:
        raise ValueError("waiting lock requires one to four staff")
    padded = staff_ids + (0,) * (4 - len(staff_ids))
    return padded[0], padded[1], padded[2], padded[3]


def _append_buffer_conflict(conflicts, row, wanted_keys) -> None:
    expected = {"source_id", "staff_id", "lock_date"}
    if set(row) != expected or not _valid_occupancy_identity(row):
        raise ValueError("invalid assignment buffer occupancy row")
    if (row["staff_id"], row["lock_date"]) not in wanted_keys:
        return
    conflicts.append(
        {
            "staff_id": row["staff_id"],
            "lock_date": row["lock_date"],
            "source_type": "assignment",
            "source_id": row["source_id"],
        }
    )


def _valid_occupancy_identity(row) -> bool:
    return (
        isinstance(row["source_id"], int)
        and not isinstance(row["source_id"], bool)
        and row["source_id"] > 0
        and isinstance(row["staff_id"], int)
        and not isinstance(row["staff_id"], bool)
        and row["staff_id"] > 0
        and row["lock_date"].__class__ is date
    )


def _active_waiting_buffer_rows(rows):
    segments = {}
    expected = {
        "source_id",
        "lock_id",
        "segment_id",
        "staff_id",
        "assigned_end_date",
    }
    for row in rows:
        if set(row) != expected:
            raise ValueError("invalid active waiting buffer row")
        key = (row["lock_id"], row["segment_id"], row["staff_id"])
        segments.setdefault(key, row)
    return tuple(segments.values())


def _append_active_waiting_buffer_conflicts(conflicts, wanted_rows, sources):
    wanted = {
        (row["staff_id"], row["lock_date"])
        for row in wanted_rows
    }
    for source in sources:
        segment = WaitingDepositSegment(
            source["segment_id"],
            source["staff_id"],
            source["assigned_end_date"],
            source["assigned_end_date"],
        )
        occupancy = project_waiting_deposit_occupancy((segment,))
        for item in occupancy:
            if item.kind is not WaitingDepositOccupancyKind.BUFFER:
                continue
            if (item.staff_id, item.occupancy_date) not in wanted:
                continue
            conflicts.append(
                {
                    "staff_id": item.staff_id,
                    "lock_date": item.occupancy_date,
                    "source_type": "active_lock",
                    "source_id": source["source_id"],
                }
            )


def _existing_result(
    cursor: Any,
    event_row: dict[str, Any],
    request: dict[str, Any],
    snapshot: dict[str, Any],
    expected_preview_fingerprint: PreviewFingerprint | None = None,
) -> dict[str, Any]:
    """Validate an exact event-key replay without repairing any stored state."""
    expected_keys = {"id", "lock_id", "event_type", "event_key", "actor", "reason", "payload"}
    if set(event_row) != expected_keys:
        raise ValueError("invalid availability lock event row")
    lock_id = event_row["lock_id"]
    if isinstance(lock_id, bool) or not isinstance(lock_id, int) or lock_id <= 0:
        raise ValueError("invalid availability lock event lock_id")
    if event_row["event_type"] != "lock_acquired" or event_row["event_key"] != request["event_key"] or event_row["actor"] != request["actor"] or event_row["reason"] is not None:
        raise ValueError("event_key has already been used")
    cursor.execute(
        "SELECT id, plan_id, status, is_active FROM caregiver_availability_locks WHERE id = %s FOR UPDATE",
        (lock_id,),
    )
    header = _one(cursor, "availability lock event has no lock header")
    if set(header) != {"id", "plan_id", "status", "is_active"} or header != {"id": lock_id, "plan_id": request["plan_id"], "status": "active", "is_active": 1}:
        raise ValueError("event_key has inconsistent active lock")
    cursor.execute(
        "SELECT segment_id, staff_id, lock_date FROM caregiver_availability_lock_days "
        "WHERE lock_id = %s AND active_marker = 1 ORDER BY segment_id, lock_date FOR UPDATE",
        (lock_id,),
    )
    days = _rows(cursor, "invalid availability lock day rows")
    if any(set(day) != {"segment_id", "staff_id", "lock_date"} for day in days):
        raise ValueError("invalid availability lock day rows")
    canonical_days: list[dict[str, Any]] = []
    for day in days:
        if (
            isinstance(day["segment_id"], bool)
            or not isinstance(day["segment_id"], int)
            or day["segment_id"] <= 0
            or isinstance(day["staff_id"], bool)
            or not isinstance(day["staff_id"], int)
            or day["staff_id"] <= 0
            or day["lock_date"].__class__ is not date
        ):
            raise ValueError("invalid availability lock day rows")
        canonical_days.append(
            {
                "segment_id": day["segment_id"],
                "staff_id": day["staff_id"],
                "lock_date": day["lock_date"].isoformat(),
            }
        )
    canonical_days.sort(key=lambda row: (row["lock_date"], row["segment_id"], row["staff_id"]))
    if canonical_days != snapshot["lock_rows"]:
        raise ValueError("event_key has inconsistent lock days")
    payload = event_row["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid availability lock event payload") from exc
    expected_payload = build_acquired_event_payload({**request, "lock_id": lock_id}, snapshot)
    if expected_preview_fingerprint is not None:
        expected_payload["preview_fingerprint"] = (
            expected_preview_fingerprint.value
        )
    if payload != expected_payload:
        raise ValueError("event_key has inconsistent payload")
    return {"result": "existing", "lock_id": lock_id, "plan_id": request["plan_id"], "case_no": request["case_no"], "lock_rows": snapshot["lock_rows"]}


def _run_in_application_uow(operation: Callable[[Any, Any], dict[str, Any]]) -> dict[str, Any]:
    """Run one lock mutation with an Application-owned outer transaction."""
    connection = cursor = None
    cursor_closed = {"value": False}
    connection_closed = {"value": False}
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
            except BaseException:
                pass
        raise
    finally:
        # The outer application owns both resources; operation code never closes them.
        _close_once(cursor, cursor_closed)
        _close_once(connection, connection_closed)


def acquire_caregiver_availability_lock(
    case_no: Any,
    plan_id: Any,
    event_key: Any,
    actor: Any,
    expected_preview_fingerprint: Any = None,
) -> dict[str, Any]:
    """Atomically reserve all dates in a confirmed proposed matching plan."""
    request = normalize_lock_acquisition_request(case_no, plan_id, event_key, actor, 1)
    expected_fingerprint = _optional_preview_fingerprint(
        expected_preview_fingerprint
    )
    return _run_in_application_uow(
        lambda connection, cursor: _acquire_caregiver_availability_lock_in_transaction(
            connection, cursor, request, expected_fingerprint
        )
    )


def _acquire_caregiver_availability_lock_in_transaction(
    connection: Any,
    cursor: Any,
    request: dict[str, Any],
    expected_fingerprint: PreviewFingerprint | None,
) -> dict[str, Any]:
    try:
        # The cursor is created and closed by the Application transaction owner.
        preliminary_plan, preliminary_segments = _load_prelock_snapshot(cursor, request["case_no"], request["plan_id"])
        preliminary_snapshot = normalize_plan_snapshot(request["case_no"], request["plan_id"], preliminary_plan, preliminary_segments)
        locked_ids = lock_staff_occupancy_mutex(cursor, list(preliminary_snapshot["staff_ids"]))
        if locked_ids != preliminary_snapshot["staff_ids"]:
            raise ValueError("staff mutex result does not match matching plan")
        order_row, locked_plan, locked_segments = _lock_snapshot(cursor, request["case_no"], request["plan_id"])
        locked_snapshot = _canonical_snapshot(request["case_no"], request["plan_id"], order_row, locked_plan, locked_segments)
        if locked_snapshot != preliminary_snapshot:
            raise ValueError("matching plan changed while acquiring lock")
        commitment_days = _require_active_precontract_commitment(cursor, request["plan_id"])
        locked_snapshot = _with_exact_commitment_lock_rows(
            locked_snapshot, commitment_days
        )
        _require_customer_pre_execution_commitment(
            cursor, request["case_no"], request["plan_id"],
        )
        conflicts = _occupancy_conflicts(cursor, locked_snapshot)
        cursor.execute(
            "SELECT id, lock_id, event_type, event_key, actor, reason, payload "
            "FROM caregiver_availability_lock_events WHERE event_key = %s FOR UPDATE",
            (request["event_key"],),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if locked_plan["status"] != "accepted" or locked_plan["is_active"] != 1:
                raise ValueError("event_key has already been used")
            return _existing_result(
                cursor,
                existing,
                request,
                locked_snapshot,
                expected_fingerprint,
            )
        if locked_plan["status"] != "proposed" or locked_plan["is_active"] != 1:
            raise ValueError("matching plan is not an active proposed plan")
        fresh_preview = _build_acquire_preview(locked_snapshot, conflicts)
        if (
            expected_fingerprint is not None
            and fresh_preview["preview_fingerprint"]
            != expected_fingerprint.value
        ):
            raise ValueError("stale_preview")
        if conflicts:
            raise ValueError(json.dumps({"conflicts": conflicts}, ensure_ascii=False, sort_keys=True))
        cursor.execute(
            "INSERT INTO caregiver_availability_locks (plan_id, status, is_active, created_by) "
            "VALUES (%s, 'active', 1, %s)",
            (request["plan_id"], request["actor"]),
        )
        lock_id = cursor.lastrowid
        if isinstance(lock_id, bool) or not isinstance(lock_id, int) or lock_id <= 0:
            raise ValueError("lock insert did not return a valid id")
        for row in locked_snapshot["lock_rows"]:
            cursor.execute(
                "INSERT INTO caregiver_availability_lock_days "
                "(lock_id, segment_id, staff_id, lock_date, active_marker) VALUES (%s, %s, %s, %s, 1)",
                (lock_id, row["segment_id"], row["staff_id"], row["lock_date"]),
            )
        cursor.execute(
            "UPDATE caregiver_matching_plans SET status = 'accepted', is_active = 1 "
            "WHERE id = %s AND case_no = %s AND status = 'proposed' AND is_active = 1",
            (request["plan_id"], request["case_no"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("matching plan lifecycle update failed")
        payload = build_acquired_event_payload({**request, "lock_id": lock_id}, locked_snapshot)
        if expected_fingerprint is not None:
            payload["preview_fingerprint"] = expected_fingerprint.value
        cursor.execute(
            "INSERT INTO caregiver_availability_lock_events "
            "(lock_id, event_type, event_key, actor, reason, payload) VALUES (%s, 'lock_acquired', %s, %s, NULL, %s)",
            (lock_id, request["event_key"], request["actor"], json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))),
        )
        return {"result": "created", "lock_id": lock_id, "plan_id": request["plan_id"], "case_no": request["case_no"], "lock_rows": locked_snapshot["lock_rows"]}
    finally:
        pass


# Kept cohesive so the read snapshot and all occupancy facts share one DB view.
def preview_caregiver_availability_lock(
    case_no: Any,
    plan_id: Any,
) -> dict[str, Any]:
    request = normalize_lock_acquisition_request(
        case_no,
        plan_id,
        "preview-only",
        "preview-only",
        1,
    )
    connection = cursor = None
    cursor_closed = {"value": False}
    connection_closed = {"value": False}
    try:
        connection = get_connection()
        cursor = connection.cursor()
        plan, segments = _load_prelock_snapshot(
            cursor,
            request["case_no"],
            request["plan_id"],
        )
        cursor.execute(
            "SELECT case_no, status, start_date, end_date "
            "FROM orders WHERE case_no = %s",
            (request["case_no"],),
        )
        order = _one(cursor, "case not found")
        snapshot = _canonical_snapshot(
            request["case_no"],
            request["plan_id"],
            order,
            plan,
            segments,
        )
        if plan["status"] != "proposed" or plan["is_active"] != 1:
            raise ValueError("matching plan is not an active proposed plan")
        commitment_days = _require_active_precontract_commitment(cursor, request["plan_id"])
        snapshot = _with_exact_commitment_lock_rows(snapshot, commitment_days)
        _require_customer_pre_execution_commitment(
            cursor, request["case_no"], request["plan_id"],
        )
        conflicts = _occupancy_conflicts(cursor, snapshot)
        return _build_acquire_preview(snapshot, conflicts)
    finally:
        _close_once(cursor, cursor_closed)
        _close_once(connection, connection_closed)


def _build_acquire_preview(snapshot, conflicts):
    occupancy = tuple(
        {
            "segment_id": row["segment_id"],
            "staff_id": row["staff_id"],
            "occupancy_date": row["lock_date"].isoformat(),
            "kind": row["lock_kind"],
        }
        for row in _proposed_occupancy_rows(snapshot)
    )
    payload = {
        "case_no": snapshot["case_no"],
        "plan_id": snapshot["plan_id"],
        "service_day_count": sum(
            row["kind"] == WaitingDepositOccupancyKind.SERVICE
            for row in occupancy
        ),
        "buffer_day_count": sum(
            row["kind"] == WaitingDepositOccupancyKind.BUFFER
            for row in occupancy
        ),
        "occupancy": occupancy,
        "conflicts": tuple(conflicts),
        "apply_allowed": not conflicts,
    }
    return {
        **payload,
        "preview_fingerprint": fingerprint_payload(payload).value,
    }


def _optional_preview_fingerprint(value):
    if value is None:
        return None
    return PreviewFingerprint(value)

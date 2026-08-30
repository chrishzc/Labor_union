"""Matching-plan communication, willingness, resume, and cancellation events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineDeliveryTaskId, LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.ports import unconfigured_connection_factory
from subsystems.line.delivery_contracts import (
    EnqueueLineDeliveryResult,
    LineDeliveryCommandOutcome,
)
from subsystems.line.ports import LineDeliveryTaskRepositoryPort


get_connection = unconfigured_connection_factory


LineDeliveryTaskRepositoryFactory = Callable[
    [Any], LineDeliveryTaskRepositoryPort
]


def _unconfigured_line_delivery_task_repository(
    _connection: Any,
) -> LineDeliveryTaskRepositoryPort:
    raise RuntimeError("LINE delivery task repository is not configured")


get_line_delivery_task_repository: LineDeliveryTaskRepositoryFactory = (
    _unconfigured_line_delivery_task_repository
)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field} is too long")
    return normalized


def _close(resource: Any) -> None:
    closer = getattr(resource, "close", None)
    if callable(closer):
        try:
            closer()
        except BaseException:
            pass


def _event_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise ValueError("matching event payload is invalid")
    return dict(value)


def _load_contact_state(cursor: Any, case_no: str, plan_id: int) -> dict[str, Any]:
    cursor.execute(
        """SELECT p.id, p.case_no, p.version, p.status, p.is_active,
                  o.status AS order_status, c.line_user_id AS client_line_user_id
             FROM caregiver_matching_plans p
             JOIN orders o ON o.case_no = p.case_no
             JOIN clients c ON c.id = o.client_id
            WHERE p.id = %s AND p.case_no = %s""",
        (plan_id, case_no),
    )
    plan = cursor.fetchone()
    if not isinstance(plan, Mapping):
        raise ValueError("matching plan not found")
    cursor.execute(
        """SELECT s.id AS segment_id, s.segment_order, s.staff_id,
                  s.assigned_start_date, s.assigned_end_date,
                  st.name AS staff_name, st.line_user_id AS staff_line_user_id
             FROM caregiver_matching_plan_segments s
             JOIN staff st ON st.id = s.staff_id
            WHERE s.plan_id = %s
            ORDER BY s.segment_order ASC""",
        (plan_id,),
    )
    segments = [dict(row) for row in (cursor.fetchall() or [])]
    if not 1 <= len(segments) <= 4:
        raise ValueError("matching plan segments are invalid")
    cursor.execute(
        """SELECT id, segment_id, event_type, event_key, actor, payload, occurred_at
             FROM caregiver_matching_plan_events
            WHERE plan_id = %s
            ORDER BY occurred_at ASC, id ASC""",
        (plan_id,),
    )
    events = [dict(row) for row in (cursor.fetchall() or [])]
    latest_willingness: dict[int, str] = {}
    info_sent: dict[int, set[str]] = {}
    resume_sent: set[int] = set()
    for event in events:
        segment_id = event.get("segment_id")
        if not isinstance(segment_id, int):
            continue
        payload = _event_payload(event.get("payload"))
        if event.get("event_type") == "willingness_changed":
            status = payload.get("willingness")
            if status not in {"pending", "willing", "unwilling"}:
                raise ValueError("matching willingness event is invalid")
            latest_willingness[segment_id] = status
        elif event.get("event_type") in {"info_1_sent", "info_2_sent"}:
            info_sent.setdefault(segment_id, set()).add(event["event_type"])
        elif event.get("event_type") == "resume_sent":
            resume_sent.add(segment_id)
    public_segments = []
    for segment in segments:
        segment_id = _positive_int(segment["segment_id"], "segment_id")
        public_segments.append(
            {
                **segment,
                "assigned_start_date": segment["assigned_start_date"].isoformat()
                if hasattr(segment["assigned_start_date"], "isoformat")
                else str(segment["assigned_start_date"]),
                "assigned_end_date": segment["assigned_end_date"].isoformat()
                if hasattr(segment["assigned_end_date"], "isoformat")
                else str(segment["assigned_end_date"]),
                "willingness": latest_willingness.get(segment_id, "pending"),
                "info_1_sent": "info_1_sent" in info_sent.get(segment_id, set()),
                "info_2_sent": "info_2_sent" in info_sent.get(segment_id, set()),
                "resume_sent": segment_id in resume_sent,
            }
        )
    return {
        "plan": dict(plan),
        "segments": public_segments,
        "all_willing": all(
            segment["willingness"] == "willing" for segment in public_segments
        ),
    }


def get_matching_plan_contact_state(case_no: Any, plan_id: Any) -> dict[str, Any]:
    case_no = _text(case_no, "case_no", 50)
    plan_id = _positive_int(plan_id, "plan_id")
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        return _load_contact_state(cursor, case_no, plan_id)
    finally:
        _close(cursor)
        _close(connection)


def get_active_matching_plan_state(case_no: Any) -> dict[str, Any]:
    """Reload the active negotiation plan and its deposit-lock lifecycle."""
    case_no = _text(case_no, "case_no", 50)
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """SELECT id
                 FROM caregiver_matching_plans
                WHERE case_no = %s
                  AND is_active = 1
                  AND status IN ('proposed', 'accepted')
                ORDER BY version DESC
                LIMIT 1""",
            (case_no,),
        )
        active_plan = cursor.fetchone()
        if not isinstance(active_plan, Mapping):
            raise ValueError("active matching plan not found")
        plan_id = _positive_int(active_plan.get("id"), "plan_id")
        state = _load_contact_state(cursor, case_no, plan_id)
        cursor.execute(
            """SELECT id AS lock_id, plan_id, status, created_by, created_at
                 FROM caregiver_availability_locks
                WHERE plan_id = %s
                  AND status = 'active'
                  AND is_active = 1
                LIMIT 1""",
            (plan_id,),
        )
        lock = cursor.fetchone()
        state["availability_lock"] = dict(lock) if isinstance(lock, Mapping) else None
        cursor.execute(
            """SELECT contracted_amount_ntd AS deposit_receivable,
                      allocated_net_amount_ntd AS deposit_received,
                      CASE WHEN settlement_state = 'settled' THEN updated_at END
                          AS deposit_received_at
                 FROM client_deposit_settlement_projection
                WHERE case_no = %s""",
            (case_no,),
        )
        payment = cursor.fetchone()
        state["deposit"] = dict(payment) if isinstance(payment, Mapping) else None
        return state
    finally:
        _close(cursor)
        _close(connection)


def _run_in_application_uow(operation: Callable[[Any, Any], dict[str, Any]]) -> dict[str, Any]:
    """Own one matching communication mutation and its durable task atomically."""
    connection = cursor = None
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
        _close(cursor)
        _close(connection)


def _enqueue_matching_willingness_reply(
    connection: Any,
    *,
    event_id: int,
    event_key: str,
    reply_to_user_id: str,
    reply_message: str,
) -> int:
    """Enqueue the reply through the caller-owned canonical LINE repository."""
    request = LineDeliveryRequest(
        recipient=LineRecipient(
            LineRecipientType.USER,
            LineUserId(reply_to_user_id),
        ),
        message_kind=LineMessageKind.TEXT,
        payload_json=canonical_line_payload_json(
            {"type": "text", "text": reply_message}
        ),
        scheduled_at=datetime.now(timezone.utc),
        idempotency_key=IdempotencyKey(
            f"line-matching-willingness:{event_key}"
        ),
        correlation_id=CorrelationId(
            f"matching-willingness:{event_key}"
        ),
        source_aggregate_type="matching_willingness_card",
        source_aggregate_identity=str(event_id),
    )
    result = get_line_delivery_task_repository(connection).enqueue(request)
    if not isinstance(result, EnqueueLineDeliveryResult):
        raise TypeError("LINE delivery task enqueue returned an invalid result")
    if result.outcome not in {
        LineDeliveryCommandOutcome.CREATED,
        LineDeliveryCommandOutcome.EXISTING,
    }:
        raise ValueError("LINE willingness reply task was not accepted")
    if not isinstance(result.task_id, LineDeliveryTaskId):
        raise TypeError("LINE delivery task enqueue returned an invalid task ID")
    return result.task_id.value


def record_matching_plan_willingness(
    case_no: Any,
    plan_id: Any,
    segment_id: Any,
    willingness: Any,
    event_key: Any,
    actor: Any,
    *,
    reply_to_user_id: Any | None = None,
    reply_message: Any | None = None,
) -> dict[str, Any]:
    case_no = _text(case_no, "case_no", 50)
    plan_id = _positive_int(plan_id, "plan_id")
    segment_id = _positive_int(segment_id, "segment_id")
    if willingness not in {"pending", "willing", "unwilling"}:
        raise ValueError("willingness is invalid")
    event_key = _text(event_key, "event_key", 100)
    actor = _text(actor, "actor", 100)
    if (reply_to_user_id is None) != (reply_message is None):
        raise ValueError("LINE reply recipient and message must be supplied together")
    if reply_to_user_id is not None:
        reply_to_user_id = _text(reply_to_user_id, "reply_to_user_id", 255)
        reply_message = _text(reply_message, "reply_message", 2000)
    return _run_in_application_uow(
        lambda connection, cursor: _record_matching_plan_willingness_in_transaction(
            connection, cursor, case_no, plan_id, segment_id, willingness,
            event_key, actor, reply_to_user_id, reply_message
        )
    )


def _record_matching_plan_willingness_in_transaction(
    connection: Any,
    cursor: Any,
    case_no: str,
    plan_id: int,
    segment_id: int,
    willingness: str,
    event_key: str,
    actor: str,
    reply_to_user_id: str | None,
    reply_message: str | None,
) -> dict[str, Any]:
    try:
        cursor.execute(
            """SELECT p.status, p.is_active, s.id AS segment_id
                 FROM caregiver_matching_plans p
                 JOIN caregiver_matching_plan_segments s ON s.plan_id = p.id
                WHERE p.id = %s AND p.case_no = %s AND s.id = %s
                FOR UPDATE""",
            (plan_id, case_no, segment_id),
        )
        row = cursor.fetchone()
        if (
            not isinstance(row, Mapping)
            or row.get("status") not in {"proposed", "accepted"}
            or row.get("segment_id") != segment_id
        ):
            raise ValueError("matching segment is not editable")
        cursor.execute(
            """SELECT id, plan_id, segment_id, event_type, payload
                 FROM caregiver_matching_plan_events
                WHERE event_key = %s FOR UPDATE""",
            (event_key,),
        )
        existing = cursor.fetchone()
        payload = {"willingness": willingness}
        if existing is not None:
            if (
                existing.get("plan_id") == plan_id
                and existing.get("segment_id") == segment_id
                and existing.get("event_type") == "willingness_changed"
                and _event_payload(existing.get("payload")) == payload
            ):
                return {"status": "idempotent_replay", "event_id": existing["id"]}
            raise ValueError("event_key belongs to a different matching event")
        cursor.execute(
            """INSERT INTO caregiver_matching_plan_events
                   (plan_id, segment_id, event_type, event_key, actor, payload)
               VALUES (%s, %s, 'willingness_changed', %s, %s, %s)""",
            (
                plan_id,
                segment_id,
                event_key,
                actor,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        event_id = _positive_int(cursor.lastrowid, "event_id")
        line_task_id = None
        if reply_to_user_id is not None:
            line_task_id = _enqueue_matching_willingness_reply(
                connection,
                event_id=event_id,
                event_key=event_key,
                reply_to_user_id=reply_to_user_id,
                reply_message=reply_message,
            )
        return {"status": "recorded", "event_id": event_id, "line_task_id": line_task_id, **payload}
    finally:
        pass


def cancel_matching_plan(
    case_no: Any,
    plan_id: Any,
    event_key: Any,
    actor: Any,
    reason: Any,
) -> dict[str, Any]:
    case_no = _text(case_no, "case_no", 50)
    plan_id = _positive_int(plan_id, "plan_id")
    event_key = _text(event_key, "event_key", 100)
    actor = _text(actor, "actor", 100)
    reason = _text(reason, "reason", 255)
    return _run_in_application_uow(
        lambda connection, cursor: _cancel_matching_plan_in_transaction(
            connection, cursor, case_no, plan_id, event_key, actor, reason
        )
    )


def _cancel_matching_plan_in_transaction(
    connection: Any,
    cursor: Any,
    case_no: str,
    plan_id: int,
    event_key: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    try:
        cursor.execute(
            """SELECT p.status, p.is_active, o.status AS order_status
                 FROM caregiver_matching_plans p
                 JOIN orders o ON o.case_no = p.case_no
                WHERE p.id = %s AND p.case_no = %s FOR UPDATE""",
            (plan_id, case_no),
        )
        plan = cursor.fetchone()
        if not isinstance(plan, Mapping):
            raise ValueError("matching plan not found")
        cursor.execute(
            """SELECT id, plan_id, segment_id, event_type, payload
                 FROM caregiver_matching_plan_events
                WHERE event_key = %s FOR UPDATE""",
            (event_key,),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if (
                existing.get("plan_id") == plan_id
                and existing.get("segment_id") is None
                and existing.get("event_type") == "plan_cancelled"
                and _event_payload(existing.get("payload")).get("reason") == reason
            ):
                return {"status": "idempotent_replay", "event_id": existing["id"]}
            raise ValueError("event_key belongs to a different matching event")
        if (
            plan.get("status") != "proposed"
            or plan.get("is_active") != 1
            or plan.get("order_status") != "洽談中"
        ):
            raise ValueError("only an active proposed negotiation plan can be cancelled")
        cursor.execute(
            """UPDATE caregiver_matching_plans
                  SET status = 'cancelled', is_active = NULL
                WHERE id = %s AND case_no = %s
                  AND status = 'proposed' AND is_active = 1""",
            (plan_id, case_no),
        )
        if cursor.rowcount != 1:
            raise ValueError("matching plan cancellation did not affect one row")
        cursor.execute(
            """INSERT INTO caregiver_matching_plan_events
                   (plan_id, segment_id, event_type, event_key, actor, payload)
               VALUES (%s, NULL, 'plan_cancelled', %s, %s, %s)""",
            (
                plan_id,
                event_key,
                actor,
                json.dumps({"reason": reason}, ensure_ascii=False, sort_keys=True),
            ),
        )
        event_id = _positive_int(cursor.lastrowid, "event_id")
        return {"status": "cancelled", "event_id": event_id}
    finally:
        pass

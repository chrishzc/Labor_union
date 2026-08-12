"""Candidate-contact pool workflow; it never creates a formal assignment."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Mapping

from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.line.delivery_task_workflow import enqueue_line_task
from subsystems.scheduling.segmented_availability_query import (
    search_segmented_caregiver_availability,
)


def _required_text(value: Any, field: str, maximum: int = 191) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{field}_invalid")
    return value.strip()


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field}_invalid")
    return value


def _close(resource: Any) -> None:
    closer = getattr(resource, "close", None)
    if callable(closer):
        closer()


def _require_full_coverage(case_no: str, staff_id: int, start_date: str, end_date: str) -> dict[str, Any]:
    result = search_segmented_caregiver_availability(
        case_no=case_no,
        segment_count=1,
        segment_drafts=[{"staff_id": staff_id, "start_date": start_date, "end_date": end_date}],
        as_of=date.today().isoformat(),
    )
    candidate = next(
        (item for item in result.get("candidate_options", []) if item.get("staff_id") == staff_id),
        None,
    )
    if not isinstance(candidate, Mapping) or not candidate.get("full_case_coverage"):
        raise ValueError("candidate_no_longer_fully_available")
    return dict(candidate)


def _event_payload(value: Any) -> dict[str, Any]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("candidate_contact_event_invalid")
    return dict(parsed)


def add_candidates(case_no: Any, candidates: Any, actor: Any, event_key: Any) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50)
    actor = _required_text(actor, "actor", 100)
    event_key = _required_text(event_key, "event_key", 100)
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidate_list_required")
    validated = []
    seen: set[int] = set()
    for item in candidates:
        if not isinstance(item, Mapping):
            raise ValueError("candidate_invalid")
        staff_id = _positive_int(item.get("staff_id"), "staff_id")
        if staff_id in seen:
            continue
        seen.add(staff_id)
        start_date = _required_text(item.get("start_date"), "start_date", 10)
        end_date = _required_text(item.get("end_date"), "end_date", 10)
        validated.append(_require_full_coverage(case_no, staff_id, start_date, end_date))
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT case_no FROM orders WHERE case_no=%s AND status='洽談中' FOR UPDATE", (case_no,))
        if not isinstance(cursor.fetchone(), Mapping):
            raise ValueError("candidate_contact_order_not_negotiating")
        cursor.execute("SELECT id FROM caregiver_candidate_contact_pools WHERE case_no=%s FOR UPDATE", (case_no,))
        pool = cursor.fetchone()
        if isinstance(pool, Mapping):
            pool_id = _positive_int(pool["id"], "pool_id")
        else:
            cursor.execute("INSERT INTO caregiver_candidate_contact_pools (case_no, created_by) VALUES (%s,%s)", (case_no, actor))
            pool_id = _positive_int(cursor.lastrowid, "pool_id")
        created_ids = []
        for candidate in validated:
            cursor.execute("SELECT id FROM caregiver_candidate_contact_entries WHERE pool_id=%s AND staff_id=%s AND active_marker=1 FOR UPDATE", (pool_id, candidate["staff_id"]))
            existing = cursor.fetchone()
            if isinstance(existing, Mapping):
                created_ids.append(_positive_int(existing["id"], "candidate_id"))
                continue
            cursor.execute("INSERT INTO caregiver_candidate_contact_entries (pool_id, staff_id, service_start_date, service_end_date, coverage_fingerprint, active_marker) VALUES (%s,%s,%s,%s,%s,1)", (pool_id, candidate["staff_id"], candidate["case_period_start"], candidate["case_period_end"], candidate["coverage_fingerprint"]))
            created_ids.append(_positive_int(cursor.lastrowid, "candidate_id"))
        cursor.execute("INSERT INTO caregiver_candidate_contact_events (pool_id, candidate_id, event_type, event_key, actor, payload) VALUES (%s,NULL,'candidates_added',%s,%s,%s)", (pool_id, event_key, actor, json.dumps({"candidate_ids": created_ids}, sort_keys=True)))
        connection.commit()
        return {"pool_id": pool_id, "candidate_ids": created_ids, "status": "recorded"}
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        _close(cursor)
        _close(connection)


def query_pool(case_no: Any) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50)
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT id, case_no FROM caregiver_candidate_contact_pools WHERE case_no=%s", (case_no,))
        pool = cursor.fetchone()
        if not isinstance(pool, Mapping):
            return {"case_no": case_no, "candidates": []}
        pool_id = _positive_int(pool["id"], "pool_id")
        cursor.execute("SELECT e.id, e.staff_id, e.service_start_date, e.service_end_date, e.status, e.created_at, s.name AS staff_name FROM caregiver_candidate_contact_entries e JOIN staff s ON s.id=e.staff_id WHERE e.pool_id=%s AND e.active_marker=1 ORDER BY e.id", (pool_id,))
        entries = [dict(row) for row in cursor.fetchall() or []]
        cursor.execute("SELECT candidate_id, event_type, payload, occurred_at FROM caregiver_candidate_contact_events WHERE pool_id=%s ORDER BY occurred_at,id", (pool_id,))
        events = [dict(row) for row in cursor.fetchall() or []]
        by_candidate: dict[int, list[dict[str, Any]]] = {}
        for event in events:
            candidate_id = event.get("candidate_id")
            if isinstance(candidate_id, int):
                by_candidate.setdefault(candidate_id, []).append(event)
        candidates = []
        for entry in entries:
            willingness, reason = "pending", None
            information: dict[str, dict[str, Any] | None] = {"1": None, "2": None}
            for event in by_candidate.get(entry["id"], []):
                payload = _event_payload(event["payload"])
                if event["event_type"] == "willingness_changed":
                    willingness, reason = payload["willingness"], payload.get("reason")
                if event["event_type"] in {"info_1_sent", "info_2_sent"}:
                    information[event["event_type"][5]] = {"status": payload["delivery_status"], "sent_at": event["occurred_at"].isoformat()}
            candidates.append({**entry, "willingness": willingness, "reason": reason, "information": information})
        return {"pool_id": pool_id, "case_no": case_no, "candidates": candidates}
    finally:
        _close(cursor)
        _close(connection)


def send_information(case_no: Any, candidate_id: Any, info_type: Any, actor: Any, event_key: Any) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50)
    candidate_id = _positive_int(candidate_id, "candidate_id")
    actor = _required_text(actor, "actor", 100)
    event_key = _required_text(event_key, "event_key", 100)
    if info_type not in {1, 2}:
        raise ValueError("info_type_invalid")
    connection = cursor = None
    try:
        connection = get_connection(); cursor = connection.cursor()
        cursor.execute("SELECT p.id AS pool_id, e.staff_id, e.service_start_date, e.service_end_date, s.line_user_id FROM caregiver_candidate_contact_pools p JOIN caregiver_candidate_contact_entries e ON e.pool_id=p.id JOIN staff s ON s.id=e.staff_id WHERE p.case_no=%s AND e.id=%s AND e.active_marker=1 FOR UPDATE", (case_no, candidate_id))
        entry = cursor.fetchone()
        if not isinstance(entry, Mapping): raise ValueError("candidate_contact_not_found")
        _require_full_coverage(case_no, entry["staff_id"], str(entry["service_start_date"]), str(entry["service_end_date"]))
        recipient = entry.get("line_user_id")
        if not isinstance(recipient, str) or not recipient.strip(): raise ValueError("caregiver_has_no_line_delivery_identity")
        cursor.execute("SELECT id FROM caregiver_candidate_contact_events WHERE event_key=%s FOR UPDATE", (event_key,))
        existing = cursor.fetchone()
        if isinstance(existing, Mapping):
            connection.rollback(); return {"status": "idempotent_replay", "event_id": existing["id"]}
        task_id = enqueue_line_task(cursor, to_user_id=recipient.strip(), message_content=f"訂單資訊-{info_type}\n服務期間：{entry['service_start_date']}～{entry['service_end_date']}", task_type="candidate_matching_willingness_card", payload={"case_no": case_no, "candidate_id": candidate_id, "info_type": info_type}, source_event_id=event_key, idempotency_key=event_key)
        cursor.execute("INSERT INTO caregiver_candidate_contact_events (pool_id,candidate_id,event_type,event_key,actor,payload) VALUES (%s,%s,%s,%s,%s,%s)", (entry["pool_id"], candidate_id, f"info_{info_type}_sent", event_key, actor, json.dumps({"line_task_id": task_id, "delivery_status": "queued"}, sort_keys=True)))
        event_id = _positive_int(cursor.lastrowid, "event_id"); connection.commit()
        return {"status": "queued", "event_id": event_id, "line_task_id": task_id}
    except Exception:
        if connection is not None: connection.rollback()
        raise
    finally:
        _close(cursor); _close(connection)


def record_willingness(case_no: Any, candidate_id: Any, willingness: Any, reason: Any, actor: Any, event_key: Any) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50); candidate_id = _positive_int(candidate_id, "candidate_id")
    actor = _required_text(actor, "actor", 100); event_key = _required_text(event_key, "event_key", 100)
    if willingness not in {"willing", "unwilling"}: raise ValueError("willingness_invalid")
    reason = _required_text(reason, "reason", 500) if willingness == "unwilling" else (str(reason or "").strip() or "人工補登願意")
    connection = cursor = None
    try:
        connection = get_connection(); cursor = connection.cursor()
        cursor.execute("SELECT p.id AS pool_id FROM caregiver_candidate_contact_pools p JOIN caregiver_candidate_contact_entries e ON e.pool_id=p.id WHERE p.case_no=%s AND e.id=%s AND e.active_marker=1 FOR UPDATE", (case_no, candidate_id))
        row = cursor.fetchone()
        if not isinstance(row, Mapping): raise ValueError("candidate_contact_not_found")
        cursor.execute("SELECT id FROM caregiver_candidate_contact_events WHERE event_key=%s FOR UPDATE", (event_key,))
        existing = cursor.fetchone()
        if isinstance(existing, Mapping): connection.rollback(); return {"status":"idempotent_replay", "event_id":existing["id"]}
        cursor.execute("INSERT INTO caregiver_candidate_contact_events (pool_id,candidate_id,event_type,event_key,actor,payload) VALUES (%s,%s,'willingness_changed',%s,%s,%s)", (row["pool_id"], candidate_id, event_key, actor, json.dumps({"willingness": willingness, "reason": reason}, ensure_ascii=False, sort_keys=True)))
        event_id = _positive_int(cursor.lastrowid, "event_id"); connection.commit(); return {"status":"recorded", "event_id":event_id}
    except Exception:
        if connection is not None: connection.rollback()
        raise
    finally:
        _close(cursor); _close(connection)

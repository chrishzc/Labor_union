"""File: candidate_contact_pool_workflow.py
Description: 管理候選聯繫池 workflow 與其 typed state，不建立正式指派。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.fingerprints import fingerprint_payload
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


@dataclass(frozen=True, slots=True)
class CandidateInformationDelivery:
    status: str
    sent_at: datetime

    def __post_init__(self) -> None:
        if self.status not in {
            "queued",
            "pending",
            "sent",
            "retryable_failed",
            "failed",
            "cancelled",
        }:
            raise ValueError("information_delivery_status_invalid")
        if not isinstance(self.sent_at, datetime):
            raise TypeError("sent_at_invalid")


@dataclass(frozen=True, slots=True)
class CandidateInformationState:
    information_1: CandidateInformationDelivery | None = None
    information_2: CandidateInformationDelivery | None = None

    def __post_init__(self) -> None:
        if self.information_1 is not None and not isinstance(
            self.information_1, CandidateInformationDelivery
        ):
            raise TypeError("information_1_invalid")
        if self.information_2 is not None and not isinstance(
            self.information_2, CandidateInformationDelivery
        ):
            raise TypeError("information_2_invalid")


@dataclass(frozen=True, slots=True)
class CandidateContactEventState:
    id: int
    candidate_id: int | None
    event_key: str
    event_type: str
    actor: str
    occurred_at: datetime
    payload_fingerprint: str

    def __post_init__(self) -> None:
        _positive_int(self.id, "event_id")
        if self.candidate_id is not None:
            _positive_int(self.candidate_id, "candidate_id")
        _required_text(self.event_key, "event_key", 100)
        _required_text(self.actor, "actor", 100)
        if self.event_type not in {
            "candidates_added",
            "info_1_sent",
            "info_2_sent",
            "willingness_changed",
        }:
            raise ValueError("event_type_invalid")
        if self.event_type == "candidates_added":
            if self.candidate_id is not None:
                raise ValueError("candidates_added_candidate_invalid")
        elif self.candidate_id is None:
            raise ValueError("candidate_id_required")
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at_invalid")
        if (
            not isinstance(self.payload_fingerprint, str)
            or len(self.payload_fingerprint) != 64
            or self.payload_fingerprint != self.payload_fingerprint.lower()
            or any(char not in "0123456789abcdef" for char in self.payload_fingerprint)
        ):
            raise ValueError("payload_fingerprint_invalid")


@dataclass(frozen=True, slots=True)
class CandidateContactEntryState:
    id: int
    staff_id: int
    service_start_date: date
    service_end_date: date
    status: str
    created_at: datetime
    staff_name: str
    willingness: str
    reason: str | None
    information: CandidateInformationState

    def __post_init__(self) -> None:
        _positive_int(self.id, "candidate_id")
        _positive_int(self.staff_id, "staff_id")
        if not isinstance(self.service_start_date, date) or not isinstance(
            self.service_end_date, date
        ):
            raise TypeError("service_date_invalid")
        if self.service_start_date > self.service_end_date:
            raise ValueError("service_date_range_invalid")
        if self.status not in {"active", "selected", "withdrawn"}:
            raise ValueError("candidate_status_invalid")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at_invalid")
        _required_text(self.staff_name, "staff_name", 100)
        if self.willingness not in {"pending", "willing", "unwilling"}:
            raise ValueError("willingness_invalid")
        if self.reason is not None:
            _required_text(self.reason, "reason", 500)
        if self.willingness == "unwilling" and (
            not isinstance(self.reason, str) or not self.reason.strip()
        ):
            raise ValueError("unwilling_reason_required")
        if not isinstance(self.information, CandidateInformationState):
            raise TypeError("information_invalid")


@dataclass(frozen=True, slots=True)
class CandidateContactPoolState:
    pool_id: int | None
    case_no: str
    candidates: tuple[CandidateContactEntryState, ...]
    events: tuple[CandidateContactEventState, ...] = ()

    def __post_init__(self) -> None:
        if self.pool_id is not None:
            _positive_int(self.pool_id, "pool_id")
        _required_text(self.case_no, "case_no", 50)
        if not isinstance(self.candidates, tuple) or len(self.candidates) > 50:
            raise TypeError("candidates_invalid")
        if any(not isinstance(item, CandidateContactEntryState) for item in self.candidates):
            raise TypeError("candidate_entry_invalid")
        if not isinstance(self.events, tuple) or any(
            not isinstance(item, CandidateContactEventState) for item in self.events
        ):
            raise TypeError("events_invalid")
        event_ids = tuple(item.id for item in self.events)
        if event_ids != tuple(sorted(set(event_ids))):
            raise ValueError("event_ids_not_sorted_unique")


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


def _coverage_fingerprint(case_no: str, candidate: Mapping[str, Any]) -> str:
    """Bind the saved contact candidate to the availability facts just rechecked."""
    return fingerprint_payload(
        {
            "case_no": case_no,
            "staff_id": candidate["staff_id"],
            "case_period_start": candidate["case_period_start"],
            "case_period_end": candidate["case_period_end"],
            "required_service_dates": candidate["required_service_dates"],
            "supported_service_dates": candidate["supported_service_dates"],
            "source_scheduling_version": candidate["source_scheduling_version"],
        }
    ).value


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
        candidate = _require_full_coverage(case_no, staff_id, start_date, end_date)
        candidate["coverage_fingerprint"] = _coverage_fingerprint(case_no, candidate)
        validated.append(candidate)
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


def query_pool(
    case_no: Any,
    *,
    connection: Any | None = None,
    for_update: bool = False,
) -> CandidateContactPoolState:
    """Read a typed pool; borrowed connections are never committed or closed."""

    case_no = _required_text(case_no, "case_no", 50)
    owns_connection = connection is None
    cursor = None
    try:
        if connection is None:
            connection = get_connection()
        cursor = connection.cursor()
        lock_clause = " FOR UPDATE" if for_update else ""
        cursor.execute(
            "SELECT id, case_no FROM caregiver_candidate_contact_pools WHERE case_no=%s"
            + lock_clause,
            (case_no,),
        )
        pool = cursor.fetchone()
        if not isinstance(pool, Mapping):
            return CandidateContactPoolState(pool_id=None, case_no=case_no, candidates=())
        pool_id = _positive_int(pool["id"], "pool_id")
        cursor.execute("SELECT e.id, e.staff_id, e.service_start_date, e.service_end_date, e.status, e.created_at, s.name AS staff_name FROM caregiver_candidate_contact_entries e JOIN staff s ON s.id=e.staff_id WHERE e.pool_id=%s AND e.active_marker=1 ORDER BY e.id" + lock_clause, (pool_id,))
        entries = [dict(row) for row in cursor.fetchall() or []]
        cursor.execute("SELECT id, candidate_id, event_type, event_key, actor, payload, occurred_at FROM caregiver_candidate_contact_events WHERE pool_id=%s ORDER BY occurred_at,id" + lock_clause, (pool_id,))
        events = [dict(row) for row in cursor.fetchall() or []]
        typed_events: list[CandidateContactEventState] = []
        for event in events:
            event_id = _positive_int(event.get("id"), "event_id")
            candidate_id = event.get("candidate_id")
            if candidate_id is not None:
                candidate_id = _positive_int(candidate_id, "candidate_id")
            occurred_at = event.get("occurred_at")
            if not isinstance(occurred_at, datetime):
                raise TypeError("event occurred_at must be a datetime value")
            payload = _event_payload(event.get("payload"))
            typed_events.append(
                CandidateContactEventState(
                    id=event_id,
                    candidate_id=candidate_id,
                    event_key=_required_text(event.get("event_key"), "event_key", 100),
                    event_type=_required_text(event.get("event_type"), "event_type", 100),
                    actor=_required_text(event.get("actor"), "actor", 100),
                    occurred_at=occurred_at,
                    payload_fingerprint=fingerprint_payload(payload).value,
                )
            )
        by_candidate: dict[int, list[dict[str, Any]]] = {}
        for event in events:
            candidate_id = event.get("candidate_id")
            if isinstance(candidate_id, int):
                by_candidate.setdefault(candidate_id, []).append(event)
        candidates: list[CandidateContactEntryState] = []
        for entry in entries:
            service_start_date = entry["service_start_date"]
            service_end_date = entry["service_end_date"]
            created_at = entry["created_at"]
            if type(service_start_date) is not date or type(service_end_date) is not date:
                raise TypeError("candidate service dates must be date values")
            if type(created_at) is not datetime:
                raise TypeError("candidate created_at must be a datetime value")
            willingness, reason, information = _typed_candidate_projection(
                by_candidate.get(entry["id"], [])
            )
            candidates.append(
                CandidateContactEntryState(
                    id=entry["id"],
                    staff_id=entry["staff_id"],
                    service_start_date=service_start_date,
                    service_end_date=service_end_date,
                    status=entry["status"],
                    created_at=created_at,
                    staff_name=entry["staff_name"],
                    willingness=willingness,
                    reason=reason,
                    information=information,
                )
            )
        return CandidateContactPoolState(
            pool_id=pool_id,
            case_no=case_no,
            candidates=tuple(candidates),
            events=tuple(sorted(typed_events, key=lambda item: item.id)),
        )
    finally:
        _close(cursor)
        if owns_connection:
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


def _candidate_projection(events: list[dict[str, Any]]):
    willingness, reason = "pending", None
    information: dict[str, dict[str, Any] | None] = {"1": None, "2": None}
    relevant_types = {"willingness_changed", "info_1_sent", "info_2_sent"}
    for event in events:
        event_type = event["event_type"]
        if event_type not in relevant_types:
            continue
        payload = _event_payload(event["payload"])
        if event_type == "willingness_changed":
            willingness, reason = payload["willingness"], payload.get("reason")
            continue
        information[event_type[5]] = {
            "status": payload["delivery_status"],
            "sent_at": event["occurred_at"].isoformat(),
        }
    return willingness, reason, information


def _typed_candidate_projection(
    events: list[dict[str, Any]],
) -> tuple[str, str | None, CandidateInformationState]:
    willingness, reason, information = _candidate_projection(events)
    typed_information: dict[str, CandidateInformationDelivery | None] = {
        "1": None,
        "2": None,
    }
    for key, value in information.items():
        if value is None:
            continue
        sent_at = value["sent_at"]
        if isinstance(sent_at, str):
            sent_at = datetime.fromisoformat(sent_at)
        elif not isinstance(sent_at, datetime):
            raise TypeError("information sent_at must be a datetime value")
        typed_information[key] = CandidateInformationDelivery(
            status=value["status"],
            sent_at=sent_at,
        )
    return (
        willingness,
        reason,
        CandidateInformationState(
            information_1=typed_information["1"],
            information_2=typed_information["2"],
        ),
    )


__all__ = [
    "CandidateContactEventState",
    "CandidateContactEntryState",
    "CandidateContactPoolState",
    "CandidateInformationDelivery",
    "CandidateInformationState",
    "add_candidates",
    "query_pool",
    "record_willingness",
    "send_information",
]

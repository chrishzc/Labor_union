"""File: candidate_contact_pool_workflow.py
Description: 管理候選聯繫池 workflow 與其 typed state，不建立正式指派。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineUserId
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.order_information_repository import MySqlOrderInformationRepository
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.ports import unconfigured_connection_factory
from subsystems.scheduling.matching_line_cards import candidate_contact_information_card
from subsystems.scheduling.segmented_availability_query import (
    search_candidate_inquiry_availability,
)


get_connection = unconfigured_connection_factory
segmented_facts_port: Any | None = None


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
    event_id: int | None = None
    line_task_id: int | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            "queued",
            "pending",
            "sent",
            "manually_confirmed",
            "retryable_failed",
            "failed",
            "cancelled",
        }:
            raise ValueError("information_delivery_status_invalid")
        if not isinstance(self.sent_at, datetime):
            raise TypeError("sent_at_invalid")
        if self.event_id is not None:
            _positive_int(self.event_id, "information_event_id")
        if self.line_task_id is not None:
            _positive_int(self.line_task_id, "information_line_task_id")


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
    latest_willingness_event_id: int | None = None

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
        if self.latest_willingness_event_id is not None:
            _positive_int(self.latest_willingness_event_id, "latest_willingness_event_id")


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
    availability_kwargs = {
        "case_no": case_no,
        "segment_drafts": [{"staff_id": staff_id, "start_date": start_date, "end_date": end_date}],
        "as_of": date.today().isoformat(),
        "filter_policy": {"region": False, "cooking": False, "preferred_service_days": False, "daily_service_hours": False},
    }
    if segmented_facts_port is not None:
        availability_kwargs["facts_port"] = segmented_facts_port
    result = search_candidate_inquiry_availability(
        **availability_kwargs,
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


def _run_in_application_uow(operation: Callable[[Any, Any], dict[str, Any]]) -> dict[str, Any]:
    """Own one candidate-pool mutation transaction at the Application boundary."""
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
    return _run_in_application_uow(
        lambda connection, cursor: _add_candidates_in_transaction(
            connection, cursor, case_no, validated, actor, event_key
        )
    )


def _add_candidates_in_transaction(
    connection: Any,
    cursor: Any,
    case_no: str,
    validated: list[dict[str, Any]],
    actor: str,
    event_key: str,
) -> dict[str, Any]:
    try:
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
        new_candidate_created = False
        for candidate in validated:
            cursor.execute("SELECT id FROM caregiver_candidate_contact_entries WHERE pool_id=%s AND staff_id=%s AND active_marker=1 FOR UPDATE", (pool_id, candidate["staff_id"]))
            existing = cursor.fetchone()
            if isinstance(existing, Mapping):
                created_ids.append(_positive_int(existing["id"], "candidate_id"))
                continue
            cursor.execute("INSERT INTO caregiver_candidate_contact_entries (pool_id, staff_id, service_start_date, service_end_date, coverage_fingerprint, active_marker) VALUES (%s,%s,%s,%s,%s,1)", (pool_id, candidate["staff_id"], candidate["case_period_start"], candidate["case_period_end"], candidate["coverage_fingerprint"]))
            created_ids.append(_positive_int(cursor.lastrowid, "candidate_id"))
            new_candidate_created = True
        payload = {
            "candidate_ids": created_ids,
            "candidate_coverage_fingerprints": [
                {
                    "staff_id": candidate["staff_id"],
                    "coverage_fingerprint": candidate["coverage_fingerprint"],
                }
                for candidate in validated
            ],
        }
        cursor.execute(
            "SELECT id,pool_id,candidate_id,event_type,actor,payload "
            "FROM caregiver_candidate_contact_events WHERE event_key=%s FOR UPDATE",
            (event_key,),
        )
        existing_event = cursor.fetchone()
        if isinstance(existing_event, Mapping):
            if (
                existing_event.get("pool_id") == pool_id
                and existing_event.get("candidate_id") is None
                and existing_event.get("event_type") == "candidates_added"
                and existing_event.get("actor") == actor
                and _event_payload(existing_event.get("payload")) == payload
            ):
                return {
                    "pool_id": pool_id,
                    "candidate_ids": created_ids,
                    "status": "recorded",
                }
            raise ValueError("candidate_contact_idempotency_conflict")
        cursor.execute("INSERT INTO caregiver_candidate_contact_events (pool_id, candidate_id, event_type, event_key, actor, payload) VALUES (%s,NULL,'candidates_added',%s,%s,%s)", (pool_id, event_key, actor, json.dumps(payload, sort_keys=True)))
        if new_candidate_created:
            _cancel_pending_manual_followup(cursor, pool_id)
        return {"pool_id": pool_id, "candidate_ids": created_ids, "status": "recorded"}
    finally:
        pass


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
            willingness, reason, latest_willingness_event_id, information = _typed_candidate_projection(
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
                    latest_willingness_event_id=latest_willingness_event_id,
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


_MANUAL_INFORMATION_METHODS = {"phone", "in_person", "paper", "other"}


def _manual_information_preview(
    state: CandidateContactPoolState,
    candidate_id: Any,
    info_type: Any,
    confirmation_method: Any,
    reason: Any,
    actor: Any,
) -> dict[str, Any]:
    candidate_id = _positive_int(candidate_id, "candidate_id")
    if info_type not in {1, 2}:
        raise ValueError("info_type_invalid")
    confirmation_method = _required_text(
        confirmation_method, "confirmation_method", 30
    )
    if confirmation_method not in _MANUAL_INFORMATION_METHODS:
        raise ValueError("confirmation_method_invalid")
    reason = _required_text(reason, "reason", 500)
    actor = _required_text(actor, "actor", 100)
    candidate = next(
        (item for item in state.candidates if item.id == candidate_id),
        None,
    )
    if candidate is None:
        raise ValueError("candidate_contact_not_found")
    if candidate.status != "active":
        raise ValueError("candidate_contact_is_read_only")
    information = (
        candidate.information.information_1
        if info_type == 1
        else candidate.information.information_2
    )
    current_status = information.status if information is not None else None
    if current_status in {"sent", "manually_confirmed"}:
        raise ValueError("candidate_information_already_confirmed")
    expected_version = max((event.id for event in state.events), default=0)
    payload = {
        "case_no": state.case_no,
        "pool_id": state.pool_id,
        "candidate_id": candidate.id,
        "staff_id": candidate.staff_id,
        "info_type": info_type,
        "confirmation_method": confirmation_method,
        "reason": reason,
        "actor": actor,
        "expected_version": expected_version,
    }
    return {
        **payload,
        "current_status": current_status,
        "preview_fingerprint": fingerprint_payload(payload).value,
        "apply_allowed": True,
    }


def preview_manual_information_confirmation(
    case_no: Any,
    candidate_id: Any,
    info_type: Any,
    confirmation_method: Any,
    reason: Any,
    actor: Any,
) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50)
    connection = cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT status FROM orders WHERE case_no=%s", (case_no,))
        order = cursor.fetchone()
        if not isinstance(order, Mapping) or order.get("status") != "洽談中":
            raise ValueError("candidate_contact_order_not_negotiating")
        state = query_pool(case_no, connection=connection)
        return _manual_information_preview(
            state, candidate_id, info_type, confirmation_method, reason, actor
        )
    finally:
        _close(cursor)
        _close(connection)


def apply_manual_information_confirmation(
    case_no: Any,
    candidate_id: Any,
    info_type: Any,
    confirmation_method: Any,
    reason: Any,
    actor: Any,
    expected_version: Any,
    preview_fingerprint: Any,
    event_key: Any,
) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50)
    candidate_id = _positive_int(candidate_id, "candidate_id")
    actor = _required_text(actor, "actor", 100)
    event_key = _required_text(event_key, "event_key", 100)
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
        raise ValueError("expected_version_invalid")
    preview_fingerprint = _required_text(
        preview_fingerprint, "preview_fingerprint", 64
    )
    if len(preview_fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in preview_fingerprint
    ):
        raise ValueError("preview_fingerprint_invalid")
    return _run_in_application_uow(
        lambda connection, cursor: _apply_manual_information_confirmation_in_transaction(
            connection,
            cursor,
            case_no,
            candidate_id,
            info_type,
            confirmation_method,
            reason,
            actor,
            expected_version,
            preview_fingerprint,
            event_key,
        )
    )


def _apply_manual_information_confirmation_in_transaction(
    connection: Any,
    cursor: Any,
    case_no: str,
    candidate_id: int,
    info_type: Any,
    confirmation_method: Any,
    reason: Any,
    actor: str,
    expected_version: int,
    preview_fingerprint: str,
    event_key: str,
) -> dict[str, Any]:
    try:
        cursor.execute(
            "SELECT status FROM orders WHERE case_no=%s FOR UPDATE", (case_no,)
        )
        order = cursor.fetchone()
        state = query_pool(case_no, connection=connection, for_update=True)
        existing = next(
            (event for event in state.events if event.event_key == event_key),
            None,
        )
        confirmation_method = _required_text(
            confirmation_method, "confirmation_method", 30
        )
        if confirmation_method not in _MANUAL_INFORMATION_METHODS:
            raise ValueError("confirmation_method_invalid")
        reason = _required_text(reason, "reason", 500)
        payload = {
            "delivery_status": "manually_confirmed",
            "confirmation_method": confirmation_method,
            "reason": reason,
            "preview_fingerprint": preview_fingerprint,
        }
        if existing is not None:
            if (
                existing.candidate_id == candidate_id
                and existing.event_type == f"info_{info_type}_sent"
                and existing.actor == actor
                and existing.payload_fingerprint == fingerprint_payload(payload).value
            ):
                return {
                    "status": "idempotent_replay",
                    "event_id": existing.id,
                    "pool_version": existing.id,
                    "delivery_status": "manually_confirmed",
                    "confirmation_method": confirmation_method,
                }
            raise ValueError("event_key_belongs_to_different_candidate_event")
        preview = _manual_information_preview(
            state, candidate_id, info_type, confirmation_method, reason, actor
        )
        if not isinstance(order, Mapping) or order.get("status") != "洽談中":
            raise ValueError("candidate_contact_order_not_negotiating")
        if preview["expected_version"] != expected_version:
            raise ValueError("candidate_contact_pool_version_stale")
        if preview["preview_fingerprint"] != preview_fingerprint:
            raise ValueError("candidate_information_preview_stale")
        candidate = next(item for item in state.candidates if item.id == candidate_id)
        _require_full_coverage(
            case_no,
            candidate.staff_id,
            candidate.service_start_date.isoformat(),
            candidate.service_end_date.isoformat(),
        )
        cursor.execute(
            "INSERT INTO caregiver_candidate_contact_events "
            "(pool_id,candidate_id,event_type,event_key,actor,payload) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                state.pool_id,
                candidate_id,
                f"info_{info_type}_sent",
                event_key,
                actor,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        event_id = _positive_int(cursor.lastrowid, "event_id")
        _cancel_pending_manual_followup(cursor, state.pool_id)
        return {
            "status": "recorded",
            "event_id": event_id,
            "pool_version": event_id,
            "delivery_status": "manually_confirmed",
            "confirmation_method": confirmation_method,
        }
    finally:
        pass


def preview_information(case_no: str, candidate_id: int, info_type: int):
    case_no = _required_text(case_no, "case_no", 50)
    candidate_id = _positive_int(candidate_id, "candidate_id")
    connection = get_connection()
    try:
        return MySqlOrderInformationRepository(connection).preview_candidate_information(case_no, candidate_id, info_type)
    finally:
        _close(connection)


def preview_recontact_information(case_no: str, candidate_id: int, info_type: int):
    """Preview current Orders dates and recheck the original candidate against them."""

    case_no = _required_text(case_no, "case_no", 50)
    candidate_id = _positive_int(candidate_id, "candidate_id")
    if info_type not in {1, 2}:
        raise ValueError("info_type_invalid")
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT orders.status,orders.start_date,orders.end_date,entry.staff_id "
                "FROM orders JOIN caregiver_candidate_contact_pools pool "
                "ON pool.case_no=orders.case_no "
                "JOIN caregiver_candidate_contact_entries entry ON entry.pool_id=pool.id "
                "WHERE orders.case_no=%s AND entry.id=%s "
                "AND entry.active_marker=1 AND entry.status='active'",
                (case_no, candidate_id),
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise ValueError("candidate_contact_not_found")
        if row.get("status") != "洽談中":
            raise ValueError("candidate_contact_order_not_negotiating")
        service_period = _current_service_period(row)
        _require_full_coverage(
            case_no,
            int(row["staff_id"]),
            service_period[0].isoformat(),
            service_period[1].isoformat(),
        )
        return MySqlOrderInformationRepository(connection).preview_candidate_information(
            case_no,
            candidate_id,
            info_type,
            service_period=service_period,
        )
    finally:
        _close(connection)


def send_information(case_no: Any, candidate_id: Any, info_type: Any, actor: Any, event_key: Any, preview_fingerprint: str | None = None) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50)
    candidate_id = _positive_int(candidate_id, "candidate_id")
    actor = _required_text(actor, "actor", 100)
    event_key = _required_text(event_key, "event_key", 100)
    if info_type not in {1, 2}:
        raise ValueError("info_type_invalid")
    return _run_in_application_uow(
        lambda connection, cursor: _send_information_in_transaction(
            connection, cursor, case_no, candidate_id, info_type, actor, event_key, preview_fingerprint
        )
    )


def send_recontact_information(
    case_no: Any,
    candidate_id: Any,
    info_type: Any,
    actor: Any,
    event_key: Any,
    preview_fingerprint: str | None = None,
) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50)
    candidate_id = _positive_int(candidate_id, "candidate_id")
    actor = _required_text(actor, "actor", 100)
    event_key = _required_text(event_key, "event_key", 93)
    if info_type not in {1, 2}:
        raise ValueError("info_type_invalid")
    return _run_in_application_uow(
        lambda connection, cursor: _send_information_in_transaction(
            connection,
            cursor,
            case_no,
            candidate_id,
            info_type,
            actor,
            event_key,
            preview_fingerprint,
            refresh_period_from_order=True,
        )
    )


def _send_information_in_transaction(
    connection: Any,
    cursor: Any,
    case_no: str,
    candidate_id: int,
    info_type: int,
    actor: str,
    event_key: str,
    preview_fingerprint: str | None = None,
    refresh_period_from_order: bool = False,
) -> dict[str, Any]:
    try:
        cursor.execute("SELECT p.id AS pool_id, e.staff_id, e.service_start_date, e.service_end_date, "
                       "e.coverage_fingerprint,"
                       "s.line_user_id,o.status AS order_status,o.start_date AS order_start_date,"
                       "o.end_date AS order_end_date FROM caregiver_candidate_contact_pools p "
                       "JOIN caregiver_candidate_contact_entries e ON e.pool_id=p.id "
                       "JOIN staff s ON s.id=e.staff_id JOIN orders o ON o.case_no=p.case_no "
                       "WHERE p.case_no=%s AND e.id=%s AND e.active_marker=1 "
                       "AND e.status='active' FOR UPDATE", (case_no, candidate_id))
        entry = cursor.fetchone()
        if not isinstance(entry, Mapping): raise ValueError("candidate_contact_not_found")
        if entry.get("order_status") != "洽談中":
            raise ValueError("candidate_contact_order_not_negotiating")
        recipient = entry.get("line_user_id")
        if not isinstance(recipient, str) or not recipient.strip(): raise ValueError("caregiver_has_no_line_delivery_identity")
        cursor.execute("SELECT id,pool_id,candidate_id,event_type,actor,payload FROM caregiver_candidate_contact_events WHERE event_key=%s FOR UPDATE", (event_key,))
        existing = cursor.fetchone()
        if isinstance(existing, Mapping):
            if (
                existing.get("pool_id") != entry.get("pool_id")
                or existing.get("candidate_id") != candidate_id
                or existing.get("event_type") != f"info_{info_type}_sent"
                or existing.get("actor") != actor
                or _event_payload(existing.get("payload")).get("preview_fingerprint")
                != preview_fingerprint
            ):
                raise ValueError("candidate_information_idempotency_conflict")
            existing_payload = _event_payload(existing.get("payload"))
            task_id = existing_payload.get("line_task_id")
            return {
                "status": "idempotent_replay",
                "event_id": existing["id"],
                "line_task_id": _positive_int(task_id, "line_task_id") if task_id is not None else None,
            }
        if refresh_period_from_order:
            if entry.get("order_status") != "洽談中":
                raise ValueError("candidate_contact_order_not_negotiating")
            service_period = _current_service_period(entry)
        else:
            service_period = (entry["service_start_date"], entry["service_end_date"])
        coverage = _require_full_coverage(
            case_no,
            entry["staff_id"],
            str(service_period[0]),
            str(service_period[1]),
        )
        preview = MySqlOrderInformationRepository(connection).preview_candidate_information(
            case_no,
            candidate_id,
            info_type,
            for_update=True,
            service_period=service_period if refresh_period_from_order else None,
        )
        if preview_fingerprint != preview.preview_fingerprint:
            raise ValueError("candidate_information_preview_stale")
        refreshed_coverage_fingerprint = (
            _coverage_fingerprint(case_no, coverage)
            if refresh_period_from_order
            else None
        )
        if refresh_period_from_order and (
            service_period != (entry["service_start_date"], entry["service_end_date"])
            or refreshed_coverage_fingerprint != entry.get("coverage_fingerprint")
        ):
            cursor.execute(
                "UPDATE caregiver_candidate_contact_entries "
                "SET service_start_date=%s,service_end_date=%s,coverage_fingerprint=%s "
                "WHERE id=%s AND service_start_date=%s AND service_end_date=%s",
                (
                    service_period[0],
                    service_period[1],
                    refreshed_coverage_fingerprint,
                    candidate_id,
                    entry["service_start_date"],
                    entry["service_end_date"],
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("candidate_contact_period_conflict")
            cursor.execute(
                "INSERT INTO caregiver_candidate_contact_events "
                "(pool_id,candidate_id,event_type,event_key,actor,payload) "
                "VALUES (%s,%s,'willingness_changed',%s,%s,%s)",
                (
                    entry["pool_id"],
                    candidate_id,
                    f"{event_key}:period",
                    actor,
                    json.dumps(
                        {
                            "response_kind": "candidate_period_refreshed",
                            "before_start_date": str(entry["service_start_date"]),
                            "before_end_date": str(entry["service_end_date"]),
                            "after_start_date": str(service_period[0]),
                            "after_end_date": str(service_period[1]),
                            "before_coverage_fingerprint": str(
                                entry.get("coverage_fingerprint") or ""
                            ),
                            "after_coverage_fingerprint": refreshed_coverage_fingerprint,
                        },
                        sort_keys=True,
                    ),
                ),
            )
        message = candidate_contact_information_card(
            case_no,
            info_type,
            preview.text,
            hashlib.sha256(event_key.encode("utf-8")).hexdigest(),
            _candidate_contact_liff_url(
                hashlib.sha256(event_key.encode("utf-8")).hexdigest()
            ),
        )
        delivery = MySqlLineDeliveryTaskRepository(connection).enqueue(
            LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, LineUserId(recipient.strip())),
                LineMessageKind.FLEX,
                message,
                datetime.now(timezone.utc),
                IdempotencyKey(event_key),
                CorrelationId(f"candidate-contact:{event_key}"),
                "candidate_matching_willingness_card",
                event_key,
            )
        )
        task_id = delivery.task_id.value
        cursor.execute("INSERT INTO caregiver_candidate_contact_events (pool_id,candidate_id,event_type,event_key,actor,payload) VALUES (%s,%s,%s,%s,%s,%s)", (entry["pool_id"], candidate_id, f"info_{info_type}_sent", event_key, actor, json.dumps({"line_task_id": task_id, "delivery_status": "queued", "preview_fingerprint": preview_fingerprint}, sort_keys=True)))
        event_id = _positive_int(cursor.lastrowid, "event_id")
        _cancel_pending_manual_followup(cursor, int(entry["pool_id"]))
        return {"status": "queued", "event_id": event_id, "line_task_id": task_id}
    finally:
        pass


def _current_service_period(row: Mapping[str, object]) -> tuple[date, date]:
    start = row.get("order_start_date", row.get("start_date"))
    end = row.get("order_end_date", row.get("end_date"))
    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("candidate_contact_current_service_period_invalid")
    return start, end


def _candidate_contact_liff_url(interaction_reference: str) -> str:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if liff_id and liff_id != "your_liff_id_here":
        return (
            f"https://liff.line.me/{liff_id}/?"
            + urlencode({"target": "candidate_contact", "ref": interaction_reference})
        )
    public_base = (
        os.getenv("LINE_PUBLIC_BASE_URL", "").strip()
        or os.getenv("BASE_URL", "").strip()
    ).rstrip("/")
    if public_base.startswith("https://"):
        return f"{public_base}/line-candidate-contact?{urlencode({'ref': interaction_reference})}"
    raise ValueError("candidate_contact_liff_not_configured")


def record_willingness(case_no: Any, candidate_id: Any, willingness: Any, reason: Any, actor: Any, event_key: Any) -> dict[str, Any]:
    case_no = _required_text(case_no, "case_no", 50); candidate_id = _positive_int(candidate_id, "candidate_id")
    actor = _required_text(actor, "actor", 100); event_key = _required_text(event_key, "event_key", 100)
    if willingness not in {"willing", "unwilling"}: raise ValueError("willingness_invalid")
    if not isinstance(reason, str): raise ValueError("reason_invalid")
    reason = _required_text(reason, "reason", 500) if willingness == "unwilling" else (reason.strip() or "人工補登願意")
    return _run_in_application_uow(
        lambda connection, cursor: _record_willingness_in_transaction(
            connection, cursor, case_no, candidate_id, willingness, reason, actor, event_key
        )
    )


def _record_willingness_in_transaction(
    connection: Any,
    cursor: Any,
    case_no: str,
    candidate_id: int,
    willingness: str,
    reason: str,
    actor: str,
    event_key: str,
) -> dict[str, Any]:
    try:
        cursor.execute(
            "SELECT p.id AS pool_id,o.status AS order_status "
            "FROM caregiver_candidate_contact_pools p "
            "JOIN caregiver_candidate_contact_entries e ON e.pool_id=p.id "
            "JOIN orders o ON o.case_no=p.case_no "
            "WHERE p.case_no=%s AND e.id=%s AND e.active_marker=1 "
            "AND e.status='active' FOR UPDATE",
            (case_no, candidate_id),
        )
        row = cursor.fetchone()
        if not isinstance(row, Mapping): raise ValueError("candidate_contact_not_found")
        if row.get("order_status") != "洽談中":
            raise ValueError("candidate_contact_order_not_negotiating")
        payload = {"willingness": willingness, "reason": reason}
        cursor.execute("SELECT id,pool_id,candidate_id,event_type,actor,payload FROM caregiver_candidate_contact_events WHERE event_key=%s FOR UPDATE", (event_key,))
        existing = cursor.fetchone()
        if isinstance(existing, Mapping):
            if (
                existing.get("pool_id") == row["pool_id"]
                and existing.get("candidate_id") == candidate_id
                and existing.get("event_type") == "willingness_changed"
                and existing.get("actor") == actor
                and _event_payload(existing.get("payload")) == payload
            ):
                return {"status":"idempotent_replay", "event_id":existing["id"]}
            raise ValueError("candidate_contact_idempotency_conflict")
        cursor.execute("INSERT INTO caregiver_candidate_contact_events (pool_id,candidate_id,event_type,event_key,actor,payload) VALUES (%s,%s,'willingness_changed',%s,%s,%s)", (row["pool_id"], candidate_id, event_key, actor, json.dumps(payload, ensure_ascii=False, sort_keys=True)))
        event_id = _positive_int(cursor.lastrowid, "event_id")
        if willingness == "willing":
            _cancel_pending_candidate_coordination(cursor, int(row["pool_id"]))
        return {"status":"recorded", "event_id":event_id}
    finally:
        pass


def _cancel_pending_candidate_coordination(cursor: Any, pool_id: int) -> None:
    cursor.execute(
        "UPDATE line_delivery_tasks SET processing_status='cancelled',"
        "error_code='candidate_contact_pool_resolved',"
        "error_message='candidate contact pool already has a willing caregiver',"
        "lease_owner=NULL,lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL "
        "WHERE processing_status IN ('pending','retryable_failed') AND (("
        "source_aggregate_type='candidate_contact_adjustment' "
        "AND CAST(source_aggregate_identity AS UNSIGNED)=%s) OR ("
        "source_aggregate_type='candidate_contact_question' "
        "AND CAST(source_aggregate_identity AS UNSIGNED) IN ("
        "SELECT id FROM caregiver_candidate_contact_events WHERE pool_id=%s)))",
        (pool_id, pool_id),
    )
    _cancel_pending_manual_followup(cursor, pool_id)


def _cancel_pending_manual_followup(cursor: Any, pool_id: int) -> None:
    cursor.execute(
        "UPDATE line_delivery_tasks SET processing_status='cancelled',"
        "error_code='candidate_contact_pool_changed',"
        "error_message='candidate contact pool changed before manual follow-up delivery',"
        "lease_owner=NULL,lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL "
        "WHERE source_aggregate_type='candidate_contact_manual_followup' "
        "AND CAST(SUBSTRING_INDEX(source_aggregate_identity,':',1) AS UNSIGNED)=%s "
        "AND processing_status IN ('pending','retryable_failed')",
        (pool_id,),
    )


def _candidate_projection(events: list[dict[str, Any]]):
    willingness, reason = "pending", None
    latest_willingness_event_id: int | None = None
    information: dict[str, dict[str, Any] | None] = {"1": None, "2": None}
    relevant_types = {"willingness_changed", "info_1_sent", "info_2_sent"}
    for event in events:
        event_type = event["event_type"]
        if event_type not in relevant_types:
            continue
        payload = _event_payload(event["payload"])
        if event_type == "willingness_changed":
            if payload.get("willingness") in {"pending", "willing", "unwilling"}:
                willingness, reason = payload["willingness"], payload.get("reason")
                latest_willingness_event_id = _positive_int(
                    event["id"], "latest_willingness_event_id"
                )
            continue
        information[event_type[5]] = {
            "status": payload["delivery_status"],
            "sent_at": event["occurred_at"].isoformat(),
            "event_id": event["id"],
            "line_task_id": payload.get("line_task_id"),
        }
    return willingness, reason, latest_willingness_event_id, information


def _typed_candidate_projection(
    events: list[dict[str, Any]],
) -> tuple[str, str | None, int | None, CandidateInformationState]:
    willingness, reason, latest_willingness_event_id, information = _candidate_projection(events)
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
            event_id=_positive_int(value["event_id"], "information_event_id"),
            line_task_id=(
                _positive_int(value["line_task_id"], "information_line_task_id")
                if value["line_task_id"] is not None else None
            ),
        )
    return (
        willingness,
        reason,
        latest_willingness_event_id,
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
    "apply_manual_information_confirmation",
    "preview_manual_information_confirmation",
]

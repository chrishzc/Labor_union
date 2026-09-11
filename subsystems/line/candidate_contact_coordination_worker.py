"""Close silent candidate responses and dispatch one deferred adjustment summary."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId, LineUserId
from domains.scheduling.candidate_contact_response import (
    CandidateContactState,
    CandidatePoolResolution,
    category_label,
    resolve_candidate_pool,
)
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from shared_kernel.identities import CorrelationId, IdempotencyKey


_RESPONSE_LIFETIME = timedelta(hours=24)
_MANUAL_FOLLOWUP_SOURCE = "candidate_contact_manual_followup"


@dataclass(frozen=True, slots=True)
class CandidateManualFollowup:
    pool_id: int
    case_no: str
    candidate_count: int
    no_interest_count: int
    timed_out_count: int
    action_required: str
    completed_at: datetime
    notification_status: str
    notification_task_id: int | None


@dataclass(frozen=True, slots=True)
class CandidateManualFollowupPage:
    items: tuple[CandidateManualFollowup, ...]
    total: int


@dataclass(frozen=True, slots=True)
class CandidateManualFollowupIssue:
    category: str
    label: str
    detail: str
    candidate_ids: tuple[int, ...]
    formal_terms_supported: bool


@dataclass(frozen=True, slots=True)
class CandidateManualFollowupCandidate:
    candidate_id: int
    staff_name: str
    recontact_queued: bool


@dataclass(frozen=True, slots=True)
class CandidateManualFollowupOperation:
    pool_id: int
    case_no: str
    customer_answer_event_id: int
    customer_answered_at: datetime
    issues: tuple[CandidateManualFollowupIssue, ...]
    candidates: tuple[CandidateManualFollowupCandidate, ...]
    terms_change_completed: bool
    terms_change_receipt_at: datetime | None
    recontact_allowed: bool


_FORMAL_TERMS_CATEGORIES = frozenset(
    {
        "service_dates",
        "daily_service_window",
        "daily_service_hours",
        "cooking_requirement",
    }
)


class CandidateContactCoordinationWorker:
    def __init__(self, connection_factory: Callable[[], Any], now: Callable[[], datetime], *, batch_size: int = 25) -> None:
        self._connection_factory = connection_factory
        self._now = now
        self._batch_size = batch_size

    def run_once(self) -> int:
        connection = self._connection_factory()
        processed = 0
        try:
            with connection.cursor() as cursor:
                processed += _cancel_inactive_order_manual_followups(cursor)
                cursor.execute(
                    "SELECT pool.id,pool.case_no FROM caregiver_candidate_contact_pools pool "
                    "JOIN orders ON orders.case_no=pool.case_no AND orders.status='洽談中' "
                    "ORDER BY pool.id LIMIT %s FOR UPDATE",
                    (self._batch_size,),
                )
                pools = tuple(cursor.fetchall() or ())
                for pool in pools:
                    processed += _process_pool(connection, cursor, pool, self._now())
            connection.commit()
            return processed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _cancel_inactive_order_manual_followups(cursor) -> int:
    cursor.execute(
        "UPDATE line_delivery_tasks task "
        "JOIN caregiver_candidate_contact_pools pool ON "
        "CAST(SUBSTRING_INDEX(task.source_aggregate_identity,':',1) AS UNSIGNED)=pool.id "
        "JOIN orders ON orders.case_no=pool.case_no "
        "SET task.processing_status='cancelled',"
        "task.error_code='candidate_contact_order_inactive',"
        "task.error_message='candidate contact order left negotiating state',"
        "task.lease_owner=NULL,task.lease_acquired_at_utc=NULL,"
        "task.lease_expires_at_utc=NULL "
        "WHERE task.source_aggregate_type=%s "
        "AND task.processing_status IN ('pending','retryable_failed') "
        "AND orders.status<>'洽談中'",
        (_MANUAL_FOLLOWUP_SOURCE,),
    )
    return int(cursor.rowcount or 0)


def query_manual_followups(
    connection_factory: Callable[[], Any],
    now: datetime,
    *,
    limit: int = 100,
) -> CandidateManualFollowupPage:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("candidate_contact_manual_followup_limit_invalid")
    connection = connection_factory()
    items: list[CandidateManualFollowup] = []
    total = 0
    after_pool_id = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,group_id FROM line_alert_notification_targets "
                "WHERE target_type='group' AND enabled=TRUE ORDER BY id LIMIT 2"
            )
            targets = tuple(cursor.fetchall() or ())
            target_status = (
                "pending"
                if len(targets) == 1
                and str(targets[0].get("group_id") or "").strip()
                else "target_missing"
                if not targets
                else "target_conflict"
            )
            while True:
                cursor.execute(
                    "SELECT pool.id,pool.case_no FROM caregiver_candidate_contact_pools pool "
                    "JOIN orders ON orders.case_no=pool.case_no AND orders.status='洽談中' "
                    "WHERE pool.id>%s ORDER BY pool.id LIMIT 100",
                    (after_pool_id,),
                )
                pools = tuple(cursor.fetchall() or ())
                if not pools:
                    break
                after_pool_id = int(pools[-1]["id"])
                for pool in pools:
                    candidates, events, states, adjustment_events = _read_pool_observation(
                        cursor, int(pool["id"]), now
                    )
                    resolution = resolve_candidate_pool(
                        states.values(),
                        has_condition_adjustments=bool(adjustment_events),
                    )
                    if resolution is not CandidatePoolResolution.UNION_MANUAL_FOLLOWUP:
                        continue
                    total += 1
                    if len(items) >= limit:
                        continue
                    source_identity = _manual_followup_source_identity(int(pool["id"]), events)
                    cursor.execute(
                        "SELECT id,processing_status FROM line_delivery_tasks "
                        "WHERE source_aggregate_type=%s AND source_aggregate_identity=%s "
                        "ORDER BY id DESC LIMIT 1",
                        (_MANUAL_FOLLOWUP_SOURCE, source_identity),
                    )
                    task = cursor.fetchone()
                    if isinstance(task, Mapping):
                        notification_status = str(task["processing_status"])
                        task_id = int(task["id"])
                    else:
                        notification_status = target_status
                        task_id = None
                    items.append(
                        _manual_followup_snapshot(
                            pool,
                            candidates,
                            events,
                            notification_status=notification_status,
                            notification_task_id=task_id,
                        )
                    )
        return CandidateManualFollowupPage(tuple(items), total)
    finally:
        connection.close()


def query_manual_followup_operation(
    connection_factory: Callable[[], Any],
    pool_id: int,
    case_no: str,
) -> CandidateManualFollowupOperation:
    """Project the exact accepted adjustment and its post-change recontact gate."""

    if isinstance(pool_id, bool) or not isinstance(pool_id, int) or pool_id <= 0:
        raise ValueError("candidate_contact_manual_followup_pool_invalid")
    if not isinstance(case_no, str) or not case_no.strip() or len(case_no.strip()) > 50:
        raise ValueError("candidate_contact_manual_followup_case_invalid")
    canonical_case_no = case_no.strip()
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pool.id,pool.case_no,orders.status AS order_status "
                "FROM caregiver_candidate_contact_pools pool "
                "JOIN orders ON orders.case_no=pool.case_no "
                "WHERE pool.id=%s AND pool.case_no=%s",
                (pool_id, canonical_case_no),
            )
            pool = cursor.fetchone()
            if not isinstance(pool, Mapping):
                raise ValueError("candidate_contact_manual_followup_not_found")
            if pool.get("order_status") != "洽談中":
                raise ValueError("candidate_contact_order_not_negotiating")
            cursor.execute(
                "SELECT entry.id,staff.name AS staff_name "
                "FROM caregiver_candidate_contact_entries entry "
                "JOIN staff ON staff.id=entry.staff_id "
                "WHERE entry.pool_id=%s AND entry.active_marker=1 "
                "AND entry.status='active' ORDER BY entry.id",
                (pool_id,),
            )
            candidate_rows = tuple(cursor.fetchall() or ())
            cursor.execute(
                "SELECT id,candidate_id,event_key,actor,payload,occurred_at "
                "FROM caregiver_candidate_contact_events "
                "WHERE pool_id=%s ORDER BY id",
                (pool_id,),
            )
            events = tuple(cursor.fetchall() or ())
            answer = _latest_accepted_adjustment_answer(events)
            answer_payload = _payload(answer)
            batch_id = int(answer_payload["source_coordination_event_id"])
            batch = next((item for item in events if int(item["id"]) == batch_id), None)
            if not isinstance(batch, Mapping):
                raise ValueError("candidate_contact_adjustment_batch_missing")
            source_ids = tuple(
                sorted(
                    int(value)
                    for value in (_payload(batch).get("source_response_event_ids") or ())
                    if isinstance(value, int) and not isinstance(value, bool) and value > 0
                )
            )
            sources = tuple(item for item in events if int(item["id"]) in source_ids)
            if len(sources) != len(source_ids) or not sources:
                raise ValueError("candidate_contact_adjustment_sources_incomplete")
            issues = _manual_followup_operation_issues(sources)
            affected_ids = {candidate_id for issue in issues for candidate_id in issue.candidate_ids}
            candidates_by_id = {
                int(item["id"]): str(item.get("staff_name") or "").strip()
                for item in candidate_rows
            }
            if not affected_ids or any(
                candidate_id not in candidates_by_id or not candidates_by_id[candidate_id]
                for candidate_id in affected_ids
            ):
                raise ValueError("candidate_contact_adjustment_candidates_incomplete")
            correlation_prefix = f"mobile-matching-followup:{pool_id}:"
            cursor.execute(
                "SELECT created_at FROM order_terms_apply_receipts "
                "WHERE case_no=%s AND correlation_id LIKE %s "
                "AND created_at >= %s ORDER BY id DESC LIMIT 1",
                (
                    canonical_case_no,
                    correlation_prefix + "%",
                    answer["occurred_at"],
                ),
            )
            receipt = cursor.fetchone()
            receipt_at = (
                _aware_utc(receipt.get("created_at"))
                if isinstance(receipt, Mapping) and receipt.get("created_at") is not None
                else None
            )
            recontacted_ids: set[int] = set()
            if receipt_at is not None:
                for event in events:
                    candidate_id = int(event.get("candidate_id") or 0)
                    if (
                        candidate_id in affected_ids
                        and str(event.get("event_type") or "") in {"info_1_sent", "info_2_sent"}
                        and _aware_utc(event.get("occurred_at")) >= receipt_at
                    ):
                        recontacted_ids.add(candidate_id)
            unsupported = any(not issue.formal_terms_supported for issue in issues)
            candidates = tuple(
                CandidateManualFollowupCandidate(
                    candidate_id=candidate_id,
                    staff_name=candidates_by_id[candidate_id],
                    recontact_queued=candidate_id in recontacted_ids,
                )
                for candidate_id in sorted(affected_ids)
            )
            return CandidateManualFollowupOperation(
                pool_id=pool_id,
                case_no=canonical_case_no,
                customer_answer_event_id=int(answer["id"]),
                customer_answered_at=_aware_utc(answer.get("occurred_at")),
                issues=issues,
                candidates=candidates,
                terms_change_completed=receipt_at is not None,
                terms_change_receipt_at=receipt_at,
                recontact_allowed=receipt_at is not None and not unsupported,
            )
    finally:
        connection.close()


def _latest_accepted_adjustment_answer(events) -> Mapping[str, object]:
    answers = _relevant_customer_adjustment_answers(events)
    if not answers:
        raise ValueError("candidate_contact_customer_adjustment_not_accepted")
    latest = max(answers, key=lambda item: int(item["id"]))
    if _payload(latest).get("decision") != "can_adjust":
        raise ValueError("candidate_contact_customer_adjustment_not_accepted")
    return latest


def _manual_followup_operation_issues(
    source_events,
) -> tuple[CandidateManualFollowupIssue, ...]:
    grouped: dict[tuple[str, str], set[int]] = {}
    for event in source_events:
        candidate_id = int(event.get("candidate_id") or 0)
        for issue in _payload(event).get("issues") or ():
            if (
                candidate_id <= 0
                or not isinstance(issue, Mapping)
                or issue.get("mode") != "condition_adjustment"
            ):
                continue
            category = str(issue.get("category") or "").strip()
            detail = str(issue.get("detail") or "").strip()
            if category and detail:
                grouped.setdefault((category, detail), set()).add(candidate_id)
    if not grouped:
        raise ValueError("candidate_contact_adjustment_issues_missing")
    return tuple(
        CandidateManualFollowupIssue(
            category=category,
            label=category_label(category),
            detail=detail,
            candidate_ids=tuple(sorted(candidate_ids)),
            formal_terms_supported=category in _FORMAL_TERMS_CATEGORIES,
        )
        for (category, detail), candidate_ids in sorted(grouped.items())
    )


def _read_pool_observation(cursor, pool_id: int, now: datetime):
    cursor.execute(
        "SELECT entry.id,staff.line_user_id FROM caregiver_candidate_contact_entries entry "
        "JOIN staff ON staff.id=entry.staff_id "
        "WHERE entry.pool_id=%s AND entry.active_marker=1 AND entry.status='active' "
        "ORDER BY entry.id",
        (pool_id,),
    )
    candidates = tuple(cursor.fetchall() or ())
    if not candidates:
        return (), (), {}, ()
    cursor.execute(
        "SELECT id,candidate_id,event_key,actor,payload,occurred_at "
        "FROM caregiver_candidate_contact_events "
        "WHERE pool_id=%s AND event_type='willingness_changed' ORDER BY id",
        (pool_id,),
    )
    events = tuple(cursor.fetchall() or ())
    cursor.execute(
        "SELECT source_event.candidate_id,source_event.id AS source_event_id,"
        "delivery.sent_at_utc FROM caregiver_candidate_contact_events source_event "
        "JOIN line_delivery_tasks delivery ON delivery.id="
        "CAST(JSON_UNQUOTE(JSON_EXTRACT(source_event.payload,'$.line_task_id')) AS UNSIGNED) "
        "WHERE source_event.pool_id=%s AND source_event.event_type IN ('info_1_sent','info_2_sent') "
        "AND delivery.processing_status='sent' ORDER BY delivery.sent_at_utc,source_event.id",
        (pool_id,),
    )
    deliveries = tuple(cursor.fetchall() or ())
    delivered_by_candidate: dict[int, Mapping[str, object]] = {
        int(item["candidate_id"]): item for item in deliveries
    }
    cursor.execute(
        "SELECT CAST(source_aggregate_identity AS UNSIGNED) AS candidate_id,"
        "id AS source_event_id,sent_at_utc FROM line_delivery_tasks "
        "WHERE source_aggregate_type='candidate_contact_answer' "
        "AND processing_status='sent' AND CAST(source_aggregate_identity AS UNSIGNED) IN ("
        "SELECT id FROM caregiver_candidate_contact_entries WHERE pool_id=%s) "
        "ORDER BY sent_at_utc,id",
        (pool_id,),
    )
    for item in tuple(cursor.fetchall() or ()):
        delivered_by_candidate[int(item["candidate_id"])] = item
    states = {
        int(candidate["id"]): _candidate_state(
            int(candidate["id"]),
            events,
            delivered_by_candidate.get(int(candidate["id"])),
            now,
        )
        for candidate in candidates
    }
    return candidates, events, states, _adjustment_events(events)


def _process_pool(connection, cursor, pool: Mapping[str, object], now: datetime) -> int:
    pool_id = int(pool["id"])
    cursor.execute(
        "SELECT entry.id,staff.line_user_id FROM caregiver_candidate_contact_entries entry "
        "JOIN staff ON staff.id=entry.staff_id "
        "WHERE entry.pool_id=%s AND entry.active_marker=1 AND entry.status='active' ORDER BY entry.id",
        (pool_id,),
    )
    candidates = tuple(cursor.fetchall() or ())
    if not candidates:
        return 0
    cursor.execute(
        "SELECT id,candidate_id,event_key,actor,payload,occurred_at FROM caregiver_candidate_contact_events "
        "WHERE pool_id=%s AND event_type='willingness_changed' ORDER BY id",
        (pool_id,),
    )
    events = tuple(cursor.fetchall() or ())
    cursor.execute(
        "SELECT source_event.candidate_id,source_event.id AS source_event_id,delivery.sent_at_utc "
        "FROM caregiver_candidate_contact_events source_event "
        "JOIN line_delivery_tasks delivery "
        "ON delivery.id=CAST(JSON_UNQUOTE(JSON_EXTRACT(source_event.payload,'$.line_task_id')) AS UNSIGNED) "
        "WHERE source_event.pool_id=%s AND source_event.event_type IN ('info_1_sent','info_2_sent') "
        "AND delivery.processing_status='sent' ORDER BY delivery.sent_at_utc,source_event.id",
        (pool_id,),
    )
    deliveries = tuple(cursor.fetchall() or ())
    delivered_by_candidate: dict[int, Mapping[str, object]] = {}
    for item in deliveries:
        delivered_by_candidate[int(item["candidate_id"])] = item
    cursor.execute(
        "SELECT CAST(source_aggregate_identity AS UNSIGNED) AS candidate_id,id AS source_event_id,sent_at_utc "
        "FROM line_delivery_tasks WHERE source_aggregate_type='candidate_contact_answer' "
        "AND processing_status='sent' AND CAST(source_aggregate_identity AS UNSIGNED) IN ("
        "SELECT id FROM caregiver_candidate_contact_entries WHERE pool_id=%s) ORDER BY sent_at_utc,id",
        (pool_id,),
    )
    for item in tuple(cursor.fetchall() or ()):
        delivered_by_candidate[int(item["candidate_id"])] = item

    processed = 0
    current_events = list(events)
    for candidate in candidates:
        candidate_id = int(candidate["id"])
        state = _candidate_state(candidate_id, current_events, delivered_by_candidate.get(candidate_id), now)
        if state is CandidateContactState.DUE_TIMEOUT:
            anchor = delivered_by_candidate.get(candidate_id)
            if anchor is None:
                continue
            event_key = f"candidate-contact-timeout:{candidate_id}:{int(anchor['source_event_id'])}"
            cursor.execute(
                "INSERT IGNORE INTO caregiver_candidate_contact_events "
                "(pool_id,candidate_id,event_type,event_key,actor,payload) "
                "VALUES (%s,%s,'willingness_changed',%s,'system:candidate-contact-timeout',%s)",
                (
                    pool_id,
                    candidate_id,
                    event_key,
                    json.dumps(
                        {
                            "response_kind": "timed_out",
                            "willingness": "pending",
                            "reason": "timed_out",
                            "deadline_hours": 24,
                            "source_information_event_id": int(anchor["source_event_id"]),
                        },
                        sort_keys=True,
                    ),
                ),
            )
            if cursor.rowcount:
                processed += 1
                current_events.append(
                    {
                        "id": int(cursor.lastrowid),
                        "candidate_id": candidate_id,
                        "payload": json.dumps(
                            {"response_kind": "timed_out", "willingness": "pending"}
                        ),
                        "occurred_at": now,
                    }
                )

    states = {
        int(candidate["id"]): _candidate_state(
            int(candidate["id"]), current_events, delivered_by_candidate.get(int(candidate["id"])), now
        )
        for candidate in candidates
    }
    adjustment_events = _adjustment_events(current_events)
    resolution = resolve_candidate_pool(
        states.values(),
        has_condition_adjustments=bool(adjustment_events),
    )
    if resolution in {CandidatePoolResolution.OPEN, CandidatePoolResolution.WILLING}:
        _cancel_pending_manual_followup(cursor, pool_id)
        return processed
    if resolution is CandidatePoolResolution.UNION_MANUAL_FOLLOWUP:
        if _enqueue_manual_followup(connection, cursor, pool, candidates, current_events, now):
            processed += 1
        return processed
    _cancel_pending_manual_followup(cursor, pool_id)
    if _batch_already_dispatched(current_events, adjustment_events):
        return processed
    if _enqueue_adjustment_summary(connection, cursor, pool, adjustment_events, now):
        processed += 1
    return processed


def _candidate_state(
    candidate_id: int,
    events,
    delivery,
    now: datetime,
) -> CandidateContactState:
    candidate_events = [item for item in events if int(item.get("candidate_id") or 0) == candidate_id]
    for event in reversed(candidate_events):
        payload = _payload(event)
        kind = payload.get("response_kind")
        if payload.get("willingness") == "willing":
            return CandidateContactState.WILLING
        if kind in {"no_interest", "timed_out"} or (
            kind is None and payload.get("willingness") == "unwilling"
        ):
            return CandidateContactState.TERMINAL
        if kind == "coordination_requested":
            issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
            if any(isinstance(item, Mapping) and item.get("mode") == "information_question" for item in issues):
                answered = next(
                    (
                        later for later in candidate_events
                        if int(later.get("id") or 0) > int(event.get("id") or 0)
                        and _payload(later).get("response_kind") == "information_answered"
                        and int(_payload(later).get("source_response_event_id") or 0) == int(event["id"])
                    ),
                    None,
                )
                if answered is None:
                    return CandidateContactState.WAITING_CUSTOMER
                if delivery is not None and delivery.get("sent_at_utc") is not None:
                    sent_at = _aware_utc(delivery["sent_at_utc"])
                    if now >= sent_at + _RESPONSE_LIFETIME:
                        return CandidateContactState.DUE_TIMEOUT
                return CandidateContactState.WAITING_FINAL_RESPONSE
            return CandidateContactState.TERMINAL
    if delivery is None or delivery.get("sent_at_utc") is None:
        return CandidateContactState.NOT_DELIVERED
    sent_at = _aware_utc(delivery["sent_at_utc"])
    return (
        CandidateContactState.DUE_TIMEOUT
        if now >= sent_at + _RESPONSE_LIFETIME
        else CandidateContactState.WAITING_INITIAL
    )


def _adjustment_events(events):
    latest: dict[int, Mapping[str, object]] = {}
    for item in events:
        candidate_id = int(item.get("candidate_id") or 0)
        payload = _payload(item)
        if candidate_id and (
            payload.get("response_kind") in {"coordination_requested", "no_interest", "timed_out"}
            or payload.get("willingness") in {"willing", "unwilling"}
        ):
            latest[candidate_id] = item
    answered_source_ids = _answered_adjustment_source_ids(events)
    return tuple(
        item for item in latest.values()
        if int(item["id"]) not in answered_source_ids
        if _payload(item).get("response_kind") == "coordination_requested"
        and any(
            isinstance(issue, Mapping) and issue.get("mode") == "condition_adjustment"
            for issue in (_payload(item).get("issues") or [])
        )
    )


def _customer_adjustment_answers(events) -> tuple[Mapping[str, object], ...]:
    batch_ids = {
        int(item["id"])
        for item in events
        if _payload(item).get("response_kind") == "adjustment_batch_dispatched"
    }
    return tuple(
        item
        for item in events
        if _payload(item).get("response_kind") == "adjustment_customer_answer"
        and _payload(item).get("decision") in {"can_adjust", "cannot_adjust"}
        and int(_payload(item).get("source_coordination_event_id") or 0) in batch_ids
    )


def _answered_adjustment_source_ids(events) -> frozenset[int]:
    batch_sources = {
        int(item["id"]): tuple(
            int(source_id)
            for source_id in (_payload(item).get("source_response_event_ids") or ())
        )
        for item in events
        if _payload(item).get("response_kind") == "adjustment_batch_dispatched"
    }
    return frozenset(
        source_id
        for answer in _customer_adjustment_answers(events)
        for source_id in batch_sources.get(
            int(_payload(answer).get("source_coordination_event_id") or 0),
            (),
        )
    )


def _relevant_customer_adjustment_answers(events) -> tuple[Mapping[str, object], ...]:
    latest_ids = {int(item["id"]) for item in _latest_candidate_responses(events)}
    batch_sources = {
        int(item["id"]): {
            int(source_id)
            for source_id in (_payload(item).get("source_response_event_ids") or ())
        }
        for item in events
        if _payload(item).get("response_kind") == "adjustment_batch_dispatched"
    }
    return tuple(
        answer
        for answer in _customer_adjustment_answers(events)
        if batch_sources.get(
            int(_payload(answer).get("source_coordination_event_id") or 0), set()
        ) & latest_ids
    )


def _batch_already_dispatched(events, adjustment_events) -> bool:
    source_ids = sorted(int(item["id"]) for item in adjustment_events)
    return any(
        _payload(item).get("response_kind") == "adjustment_batch_dispatched"
        and _payload(item).get("source_response_event_ids") == source_ids
        for item in events
    )


def _latest_candidate_responses(events) -> tuple[Mapping[str, object], ...]:
    latest: dict[int, Mapping[str, object]] = {}
    for item in events:
        candidate_id = int(item.get("candidate_id") or 0)
        payload = _payload(item)
        if candidate_id and (
            payload.get("response_kind")
            in {"coordination_requested", "no_interest", "timed_out"}
            or payload.get("willingness") in {"willing", "unwilling"}
        ):
            latest[candidate_id] = item
    return tuple(latest[key] for key in sorted(latest))


def _manual_followup_snapshot(
    pool: Mapping[str, object],
    candidates,
    events,
    *,
    notification_status: str,
    notification_task_id: int | None,
) -> CandidateManualFollowup:
    latest = _latest_candidate_responses(events)
    if len(latest) != len(candidates):
        raise ValueError("candidate_contact_manual_followup_sources_incomplete")
    no_interest = 0
    timed_out = 0
    occurred_at: list[datetime] = []
    for event in latest:
        payload = _payload(event)
        if payload.get("response_kind") == "timed_out":
            timed_out += 1
        else:
            no_interest += 1
        occurred_at.append(_aware_utc(event.get("occurred_at")))
    customer_answers = _relevant_customer_adjustment_answers(events)
    occurred_at.extend(_aware_utc(event.get("occurred_at")) for event in customer_answers)
    action_required = (
        "modify_then_recontact"
        if any(_payload(item).get("decision") == "can_adjust" for item in customer_answers)
        else "manual_resolution"
    )
    return CandidateManualFollowup(
        pool_id=int(pool["id"]),
        case_no=str(pool["case_no"]),
        candidate_count=len(candidates),
        no_interest_count=no_interest,
        timed_out_count=timed_out,
        action_required=action_required,
        completed_at=max(occurred_at),
        notification_status=notification_status,
        notification_task_id=notification_task_id,
    )


def _manual_followup_source_identity(pool_id: int, events) -> str:
    source_ids = sorted(
        int(item["id"])
        for item in (
            *_latest_candidate_responses(events),
            *_relevant_customer_adjustment_answers(events),
        )
    )
    if not source_ids:
        raise ValueError("candidate_contact_manual_followup_sources_missing")
    digest = hashlib.sha256(json.dumps(source_ids).encode("utf-8")).hexdigest()[:24]
    return f"{pool_id}:{max(source_ids)}:{digest}"


def _enqueue_manual_followup(connection, cursor, pool, candidates, events, now: datetime) -> bool:
    cursor.execute(
        "SELECT id,group_id FROM line_alert_notification_targets "
        "WHERE target_type='group' AND enabled=TRUE ORDER BY id LIMIT 2 FOR UPDATE"
    )
    targets = tuple(cursor.fetchall() or ())
    if len(targets) != 1 or not str(targets[0].get("group_id") or "").strip():
        return False
    source_identity = _manual_followup_source_identity(int(pool["id"]), events)
    target = targets[0]
    idempotency_key = IdempotencyKey(
        f"candidate-contact-manual:{source_identity}:{int(target['id'])}"
    )
    cursor.execute(
        "SELECT id FROM line_delivery_tasks WHERE idempotency_key=%s LIMIT 1",
        (idempotency_key.value,),
    )
    if cursor.fetchone() is not None:
        return False
    snapshot = _manual_followup_snapshot(
        pool,
        candidates,
        events,
        notification_status="pending",
        notification_task_id=None,
    )
    if snapshot.action_required == "modify_then_recontact":
        title = "客戶同意調整，待工會修改"
        instruction = "客戶已同意調整條件。請先完成正式案件資料修改，再重新詢問相關月嫂。"
    elif any(
        _payload(item).get("decision") == "cannot_adjust"
        for item in _relevant_customer_adjustment_answers(events)
    ):
        title = "媒合需要人工處理"
        instruction = "客戶目前無法調整條件，請由工會人員接手處理。"
    else:
        title = "媒合需要人工處理"
        instruction = "沒有可與客戶協調的調整條件，請由工會人員接手處理。"
    url = _mobile_admin_liff_url(snapshot.case_no)
    message = canonical_line_payload_json(
        {
            "type": "flex",
            "altText": f"案件 {snapshot.case_no} 的媒合需要工會人工處理",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": title,
                            "weight": "bold",
                            "size": "xl",
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": f"案件編號：{snapshot.case_no}",
                            "size": "sm",
                            "color": "#666666",
                        },
                        {
                            "type": "text",
                            "text": (
                                f"已詢問 {snapshot.candidate_count} 位月嫂，皆未願意承接。"
                                f"{instruction}"
                            ),
                            "size": "sm",
                            "wrap": True,
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#047857",
                            "action": {"type": "uri", "label": "開啟待辦工作台", "uri": url},
                        }
                    ],
                },
            },
        }
    )
    result = MySqlLineDeliveryTaskRepository(connection).enqueue(
        LineDeliveryRequest(
            LineRecipient(
                LineRecipientType.GROUP,
                LineGroupId(str(target["group_id"]).strip()),
            ),
            LineMessageKind.FLEX,
            message,
            now,
            idempotency_key,
            CorrelationId(f"candidate-contact-manual:{source_identity}"),
            _MANUAL_FOLLOWUP_SOURCE,
            source_identity,
        )
    )
    return str(getattr(result.outcome, "value", result.outcome)) == "created"


def _cancel_pending_manual_followup(cursor, pool_id: int) -> None:
    cursor.execute(
        "UPDATE line_delivery_tasks SET processing_status='cancelled',"
        "error_code='candidate_contact_pool_changed',"
        "error_message='candidate contact pool no longer requires manual follow-up',"
        "lease_owner=NULL,lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL "
        "WHERE source_aggregate_type=%s "
        "AND CAST(SUBSTRING_INDEX(source_aggregate_identity,':',1) AS UNSIGNED)=%s "
        "AND processing_status IN ('pending','retryable_failed')",
        (_MANUAL_FOLLOWUP_SOURCE, pool_id),
    )


def _enqueue_adjustment_summary(connection, cursor, pool, adjustment_events, now: datetime) -> bool:
    cursor.execute(
        "SELECT binding.line_user_id FROM orders "
        "JOIN line_identity_role_bindings binding "
        "ON binding.subject_type='customer' AND binding.subject_reference="
        "CAST(orders.client_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
        "AND binding.binding_status='bound' WHERE orders.case_no=%s",
        (pool["case_no"],),
    )
    customer = cursor.fetchone()
    if not isinstance(customer, Mapping) or not str(customer.get("line_user_id") or "").strip():
        return False
    grouped: dict[tuple[str, str], set[int]] = {}
    for event in adjustment_events:
        for issue in _payload(event).get("issues") or []:
            if not isinstance(issue, Mapping) or issue.get("mode") != "condition_adjustment":
                continue
            key = (str(issue.get("category") or ""), str(issue.get("detail") or "").strip())
            grouped.setdefault(key, set()).add(int(event["candidate_id"]))
    items = [
        {"category": category, "label": category_label(category), "detail": detail, "candidate_count": len(ids)}
        for (category, detail), ids in sorted(grouped.items())
    ]
    source_ids = sorted(int(item["id"]) for item in adjustment_events)
    digest = hashlib.sha256(json.dumps(source_ids).encode("utf-8")).hexdigest()[:24]
    event_key = f"candidate-contact-adjustment-batch:{int(pool['id'])}:{digest}"
    payload = {
        "response_kind": "adjustment_batch_dispatched",
        "source_response_event_ids": source_ids,
        "items": items,
    }
    cursor.execute(
        "INSERT IGNORE INTO caregiver_candidate_contact_events "
        "(pool_id,candidate_id,event_type,event_key,actor,payload) "
        "VALUES (%s,%s,'willingness_changed',%s,'system:candidate-contact-coordinator',%s)",
        (pool["id"], adjustment_events[0]["candidate_id"], event_key, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )
    if not cursor.rowcount:
        return False
    batch_event_id = int(cursor.lastrowid)
    reference = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    url = _liff_url("candidate_contact_customer", reference)
    lines = [f"• {item['label']}：{item['detail']}（{item['candidate_count']} 位可重新詢問）" for item in items]
    message = canonical_line_payload_json({
        "type": "flex", "altText": f"案件 {pool['case_no']} 的媒合條件協調",
        "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "spacing": "md", "contents": [
            {"type": "text", "text": "目前原條件尚無月嫂願意承接", "weight": "bold", "size": "xl", "wrap": True},
            {"type": "text", "text": f"案件編號：{pool['case_no']}", "size": "sm", "color": "#666666"},
            {"type": "text", "text": "若能修改以下條件，可再詢問相關月嫂：\n" + "\n".join(lines), "size": "sm", "wrap": True},
            {"type": "text", "text": "修改後仍需重新確認月嫂最新意願。", "size": "sm", "wrap": True, "color": "#555555"}
        ]}, "footer": {"type": "box", "layout": "vertical", "contents": [
            {"type": "button", "style": "primary", "color": "#06C755", "action": {"type": "uri", "label": "回覆是否可調整", "uri": url}}
        ]}}
    })
    MySqlLineDeliveryTaskRepository(connection).enqueue(LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId(str(customer["line_user_id"]).strip())),
        LineMessageKind.FLEX, message, now,
        IdempotencyKey(f"candidate-contact-adjustment:{batch_event_id}"),
        CorrelationId(f"candidate-contact-adjustment:{batch_event_id}"),
        "candidate_contact_adjustment", str(pool["id"]),
    ))
    return True


def _payload(event: Mapping[str, object]) -> Mapping[str, object]:
    value = event.get("payload")
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, Mapping) else {}


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("candidate_contact_delivery_time_invalid")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _liff_url(target: str, reference: str) -> str:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        raise ValueError("candidate_contact_liff_not_configured")
    return f"https://liff.line.me/{liff_id}/?" + urlencode({"target": target, "ref": reference})


def _mobile_admin_liff_url(case_no: str) -> str:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        raise ValueError("candidate_contact_liff_not_configured")
    return f"https://liff.line.me/{liff_id}/?" + urlencode(
        {"target": "staff_review", "case_no": case_no}
    )


__all__ = [
    "CandidateContactCoordinationWorker",
    "CandidateManualFollowup",
    "CandidateManualFollowupCandidate",
    "CandidateManualFollowupIssue",
    "CandidateManualFollowupOperation",
    "CandidateManualFollowupPage",
    "query_manual_followup_operation",
    "query_manual_followups",
]

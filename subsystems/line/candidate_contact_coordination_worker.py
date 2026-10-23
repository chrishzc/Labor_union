"""Internal candidate reminders and human-reviewed adjustment read models."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from domains.scheduling.candidate_contact_response import category_label
from infrastructure.mysql.replacement_matching_query import CANDIDATE_CONTACT_OPEN_SQL, candidate_contact_open


@dataclass(frozen=True, slots=True)
class CandidateManualFollowup:
    pool_id: int
    case_no: str
    candidate_count: int
    reminder_count: int
    reminder_due_at: datetime


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
    question_id: int
    customer_new_conditions: str


class CandidateContactCoordinationWorker:
    """Retire queued automatic coordination effects; new coordination is staff initiated."""
    run_before_delivery = True

    def __init__(self, connection_factory, now, *, batch_size=25):
        self._connection_factory = connection_factory

    def run_once(self) -> int:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE line_delivery_tasks SET processing_status='cancelled',"
                    "error_code='candidate_coordination_staff_only',"
                    "error_message='candidate coordination now uses internal staff tasks',"
                    "lease_owner=NULL,lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL "
                    "WHERE processing_status IN ('pending','retryable_failed') AND "
                    "source_aggregate_type IN ('candidate_contact_adjustment','candidate_contact_manual_followup','candidate_contact_staff_review','matching_plan_decision')", ()
                )
                count = cursor.rowcount
                cursor.execute(
                    "UPDATE line_delivery_tasks task SET processing_status='cancelled',"
                    "error_code='candidate_question_not_staff_authored',"
                    "error_message='automatic customer questions are retired',"
                    "lease_owner=NULL,lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL "
                    "WHERE processing_status IN ('pending','retryable_failed') AND source_aggregate_type='candidate_contact_question' "
                    "AND NOT EXISTS (SELECT 1 FROM caregiver_candidate_contact_events authored WHERE "
                    "JSON_UNQUOTE(JSON_EXTRACT(authored.payload,'$.response_kind')) IN ('information_question_sent','adjustment_question_sent') "
                    "AND (CAST(JSON_UNQUOTE(JSON_EXTRACT(authored.payload,'$.source_response_event_id')) AS UNSIGNED)="
                    "CAST(task.source_aggregate_identity AS UNSIGNED) OR authored.id=CAST(task.source_aggregate_identity AS UNSIGNED)))", ()
                )
                count += cursor.rowcount
            connection.commit()
            return count
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def query_manual_followups(connection_factory, now, *, limit=100, page=1):
    """A 24-hour reminder is read-only and never changes willingness or closes a reply."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("candidate_contact_manual_followup_limit_invalid")
    if type(page) is not int or page < 1:
        raise ValueError("candidate_contact_manual_followup_page_invalid")
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pool.id AS pool_id,pool.case_no,entry.id AS candidate_id,event.id AS information_event_id,"
                "delivery.sent_at_utc FROM caregiver_candidate_contact_pools pool "
                "JOIN orders ON orders.case_no=pool.case_no "
                "JOIN caregiver_candidate_contact_entries entry ON entry.pool_id=pool.id AND entry.active_marker=1 AND entry.status='active' "
                "JOIN caregiver_candidate_contact_events event ON event.candidate_id=entry.id AND event.event_type IN ('info_1_sent','info_2_sent') "
                "JOIN line_delivery_tasks delivery ON delivery.id=CAST(JSON_UNQUOTE(JSON_EXTRACT(event.payload,'$.line_task_id')) AS UNSIGNED) "
                "WHERE " + CANDIDATE_CONTACT_OPEN_SQL + " AND delivery.processing_status='sent' "
                "AND delivery.sent_at_utc<=%s AND NOT EXISTS (SELECT 1 FROM caregiver_candidate_contact_events newer "
                "WHERE newer.candidate_id=entry.id AND newer.id>event.id AND (newer.event_type IN ('info_1_sent','info_2_sent') "
                "OR (newer.event_type='willingness_changed' AND (JSON_UNQUOTE(JSON_EXTRACT(newer.payload,'$.willingness')) IN ('willing','unwilling') "
                "OR JSON_UNQUOTE(JSON_EXTRACT(newer.payload,'$.response_kind'))='coordination_requested')))) "
                "ORDER BY pool.id,entry.id", (now - timedelta(hours=24),)
            )
            groups = {}
            for row in cursor.fetchall() or ():
                item = groups.setdefault(int(row['pool_id']), {'case_no': row['case_no'], 'candidates': set(), 'due': []})
                item['candidates'].add(int(row['candidate_id']))
                item['due'].append(_aware_utc(row['sent_at_utc']) + timedelta(hours=24))
        items = tuple(CandidateManualFollowup(pool_id, str(item['case_no']), len(item['candidates']),
                      len(item['candidates']), min(item['due'])) for pool_id, item in groups.items())
        start = (page - 1) * limit
        return CandidateManualFollowupPage(items[start:start + limit], len(items))
    finally:
        connection.close()


def query_manual_followup_operation(
    connection_factory: Callable[[], Any],
    pool_id: int,
    case_no: str,
    customer_answer_event_id: int,
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
                "SELECT pool.id,pool.case_no,orders.status AS order_status,orders.lifecycle_version AS order_version "
                "FROM caregiver_candidate_contact_pools pool "
                "JOIN orders ON orders.case_no=pool.case_no "
                "WHERE pool.id=%s AND pool.case_no=%s",
                (pool_id, canonical_case_no),
            )
            pool = cursor.fetchone()
            if not isinstance(pool, Mapping):
                raise ValueError("candidate_contact_manual_followup_not_found")
            if not candidate_contact_open(cursor, canonical_case_no, pool.get("order_status")):
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
            answers = [item for item in events if _payload(item).get("response_kind") == "adjustment_customer_answer"]
            answer = next((item for item in answers if int(item["id"]) == customer_answer_event_id), None)
            if answer is None:
                raise ValueError("candidate_contact_customer_answer_not_found")
            answer_payload = _payload(answer)
            batch_id = int(answer_payload["source_coordination_event_id"])
            batch = next((item for item in events if int(item["id"]) == batch_id), None)
            if not isinstance(batch, Mapping):
                raise ValueError("candidate_contact_adjustment_batch_missing")
            batch_payload = _payload(batch)
            if batch_payload.get("response_kind") != "adjustment_question_sent":
                raise ValueError("candidate_contact_adjustment_question_not_found")
            question_id = int(batch_payload["source_response_event_id"])
            questions = [item for item in events if _payload(item).get("response_kind") == "adjustment_question_sent"
                         and int(_payload(item).get("source_response_event_id") or 0) == question_id]
            if not questions or max(int(item["id"]) for item in questions) != batch_id:
                raise ValueError("candidate_contact_adjustment_round_stale")
            sources = tuple(item for item in events if int(item["id"]) == question_id)
            if not sources:
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
            approval = next((item for item in reversed(events)
                if _payload(item).get("response_kind") == "adjustment_approved"
                and int(_payload(item).get("customer_answer_event_id") or 0) == customer_answer_event_id), None)
            receipt_at = _aware_utc(approval["occurred_at"]) if approval else None
            approval_current = approval is not None and int(_payload(approval)["order_version"]) == int(pool["order_version"])
            recontacted_ids = {int(item["candidate_id"]) for item in events
                if approval is not None and str(item.get("event_key") or "").startswith(
                    f"mobile-matching-followup:{pool_id}:{customer_answer_event_id}:")
                and item.get("event_type") in {"info_1_sent", "info_2_sent"}}
            candidates = tuple(
                CandidateManualFollowupCandidate(
                    candidate_id=candidate_id,
                    staff_name=candidates_by_id[candidate_id],
                    recontact_queued=candidate_id in recontacted_ids,
                )
                for candidate_id in sorted(candidates_by_id)
            )
            return CandidateManualFollowupOperation(
                pool_id=pool_id,
                case_no=canonical_case_no,
                customer_answer_event_id=int(answer["id"]),
                customer_answered_at=_aware_utc(answer.get("occurred_at")),
                issues=issues,
                candidates=candidates,
                terms_change_completed=approval_current,
                terms_change_receipt_at=receipt_at,
                recontact_allowed=approval_current,
                question_id=question_id,
                customer_new_conditions=str(answer_payload["answer"]),
            )
    finally:
        connection.close()


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

        )
        for (category, detail), candidate_ids in sorted(grouped.items())
    )


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    payload = row.get("payload")
    value = json.loads(payload) if isinstance(payload, str) else payload
    return value if isinstance(value, Mapping) else {}


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("candidate_contact_delivery_time_invalid")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

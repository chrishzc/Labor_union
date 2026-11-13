"""Read-only candidate reminders and cancellation of retired coordination delivery."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from infrastructure.mysql.replacement_matching_query import CANDIDATE_CONTACT_OPEN_SQL
from subsystems.line.delivery_contracts import CANDIDATE_RECONTACT_SOURCE_PREFIX, RETIRED_CANDIDATE_COORDINATION_SOURCES


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


class CandidateContactCoordinationWorker:
    """Cancel outstanding work from retired candidate coordination flows."""
    run_before_delivery = True

    def __init__(self, connection_factory, now, *, batch_size=25):
        self._connection_factory = connection_factory

    def run_once(self) -> int:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                retired_sources = (*RETIRED_CANDIDATE_COORDINATION_SOURCES, "matching_plan_decision")
                placeholders = ",".join(["%s"] * len(retired_sources))
                cursor.execute(
                    "UPDATE line_delivery_tasks SET processing_status='cancelled',"
                    "error_code='candidate_coordination_retired',"
                    "error_message='candidate coordination delivery retired',"
                    "lease_owner=NULL,lease_acquired_at_utc=NULL,lease_expires_at_utc=NULL "
                    "WHERE processing_status IN ('pending','retryable_failed') AND "
                    f"(source_aggregate_type IN ({placeholders}) "
                    "OR (source_aggregate_type='candidate_matching_willingness_card' AND source_aggregate_identity LIKE %s))",
                    (*retired_sources, CANDIDATE_RECONTACT_SOURCE_PREFIX + "%"),
                )
                count = cursor.rowcount
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


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("candidate_contact_delivery_time_invalid")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

"""MySQL adapter for LINE replies to candidate contact-pool information cards."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from domains.line.identities import LineUserId
from shared_kernel.identities import IdempotencyKey


class MySqlCandidateContactPoolLineReplyRepository:
    def __init__(
        self,
        connection: Any,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._connection = connection
        self._now = now

    def record_willingness(
        self,
        interaction_reference: str,
        willingness: str,
        line_user_id: LineUserId,
        event_key: IdempotencyKey,
    ) -> int:
        if willingness not in {"willing", "unwilling"}:
            raise ValueError("candidate willingness is invalid")
        reference = interaction_reference.strip()
        if not reference:
            raise ValueError("candidate interaction reference is required")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_event.id AS source_event_id, source_event.pool_id, "
                "source_event.candidate_id, entry.status AS candidate_status, "
                "staff.line_user_id, orders.status AS order_status, "
                "COALESCE((SELECT MAX(answer_delivery.sent_at_utc) FROM line_delivery_tasks answer_delivery "
                "WHERE answer_delivery.source_aggregate_type='candidate_contact_answer' "
                "AND CAST(answer_delivery.source_aggregate_identity AS UNSIGNED)=entry.id "
                "AND answer_delivery.processing_status='sent'), delivery.sent_at_utc) AS sent_at_utc "
                "FROM caregiver_candidate_contact_events source_event "
                "JOIN caregiver_candidate_contact_pools pool ON pool.id=source_event.pool_id "
                "JOIN caregiver_candidate_contact_entries entry "
                "ON entry.id=source_event.candidate_id AND entry.pool_id=source_event.pool_id "
                "AND entry.active_marker=1 "
                "JOIN staff ON staff.id=entry.staff_id "
                "JOIN orders ON orders.case_no=pool.case_no "
                "JOIN line_delivery_tasks delivery "
                "ON delivery.id=CAST(JSON_UNQUOTE(JSON_EXTRACT(source_event.payload,'$.line_task_id')) AS UNSIGNED) "
                "WHERE UNHEX(SHA2(source_event.event_key,256))=UNHEX(%s) "
                "AND source_event.event_type IN ('info_1_sent','info_2_sent') FOR UPDATE",
                (reference,),
            )
            binding = cursor.fetchone()
            if not isinstance(binding, Mapping):
                raise LookupError("candidate contact interaction not found")
            if str(binding.get("line_user_id") or "") != line_user_id.value:
                raise LookupError("candidate contact recipient mismatch")
            if binding.get("candidate_status") != "active" or binding.get("order_status") != "洽談中":
                raise ValueError("candidate contact interaction is no longer active")

            cursor.execute(
                "SELECT id,candidate_id,event_type,payload "
                "FROM caregiver_candidate_contact_events WHERE event_key=%s FOR UPDATE",
                (event_key.value,),
            )
            existing = cursor.fetchone()
            payload = {
                "willingness": willingness,
                "reason": (
                    "LINE 按鈕回覆願意承接"
                    if willingness == "willing"
                    else "LINE 按鈕回覆目前無法承接"
                ),
                "source_information_event_id": int(binding["source_event_id"]),
            }
            if isinstance(existing, Mapping):
                existing_payload = existing.get("payload")
                if isinstance(existing_payload, str):
                    existing_payload = json.loads(existing_payload)
                if (
                    existing.get("candidate_id") == binding.get("candidate_id")
                    and existing.get("event_type") == "willingness_changed"
                    and existing_payload == payload
                ):
                    return int(existing["id"])
                raise ValueError("candidate contact reply idempotency conflict")

            sent_at = binding.get("sent_at_utc")
            if not isinstance(sent_at, datetime):
                raise ValueError("candidate contact information was not delivered")
            sent_at = (
                sent_at.replace(tzinfo=timezone.utc)
                if sent_at.tzinfo is None
                else sent_at.astimezone(timezone.utc)
            )
            if self._now() >= sent_at + timedelta(hours=24):
                raise ValueError("candidate contact response expired")
            if _pool_has_willing_candidate(
                cursor,
                int(binding["pool_id"]),
                excluding_candidate_id=int(binding["candidate_id"]),
            ):
                raise ValueError("candidate contact pool is already resolved")

            cursor.execute(
                "INSERT INTO caregiver_candidate_contact_events "
                "(pool_id,candidate_id,event_type,event_key,actor,payload) "
                "VALUES (%s,%s,'willingness_changed',%s,%s,%s)",
                (
                    binding["pool_id"],
                    binding["candidate_id"],
                    event_key.value,
                    f"line:{line_user_id.value}",
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )
            event_id = int(cursor.lastrowid)
            if willingness == "willing":
                _cancel_pending_coordination(cursor, int(binding["pool_id"]))
            return event_id


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    value = row.get("payload")
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, Mapping) else {}


def _pool_has_willing_candidate(
    cursor,
    pool_id: int,
    *,
    excluding_candidate_id: int | None = None,
) -> bool:
    cursor.execute(
        "SELECT candidate_id,payload FROM caregiver_candidate_contact_events "
        "WHERE pool_id=%s AND candidate_id IS NOT NULL "
        "AND event_type='willingness_changed' ORDER BY id",
        (pool_id,),
    )
    latest: dict[int, Mapping[str, object]] = {}
    for row in cursor.fetchall() or ():
        if not isinstance(row, Mapping):
            continue
        candidate_id = int(row.get("candidate_id") or 0)
        payload = _payload(row)
        if candidate_id and (
            payload.get("response_kind")
            in {"coordination_requested", "no_interest", "timed_out"}
            or payload.get("willingness") in {"pending", "willing", "unwilling"}
        ):
            latest[candidate_id] = payload
    return any(
        candidate_id != excluding_candidate_id
        and payload.get("willingness") == "willing"
        for candidate_id, payload in latest.items()
    )


def _cancel_pending_coordination(cursor, pool_id: int) -> None:
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

__all__ = ["MySqlCandidateContactPoolLineReplyRepository"]

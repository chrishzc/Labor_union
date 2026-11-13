"""MySQL adapter for LINE replies to candidate contact-pool information cards."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from infrastructure.mysql.replacement_matching_query import candidate_contact_open
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
                "source_event.candidate_id, pool.case_no, entry.status AS candidate_status, "
                "EXISTS(SELECT 1 FROM caregiver_candidate_contact_events refreshed "
                "WHERE refreshed.candidate_id=entry.id AND refreshed.id>source_event.id "
                "AND refreshed.event_type='willingness_changed' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(refreshed.payload,'$.response_kind'))='candidate_period_refreshed') AS period_stale, "
                "staff_binding.line_user_id, orders.status AS order_status, "
                "delivery.sent_at_utc "
                "FROM caregiver_candidate_contact_events source_event "
                "JOIN caregiver_candidate_contact_pools pool ON pool.id=source_event.pool_id "
                "JOIN caregiver_candidate_contact_entries entry "
                "ON entry.id=source_event.candidate_id AND entry.pool_id=source_event.pool_id "
                "AND entry.active_marker=1 "
                "JOIN staff ON staff.id=entry.staff_id "
                "JOIN line_identity_role_bindings staff_binding "
                "ON staff_binding.subject_type='staff' "
                "AND staff_binding.subject_reference=CAST(staff.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
                "AND staff_binding.binding_status='bound' "
                "AND staff_binding.line_user_id=staff.line_user_id "
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
            if binding.get("candidate_status") != "active" or not candidate_contact_open(cursor, str(binding["case_no"]), binding.get("order_status")):
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

            if binding.get("period_stale"):
                raise ValueError("candidate contact period has changed")
            if not isinstance(binding.get("sent_at_utc"), datetime):
                raise ValueError("candidate contact information was not delivered")
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
            return int(cursor.lastrowid)

__all__ = ["MySqlCandidateContactPoolLineReplyRepository"]

"""
File: matching_notification_repository.py
Description: 持久化媒合通知、互動與回覆，拒絕退休人員的新派送與回覆。
"""

from __future__ import annotations

import json
from hashlib import sha256
from datetime import datetime
from typing import Any, Mapping

from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId, LineUserId
from domains.scheduling.matching_communication import (
    CaregiverWillingness,
    CustomerMatchingDecision,
    MatchingCommunicationConflictError,
    MatchingNotificationKind,
    MatchingPlanReference,
    MatchingResponseSource,
)
from infrastructure.mysql.line_repository_support import database_utc
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.scheduling.matching_notification_contracts import (
    ManualCustomerProfilesEvidence,
    ManualCustomerProfilesReceipt,
    ManualMatchingConfirmationMethod,
    MatchingContactState,
    MatchingNotificationProjectionStatus,
    MatchingNotificationResult,
    MatchingResponseResult,
    MatchingSegmentContact,
)


class MySqlMatchingNotificationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get_contact_state(
        self,
        case_no: str,
        plan_id: int,
        *,
        lock: bool = False,
    ) -> MatchingContactState | None:
        with self._connection.cursor() as cursor:
            plan = self._plan_row(cursor, case_no, plan_id, lock)
            if plan is None:
                return None
            segments = self._segment_rows(cursor, plan_id)
            responses = self._latest_responses(cursor, plan_id)
            deliveries = self._latest_deliveries(cursor, plan_id)
            manual_profiles = self._manual_profile_events(cursor, plan_id)
        return _contact_state(plan, segments, responses, deliveries, manual_profiles)

    def get_manual_customer_profiles_result(
        self,
        key: IdempotencyKey,
        fingerprint: str,
    ) -> ManualCustomerProfilesReceipt | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_MANUAL_PROFILE_BY_KEY_SQL, (key.value,))
            rows = tuple(dict(row) for row in (cursor.fetchall() or ()))
            if not rows:
                return None
            plan_id = int(rows[0]["plan_id"])
            segments = self._segment_rows(cursor, plan_id)
        evidence = _manual_profile_evidence(rows, segments, required=True)
        if evidence.preview_fingerprint.value != fingerprint:
            raise MatchingCommunicationConflictError(
                "manual customer profiles idempotency key has a different payload"
            )
        plan = MatchingPlanReference(
            str(rows[0]["case_no"]),
            plan_id,
            int(rows[0]["communication_version"]),
        )
        return ManualCustomerProfilesReceipt(plan, evidence, replayed=True)

    def append_manual_customer_profiles(
        self,
        *,
        plan: MatchingPlanReference,
        segment_ids: tuple[int, ...],
        confirmation_method: ManualMatchingConfirmationMethod,
        reason: str,
        actor_id: str,
        idempotency_key: IdempotencyKey,
        fingerprint: str,
    ) -> ManualCustomerProfilesEvidence:
        payload = {
            "delivery_status": "manually_confirmed",
            "confirmation_method": confirmation_method.value,
            "reason": reason,
            "actor_id": actor_id,
            "idempotency_key": idempotency_key.value,
            "preview_fingerprint": fingerprint,
        }
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        event_ids: list[int] = []
        with self._connection.cursor() as cursor:
            for segment_id in segment_ids:
                event_key = "manual-profile:" + sha256(
                    f"{idempotency_key.value}:{segment_id}".encode("utf-8")
                ).hexdigest()
                cursor.execute(
                    _INSERT_MANUAL_PROFILE_SQL,
                    (plan.plan_id, segment_id, event_key, actor_id, payload_json),
                )
                event_ids.append(int(cursor.lastrowid))
        return ManualCustomerProfilesEvidence(
            tuple(event_ids),
            confirmation_method,
            reason,
            actor_id,
            idempotency_key,
            PreviewFingerprint(fingerprint),
        )

    def get_intent_result(
        self,
        key: IdempotencyKey,
        fingerprint: str,
    ) -> MatchingNotificationResult | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_INTENT_BY_KEY_SQL, (key.value,))
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            return None
        if str(row["payload_fingerprint"]) != fingerprint:
            raise MatchingCommunicationConflictError(
                "matching notification idempotency key has a different payload"
            )
        return _notification_result(row)

    def append_notification_intent(
        self,
        *,
        plan: MatchingPlanReference,
        segment_id: int | None,
        kind: MatchingNotificationKind,
        recipient: LineUserId,
        payload_snapshot: Mapping[str, object],
        idempotency_key: IdempotencyKey,
        fingerprint: str,
        actor_id: str,
    ) -> int:
        payload_json = json.dumps(payload_snapshot, ensure_ascii=False, sort_keys=True)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _INSERT_INTENT_SQL,
                (
                    plan.plan_id,
                    segment_id,
                    kind.value,
                    recipient.value,
                    payload_json,
                    idempotency_key.value,
                    fingerprint,
                    actor_id,
                ),
            )
            return int(cursor.lastrowid)

    def project_intent(
        self,
        intent_id: int,
        delivery_task_id: LineDeliveryTaskId,
        projected_at: datetime,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PROJECT_INTENT_SQL,
                (delivery_task_id.value, database_utc(projected_at), intent_id),
            )
            if cursor.rowcount != 1:
                raise MatchingCommunicationConflictError("matching intent was already projected")

    def open_interaction(
        self,
        *,
        token_hash: str,
        plan_id: int,
        segment_id: int | None,
        action_scope: str,
        recipient: LineUserId,
        expires_at: datetime,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _INSERT_INTERACTION_SQL,
                (
                    token_hash,
                    plan_id,
                    segment_id,
                    action_scope,
                    recipient.value,
                    database_utc(expires_at),
                ),
            )

    def interaction(self, token_hash: str) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_INTERACTION_BY_TOKEN_SQL, (token_hash,))
            row = cursor.fetchone()
        return dict(row) if isinstance(row, Mapping) else None

    def append_response(
        self,
        *,
        plan: MatchingPlanReference,
        segment_id: int | None,
        response_type: str,
        response_value: str,
        source: MatchingResponseSource,
        actor_id: str,
        line_user_id: LineUserId | None,
        reason: str | None,
        idempotency_key: IdempotencyKey,
        fingerprint: str,
        occurred_at: datetime,
        token_hash: str | None = None,
    ) -> MatchingResponseResult:
        existing = self._existing_response(idempotency_key, fingerprint)
        if existing is not None:
            return existing
        self._advance_version(plan)
        event_id = self._insert_response(
            plan,
            segment_id,
            response_type,
            response_value,
            source,
            actor_id,
            line_user_id,
            reason,
            idempotency_key,
            fingerprint,
            occurred_at,
        )
        if token_hash is not None:
            self._consume_interaction(token_hash, line_user_id, occurred_at)
        return MatchingResponseResult(
            event_id,
            MatchingPlanReference(plan.case_no, plan.plan_id, plan.version + 1),
            source,
            caregiver_willingness=(
                CaregiverWillingness(response_value)
                if response_type == "caregiver_willingness" else None
            ),
            customer_decision=(
                CustomerMatchingDecision(response_value)
                if response_type == "customer_decision" else None
            ),
        )

    def caregiver_card_facts(self, plan_id: int, segment_id: int) -> dict[str, object]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CAREGIVER_CARD_FACTS_SQL, (plan_id, segment_id))
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise LookupError("matching segment not found")
        return dict(row)

    def customer_profile_facts(self, plan_id: int) -> tuple[dict[str, object], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CUSTOMER_PROFILE_FACTS_SQL, (plan_id,))
            rows = cursor.fetchall() or ()
        return tuple(_profile_row(row) for row in rows)

    def _plan_row(self, cursor, case_no, plan_id, lock):
        suffix = " FOR UPDATE" if lock else ""
        cursor.execute(_PLAN_SQL + suffix, (plan_id, case_no))
        row = cursor.fetchone()
        return dict(row) if isinstance(row, Mapping) else None

    def _segment_rows(self, cursor, plan_id):
        cursor.execute(_SEGMENTS_SQL, (plan_id,))
        return tuple(dict(row) for row in (cursor.fetchall() or ()))

    def _latest_responses(self, cursor, plan_id):
        cursor.execute(_RESPONSES_SQL, (plan_id,))
        return tuple(dict(row) for row in (cursor.fetchall() or ()))

    def _latest_deliveries(self, cursor, plan_id):
        cursor.execute(_DELIVERIES_SQL, (plan_id,))
        return tuple(dict(row) for row in (cursor.fetchall() or ()))

    def _manual_profile_events(self, cursor, plan_id):
        cursor.execute(_MANUAL_PROFILE_EVENTS_SQL, (plan_id,))
        return tuple(dict(row) for row in (cursor.fetchall() or ()))

    def _existing_response(self, key, fingerprint):
        with self._connection.cursor() as cursor:
            cursor.execute(_RESPONSE_BY_KEY_SQL, (key.value,))
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            return None
        if str(row["payload_fingerprint"]) != fingerprint:
            raise MatchingCommunicationConflictError(
                "matching response idempotency key has a different payload"
            )
        return _response_result(row)

    def _advance_version(self, plan):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _ADVANCE_VERSION_SQL,
                (plan.plan_id, plan.case_no, plan.version),
            )
            if cursor.rowcount != 1:
                raise MatchingCommunicationConflictError("matching plan version is stale")

    # Response insertion is kept cohesive so the immutable fact matches one version advance.
    def _insert_response(self, plan, segment_id, response_type, response_value, source,
                         actor_id, line_user_id, reason, key, fingerprint, occurred_at):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _INSERT_RESPONSE_SQL,
                (
                    plan.plan_id, segment_id, response_type, response_value,
                    source.value, actor_id,
                    line_user_id.value if line_user_id else None,
                    reason, key.value, fingerprint, database_utc(occurred_at),
                ),
            )
            return int(cursor.lastrowid)

    def _consume_interaction(self, token_hash, line_user_id, occurred_at):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CONSUME_INTERACTION_SQL,
                (
                    database_utc(occurred_at),
                    line_user_id.value if line_user_id else None,
                    token_hash,
                ),
            )
            if cursor.rowcount != 1:
                raise MatchingCommunicationConflictError("matching interaction is not active")


def _contact_state(plan, segments, responses, deliveries, manual_profiles=()):
    response_map = _response_map(responses)
    delivery_map = _delivery_map(deliveries)
    contact_segments = tuple(
        _segment_contact(row, response_map, delivery_map) for row in segments
    )
    reference = MatchingPlanReference(
        str(plan["case_no"]), int(plan["id"]), int(plan["communication_version"])
    )
    return MatchingContactState(
        reference,
        str(plan["status"]),
        bool(plan["is_active"]),
        str(plan["order_status"]),
        LineUserId(str(plan["client_line_user_id"])) if plan.get("client_line_user_id") else None,
        CustomerMatchingDecision(response_map.get((None, "customer_decision"), "pending")),
        delivery_map.get((None, "customer_profiles")),
        contact_segments,
        _manual_profile_evidence(manual_profiles, segments),
    )


def _manual_profile_evidence(rows, segments, *, required=False):
    if not rows:
        if required:
            raise MatchingCommunicationConflictError(
                "manual customer profiles receipt is incomplete"
            )
        return None
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        key = str(row.get("idempotency_key") or "")
        if key:
            groups.setdefault(key, []).append(row)
    expected_segments = {int(segment["segment_id"]) for segment in segments}
    for key, group in groups.items():
        actual_segments = {int(row["segment_id"]) for row in group}
        if actual_segments != expected_segments:
            continue
        first = group[0]
        fingerprint = str(first["preview_fingerprint"])
        method = str(first["confirmation_method"])
        reason = str(first["reason"])
        actor_id = str(first["actor_id"])
        if any(
            str(row["preview_fingerprint"]) != fingerprint
            or str(row["confirmation_method"]) != method
            or str(row["reason"]) != reason
            or str(row["actor_id"]) != actor_id
            for row in group
        ):
            raise MatchingCommunicationConflictError(
                "manual customer profiles evidence is inconsistent"
            )
        return ManualCustomerProfilesEvidence(
            tuple(sorted(int(row["id"]) for row in group)),
            ManualMatchingConfirmationMethod(method),
            reason,
            actor_id,
            IdempotencyKey(key),
            PreviewFingerprint(fingerprint),
        )
    if required:
        raise MatchingCommunicationConflictError(
            "manual customer profiles receipt is incomplete"
        )
    return None


def _segment_contact(row, responses, deliveries):
    segment_id = int(row["segment_id"])
    return MatchingSegmentContact(
        segment_id,
        int(row["segment_order"]),
        int(row["staff_id"]),
        str(row["staff_name"]),
        LineUserId(str(row["staff_line_user_id"])) if row.get("staff_line_user_id") else None,
        str(row["assigned_start_date"]),
        str(row["assigned_end_date"]),
        CaregiverWillingness(responses.get((segment_id, "caregiver_willingness"), "pending")),
        deliveries.get((segment_id, "caregiver_info_1")),
        deliveries.get((segment_id, "caregiver_info_2")),
    )


def _response_map(rows):
    values = {}
    for row in rows:
        key = (row.get("segment_id"), str(row["response_type"]))
        values.setdefault(key, str(row["response_value"]))
    return values


def _delivery_map(rows):
    values = {}
    for row in rows:
        key = (row.get("segment_id"), str(row["notification_kind"]))
        values.setdefault(key, LineDeliveryStatus(str(row["processing_status"])))
    return values


def _notification_result(row):
    task_id = row.get("delivery_task_id")
    return MatchingNotificationResult(
        int(row["id"]),
        MatchingPlanReference(str(row["case_no"]), int(row["plan_id"]), int(row["communication_version"])),
        MatchingNotificationKind(str(row["notification_kind"])),
        MatchingNotificationProjectionStatus(str(row["projection_status"])),
        LineDeliveryTaskId(int(task_id)) if task_id is not None else None,
    )


def _response_result(row):
    response_type = str(row["response_type"])
    response_value = str(row["response_value"])
    return MatchingResponseResult(
        int(row["id"]),
        MatchingPlanReference(str(row["case_no"]), int(row["plan_id"]), int(row["communication_version"])),
        MatchingResponseSource(str(row["response_source"])),
        CaregiverWillingness(response_value) if response_type == "caregiver_willingness" else None,
        CustomerMatchingDecision(response_value) if response_type == "customer_decision" else None,
    )


def _profile_row(row):
    value = dict(row)
    for field in ("service_regions", "special_skills"):
        raw = value.get(field)
        if isinstance(raw, str):
            value[field] = json.loads(raw)
    return value


_PLAN_SQL = """SELECT p.id,p.case_no,p.communication_version,p.status,p.is_active,
o.status AS order_status,c.line_user_id AS client_line_user_id
FROM caregiver_matching_plans p JOIN orders o ON o.case_no=p.case_no
JOIN clients c ON c.id=o.client_id WHERE p.id=%s AND p.case_no=%s"""
_SEGMENTS_SQL = """SELECT s.id AS segment_id,s.segment_order,s.staff_id,
s.assigned_start_date,s.assigned_end_date,st.name AS staff_name,
st.line_user_id AS staff_line_user_id FROM caregiver_matching_plan_segments s
JOIN staff st ON st.id=s.staff_id LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=st.id
WHERE s.plan_id=%s AND st.status='active' AND COALESCE(lifecycle.lifecycle_state,'active')='active' ORDER BY s.segment_order"""
_RESPONSES_SQL = """SELECT segment_id,response_type,response_value FROM
matching_response_events WHERE plan_id=%s ORDER BY occurred_at_utc DESC,id DESC"""
_DELIVERIES_SQL = """SELECT i.segment_id,i.notification_kind,t.processing_status
FROM matching_notification_intents i JOIN line_delivery_tasks t ON t.id=i.delivery_task_id
WHERE i.plan_id=%s ORDER BY i.created_at_utc DESC,i.id DESC"""
_MANUAL_PROFILE_EVENTS_SQL = """SELECT e.id,e.plan_id,e.segment_id,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.confirmation_method')) AS confirmation_method,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.reason')) AS reason,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.actor_id')) AS actor_id,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.idempotency_key')) AS idempotency_key,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.preview_fingerprint')) AS preview_fingerprint
FROM caregiver_matching_plan_events e WHERE e.plan_id=%s
AND e.event_type='resume_sent'
AND JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.delivery_status'))='manually_confirmed'
ORDER BY e.occurred_at DESC,e.id DESC"""
_MANUAL_PROFILE_BY_KEY_SQL = """SELECT e.id,e.plan_id,e.segment_id,
p.case_no,p.communication_version,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.confirmation_method')) AS confirmation_method,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.reason')) AS reason,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.actor_id')) AS actor_id,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.idempotency_key')) AS idempotency_key,
JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.preview_fingerprint')) AS preview_fingerprint
FROM caregiver_matching_plan_events e JOIN caregiver_matching_plans p ON p.id=e.plan_id
WHERE e.event_type='resume_sent'
AND JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.delivery_status'))='manually_confirmed'
AND JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.idempotency_key'))=%s
ORDER BY e.id"""
_INSERT_MANUAL_PROFILE_SQL = """INSERT INTO caregiver_matching_plan_events
(plan_id,segment_id,event_type,event_key,actor,payload)
VALUES (%s,%s,'resume_sent',%s,%s,%s)"""
_INTENT_BY_KEY_SQL = """SELECT i.*,p.case_no,p.communication_version
FROM matching_notification_intents i JOIN caregiver_matching_plans p ON p.id=i.plan_id
WHERE i.idempotency_key=%s"""
_INSERT_INTENT_SQL = """INSERT INTO matching_notification_intents
(plan_id,segment_id,notification_kind,recipient_line_user_id,payload_snapshot,
idempotency_key,payload_fingerprint,created_by_actor_id)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
_PROJECT_INTENT_SQL = """UPDATE matching_notification_intents SET
projection_status='projected',delivery_task_id=%s,projected_at_utc=%s
WHERE id=%s AND projection_status='pending'"""
_INSERT_INTERACTION_SQL = """INSERT INTO matching_line_interactions
(token_hash,plan_id,segment_id,action_scope,recipient_line_user_id,expires_at_utc)
VALUES (%s,%s,%s,%s,%s,%s)"""
_INTERACTION_BY_TOKEN_SQL = """SELECT i.*,p.case_no,p.communication_version,p.status,
p.is_active FROM matching_line_interactions i JOIN caregiver_matching_plans p ON p.id=i.plan_id
LEFT JOIN caregiver_matching_plan_segments s ON s.id=i.segment_id LEFT JOIN staff st ON st.id=s.staff_id
LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=st.id WHERE i.token_hash=%s
AND (i.segment_id IS NULL OR (st.status='active' AND COALESCE(lifecycle.lifecycle_state,'active')='active')) FOR UPDATE"""
_RESPONSE_BY_KEY_SQL = """SELECT e.*,p.case_no,p.communication_version
FROM matching_response_events e JOIN caregiver_matching_plans p ON p.id=e.plan_id
WHERE e.idempotency_key=%s"""
_ADVANCE_VERSION_SQL = """UPDATE caregiver_matching_plans SET
communication_version=communication_version+1 WHERE id=%s AND case_no=%s
AND communication_version=%s AND is_active=1"""
_INSERT_RESPONSE_SQL = """INSERT INTO matching_response_events
(plan_id,segment_id,response_type,response_value,response_source,actor_id,line_user_id,
reason,idempotency_key,payload_fingerprint,occurred_at_utc)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
_CONSUME_INTERACTION_SQL = """UPDATE matching_line_interactions SET
interaction_status='consumed',consumed_at_utc=%s,consumed_by_line_user_id=%s
WHERE token_hash=%s AND interaction_status='active'"""
_CAREGIVER_CARD_FACTS_SQL = """SELECT p.case_no,s.assigned_start_date AS start_date,
s.assigned_end_date AS end_date,c.city,c.service_type,c.service_time,c.baby_info,
c.residence_type FROM caregiver_matching_plans p
JOIN caregiver_matching_plan_segments s ON s.plan_id=p.id
JOIN orders o ON o.case_no=p.case_no JOIN clients c ON c.id=o.client_id
WHERE p.id=%s AND s.id=%s"""
_CUSTOMER_PROFILE_FACTS_SQL = """SELECT st.id,st.name,st.city,st.has_massage_cert,
st.care_babies,st.service_regions,st.special_skills
FROM caregiver_matching_plan_segments s JOIN staff st ON st.id=s.staff_id
WHERE s.plan_id=%s ORDER BY s.segment_order"""


__all__ = ["MySqlMatchingNotificationRepository"]

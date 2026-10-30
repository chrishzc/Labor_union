"""Verified candidate replies and staff-authored information coordination."""

from __future__ import annotations

from infrastructure.mysql.line_message_copy import configured_message_payload

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from infrastructure.mysql.replacement_matching_query import CANDIDATE_CONTACT_OPEN_SQL, candidate_contact_open
from domains.line.identities import LineUserId
from domains.scheduling.candidate_contact_response import (
    CandidateCoordinationResponse,
    CandidateIssueMode,
    category_label,
)
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from shared_kernel.identities import CorrelationId, IdempotencyKey


_STAFF_QUESTION_SQL = (
    "SELECT source_event.id AS source_event_id,source_event.pool_id,source_event.candidate_id,"
    "source_event.event_key,source_event.payload,pool.case_no,staff.name AS staff_name,orders.status AS order_status,"
    "staff_binding.line_user_id AS staff_line_user_id,customer_binding.line_user_id AS customer_line_user_id "
    "FROM caregiver_candidate_contact_events source_event "
    "JOIN caregiver_candidate_contact_pools pool ON pool.id=source_event.pool_id "
    "JOIN caregiver_candidate_contact_entries entry ON entry.id=source_event.candidate_id "
    "AND entry.active_marker=1 AND entry.status='active' "
    "JOIN staff ON staff.id=entry.staff_id JOIN orders ON orders.case_no=pool.case_no "
    "LEFT JOIN line_identity_role_bindings staff_binding ON staff_binding.subject_type='staff' "
    "AND staff_binding.subject_reference=CAST(staff.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
    "AND staff_binding.binding_status='bound' AND staff_binding.line_user_id=staff.line_user_id "
    "LEFT JOIN line_identity_role_bindings customer_binding ON customer_binding.subject_type='customer' "
    "AND customer_binding.subject_reference=CAST(orders.client_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
    "AND customer_binding.binding_status='bound' "
    "WHERE source_event.event_type='willingness_changed' "
    "AND JSON_UNQUOTE(JSON_EXTRACT(source_event.payload,'$.response_kind'))='coordination_requested' "
    "AND JSON_LENGTH(JSON_EXTRACT(source_event.payload,'$.issues'))>0"
)


class CandidateContactResponseError(ValueError):
    pass


class CandidateContactResponseApplication:
    def __init__(
        self,
        connection_factory: Callable[[], Any],
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._connection_factory = connection_factory
        self._now = now

    def query(self, reference: str, line_user_id: LineUserId) -> dict[str, object]:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                context = _candidate_context(cursor, reference, line_user_id, lock=False)
                latest = _latest_candidate_response(cursor, int(context["candidate_id"]))
                contact_open = candidate_contact_open(cursor, str(context["case_no"]), context["order_status"])
            is_open = (
                context["candidate_status"] == "active"
                and contact_open
            )
            return {
                "case_no": str(context["case_no"]),
                "candidate_id": int(context["candidate_id"]),
                "staff_name": str(context["staff_name"]),
                "status": "open" if is_open else "closed",
                "deadline_at": None,
                "current_response_kind": None if latest is None else _response_kind(latest),
            }
        finally:
            connection.close()

    def submit(
        self,
        reference: str,
        line_user_id: LineUserId,
        response: CandidateCoordinationResponse,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, object]:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                context = _candidate_context(cursor, reference, line_user_id, lock=True)
                existing = _existing_event(cursor, idempotency_key.value)
                payload = {
                    **response.as_payload(),
                    "source_information_event_id": int(context["source_event_id"]),
                }
                if existing is not None:
                    _require_same_event(existing, int(context["candidate_id"]), payload)
                    connection.rollback()
                    return {
                        "status": "idempotent_replay",
                        "event_id": int(existing["id"]),
                        "response_kind": response.response_kind.value,
                        "customer_message_queued": False,
                        "union_followup_required": bool(response.issues),
                    }
                if context["candidate_status"] != "active" or not candidate_contact_open(cursor, str(context["case_no"]), context["order_status"]):
                    raise CandidateContactResponseError("candidate_contact_closed")
                cursor.execute(
                    "INSERT INTO caregiver_candidate_contact_events "
                    "(pool_id,candidate_id,event_type,event_key,actor,payload) "
                    "VALUES (%s,%s,'willingness_changed',%s,%s,%s)",
                    (
                        context["pool_id"],
                        context["candidate_id"],
                        idempotency_key.value,
                        f"line:{line_user_id.value}",
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
                event_id = int(cursor.lastrowid)
            connection.commit()
            return {
                "status": "recorded",
                "event_id": event_id,
                "response_kind": response.response_kind.value,
                "customer_message_queued": False,
                "union_followup_required": bool(response.issues),
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def query_staff_questions(self, *, page: int = 1, page_size: int = 25,
                             case_no: str | None = None, question_id: int | None = None) -> dict[str, object]:
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 50:
            raise CandidateContactResponseError("candidate_contact_page_invalid")
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                source = (
                    _STAFF_QUESTION_SQL + " AND " + CANDIDATE_CONTACT_OPEN_SQL
                    + " AND NOT EXISTS (SELECT 1 FROM caregiver_candidate_contact_events newer "
                    "WHERE newer.candidate_id=source_event.candidate_id AND newer.id>source_event.id "
                    "AND newer.event_type='willingness_changed' AND ("
                    "JSON_UNQUOTE(JSON_EXTRACT(newer.payload,'$.response_kind')) IN "
                    "('coordination_requested','no_interest','timed_out','information_answered','candidate_period_refreshed') "
                    "OR JSON_UNQUOTE(JSON_EXTRACT(newer.payload,'$.willingness')) IN ('pending','willing','unwilling'))) "
                )
                params = []
                if case_no is not None:
                    source += " AND pool.case_no=%s"
                    params.append(case_no)
                if question_id is not None:
                    source += " AND source_event.id=%s"
                    params.append(question_id)
                cursor.execute("SELECT COUNT(*) AS total FROM (" + source + ") questions", tuple(params))
                total = int(cursor.fetchone()["total"])
                cursor.execute(
                    source + " ORDER BY source_event.id LIMIT %s OFFSET %s",
                    (*params, page_size, (page - 1) * page_size),
                )
                contexts = tuple(cursor.fetchall() or ())
                items = []
                for context in contexts:
                    question_id = int(context["source_event_id"])
                    customer_message = _manual_information_message(cursor, question_id, "customer")
                    is_adjustment = _has_adjustment(context)
                    answer_source_id = int(customer_message["id"]) if is_adjustment and customer_message else question_id
                    customer_answer = _customer_answer(cursor, answer_source_id)
                    approval = _adjustment_approval(cursor, int(customer_answer["id"])) if customer_answer and is_adjustment else None
                    items.append({
                        "question_id": question_id,
                        "pool_id": int(context["pool_id"]),
                        "request_kind": "condition_adjustment" if is_adjustment else "information_question",
                        "customer_answer_event_id": int(customer_answer["id"]) if customer_answer else None,
                        "review_completed": approval is not None,
                        "case_no": str(context["case_no"]),
                        "staff_name": str(context["staff_name"]),
                        "issues": [{"label": category_label(str(item["category"])), "detail": str(item["detail"])}
                                   for item in (_payload(context).get("issues") or ())],
                        "customer_answer": None if customer_answer is None else str(_payload(customer_answer)["answer"]),
                        "customer_message": None if customer_message is None else str(_payload(customer_message)["message_text"]),
                        "customer_available": bool(context.get("customer_line_user_id")),
                    })
            return {"items": items, "total": total, "page": page, "page_size": page_size}
        finally:
            connection.close()

    def send_staff_information(
        self, question_id: int, recipient: str, message_text: str,
        actor: str, idempotency_key: IdempotencyKey,
    ) -> dict[str, object]:
        text = message_text.strip() if isinstance(message_text, str) else ""
        if recipient not in {"caregiver", "customer"} or not text or len(text) > 1000:
            raise CandidateContactResponseError("candidate_contact_message_invalid")
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_STAFF_QUESTION_SQL + " AND source_event.id=%s FOR UPDATE", (question_id,))
                context = cursor.fetchone()
                if not isinstance(context, Mapping):
                    raise CandidateContactResponseError("candidate_contact_question_not_found")
                is_adjustment = _has_adjustment(context)
                payload = {
                    "response_kind": "information_answered" if recipient == "caregiver" else "adjustment_question_sent" if is_adjustment else "information_question_sent",
                    "source_response_event_id": question_id,
                    "recipient": recipient,
                    "message_text": text,
                    "author": actor,
                }
                existing = _existing_event(cursor, idempotency_key.value)
                if existing is not None:
                    _require_same_event(existing, int(context["candidate_id"]), payload)
                    connection.rollback()
                    return {"status": "idempotent_replay", "event_id": int(existing["id"])}
                latest = _latest_candidate_response(cursor, int(context["candidate_id"]))
                if (latest is None or int(latest["id"]) != question_id
                    or _manual_information_message(cursor, question_id, "caregiver") is not None
                    or not candidate_contact_open(cursor, str(context["case_no"]), context["order_status"])):
                    raise CandidateContactResponseError("candidate_contact_question_closed")
                is_adjustment = _has_adjustment(context)
                if is_adjustment and recipient != "customer":
                    raise CandidateContactResponseError("candidate_contact_adjustment_requires_review")
                if recipient == "customer":
                    previous = _manual_information_message(cursor, question_id, "customer")
                    if previous is not None:
                        answer = _customer_answer(cursor, int(previous["id"]) if is_adjustment else question_id)
                        if not is_adjustment or answer is None:
                            raise CandidateContactResponseError("candidate_contact_question_already_sent")
                        if _adjustment_approval(cursor, int(answer["id"])) is not None:
                            raise CandidateContactResponseError("candidate_contact_adjustment_already_approved")
                if not context.get("staff_line_user_id"):
                    raise CandidateContactResponseError("candidate_contact_recipient_unavailable")
                if recipient == "customer" and not context.get("customer_line_user_id"):
                    raise CandidateContactResponseError("candidate_contact_customer_unavailable")
                cursor.execute(
                    "INSERT INTO caregiver_candidate_contact_events "
                    "(pool_id,candidate_id,event_type,event_key,actor,payload) "
                    "VALUES (%s,%s,'willingness_changed',%s,%s,%s)",
                    (context["pool_id"], context["candidate_id"], idempotency_key.value, actor,
                     json.dumps(payload, ensure_ascii=False, sort_keys=True)),
                )
                event_id = int(cursor.lastrowid)
                if recipient == "caregiver":
                    _enqueue_caregiver_answer(connection, context, text, event_id, self._now())
                else:
                    _enqueue_staff_customer_question(
                        connection, context, text, event_id if is_adjustment else question_id, self._now(),
                        reference_key=idempotency_key.value if is_adjustment else None,
                    )
            connection.commit()
            return {"status": "queued", "event_id": event_id}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def query_customer(self, reference: str, line_user_id: LineUserId) -> dict[str, object]:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                context = _customer_coordination_context(cursor, reference, line_user_id, lock=False)
                is_adjustment = _payload(context).get("response_kind") == "adjustment_question_sent"
                message = context if is_adjustment else _manual_information_message(cursor, int(context["source_event_id"]), "customer")
                answered = _customer_answer(cursor, int(context["source_event_id"]))
                current = _customer_question_is_current(cursor, context)
                contact_open = candidate_contact_open(cursor, str(context["case_no"]), context["order_status"])
            return {
                "case_no": str(context["case_no"]),
                "request_kind": "condition_adjustment" if is_adjustment else "information_question",
                "status": "open" if answered is None and current and contact_open else "closed",
                "message_text": str(_payload(message)["message_text"]),
                "issues": [],
            }
        finally:
            connection.close()

    def submit_customer_answer(self, reference, line_user_id, answer, idempotency_key):
        text = answer.strip() if isinstance(answer, str) else ""
        if not text or len(text) > 1000:
            raise CandidateContactResponseError("candidate_contact_answer_invalid")
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                context = _customer_coordination_context(cursor, reference, line_user_id, lock=True)
                is_adjustment = _payload(context).get("response_kind") == "adjustment_question_sent"
                payload = {
                    "response_kind": "adjustment_customer_answer" if is_adjustment else "information_customer_answered",
                    "answer": text,
                    "source_coordination_event_id": int(context["source_event_id"]),
                    "source_response_event_id": int(_payload(context)["source_response_event_id"]) if is_adjustment else int(context["source_event_id"]),
                }
                existing = _existing_event(cursor, idempotency_key.value)
                if existing is not None:
                    _require_same_event(existing, int(context["candidate_id"]), payload)
                    connection.rollback()
                    return {"status": "idempotent_replay", "event_id": int(existing["id"]),
                            "caregiver_message_queued": False, "union_followup_required": True}
                if not _customer_question_is_current(cursor, context) or not candidate_contact_open(cursor, str(context["case_no"]), context["order_status"]):
                    raise CandidateContactResponseError("candidate_contact_question_closed")
                if _customer_answer(cursor, int(context["source_event_id"])) is not None:
                    raise CandidateContactResponseError("candidate_contact_answer_already_recorded")
                cursor.execute(
                    "INSERT INTO caregiver_candidate_contact_events (pool_id,candidate_id,event_type,event_key,actor,payload) "
                    "VALUES (%s,%s,'willingness_changed',%s,%s,%s)",
                    (context["pool_id"], context["candidate_id"], idempotency_key.value, f"line:{line_user_id.value}",
                     json.dumps(payload, ensure_ascii=False, sort_keys=True)),
                )
                event_id = int(cursor.lastrowid)
            connection.commit()
            return {"status": "recorded", "event_id": event_id, "caregiver_message_queued": False, "union_followup_required": True}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()



def _candidate_context(cursor, reference: str, line_user_id: LineUserId, *, lock: bool):
    if not isinstance(reference, str) or len(reference) != 64:
        raise CandidateContactResponseError("candidate_contact_reference_invalid")
    cursor.execute(
        "SELECT source_event.id AS source_event_id, source_event.pool_id, "
        "source_event.candidate_id, pool.case_no, entry.status AS candidate_status, "
        "staff.name AS staff_name, staff_binding.line_user_id, orders.status AS order_status, "
        "EXISTS(SELECT 1 FROM caregiver_candidate_contact_events refreshed WHERE refreshed.candidate_id=entry.id "
        "AND refreshed.id>source_event.id AND refreshed.event_type='willingness_changed' "
        "AND JSON_UNQUOTE(JSON_EXTRACT(refreshed.payload,'$.response_kind'))='candidate_period_refreshed') AS period_stale, "
        "COALESCE((SELECT MAX(answer_delivery.sent_at_utc) FROM line_delivery_tasks answer_delivery "
        "WHERE answer_delivery.source_aggregate_type='candidate_contact_answer' "
        "AND answer_delivery.source_aggregate_identity="
        "CAST(entry.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
        "AND answer_delivery.processing_status='sent'), delivery.sent_at_utc) AS sent_at_utc "
        "FROM caregiver_candidate_contact_events source_event "
        "JOIN caregiver_candidate_contact_pools pool ON pool.id=source_event.pool_id "
        "JOIN caregiver_candidate_contact_entries entry "
        "ON entry.id=source_event.candidate_id AND entry.pool_id=source_event.pool_id "
        "AND entry.active_marker=1 "
        "JOIN staff ON staff.id=entry.staff_id "
        "JOIN line_identity_role_bindings staff_binding ON staff_binding.subject_type='staff' "
        "AND staff_binding.subject_reference=CAST(staff.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
        "AND staff_binding.binding_status='bound' AND staff_binding.line_user_id=staff.line_user_id "
        "JOIN orders ON orders.case_no=pool.case_no "
        "JOIN line_delivery_tasks delivery "
        "ON delivery.id=CAST(JSON_UNQUOTE(JSON_EXTRACT(source_event.payload,'$.line_task_id')) AS UNSIGNED) "
        "WHERE SHA2(source_event.event_key,256)=%s "
        "AND source_event.event_type IN ('info_1_sent','info_2_sent')"
        + (" FOR UPDATE" if lock else ""),
        (reference,),
    )
    context = cursor.fetchone()
    if not isinstance(context, Mapping):
        raise CandidateContactResponseError("candidate_contact_not_found")
    if str(context.get("line_user_id") or "") != line_user_id.value:
        raise CandidateContactResponseError("candidate_contact_recipient_mismatch")
    if context.get("period_stale"):
        raise CandidateContactResponseError("candidate_contact_period_changed")
    if context.get("sent_at_utc") is None:
        raise CandidateContactResponseError("candidate_contact_information_not_delivered")
    return context


def _latest_candidate_response(cursor, candidate_id: int):
    cursor.execute(
        "SELECT id,payload FROM caregiver_candidate_contact_events "
        "WHERE candidate_id=%s AND event_type='willingness_changed' ORDER BY id DESC",
        (candidate_id,),
    )
    for row in cursor.fetchall() or ():
        if isinstance(row, Mapping) and _is_candidate_response_payload(_payload(row)):
            return row
    return None


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    value = row.get("payload")
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, Mapping) else {}


def _response_kind(row: Mapping[str, object]) -> str | None:
    value = _payload(row).get("response_kind")
    return str(value) if value in {"coordination_requested", "no_interest", "timed_out"} else None


def _willingness(row: Mapping[str, object]) -> str | None:
    value = _payload(row).get("willingness")
    return str(value) if value in {"pending", "willing", "unwilling"} else None


def _is_candidate_response_payload(payload: Mapping[str, object]) -> bool:
    return payload.get("response_kind") in {
        "coordination_requested",
        "no_interest",
        "timed_out",
    } or payload.get("willingness") in {"pending", "willing", "unwilling"}


def _existing_event(cursor, event_key: str):
    cursor.execute(
        "SELECT id,candidate_id,event_type,payload FROM caregiver_candidate_contact_events "
        "WHERE event_key=%s FOR UPDATE",
        (event_key,),
    )
    row = cursor.fetchone()
    return row if isinstance(row, Mapping) else None


def _require_same_event(existing, candidate_id: int, payload: Mapping[str, object]) -> None:
    if (
        int(existing.get("candidate_id") or 0) != candidate_id
        or existing.get("event_type") != "willingness_changed"
        or _payload(existing) != payload
    ):
        raise CandidateContactResponseError("candidate_contact_idempotency_conflict")


def _manual_information_message(cursor, question_id: int, recipient: str):
    kinds = ("information_answered",) if recipient == "caregiver" else ("information_question_sent", "adjustment_question_sent")
    cursor.execute(
        "SELECT id,payload FROM caregiver_candidate_contact_events WHERE event_type='willingness_changed' "
        "AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.response_kind')) IN (" + ",".join(["%s"] * len(kinds)) + ") "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.source_response_event_id')) AS UNSIGNED)=%s "
        "ORDER BY id DESC LIMIT 1", (*kinds, question_id),
    )
    row = cursor.fetchone()
    return row if isinstance(row, Mapping) else None


def _enqueue_staff_customer_question(connection, context, text: str, question_id: int, now: datetime, *, reference_key=None) -> None:
    reference = hashlib.sha256(str(reference_key or context["event_key"]).encode("utf-8")).hexdigest()
    from subsystems.scheduling.matching_line_cards import candidate_customer_question_card
    message = candidate_customer_question_card(
        str(context["case_no"]), text, _liff_url("candidate_contact_customer", reference),
    )
    message = canonical_line_payload_json(configured_message_payload(connection, "card-union-question", json.loads(message), {"case_no": context["case_no"]}))
    MySqlLineDeliveryTaskRepository(connection).enqueue(LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId(str(context["customer_line_user_id"]).strip())),
        LineMessageKind.FLEX, message, now,
        IdempotencyKey(f"candidate-information-customer:{question_id}"),
        CorrelationId(f"candidate-information-customer:{question_id}"),
        "candidate_contact_question", str(question_id),
    ))


def _customer_coordination_context(cursor, reference: str, line_user_id: LineUserId, *, lock: bool):
    if not isinstance(reference, str) or len(reference) != 64:
        raise CandidateContactResponseError("candidate_contact_reference_invalid")
    cursor.execute(
        "SELECT response_event.id AS source_event_id,response_event.pool_id,response_event.candidate_id,"
        "response_event.payload,pool.case_no,entry.status AS candidate_status,staff_binding.line_user_id AS staff_line_user_id,"
        "orders.status AS order_status,binding.line_user_id AS customer_line_user_id "
        "FROM caregiver_candidate_contact_events response_event "
        "JOIN caregiver_candidate_contact_pools pool ON pool.id=response_event.pool_id "
        "JOIN caregiver_candidate_contact_entries entry ON entry.id=response_event.candidate_id AND entry.active_marker=1 "
        "JOIN staff ON staff.id=entry.staff_id "
        "JOIN line_identity_role_bindings staff_binding ON staff_binding.subject_type='staff' "
        "AND staff_binding.subject_reference=CAST(staff.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
        "AND staff_binding.binding_status='bound' AND staff_binding.line_user_id=staff.line_user_id "
        "JOIN orders ON orders.case_no=pool.case_no "
        "JOIN line_identity_role_bindings binding ON binding.subject_type='customer' "
        "AND binding.subject_reference="
        "CAST(orders.client_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
        "AND binding.binding_status='bound' "
        "WHERE SHA2(response_event.event_key,256)=%s AND response_event.event_type='willingness_changed'"
        + (" FOR UPDATE" if lock else ""),
        (reference,),
    )
    context = cursor.fetchone()
    if not isinstance(context, Mapping):
        raise CandidateContactResponseError("candidate_contact_question_not_found")
    if str(context.get("customer_line_user_id") or "") != line_user_id.value:
        raise CandidateContactResponseError("candidate_contact_recipient_mismatch")
    response_kind = _payload(context).get("response_kind")
    if response_kind not in {"coordination_requested", "adjustment_question_sent"}:
        raise CandidateContactResponseError("candidate_contact_question_not_found")
    if response_kind == "coordination_requested" and (
        not _information_issue_payloads(context)
        or _manual_information_message(cursor, int(context["source_event_id"]), "customer") is None
    ):
        raise CandidateContactResponseError("candidate_contact_question_not_sent")
    return context


def _has_adjustment(context) -> bool:
    return any(item.get("mode") == "condition_adjustment" for item in (_payload(context).get("issues") or ()))


def _adjustment_approval(cursor, answer_id):
    cursor.execute("SELECT id,payload FROM caregiver_candidate_contact_events WHERE "
        "JSON_UNQUOTE(JSON_EXTRACT(payload,'$.response_kind'))='adjustment_approved' "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.customer_answer_event_id')) AS UNSIGNED)=%s LIMIT 1", (answer_id,))
    row = cursor.fetchone()
    return row if isinstance(row, Mapping) else None


def _customer_question_is_current(cursor, context) -> bool:
    if _payload(context).get("response_kind") != "adjustment_question_sent":
        return _information_question_is_current(cursor, context)
    question_id = int(_payload(context)["source_response_event_id"])
    latest_message = _manual_information_message(cursor, question_id, "customer")
    latest = _latest_candidate_response(cursor, int(context["candidate_id"]))
    return (latest_message is not None and int(latest_message["id"]) == int(context["source_event_id"])
            and latest is not None and int(latest["id"]) == question_id and context["candidate_status"] == "active")


def _information_question_is_current(cursor, context) -> bool:
    latest = _latest_candidate_response(cursor, int(context["candidate_id"]))
    return (
        latest is not None
        and int(latest["id"]) == int(context["source_event_id"])
        and context["candidate_status"] == "active"
        and _manual_information_message(cursor, int(context["source_event_id"]), "caregiver") is None
    )


def _information_issue_payloads(context: Mapping[str, object]) -> list[Mapping[str, object]]:
    parsed = _payload(context)
    issues = parsed.get("issues")
    if not isinstance(issues, list):
        return []
    return [
        item for item in issues
        if isinstance(item, Mapping) and item.get("mode") == "information_question"
    ]


def _customer_answer(cursor, source_event_id: int):
    cursor.execute(
        "SELECT id,payload FROM caregiver_candidate_contact_events "
        "WHERE candidate_id IS NOT NULL AND event_type='willingness_changed' AND (("
        "JSON_UNQUOTE(JSON_EXTRACT(payload,'$.response_kind')) IN ('information_answered','information_customer_answered') "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.source_coordination_event_id')) AS UNSIGNED)=%s) "
        "OR (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.response_kind'))='adjustment_customer_answer' "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.source_coordination_event_id')) AS UNSIGNED)=%s)) "
        "ORDER BY id DESC LIMIT 1",
        (source_event_id, source_event_id),
    )
    row = cursor.fetchone()
    return row if isinstance(row, Mapping) else None


def _enqueue_caregiver_answer(connection, context, answer: str, event_id: int, now: datetime) -> None:
    reference = _source_information_reference(connection, int(context["candidate_id"]))
    response_url = _liff_url("candidate_contact", reference)
    from subsystems.scheduling.matching_line_cards import candidate_caregiver_answer_card
    message = candidate_caregiver_answer_card(str(context["case_no"]), answer, reference, response_url)
    message = canonical_line_payload_json(configured_message_payload(connection, "card-union-answer", json.loads(message), {"case_no": context["case_no"]}))
    MySqlLineDeliveryTaskRepository(connection).enqueue(
        LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId(str(context["staff_line_user_id"]).strip())),
            LineMessageKind.FLEX,
            message,
            now,
            IdempotencyKey(f"candidate-contact-answer:{event_id}"),
            CorrelationId(f"candidate-contact-answer:{event_id}"),
            "candidate_contact_answer",
            str(context["candidate_id"]),
        )
    )


def _source_information_reference(connection, candidate_id: int) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT event_key FROM caregiver_candidate_contact_events "
            "WHERE candidate_id=%s AND event_type IN ('info_1_sent','info_2_sent') ORDER BY id DESC LIMIT 1",
            (candidate_id,),
        )
        row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise CandidateContactResponseError("candidate_contact_information_not_found")
    return hashlib.sha256(str(row["event_key"]).encode("utf-8")).hexdigest()


def _liff_url(target: str, reference: str) -> str:
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if not liff_id or liff_id == "your_liff_id_here":
        raise CandidateContactResponseError("candidate_contact_liff_not_configured")
    return f"https://liff.line.me/{liff_id}/?" + urlencode({"target": target, "ref": reference})


__all__ = ["CandidateContactResponseApplication", "CandidateContactResponseError"]

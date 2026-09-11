"""Verified LIFF intake and direct customer coordination for candidate responses."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
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


_RESPONSE_LIFETIME = timedelta(hours=24)


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
                pool_resolved = _pool_has_willing_candidate(
                    cursor,
                    int(context["pool_id"]),
                    excluding_candidate_id=int(context["candidate_id"]),
                )
            deadline = _deadline(context.get("sent_at_utc"))
            is_open = (
                context["candidate_status"] == "active"
                and context["order_status"] == "洽談中"
                and self._now() < deadline
                and not pool_resolved
            )
            return {
                "case_no": str(context["case_no"]),
                "candidate_id": int(context["candidate_id"]),
                "staff_name": str(context["staff_name"]),
                "status": "open" if is_open else "closed",
                "deadline_at": deadline.isoformat(),
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
                        "customer_message_queued": bool(
                            response.has_information_questions
                            and _delivery_task_exists(
                                cursor, "candidate_contact_question", str(existing["id"])
                            )
                        ),
                    }
                if _pool_has_willing_candidate(
                    cursor,
                    int(context["pool_id"]),
                    excluding_candidate_id=int(context["candidate_id"]),
                ):
                    raise CandidateContactResponseError("candidate_contact_pool_resolved")
                if context["candidate_status"] != "active" or context["order_status"] != "洽談中":
                    raise CandidateContactResponseError("candidate_contact_closed")
                if self._now() >= _deadline(context.get("sent_at_utc")):
                    raise CandidateContactResponseError("candidate_contact_response_expired")
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
                queued = False
                if response.has_information_questions:
                    queued = _enqueue_customer_questions(
                        connection,
                        context,
                        response,
                        event_id,
                        idempotency_key.value,
                        self._now(),
                    )
                    if not queued:
                        raise CandidateContactResponseError(
                            "candidate_contact_customer_unavailable"
                        )
            connection.commit()
            return {
                "status": "recorded",
                "event_id": event_id,
                "response_kind": response.response_kind.value,
                "customer_message_queued": queued,
            }
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
                answered = _customer_answer(cursor, int(context["source_event_id"]))
                pool_resolved = _pool_has_willing_candidate(
                    cursor, int(context["pool_id"])
                )
            payload = _payload(context)
            request_kind = (
                "condition_adjustment"
                if payload.get("response_kind") == "adjustment_batch_dispatched"
                else "information_question"
            )
            issues = (
                _adjustment_item_payloads(context)
                if request_kind == "condition_adjustment"
                else _information_issue_payloads(context)
            )
            return {
                "case_no": str(context["case_no"]),
                "request_kind": request_kind,
                "status": (
                    "closed"
                    if answered is not None
                    or pool_resolved
                    or context["order_status"] != "洽談中"
                    else "open"
                ),
                "issues": [
                    {
                        "category": str(item["category"]),
                        "label": category_label(str(item["category"])),
                        "detail": str(item["detail"]),
                        "candidate_count": (
                            int(item["candidate_count"])
                            if item.get("candidate_count") is not None
                            else None
                        ),
                    }
                    for item in issues
                ],
            }
        finally:
            connection.close()

    def submit_customer_answer(
        self,
        reference: str,
        line_user_id: LineUserId,
        answer: str,
        decision: str | None,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, object]:
        normalized_answer = answer.strip() if isinstance(answer, str) else ""
        if len(normalized_answer) > 1000:
            raise CandidateContactResponseError("candidate_contact_answer_invalid")
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                context = _customer_coordination_context(cursor, reference, line_user_id, lock=True)
                source_payload = _payload(context)
                is_adjustment = source_payload.get("response_kind") == "adjustment_batch_dispatched"
                if is_adjustment:
                    if decision not in {"can_adjust", "cannot_adjust"}:
                        raise CandidateContactResponseError("candidate_contact_adjustment_decision_required")
                    payload = {
                        "response_kind": "adjustment_customer_answer",
                        "decision": decision,
                        "answer": normalized_answer,
                        "source_coordination_event_id": int(context["source_event_id"]),
                    }
                else:
                    if not normalized_answer:
                        raise CandidateContactResponseError("candidate_contact_answer_invalid")
                    payload = {
                        "response_kind": "information_answered",
                        "answer": normalized_answer,
                        "source_coordination_event_id": int(context["source_event_id"]),
                        "source_response_event_id": int(context["source_event_id"]),
                    }
                existing = _existing_event(cursor, idempotency_key.value)
                if existing is not None:
                    _require_same_event(existing, int(context["candidate_id"]), payload)
                    connection.rollback()
                    return {
                        "status": "idempotent_replay",
                        "event_id": int(existing["id"]),
                        "caregiver_message_queued": (
                            not is_adjustment
                            and _delivery_task_exists(
                                cursor, "candidate_contact_answer", str(context["candidate_id"])
                            )
                        ),
                        "union_followup_required": is_adjustment,
                    }
                if _pool_has_willing_candidate(cursor, int(context["pool_id"])):
                    raise CandidateContactResponseError("candidate_contact_pool_resolved")
                if context["order_status"] != "洽談中":
                    raise CandidateContactResponseError("candidate_contact_closed")
                if _customer_answer(cursor, int(context["source_event_id"])) is not None:
                    raise CandidateContactResponseError("candidate_contact_answer_already_recorded")
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
                if not is_adjustment:
                    _enqueue_caregiver_answer(
                        connection,
                        context,
                        normalized_answer,
                        event_id,
                        self._now(),
                    )
            connection.commit()
            return {
                "status": "recorded",
                "event_id": event_id,
                "caregiver_message_queued": not is_adjustment,
                "union_followup_required": is_adjustment,
            }
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
        "staff.name AS staff_name, staff.line_user_id, orders.status AS order_status, "
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
    if context.get("sent_at_utc") is None:
        raise CandidateContactResponseError("candidate_contact_information_not_delivered")
    return context


def _deadline(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise CandidateContactResponseError("candidate_contact_delivery_time_invalid")
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware + _RESPONSE_LIFETIME


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
        if candidate_id and _is_candidate_response_payload(payload):
            latest[candidate_id] = payload
    return any(
        candidate_id != excluding_candidate_id
        and payload.get("willingness") == "willing"
        for candidate_id, payload in latest.items()
    )


def _delivery_task_exists(cursor, source_type: str, source_identity: str) -> bool:
    cursor.execute(
        "SELECT id FROM line_delivery_tasks WHERE source_aggregate_type=%s "
        "AND source_aggregate_identity=%s LIMIT 1",
        (source_type, source_identity),
    )
    return isinstance(cursor.fetchone(), Mapping)


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


def _enqueue_customer_questions(
    connection,
    context,
    response: CandidateCoordinationResponse,
    event_id: int,
    event_key: str,
    now: datetime,
) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT binding.line_user_id FROM orders "
            "JOIN line_identity_role_bindings binding "
            "ON binding.subject_type='customer' "
            "AND binding.subject_reference="
            "CAST(orders.client_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
            "AND binding.binding_status='bound' WHERE orders.case_no=%s",
            (context["case_no"],),
        )
        customer = cursor.fetchone()
    if not isinstance(customer, Mapping) or not str(customer.get("line_user_id") or "").strip():
        return False
    questions = [
        f"• {category_label(item.category.value)}：{item.detail}"
        for item in response.issues
        if item.mode is CandidateIssueMode.INFORMATION_QUESTION
    ]
    answer_reference = hashlib.sha256(event_key.encode("utf-8")).hexdigest()
    answer_url = _liff_url("candidate_contact_customer", answer_reference)
    message = canonical_line_payload_json(
        {
            "type": "flex",
            "altText": f"案件 {context['case_no']} 的月嫂確認問題",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "md",
                    "contents": [
                        {"type": "text", "text": "月嫂想確認案件資訊", "weight": "bold", "size": "xl", "wrap": True},
                        {"type": "text", "text": f"案件編號：{context['case_no']}", "size": "sm", "color": "#666666"},
                        {"type": "text", "text": "\n".join(questions), "size": "sm", "wrap": True},
                        {"type": "text", "text": "回答只用於本次媒合確認，不會自動修改訂單。", "size": "sm", "wrap": True, "color": "#555555"},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#06C755",
                            "action": {"type": "uri", "label": "回答月嫂問題", "uri": answer_url},
                        }
                    ],
                },
            },
        }
    )
    result = MySqlLineDeliveryTaskRepository(connection).enqueue(
        LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId(str(customer["line_user_id"]).strip())),
            LineMessageKind.FLEX,
            message,
            now,
            IdempotencyKey(f"candidate-contact-question:{event_id}"),
            CorrelationId(f"candidate-contact-question:{event_id}"),
            "candidate_contact_question",
            str(event_id),
        )
    )
    return result.task_id.value > 0


def _customer_coordination_context(cursor, reference: str, line_user_id: LineUserId, *, lock: bool):
    if not isinstance(reference, str) or len(reference) != 64:
        raise CandidateContactResponseError("candidate_contact_reference_invalid")
    cursor.execute(
        "SELECT response_event.id AS source_event_id,response_event.pool_id,response_event.candidate_id,"
        "response_event.payload,pool.case_no,entry.status AS candidate_status,staff.line_user_id AS staff_line_user_id,"
        "orders.status AS order_status,binding.line_user_id AS customer_line_user_id "
        "FROM caregiver_candidate_contact_events response_event "
        "JOIN caregiver_candidate_contact_pools pool ON pool.id=response_event.pool_id "
        "JOIN caregiver_candidate_contact_entries entry ON entry.id=response_event.candidate_id AND entry.active_marker=1 "
        "JOIN staff ON staff.id=entry.staff_id "
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
    if response_kind not in {"coordination_requested", "adjustment_batch_dispatched"}:
        raise CandidateContactResponseError("candidate_contact_question_not_found")
    if response_kind == "coordination_requested" and not _information_issue_payloads(context):
        raise CandidateContactResponseError("candidate_contact_question_not_found")
    if response_kind == "adjustment_batch_dispatched" and not _adjustment_item_payloads(context):
        raise CandidateContactResponseError("candidate_contact_question_not_found")
    return context


def _information_issue_payloads(context: Mapping[str, object]) -> list[Mapping[str, object]]:
    parsed = _payload(context)
    issues = parsed.get("issues")
    if not isinstance(issues, list):
        return []
    return [
        item for item in issues
        if isinstance(item, Mapping) and item.get("mode") == "information_question"
    ]


def _adjustment_item_payloads(context: Mapping[str, object]) -> list[Mapping[str, object]]:
    items = _payload(context).get("items")
    return [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []


def _customer_answer(cursor, source_event_id: int):
    cursor.execute(
        "SELECT id,payload FROM caregiver_candidate_contact_events "
        "WHERE candidate_id IS NOT NULL AND event_type='willingness_changed' AND (("
        "JSON_UNQUOTE(JSON_EXTRACT(payload,'$.response_kind'))='information_answered' "
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
    message = canonical_line_payload_json(
        {
            "type": "flex",
            "altText": f"案件 {context['case_no']} 的客戶回覆",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box", "layout": "vertical", "spacing": "md",
                    "contents": [
                        {"type": "text", "text": "客戶已回覆確認問題", "weight": "bold", "size": "xl", "wrap": True},
                        {"type": "text", "text": answer, "size": "sm", "wrap": True},
                        {"type": "text", "text": "請依最新資訊重新選擇是否願意承接。", "size": "sm", "wrap": True, "color": "#555555"},
                    ],
                },
                "footer": {
                    "type": "box", "layout": "vertical", "contents": [
                        {"type": "button", "style": "primary", "color": "#06C755", "action": {"type": "uri", "label": "重新回覆", "uri": response_url}}
                    ],
                },
            },
        }
    )
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

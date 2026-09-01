"""Read-only source for Scheduling's Customer Service owner handoff."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from shared_kernel.identities import CorrelationId, IdempotencyKey


@dataclass(frozen=True, slots=True)
class MatchingCoordinationCustomerServiceItem:
    reference_id: str
    case_no: str
    line_user_id: str
    category: str
    message: str
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey


class MySqlMatchingCoordinationCustomerServiceSource:
    """Expose only committed, unconsumed Customer Service intents."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_customer_service_intents(
        self, *, limit: int = 25
    ) -> tuple[MatchingCoordinationCustomerServiceItem, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("matching customer-service source limit is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.reference_id,o.case_no,o.intent_payload,o.correlation_id,"
                "o.idempotency_key,c.line_user_id "
                "FROM matching_coordination_outbox o "
                "JOIN orders ord ON ord.case_no=o.case_no "
                "JOIN clients c ON c.id=ord.client_id "
                "WHERE o.target_owner='customer_service' "
                "AND o.intent_type='customer_service_ticket' "
                "AND c.line_user_id IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM customer_service_ticket_events e "
                "WHERE e.event_key=o.reference_id) "
                "ORDER BY o.id ASC LIMIT %s",
                (limit,),
            )
            rows = tuple(cursor.fetchall() or ())
        return tuple(_item(row) for row in rows)


def _item(row: Mapping[str, Any]) -> MatchingCoordinationCustomerServiceItem:
    payload = row.get("intent_payload")
    if isinstance(payload, (str, bytes, bytearray)):
        payload = json.loads(payload)
    if not isinstance(payload, Mapping):
        raise ValueError("matching customer-service source payload is invalid")
    details = payload.get("customer_service")
    if not isinstance(details, Mapping):
        raise ValueError("matching customer-service payload is missing")
    line_user_id = row.get("line_user_id")
    category = details.get("category")
    message = details.get("message")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (line_user_id, category, message)
    ):
        raise ValueError("matching customer-service recipient or message is invalid")
    return MatchingCoordinationCustomerServiceItem(
        str(row["reference_id"]),
        str(row["case_no"]),
        line_user_id.strip(),
        category.strip(),
        message.strip(),
        CorrelationId(str(row["correlation_id"])),
        IdempotencyKey(str(row["idempotency_key"])),
    )


__all__ = [
    "MatchingCoordinationCustomerServiceItem",
    "MySqlMatchingCoordinationCustomerServiceSource",
]

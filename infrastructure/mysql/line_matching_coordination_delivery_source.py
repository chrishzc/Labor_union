"""Read-only adapter for the immutable M3 owner outbox."""

from __future__ import annotations

import json
from typing import Any, Mapping

from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.matching_coordination_delivery import (
    MatchingCoordinationOutboxItem,
)


class MySqlLineMatchingCoordinationDeliverySource:
    """Expose only committed LINE-owned M3 intents to the LINE worker."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_line_intents(self, *, limit: int = 25) -> tuple[MatchingCoordinationOutboxItem, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("matching delivery source limit is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT matching_coordination_outbox.reference_id,"
                "matching_coordination_outbox.event_id,matching_coordination_outbox.receipt_id,"
                "matching_coordination_outbox.case_no,matching_coordination_outbox.intent_type,"
                "matching_coordination_outbox.target_owner,"
                "CAST(matching_coordination_outbox.intent_payload AS CHAR) AS intent_payload,"
                "matching_coordination_outbox.idempotency_key,"
                "matching_coordination_outbox.correlation_id,"
                "delivery.scheduled_at_utc AS existing_delivery_scheduled_at "
                "FROM matching_coordination_outbox "
                "LEFT JOIN line_delivery_tasks delivery ON delivery.idempotency_key="
                "matching_coordination_outbox.idempotency_key "
                "WHERE matching_coordination_outbox.target_owner='line_integration' "
                "AND matching_coordination_outbox.intent_type IN "
                "('line_bilateral_notification','line_client_decision') "
                "ORDER BY matching_coordination_outbox.id ASC LIMIT %s",
                (limit,),
            )
            rows = tuple(cursor.fetchall() or ())
        return tuple(_item(row) for row in rows)


def _item(row: Mapping[str, Any]) -> MatchingCoordinationOutboxItem:
    if not isinstance(row, Mapping):
        raise ValueError("matching delivery source row is invalid")
    payload = row.get("intent_payload")
    if isinstance(payload, (str, bytes, bytearray)):
        payload = json.loads(payload)
    if not isinstance(payload, Mapping):
        raise ValueError("matching delivery source payload is invalid")
    if payload.get("scheduled_at") is None and row.get("existing_delivery_scheduled_at") is not None:
        scheduled_at = row["existing_delivery_scheduled_at"]
        if hasattr(scheduled_at, "isoformat"):
            scheduled_at = scheduled_at.isoformat() + "+00:00"
        payload = {
            **payload,
            "scheduled_at": scheduled_at,
            "legacy_delivery_fallback": {
                "code": "line_matching_legacy_schedule_recovered",
                "fallback": "existing_delivery_task",
            },
        }
    return MatchingCoordinationOutboxItem(
        str(row["reference_id"]),
        int(row["event_id"]),
        str(row["receipt_id"]),
        str(row["case_no"]),
        str(row["intent_type"]),
        str(row["target_owner"]),
        payload,
        IdempotencyKey(str(row["idempotency_key"])),
        CorrelationId(str(row["correlation_id"])),
    )


__all__ = ["MySqlLineMatchingCoordinationDeliverySource"]

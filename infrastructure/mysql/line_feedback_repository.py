"""MySQL adapter for the bounded LINE feedback owner.

Feedback uses the existing immutable LINE source-event and command-receipt
tables.  It never commits; the surrounding LINE Unit of Work owns the commit.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from infrastructure.mysql.line_notification_repository import MySqlLineNotificationRepository
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.feedback_contracts import (
    FeedbackAggregate,
    FeedbackOutcome,
    FeedbackRoot,
)
from subsystems.line.notification_policy import NotificationSourceEvent


_FEEDBACK_DOMAIN = "line_feedback"
_FEEDBACK_SOURCE_CONTRACTS = {
    FeedbackOutcome.RESOLVED: "LU96-M2-ROUTER-REPLY-SOURCE-V1",
    FeedbackOutcome.UNRESOLVED: "LU96-M2-FEEDBACK-UNRESOLVED-SOURCE-V1",
}
_FEEDBACK_EVENT_CODES = {
    FeedbackOutcome.RESOLVED: "feedback.resolved.recorded",
    FeedbackOutcome.UNRESOLVED: "feedback.unresolved.recorded",
}


class MySqlLineFeedbackRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._source_events = MySqlLineNotificationRepository(connection)

    def get(self, actor_id: str, source_response_id: str) -> FeedbackRoot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_event_identity,event_code,facts_snapshot,occurred_at_utc "
                "FROM line_notification_source_events WHERE source_domain=%s "
                "AND source_aggregate_type='line_feedback' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(facts_snapshot,'$.actor_id'))=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(facts_snapshot,'$.source_response_id'))=%s",
                (_FEEDBACK_DOMAIN, actor_id, source_response_id),
            )
            rows = tuple(cursor.fetchall() or ())
        if not rows:
            return None
        if len(rows) != 1:
            raise RuntimeError("line_feedback_multiple_terminal_roots")
        return _root_from_row(rows[0])

    def append(self, root: FeedbackRoot) -> None:
        outcome = root.outcome
        event_identity = f"feedback:{outcome.value}:{root.actor_id}:{root.source_response_id}"
        event = NotificationSourceEvent(
            identity=event_identity,
            event_code=_FEEDBACK_EVENT_CODES[outcome],
            historical_silent=False,
            facts={
                "actor_id": root.actor_id,
                "source_response_id": root.source_response_id,
                "outcome": outcome.value,
                "binding_version": root.binding_version,
                "response_revision": root.response_revision,
                "catalog_revision": root.catalog_revision,
                "rule_revision": root.rule_revision,
                "command_fingerprint": root.command_fingerprint.value,
                "ticket_id": root.ticket_id,
                "idempotency_key": root.idempotency_key.value,
                "correlation_id": root.correlation_id.value,
                "source_contract_id": _FEEDBACK_SOURCE_CONTRACTS[outcome],
            },
            source_domain=_FEEDBACK_DOMAIN,
            source_aggregate_type="line_feedback",
            source_aggregate_identity=f"{root.actor_id}:{root.source_response_id}",
            source_version=1,
            occurred_at=root.occurred_at,
        )
        self._source_events.register_source_event(event)

    def aggregate(
        self, catalog_revision: int, window_start: datetime, window_end: datetime
    ) -> FeedbackAggregate:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_code,COUNT(*) AS count FROM line_notification_source_events "
                "WHERE source_domain=%s AND source_aggregate_type='line_feedback' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(facts_snapshot,'$.catalog_revision'))=%s "
                "AND occurred_at_utc >= %s AND occurred_at_utc < %s GROUP BY event_code",
                (_FEEDBACK_DOMAIN, catalog_revision, window_start, window_end),
            )
            rows = tuple(cursor.fetchall() or ())
        counts = {str(row["event_code"]): int(row["count"]) for row in rows}
        return FeedbackAggregate(
            catalog_revision,
            window_start,
            window_end,
            counts.get(_FEEDBACK_EVENT_CODES[FeedbackOutcome.RESOLVED], 0),
            counts.get(_FEEDBACK_EVENT_CODES[FeedbackOutcome.UNRESOLVED], 0),
        )


def _root_from_row(row: dict[str, object]) -> FeedbackRoot:
    facts = row["facts_snapshot"]
    if isinstance(facts, str):
        facts = json.loads(facts)
    if not isinstance(facts, dict):
        raise RuntimeError("line_feedback_root_facts_invalid")
    return FeedbackRoot(
        actor_id=str(facts["actor_id"]),
        source_response_id=str(facts["source_response_id"]),
        outcome=FeedbackOutcome(str(facts["outcome"])),
        binding_version=int(facts["binding_version"]),
        response_revision=int(facts["response_revision"]),
        catalog_revision=int(facts["catalog_revision"]),
        rule_revision=(None if facts.get("rule_revision") is None else int(facts["rule_revision"])),
        command_fingerprint=PreviewFingerprint(str(facts["command_fingerprint"])),
        ticket_id=(None if facts.get("ticket_id") is None else int(facts["ticket_id"])),
        idempotency_key=IdempotencyKey(str(facts["idempotency_key"])),
        correlation_id=CorrelationId(str(facts["correlation_id"])),
        occurred_at=_aware_utc(row["occurred_at_utc"]),
    )


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("line_feedback_occurred_at_invalid")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["MySqlLineFeedbackRepository"]

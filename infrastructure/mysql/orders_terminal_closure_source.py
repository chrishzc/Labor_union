"""Read-only adapter exposing Orders terminal-closure outbox handoffs to LINE."""

from __future__ import annotations

import json
from datetime import timezone
from typing import Any

from subsystems.line.terminal_closure_contracts import TerminalClosureSourceEvent


class MySqlOrdersTerminalClosureSource:
    """LINE may read this source, but it never acknowledges or updates Orders rows."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def list_pending(self, limit: int = 100) -> tuple[tuple[int, TerminalClosureSourceEvent], ...]:
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("terminal closure source limit must be positive")
        with self._connection.cursor() as cursor:
            cursor.execute(_PENDING_SQL, (limit,))
            rows = tuple(cursor.fetchall() or ())
        result = []
        for row in rows:
            payload = row.get("payload_snapshot")
            if isinstance(payload, str):
                payload = json.loads(payload)
            event = _event_from_payload(payload, case_no=str(row["case_no"]))
            result.append((int(row["id"]), event))
        return tuple(result)

    def next_due_at(self):
        """Return the next committed handoff time for worker wake scheduling."""

        with self._connection.cursor() as cursor:
            cursor.execute(_NEXT_DUE_SQL)
            row = cursor.fetchone() or {}
        value = row.get("next_due_at_utc")
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _event_from_payload(payload: object, *, case_no: str) -> TerminalClosureSourceEvent:
    if not isinstance(payload, dict) or payload.get("event_type") != "case_terminal_closure":
        raise ValueError("orders_terminal_closure_payload_invalid")
    try:
        return TerminalClosureSourceEvent(
            source_event_identity=str(payload["source_event_identity"]),
            case_no=case_no,
            terminal_kind=str(payload["terminal_kind"]),
            orders_version=int(payload["resulting_order_version"]),
            source_subject=payload.get("source_subject"),
            producer_reference=str(payload["producer_reference"]),
            occurred_at=str(payload["occurred_at"]),
            correlation_id=str(payload["correlation_id"]),
            idempotency_identity=str(payload["idempotency_identity"]),
            binding_version=(
                int(payload["binding_version"])
                if payload.get("binding_version") is not None
                else None
            ),
            menu_revision=(
                int(payload["menu_revision"])
                if payload.get("menu_revision") is not None
                else None
            ),
            capability=str(payload.get("capability", "staff_default_restore")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("orders_terminal_closure_payload_invalid") from error


_PENDING_SQL = (
    "SELECT id,case_no,payload_snapshot FROM orders_domain_outbox "
    "WHERE intent_type='lifecycle_projection_changed' AND status='pending' "
    "AND JSON_UNQUOTE(JSON_EXTRACT(payload_snapshot,'$.event_type'))="
    "'case_terminal_closure' ORDER BY id LIMIT %s"
)
_NEXT_DUE_SQL = (
    "SELECT MIN(CASE WHEN status='pending' THEN "
    "COALESCE(next_attempt_at,created_at) END) AS next_due_at_utc "
    "FROM orders_domain_outbox WHERE intent_type='lifecycle_projection_changed' "
    "AND status='pending' AND JSON_UNQUOTE(JSON_EXTRACT(payload_snapshot,'$.event_type'))="
    "'case_terminal_closure'"
)


__all__ = ["MySqlOrdersTerminalClosureSource"]

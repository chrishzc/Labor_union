"""
File: security_alert_outbox.py
Description: 將已提交的 Access Control 安全 audit 耐久投影為可重試系統告警。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from subsystems.anomalies.system_alert_projection import upsert_system_alert


@dataclass(frozen=True)
class SecurityAlertProjectionResult:
    delivered_count: int
    failed_count: int


def consume_security_alert_outbox(connection: Any, *, maximum_events: int = 25) -> SecurityAlertProjectionResult:
    """Claim committed intents and project them without re-running Access Control commands."""
    if maximum_events < 0:
        raise ValueError("maximum_events_must_not_be_negative")
    delivered = failed = 0
    for _ in range(maximum_events):
        event: dict[str, object] | None = None
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT id,source_audit_id,alert_code,alert_identity,payload_snapshot
                    FROM admin_security_alert_outbox
                    WHERE (processing_status='pending' AND (next_attempt_at IS NULL OR next_attempt_at<=UTC_TIMESTAMP(6)))
                       OR (processing_status='processing' AND lease_expires_at<=UTC_TIMESTAMP(6))
                    ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"""
                )
                event = cursor.fetchone()
                if event is None:
                    connection.rollback()
                    break
                cursor.execute(
                    """UPDATE admin_security_alert_outbox
                    SET processing_status='processing',lease_owner='incident-worker',
                        lease_expires_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 SECOND)
                    WHERE id=%s""",
                    (event["id"],),
                )
                payload = _payload(event["payload_snapshot"])
                upsert_system_alert(
                    cursor,
                    alert_code=str(event["alert_code"]),
                    source_domain="ACCESS_CONTROL",
                    case_key=str(event["alert_identity"]),
                    reason=str(payload["reason"]),
                    details=payload,
                )
                cursor.execute(
                    """UPDATE admin_security_alert_outbox
                    SET processing_status='completed',attempt_count=attempt_count+1,
                        completed_at=UTC_TIMESTAMP(6),lease_owner=NULL,lease_expires_at=NULL
                    WHERE id=%s""",
                    (event["id"],),
                )
            connection.commit()
            delivered += 1
        except Exception:
            connection.rollback()
            failed += 1
            _mark_failed(connection, event)
    return SecurityAlertProjectionResult(delivered, failed)


def _payload(raw: object) -> dict[str, object]:
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict) or not isinstance(value.get("reason"), str):
        raise ValueError("security_alert_outbox_payload_invalid")
    return value


def _mark_failed(connection: Any, event: dict[str, object] | None) -> None:
    if event is None:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE admin_security_alert_outbox
            SET attempt_count=attempt_count+1,processing_status=CASE
                    WHEN attempt_count+1>=max_attempts THEN 'dead' ELSE 'pending' END,
                next_attempt_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 SECOND),
                lease_owner=NULL,lease_expires_at=NULL,last_error_code='projection_failed'
            WHERE id=%s""",
            (event["id"],),
        )
    connection.commit()

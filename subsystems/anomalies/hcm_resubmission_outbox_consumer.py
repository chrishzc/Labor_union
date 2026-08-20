"""
File: hcm_resubmission_outbox_consumer.py
Description: 消費已提交 HCM 修正 outbox，獨立投影單筆 warning 的 auto-resolved。
"""

from __future__ import annotations

import json

from infrastructure.mysql.import_warning_auto_resolution import (
    auto_resolve_import_warning_occurrence,
)
from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    WARNING_PROJECTION_RETRY_READY_SQL,
    warning_projection_error_code,
)


def consume_hcm_resubmission_outbox(connection, *, maximum_events: int = 50) -> int:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    delivered = 0
    for _ in range(maximum_events):
        event = _claim(connection)
        if event is None:
            connection.rollback()
            break
        try:
            payload = _payload(event["bounded_snapshot"])
            auto_resolve_import_warning_occurrence(
                connection,
                occurrence_identity=str(payload["occurrence_identity"]),
                owning_lane="hcm",
                owner_event_identity=str(payload["event_identity"]),
                projector_identity="hcm-resubmission-auto-resolve-v1",
            )
            _mark_published(connection, int(event["id"]))
            connection.commit()
            delivered += 1
        except Exception as error:
            connection.rollback()
            _mark_failed(connection, int(event["id"]), error)
    return delivered


def _claim(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,bounded_snapshot FROM case_import_hcm_correction_outbox "
            f"WHERE published_at IS NULL AND attempts<{MAX_WARNING_PROJECTION_ATTEMPTS} "
            f"AND {WARNING_PROJECTION_RETRY_READY_SQL} ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _mark_published(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE case_import_hcm_correction_outbox SET published_at=CURRENT_TIMESTAMP,last_error=NULL "
            "WHERE id=%s AND published_at IS NULL",
            (event_id,),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("hcm_resubmission_outbox_delivery_conflict")


def _mark_failed(connection, event_id: int, error: Exception) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE case_import_hcm_correction_outbox SET attempts=attempts+1,"
            "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {WARNING_PROJECTION_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={MAX_WARNING_PROJECTION_ATTEMPTS}) WHERE id=%s",
            (warning_projection_error_code(error, owning_lane="hcm"), event_id),
        )
    connection.commit()


def _payload(value: object) -> dict[str, object]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict) or not {
        "event_identity", "occurrence_identity"
    } <= set(payload):
        raise ValueError("hcm_resubmission_outbox_payload_invalid")
    return payload


__all__ = ["consume_hcm_resubmission_outbox"]

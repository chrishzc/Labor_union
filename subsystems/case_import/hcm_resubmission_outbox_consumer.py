"""Consume committed HCM correction outbox using canonical review identity."""

from __future__ import annotations

import json
import hashlib
from typing import Any, Protocol

MAX_HCM_CORRECTION_OUTBOX_ATTEMPTS = 3
HCM_CORRECTION_OUTBOX_RETRY_DELAY_SECONDS = 1
HCM_CORRECTION_OUTBOX_RETRY_READY_SQL = (
    "(last_error IS NULL OR JSON_VALID(last_error)=0 OR "
    "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(last_error,'$.retry_after_epoch')) "
    "AS DECIMAL(20,6)),0)<=UNIX_TIMESTAMP(UTC_TIMESTAMP(6)))"
)


class HcmCorrectionOutboxRuntime(Protocol):
    def hcm_resubmission_repository(self, connection: Any) -> Any: ...

    def failure_unit_of_work(self, connection: Any) -> Any: ...


def consume_hcm_resubmission_outbox(
    connection,
    *,
    maximum_events: int = 50,
    runtime: HcmCorrectionOutboxRuntime | None = None,
) -> int:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    if runtime is None:
        raise RuntimeError("hcm_correction_outbox_runtime_not_composed")
    delivered = 0
    for _ in range(maximum_events):
        event = _claim(connection)
        if event is None:
            connection.rollback()
            break
        try:
            payload = _payload(event["bounded_snapshot"])
            _require_fresh_terminal_root(connection, event, payload, runtime)
            _mark_published(connection, int(event["id"]))
            connection.commit()
            delivered += 1
        except Exception as error:
            connection.rollback()
            _record_failure(connection, int(event["id"]), error, runtime)
    return delivered


def _claim(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT outbox.id,outbox.bounded_snapshot,event.id AS correction_event_id,"
            "event.event_identity,event.canonical_review_identity,"
            "event.expected_review_version,event.resulting_review_version,"
            "event.case_no,event.client_id,"
            "event.review_binding_id,event.root_after_fingerprint "
            "FROM case_import_hcm_correction_outbox AS outbox "
            "JOIN case_import_hcm_correction_events AS event "
            "ON event.id=outbox.correction_event_id "
            f"WHERE outbox.published_at IS NULL AND outbox.attempts<{MAX_HCM_CORRECTION_OUTBOX_ATTEMPTS} "
            f"AND {HCM_CORRECTION_OUTBOX_RETRY_READY_SQL} "
            "AND NOT EXISTS (SELECT 1 FROM case_import_hcm_correction_outbox earlier "
            "JOIN case_import_hcm_correction_events earlier_event "
            "ON earlier_event.id=earlier.correction_event_id "
            "WHERE earlier.published_at IS NULL "
            "AND earlier_event.review_binding_id=event.review_binding_id "
            "AND earlier.id<outbox.id) "
            "ORDER BY outbox.id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _require_fresh_terminal_root(
    connection,
    event,
    payload,
    runtime: HcmCorrectionOutboxRuntime,
) -> None:
    review_identity = payload["review_identity"]
    if str(event.get("canonical_review_identity") or "") != review_identity:
        raise ValueError("hcm_resubmission_canonical_review_binding_mismatch")
    facts = runtime.hcm_resubmission_repository(connection).load_facts(
        review_identity,
        for_update=True,
    )
    if facts.logical_code not in {"HCM-FIELD-001", "HCM-FIELD-002"}:
        raise ValueError("hcm_resubmission_auto_resolution_code_invalid")
    if str(payload["event_identity"]) != str(event["event_identity"]):
        raise ValueError("hcm_resubmission_auto_resolution_event_mismatch")
    if (
        facts.review_identity != review_identity
        or facts.case_no != str(event["case_no"])
        or facts.client_id != int(event["client_id"])
        or facts.review_binding_id != int(event["review_binding_id"])
    ):
        raise ValueError("hcm_resubmission_auto_resolution_binding_mismatch")
    expected_version = int(event["expected_review_version"])
    resulting_version = int(event["resulting_review_version"])
    if resulting_version != expected_version + 1 or facts.review_version != resulting_version:
        raise ValueError("hcm_resubmission_review_version_stale")
    if facts.root_fingerprint != str(event["root_after_fingerprint"]):
        raise ValueError("hcm_resubmission_auto_resolution_root_stale")


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
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {HCM_CORRECTION_OUTBOX_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={MAX_HCM_CORRECTION_OUTBOX_ATTEMPTS}) WHERE id=%s",
            (_delivery_error_code(error), event_id),
        )


def _record_failure(
    connection,
    event_id: int,
    error: Exception,
    runtime: HcmCorrectionOutboxRuntime,
) -> None:
    with runtime.failure_unit_of_work(connection) as unit_of_work:
        _mark_failed(connection, event_id, error)
        unit_of_work.commit()


def _payload(value: object) -> dict[str, object]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict) or not {
        "event_identity", "review_identity"
    } <= set(payload):
        raise ValueError("hcm_resubmission_outbox_payload_invalid")
    if any(not isinstance(payload[key], str) or not payload[key].strip() for key in ("event_identity", "review_identity")):
        raise ValueError("hcm_resubmission_outbox_payload_invalid")
    return payload


def _delivery_error_code(error: Exception) -> str:
    digest = hashlib.sha256(
        f"{type(error).__name__}:{str(error).strip()}".encode("utf-8")
    ).hexdigest()[:16]
    return f"hcm_correction_outbox_delivery_failed:{digest}"


__all__ = ["HcmCorrectionOutboxRuntime", "consume_hcm_resubmission_outbox"]

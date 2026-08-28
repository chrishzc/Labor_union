"""
File: hcm_resubmission_outbox_consumer.py
Description: 消費已提交 HCM 修正 outbox，獨立投影單筆 warning 的 auto-resolved。
"""

from __future__ import annotations

import json

from domains.anomalies.registry import DesiredAlertState, default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import MySqlAnomalyRepository
from infrastructure.mysql.import_warning_auto_resolution import (
    HCM_FIELD_CORRECTION_TERMINAL_PREDICATE,
    auto_resolve_import_warning_occurrence,
    load_import_warning_review_resolution_state,
)
from infrastructure.mysql.hcm_resubmission_repository import (
    MySqlHcmResubmissionRepository,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    WARNING_PROJECTION_RETRY_READY_SQL,
    warning_projection_error_code,
)


class BorrowedUnitOfWork:
    def __enter__(self): return self
    def __exit__(self, exception_type, exception, traceback): return False
    def commit(self): return None
    def rollback(self): return None


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
            _require_fresh_terminal_root(connection, event, payload)
            auto_resolve_import_warning_occurrence(
                connection,
                occurrence_identity=str(payload["occurrence_identity"]),
                owning_lane="hcm",
                owner_event_identity=str(payload["event_identity"]),
                projector_identity="hcm-resubmission-auto-resolve-v1",
                terminal_predicate=HCM_FIELD_CORRECTION_TERMINAL_PREDICATE,
            )
            _project_review_umbrella(connection, event, payload)
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
            "SELECT outbox.id,outbox.bounded_snapshot,event.id AS correction_event_id,"
            "event.event_identity,"
            "event.prior_occurrence_id,event.case_no,event.client_id,"
            "event.review_binding_id,event.root_after_fingerprint "
            "FROM case_import_hcm_correction_outbox AS outbox "
            "JOIN case_import_hcm_correction_events AS event "
            "ON event.id=outbox.correction_event_id "
            f"WHERE outbox.published_at IS NULL AND outbox.attempts<{MAX_WARNING_PROJECTION_ATTEMPTS} "
            f"AND {WARNING_PROJECTION_RETRY_READY_SQL} "
            "AND NOT EXISTS (SELECT 1 FROM case_import_hcm_correction_outbox earlier "
            "JOIN case_import_hcm_correction_events earlier_event "
            "ON earlier_event.id=earlier.correction_event_id "
            "WHERE earlier.published_at IS NULL "
            "AND earlier_event.review_binding_id=event.review_binding_id "
            "AND earlier.id<outbox.id) "
            "ORDER BY outbox.id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _project_review_umbrella(connection, event, payload) -> None:
    state = load_import_warning_review_resolution_state(
        connection,
        occurrence_identity=str(payload["occurrence_identity"]),
        owning_lane="hcm",
    )
    source_version = int(event["correction_event_id"]) + 1
    registry = default_anomaly_registry()
    desired = DesiredAlertState(
        definition_code="IMPORT-004",
        source_identity=state.review_identity,
        source_version=source_version,
        active=state.active,
        fingerprint_values={"case_no": state.masked_case_identity},
    )
    repository = MySqlAnomalyRepository(connection)
    if repository.load_current(registry.fingerprint(desired), for_update=True) is None:
        raise ValueError("hcm_import_review_umbrella_missing")
    application = AnomalyApplication(
        registry,
        repository,
        BorrowedUnitOfWork,
    )
    resulting = application.project(
        ProjectAlertRequest(
            desired=desired,
            source_event_identity=f"hcm-correction:{event['event_identity']}",
            consumer_identity="hcm-import-review-anomaly-projector-v1",
            partition_identity=f"IMPORT-004:{state.review_identity}",
            display_snapshot={
                "review_identity": state.review_identity,
                "source_row": state.source_row,
                "masked_case_identity": state.masked_case_identity,
                "issue_codes": state.unresolved_issue_codes,
                "unresolved_count": state.unresolved_count,
            },
        )
    )
    if resulting is None:
        raise ValueError("hcm_import_review_umbrella_missing")


def _require_fresh_terminal_root(connection, event, payload) -> None:
    facts = MySqlHcmResubmissionRepository(connection).load_facts(
        str(payload["occurrence_identity"]),
        for_update=True,
    )
    if facts.logical_code not in {"HCM-FIELD-001", "HCM-FIELD-002"}:
        raise ValueError("hcm_resubmission_auto_resolution_code_invalid")
    if str(payload["event_identity"]) != str(event["event_identity"]):
        raise ValueError("hcm_resubmission_auto_resolution_event_mismatch")
    if (
        facts.occurrence_id != int(event["prior_occurrence_id"])
        or facts.case_no != str(event["case_no"])
        or facts.client_id != int(event["client_id"])
        or facts.review_binding_id != int(event["review_binding_id"])
    ):
        raise ValueError("hcm_resubmission_auto_resolution_binding_mismatch")
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

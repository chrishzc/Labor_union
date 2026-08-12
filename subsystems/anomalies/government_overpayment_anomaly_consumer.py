"""Project Government Subsidy overpayment roots into the Anomalies dispatcher."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_anomaly_consumer import BorrowedProjectionUnitOfWork
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication


def consume_government_overpayment_anomaly_events(connection, maximum_events: int = 50) -> tuple[int, int]:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        event = _claim_next_event(connection)
        if event is None:
            connection.rollback()
            break
        try:
            _project_event(connection, event)
            _mark_delivered(connection, int(event["id"]))
            connection.commit()
            delivered += 1
        except Exception:
            connection.rollback()
            _mark_failed(connection, int(event["id"]))
            failed += 1
    return delivered, failed


def build_government_overpayment_root_fact(event, source) -> FinanceManualReviewRootFact:
    payload = _payload(event["payload_snapshot"])
    identity = _text(payload.get("overpayment_identity"), "overpayment identity")
    return FinanceManualReviewRootFact(
        source_event_identity=f"government-overpayment:{identity}:{event['id']}",
        source_version=_positive(event["id"]),
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]),
        finance_import_row_id=_positive(source["finance_import_row_id"]),
        finance_import_batch_id=_positive(source["finance_import_batch_id"]),
        active=True,
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        reason_codes=("government_subsidy_overpayment_established",),
        definition_code="GOVSUB-006",
        source_identity_override=f"government-overpayment:{identity}",
        recovery_bindings=(
            ("overpayment_identity", identity),
            ("overpayment_version", _positive(source["projection_version"])),
        ),
    )


def _project_event(connection, event) -> None:
    payload = _payload(event["payload_snapshot"])
    root_fact = _root_fact_for_event(connection, event, payload)
    application = RootFactProjectionApplication(
        default_anomaly_registry(), MySqlRootFactProjectionRepository(connection),
        BorrowedProjectionUnitOfWork,
    )
    application.project(root_fact, CorrelationId(f"government-overpayment:{event['id']}"))


def _root_fact_for_event(connection, event, payload):
    if event["intent_type"] == "government_subsidy_overpayment_established":
        return build_government_overpayment_root_fact(
            event, _load_overpayment_source(connection, payload)
        )
    raise ValueError("government_overpayment_event_not_projectable")


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,batch_id,intent_type,payload_snapshot,created_at FROM government_subsidy_outbox "
            "WHERE intent_type = 'government_subsidy_overpayment_established' "
            "AND status IN ('pending','failed') "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _load_overpayment_source(connection, payload):
    identity = _text(payload.get("overpayment_identity"), "overpayment identity")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT overpayment.source_finance_import_row_id finance_import_row_id,"
            "overpayment.projection_version,bank_row.batch_id finance_import_batch_id "
            "FROM government_subsidy_overpayments overpayment "
            "JOIN finance_import_rows bank_row ON bank_row.id=overpayment.source_finance_import_row_id "
            "WHERE overpayment.overpayment_identity=%s FOR UPDATE",
            (identity,),
        )
        source = cursor.fetchone()
    if source is None:
        raise ValueError("government_subsidy_overpayment_not_found")
    return source


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE government_subsidy_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (event_id,))
        if cursor.rowcount != 1:
            raise RuntimeError("government_subsidy_outbox_delivery_conflict")


def _mark_failed(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE government_subsidy_outbox SET status='failed',attempt_count=attempt_count+1,next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),last_error='government overpayment anomaly projection failed' WHERE id=%s", (event_id,))
    connection.commit()


def _payload(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("government overpayment payload is invalid")
    return payload


def _text(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    return value


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("government overpayment identity is invalid")
    return value


def _aware(value):
    if not isinstance(value, datetime):
        raise ValueError("government overpayment event timestamp is invalid")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

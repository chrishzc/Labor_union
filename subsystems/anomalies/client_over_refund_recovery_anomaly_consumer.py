"""Project immutable Client Finance recovery matchings into Anomalies."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_anomaly_consumer import BorrowedProjectionUnitOfWork
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication


def consume_client_over_refund_recovery_anomaly_events(connection, maximum_events: int = 50) -> tuple[int, int]:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        event = _claim_next_event(connection)
        if event is None:
            connection.rollback()
            break
        try:
            payload = _payload(event["payload_snapshot"])
            source = _load_matching_source(connection, payload)
            root_fact = build_client_over_refund_recovery_root_fact(
                event, source, active=_event_is_active(event, payload)
            )
            RootFactProjectionApplication(
                default_anomaly_registry(), MySqlRootFactProjectionRepository(connection),
                BorrowedProjectionUnitOfWork,
            ).project(root_fact, CorrelationId(f"client-recovery-matching:{event['id']}"))
            _mark_delivered(connection, int(event["id"]))
            connection.commit()
            delivered += 1
        except Exception:
            connection.rollback()
            _mark_failed(connection, int(event["id"]))
            failed += 1
    return delivered, failed


def build_client_over_refund_recovery_root_fact(event, source, *, active: bool = True) -> FinanceManualReviewRootFact:
    identity = _text(source["recovery_identity"], "recovery identity")
    return FinanceManualReviewRootFact(
        source_event_identity=f"client-recovery-matching:{source['matching_identity']}:{event['id']}",
        source_version=_positive(event["id"]),
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]),
        finance_import_row_id=_positive(source["finance_import_row_id"]),
        finance_import_batch_id=_positive(source["batch_id"]),
        active=active,
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        reason_codes=("client_over_refund_recovery_matched",),
        definition_code="client_over_refund_recovery_open",
        source_identity_override=f"client-over-refund-recovery:{identity}",
        recovery_bindings=(
            ("account_version", _positive_or_zero(source["account_version"])),
            ("case_no", _text(source["case_no"], "case number")),
            ("finance_import_row_identity", str(_positive(source["finance_import_row_id"]))),
            ("matching_identity", _text(source["matching_identity"], "matching identity")),
            ("matching_version", _positive(source["matching_version"])),
            ("recovery_identity", identity),
            ("recovery_version", _positive(source["recovery_version"])),
        ),
    )


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,intent_type,payload_snapshot,created_at FROM client_finance_outbox "
            "WHERE intent_type IN ('client_over_refund_recovery_matched','client_over_refund_recovery_collected') "
            "AND status IN ('pending','failed') "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _load_matching_source(connection, payload):
    matching_identity = _text(payload.get("matching_identity"), "matching identity")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT matching.matching_identity,matching.case_no,matching.recovery_identity,matching.finance_import_row_id,"
            "matching.recovery_version,matching.account_version,matching.matching_version,row.batch_id "
            "FROM client_over_refund_recovery_matchings matching "
            "JOIN finance_import_rows row ON row.id=matching.finance_import_row_id "
            "WHERE matching.matching_identity=%s FOR UPDATE",
            (matching_identity,),
        )
        source = cursor.fetchone()
    if source is None:
        raise ValueError("client_over_refund_recovery_matching_not_found")
    return source


def _event_is_active(event, payload) -> bool:
    if event["intent_type"] == "client_over_refund_recovery_matched":
        return True
    return payload.get("resulting_status") != "recovered"


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL "
            "WHERE id=%s AND status IN ('pending','failed')", (event_id,)
        )
        if cursor.rowcount != 1:
            raise RuntimeError("client_recovery_matching_outbox_delivery_conflict")


def _mark_failed(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='failed',attempt_count=attempt_count+1,"
            "next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),"
            "last_error='client recovery matching anomaly projection failed' WHERE id=%s", (event_id,)
        )
    connection.commit()


def _payload(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("client recovery matching payload is invalid")
    return payload


def _text(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    return value


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("client recovery matching value is invalid")
    return value


def _positive_or_zero(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("client recovery matching value is invalid")
    return value


def _aware(value):
    if not isinstance(value, datetime):
        raise ValueError("client recovery matching event timestamp is invalid")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

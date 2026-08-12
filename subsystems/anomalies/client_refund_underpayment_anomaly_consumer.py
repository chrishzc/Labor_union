"""Project immutable Client Finance refund-underpayment sources into Anomalies."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_anomaly_consumer import BorrowedProjectionUnitOfWork
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication

_UNDERPAYMENT_INTENT = "client_refund_underpayment_required"


def consume_client_refund_underpayment_anomaly_events(connection, maximum_events: int = 50) -> tuple[int, int]:
    _require_page_size(maximum_events)
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


def build_client_refund_underpayment_root_fact(event, source) -> FinanceManualReviewRootFact:
    identity = _text(source["underpayment_identity"], "underpayment identity")
    return FinanceManualReviewRootFact(
        source_event_identity=f"client-refund-underpayment:{identity}:{event['id']}",
        source_version=_positive(event["id"]),
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]),
        finance_import_row_id=_positive(source["finance_import_row_id"]),
        finance_import_batch_id=_positive(source["batch_id"]),
        active=bool(source["active"]),
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        reason_codes=("client_refund_underpayment",),
        definition_code="client_refund_underpayment",
        source_identity_override=f"client-refund-underpayment:{identity}",
        recovery_bindings=_recovery_bindings(source, identity),
    )


def _project_event(connection, event) -> None:
    payload = _payload(event["payload_snapshot"])
    source = _load_underpayment_source(connection, payload)
    application = RootFactProjectionApplication(
        default_anomaly_registry(),
        MySqlRootFactProjectionRepository(connection),
        BorrowedProjectionUnitOfWork,
    )
    application.project(
        build_client_refund_underpayment_root_fact(event, source),
        CorrelationId(f"client-refund-underpayment:{event['id']}"),
    )


def _recovery_bindings(source, identity: str) -> tuple[tuple[str, object], ...]:
    return (
        ("account_version", _positive_or_zero(source["resulting_account_version"])),
        ("case_no", _text(source["case_no"], "case number")),
        ("underpayment_identity", identity),
    )


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,payload_snapshot,created_at FROM client_finance_outbox "
            "WHERE intent_type=%s AND status IN ('pending','failed') "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED",
            (_UNDERPAYMENT_INTENT,),
        )
        return cursor.fetchone()


def _load_underpayment_source(connection, payload):
    identity = _text(payload.get("underpayment_identity"), "underpayment identity")
    with connection.cursor() as cursor:
        cursor.execute(_UNDERPAYMENT_SOURCE_SQL, (identity,))
        source = cursor.fetchone()
    if source is None or source["batch_id"] is None:
        raise ValueError("client_refund_underpayment_source_not_found")
    return source


def _mark_delivered(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL "
            "WHERE id=%s AND status IN ('pending','failed')",
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("client_refund_underpayment_outbox_delivery_conflict")


def _mark_failed(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='failed',attempt_count=attempt_count+1,"
            "next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),"
            "last_error='client refund underpayment anomaly projection failed' WHERE id=%s",
            (event_id,),
        )
    connection.commit()


def _payload(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("client_refund_underpayment_payload_invalid")
    return payload


def _require_page_size(value: int) -> None:
    if not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError("maximum events must be between 1 and 100")


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    return value


def _positive(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("client_refund_underpayment_value_invalid")
    return value


def _positive_or_zero(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("client_refund_underpayment_value_invalid")
    return value


def _aware(value) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("client_refund_underpayment_timestamp_invalid")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


_UNDERPAYMENT_SOURCE_SQL = """
SELECT source.underpayment_identity,source.case_no,source.resulting_account_version,
       row.id finance_import_row_id,row.batch_id,
       EXISTS(
           SELECT 1
           FROM client_refund_underpayment_source_obligations link
           JOIN client_obligations obligation
             ON obligation.obligation_identity=link.refund_obligation_identity
           WHERE link.underpayment_identity=source.underpayment_identity
             AND obligation.status='open'
             AND obligation.amount_due_ntd>0
       ) active
FROM client_refund_underpayment_sources source
JOIN client_refund_underpayment_source_bank_rows link
  ON link.underpayment_identity=source.underpayment_identity
JOIN finance_import_rows row ON row.id=link.finance_import_row_id
WHERE source.underpayment_identity=%s
ORDER BY link.ordinal
LIMIT 1 FOR UPDATE
"""

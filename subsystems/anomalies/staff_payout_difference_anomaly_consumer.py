"""Project completed Staff Payables difference commands into state-only alerts."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_anomaly_consumer import BorrowedProjectionUnitOfWork
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication


def consume_staff_payout_difference_anomaly_events(connection, maximum_events: int = 50) -> tuple[int, int]:
    delivered = failed = 0
    for _ in range(maximum_events):
        event = _claim(connection)
        if event is None:
            connection.rollback()
            return delivered, failed
        try:
            source = _source(connection, _payload(event["payload_snapshot"]))
            _project(connection, event, source)
            _delivered(connection, event["id"])
            connection.commit()
            delivered += 1
        except Exception:
            connection.rollback()
            _failed(connection, event["id"])
            failed += 1
    return delivered, failed


def build_staff_payout_difference_root_fact(event, source) -> FinanceManualReviewRootFact:
    mode = str(source["difference_mode"])
    code = "staff_payout_underpayment" if mode == "underpayment" else "staff_payout_overpayment"
    return FinanceManualReviewRootFact(
        source_event_identity=f"staff-payout-difference:{source['payout_difference_identity']}:{event['id']}",
        source_version=int(event["id"]), origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]), finance_import_row_id=int(source["finance_import_row_id"]),
        finance_import_batch_id=int(source["batch_id"]), active=bool(source["active"]),
        integrity_blocker_active=False, amount_delta_ntd=0, reason_codes=(code,),
        definition_code=code, source_identity_override=f"staff-payout-difference:{source['payout_difference_identity']}",
        recovery_bindings=(("payout_difference_identity", str(source["payout_difference_identity"])), ("staff_id", int(source["staff_id"])), ("staff_payables_version", int(source["resulting_staff_payables_version"]))),
    )


def _claim(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,payload_snapshot,created_at FROM staff_payables_outbox WHERE intent_type='payout_anomaly_required' AND status IN ('pending','failed') ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED")
        return cursor.fetchone()


def _source(connection, payload):
    identity = payload.get("payout_difference_identity")
    if not isinstance(identity, str) or not identity:
        raise ValueError("staff_payout_difference_source_invalid")
    with connection.cursor() as cursor:
        cursor.execute("SELECT source.payout_difference_identity,source.staff_id,source.difference_mode,source.recovery_identity,source.resulting_staff_payables_version,row.id finance_import_row_id,row.batch_id,CASE WHEN source.difference_mode='underpayment' THEN EXISTS(SELECT 1 FROM staff_payout_difference_source_obligations link JOIN staff_payable_projections projection ON projection.obligation_identity=link.obligation_identity WHERE link.payout_difference_identity=source.payout_difference_identity AND projection.status='partially_paid') ELSE EXISTS(SELECT 1 FROM staff_overpayment_recoveries recovery WHERE recovery.recovery_identity=source.recovery_identity AND recovery.status IN ('open','partially_recovered')) END active FROM staff_payout_difference_sources source JOIN staff_payout_difference_source_bank_rows source_row ON source_row.payout_difference_identity=source.payout_difference_identity JOIN finance_import_rows row ON row.id=source_row.finance_import_row_id WHERE source.payout_difference_identity=%s ORDER BY source_row.ordinal LIMIT 1 FOR UPDATE", (identity,))
        source = cursor.fetchone()
    if source is None or source["batch_id"] is None:
        raise ValueError("staff_payout_difference_source_not_found")
    return source


def _project(connection, event, source):
    application = RootFactProjectionApplication(default_anomaly_registry(), MySqlRootFactProjectionRepository(connection), BorrowedProjectionUnitOfWork)
    application.project(build_staff_payout_difference_root_fact(event, source), CorrelationId(f"staff-payout-difference:{event['id']}"))


def _delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE staff_payables_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s", (event_id,))


def _failed(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE staff_payables_outbox SET status='failed',attempt_count=attempt_count+1,last_error='staff payout difference anomaly projection failed' WHERE id=%s", (event_id,))
    connection.commit()


def _payload(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("staff_payout_difference_payload_invalid")
    return payload


def _aware(value):
    if not isinstance(value, datetime):
        raise ValueError("staff_payout_difference_timestamp_invalid")
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

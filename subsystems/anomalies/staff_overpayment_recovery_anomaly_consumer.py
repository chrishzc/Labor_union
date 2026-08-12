"""Project Staff Payables recovery matching outbox events into Anomalies."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_anomaly_consumer import BorrowedProjectionUnitOfWork
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication


def consume_staff_overpayment_recovery_anomaly_events(connection, maximum_events: int = 50) -> tuple[int, int]:
    delivered = failed = 0
    for _ in range(maximum_events):
        event = _claim(connection)
        if event is None:
            connection.rollback(); break
        try:
            payload = _payload(event["payload_snapshot"])
            source = _source(connection, payload)
            RootFactProjectionApplication(default_anomaly_registry(), MySqlRootFactProjectionRepository(connection), BorrowedProjectionUnitOfWork).project(build_staff_overpayment_recovery_root_fact(event, source, active=_active(event, payload)), CorrelationId(f"staff-recovery-matching:{event['id']}"))
            _delivered(connection, event["id"]); connection.commit(); delivered += 1
        except Exception:
            connection.rollback(); _failed(connection, event["id"]); failed += 1
    return delivered, failed


def build_staff_overpayment_recovery_root_fact(event, source, *, active: bool = True):
    return FinanceManualReviewRootFact(
        source_event_identity=f"staff-recovery-matching:{source['matching_identity']}:{event['id']}", source_version=int(event["id"]), origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]), finance_import_row_id=int(source["finance_import_row_id"]), finance_import_batch_id=int(source["batch_id"]), active=active, integrity_blocker_active=False, amount_delta_ntd=0,
        reason_codes=("staff_overpayment_recovery_matched",), definition_code="staff_overpayment_recovery_open", source_identity_override=f"staff-overpayment-recovery:{source['recovery_identity']}",
        recovery_bindings=(("finance_import_row_identity", str(source["finance_import_row_id"])), ("matching_identity", source["matching_identity"]), ("matching_version", int(source["matching_version"])), ("recovery_identity", source["recovery_identity"]), ("recovery_version", int(source["recovery_version"])), ("staff_id", int(source["staff_id"])), ("staff_payables_version", int(source["staff_payables_version"]))),
    )


def _claim(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,intent_type,payload_snapshot,created_at FROM staff_payables_outbox WHERE intent_type IN ('staff_overpayment_recovery_matched','staff_overpayment_recovery_collected') AND status IN ('pending','failed') AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED")
        return cursor.fetchone()


def _source(connection, payload):
    identity = payload.get("matching_identity")
    if not isinstance(identity, str) or not identity: raise ValueError("staff recovery matching identity is invalid")
    with connection.cursor() as cursor:
        cursor.execute("SELECT matching.matching_identity,matching.recovery_identity,matching.staff_id,matching.finance_import_row_id,matching.recovery_version,matching.staff_payables_version,matching.matching_version,row.batch_id FROM staff_overpayment_recovery_matchings matching JOIN finance_import_rows row ON row.id=matching.finance_import_row_id WHERE matching.matching_identity=%s FOR UPDATE", (identity,))
        row = cursor.fetchone()
    if row is None or row["batch_id"] is None: raise ValueError("staff recovery matching source not found")
    return row


def _delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE staff_payables_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (event_id,))
        if cursor.rowcount != 1: raise RuntimeError("staff recovery matching delivery conflict")


def _failed(connection, event_id):
    with connection.cursor() as cursor: cursor.execute("UPDATE staff_payables_outbox SET status='failed',attempt_count=attempt_count+1,next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),last_error='staff recovery matching anomaly projection failed' WHERE id=%s", (event_id,))
    connection.commit()


def _payload(value):
    value = json.loads(value) if isinstance(value, str) else value
    if not isinstance(value, dict): raise ValueError("staff recovery matching payload invalid")
    return value


def _aware(value):
    if not isinstance(value, datetime): raise ValueError("staff recovery matching timestamp invalid")
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _active(event, payload):
    if event["intent_type"] == "staff_overpayment_recovery_matched":
        return True
    return False

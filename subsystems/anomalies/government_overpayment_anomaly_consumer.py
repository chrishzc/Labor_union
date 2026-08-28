"""
File: government_overpayment_anomaly_consumer.py
Description: 依政府補助超收 fresh remaining 根事實投影 GOVSUB-006。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_anomaly_consumer import BorrowedProjectionUnitOfWork
from subsystems.anomalies.root_fact_projection_workflow import (
    RootFactProjectionApplication,
    RootFactProjectionError,
)


_PROJECTABLE_INTENTS = frozenset(
    {
        "government_subsidy_overpayment_established",
        "government_subsidy_overpayment_offset",
        "government_overpayment_return_payable",
    }
)
_AUTHORIZED_PAYER_IDENTITY = "hccg"
_MAXIMUM_PROJECTION_ATTEMPTS = 3
_OVERPAYMENT_STATUSES = frozenset(
    {
        "pending_review",
        "offset_reserved",
        "offset_applied",
        "return_payable",
        "partially_returned",
        "returned",
    }
)


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
    event_id = _positive(event.get("id"))
    if event.get("intent_type") not in _PROJECTABLE_INTENTS:
        raise ValueError("government_overpayment_event_not_projectable")
    if _text(source.get("payer_identity"), "payer identity") != _AUTHORIZED_PAYER_IDENTITY:
        raise ValueError("government_subsidy_overpayment_payer_invalid")
    status = _status(source.get("status"))
    remaining = _nonnegative(source.get("remaining_amount_ntd"))
    _validate_status_remaining(status, remaining)
    return FinanceManualReviewRootFact(
        source_event_identity=f"government-overpayment:{identity}:{event_id}",
        source_version=event_id,
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]),
        finance_import_row_id=_positive(source["finance_import_row_id"]),
        finance_import_batch_id=_positive(source["finance_import_batch_id"]),
        active=status == "pending_review",
        integrity_blocker_active=False,
        amount_delta_ntd=remaining,
        reason_codes=(str(event["intent_type"]),),
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
    try:
        application.project(root_fact, CorrelationId(f"government-overpayment:{event['id']}"))
    except RootFactProjectionError as error:
        if error.error.code == "anomaly_projection_stale":
            return
        raise


def _root_fact_for_event(connection, event, payload):
    if event.get("intent_type") not in _PROJECTABLE_INTENTS:
        raise ValueError("government_overpayment_event_not_projectable")
    return build_government_overpayment_root_fact(
        event, _load_overpayment_source(connection, payload)
    )


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,batch_id,intent_type,payload_snapshot,created_at FROM government_subsidy_outbox "
            "WHERE intent_type IN ('government_subsidy_overpayment_established',"
            "'government_subsidy_overpayment_offset',"
            "'government_overpayment_return_payable') "
            "AND status IN ('pending','failed') "
            f"AND attempt_count<{_MAXIMUM_PROJECTION_ATTEMPTS} "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _load_overpayment_source(connection, payload):
    identity = _text(payload.get("overpayment_identity"), "overpayment identity")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT overpayment.source_finance_import_row_id finance_import_row_id,"
            "bank_row.batch_id finance_import_batch_id,overpayment.remaining_amount_ntd,"
            "overpayment.status,overpayment.projection_version,overpayment.payer_identity "
            "FROM government_subsidy_overpayments overpayment "
            "JOIN finance_import_rows bank_row ON bank_row.id=overpayment.source_finance_import_row_id "
            "WHERE overpayment.overpayment_identity=%s FOR UPDATE",
            (identity,),
        )
        source = cursor.fetchone()
    if source is None or not isinstance(source, Mapping):
        raise ValueError("government_subsidy_overpayment_not_found")
    return source


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE government_subsidy_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (event_id,))
        if cursor.rowcount != 1:
            raise RuntimeError("government_subsidy_outbox_delivery_conflict")


def _mark_failed(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE government_subsidy_outbox SET status='failed',"
            "attempt_count=attempt_count+1,"
            f"next_attempt_at=CASE WHEN attempt_count+1>={_MAXIMUM_PROJECTION_ATTEMPTS} "
            "THEN NULL ELSE DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND) END,"
            "last_error='government_overpayment_anomaly_projection_failed' "
            "WHERE id=%s AND status IN ('pending','failed')",
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("government_subsidy_outbox_failure_conflict")
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


def _nonnegative(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("government overpayment remaining amount is invalid")
    return value


def _status(value):
    if not isinstance(value, str) or value not in _OVERPAYMENT_STATUSES:
        raise ValueError("government overpayment status is invalid")
    return value


def _validate_status_remaining(status, remaining):
    """Keep the anomaly projection aligned with Government §4.5.1 state invariants."""
    if status in {"pending_review", "offset_reserved", "return_payable", "partially_returned"}:
        valid = remaining > 0
    else:
        valid = remaining == 0
    if not valid:
        raise ValueError("government_overpayment_status_remaining_invalid")


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("government overpayment identity is invalid")
    return value


def _aware(value):
    if not isinstance(value, datetime):
        raise ValueError("government overpayment event timestamp is invalid")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

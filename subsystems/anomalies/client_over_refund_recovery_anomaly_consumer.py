"""File: client_over_refund_recovery_anomaly_consumer.py
Description: 從 Client Finance outbox 以 fresh recovery root 投影客戶追償異常。
"""

from __future__ import annotations

import json
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

_ROOT_EVENT_TYPES = frozenset({
    "client_over_refund_recovery_established",
    "client_over_refund_recovery_updated",
})
_MAXIMUM_PROJECTION_ATTEMPTS = 3


def consume_client_over_refund_recovery_anomaly_events(
    connection, maximum_events: int = 50
) -> tuple[int, int]:
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
            source = _load_source(connection, event, payload)
            _validate_source(source)
            root_fact = build_client_over_refund_recovery_root_fact(
                event, source, active=_event_is_active(event, source)
            )
            try:
                RootFactProjectionApplication(
                    default_anomaly_registry(),
                    MySqlRootFactProjectionRepository(connection),
                    BorrowedProjectionUnitOfWork,
                ).project(root_fact, CorrelationId(f"client-recovery:{event['id']}"))
            except RootFactProjectionError as error:
                if error.error.code != "anomaly_projection_stale":
                    raise
            _mark_delivered(connection, int(event["id"]))
            connection.commit()
            delivered += 1
        except Exception:
            connection.rollback()
            _mark_failed(connection, int(event["id"]))
            failed += 1
    return delivered, failed


def build_client_over_refund_recovery_root_fact(
    event, source, *, active: bool = True
) -> FinanceManualReviewRootFact:
    identity = _text(source["recovery_identity"], "recovery identity")
    matching_identity = source.get("matching_identity")
    bindings: list[tuple[str, object]] = [
        ("account_version", _positive_or_zero(source["account_version"])),
        ("case_no", _text(source["case_no"], "case number")),
        ("finance_import_row_identity", str(_positive(source["finance_import_row_id"]))),
        ("recovery_identity", identity),
        ("recovery_version", _positive_or_zero(source["recovery_version"])),
    ]
    if matching_identity is not None:
        bindings.extend(
            (
                ("matching_identity", _text(matching_identity, "matching identity")),
                ("matching_version", _positive(source.get("matching_version"))),
            )
        )
    remaining = source.get("remaining_amount_ntd", source.get("amount_due_ntd", 0))
    event_type = _event_type(event, source)
    return FinanceManualReviewRootFact(
        source_event_identity=f"client-recovery:{identity}:{_positive(event['id'])}",
        source_version=_positive(event["id"]),
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware(event["created_at"]),
        finance_import_row_id=_positive(source["finance_import_row_id"]),
        finance_import_batch_id=_positive(source["batch_id"]),
        active=active,
        integrity_blocker_active=False,
        amount_delta_ntd=_nonnegative(remaining),
        reason_codes=(event_type,),
        definition_code="client_over_refund_recovery_open",
        source_identity_override=f"client-over-refund-recovery:{identity}",
        recovery_bindings=tuple(sorted(bindings)),
    )


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,intent_type,intent_key,payload_snapshot,created_at "
            "FROM client_finance_outbox "
            "WHERE (intent_type IN "
            "('client_over_refund_recovery_matched','client_over_refund_recovery_collected') "
            "OR (intent_type='projection_refresh' "
            "AND intent_key LIKE 'client-over-refund-recovery-%')) "
            "AND status IN ('pending','failed') "
            f"AND attempt_count<{_MAXIMUM_PROJECTION_ATTEMPTS} "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _load_source(connection, event, payload):
    event_type = _event_type(event, payload)
    if event_type == "client_over_refund_recovery_matched":
        matching_identity = _text(payload.get("matching_identity"), "matching identity")
        query = (
            "SELECT recovery.recovery_identity,recovery.case_no,matching.finance_import_row_id,"
            "recovery.amount_due_ntd,recovery.status,recovery.projection_version recovery_version,"
            "account.aggregate_version account_version,bank.batch_id,matching.matching_identity,"
            "matching.matching_version FROM client_over_refund_recovery_matchings matching "
            "JOIN client_over_refund_recoveries recovery ON recovery.recovery_identity=matching.recovery_identity "
            "JOIN finance_import_rows bank ON bank.id=matching.finance_import_row_id "
            "LEFT JOIN client_finance_accounts account ON account.case_no=recovery.case_no "
            "WHERE matching.matching_identity=%s AND matching.recovery_identity=%s FOR UPDATE"
        )
        params = (matching_identity, _text(payload.get("recovery_identity"), "recovery identity"))
    else:
        recovery_identity = _text(payload.get("recovery_identity"), "recovery identity")
        query = (
            "SELECT recovery.recovery_identity,recovery.case_no,recovery.finance_import_row_id,"
            "recovery.amount_due_ntd,recovery.status,recovery.projection_version recovery_version,"
            "account.aggregate_version account_version,bank.batch_id "
            "FROM client_over_refund_recoveries recovery "
            "JOIN finance_import_rows bank ON bank.id=recovery.finance_import_row_id "
            "LEFT JOIN client_finance_accounts account ON account.case_no=recovery.case_no "
            "WHERE recovery.recovery_identity=%s FOR UPDATE"
        )
        params = (recovery_identity,)
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        source = cursor.fetchone()
    if source is None:
        raise ValueError("client_over_refund_recovery_root_not_found")
    if event_type != "client_over_refund_recovery_matched":
        matching_identity = payload.get("matching_identity")
        if matching_identity is not None:
            source = _attach_matching(connection, source, matching_identity)
    return source


def _attach_matching(connection, source, matching_identity):
    identity = _text(matching_identity, "matching identity")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT matching_identity,matching_version,recovery_identity,case_no,"
            "finance_import_row_id,bank.batch_id FROM client_over_refund_recovery_matchings matching "
            "JOIN finance_import_rows bank ON bank.id=matching.finance_import_row_id "
            "WHERE matching_identity=%s FOR UPDATE",
            (identity,),
        )
        matching = cursor.fetchone()
    if matching is None:
        raise ValueError("client_over_refund_recovery_matching_not_found")
    if (
        matching["recovery_identity"] != source["recovery_identity"]
        or matching["case_no"] != source["case_no"]
    ):
        raise ValueError("client_over_refund_recovery_matching_stale")
    _positive(matching.get("batch_id"))
    return {
        **source,
        "finance_import_row_id": matching["finance_import_row_id"],
        "batch_id": matching["batch_id"],
        "matching_identity": matching["matching_identity"],
        "matching_version": matching["matching_version"],
    }


def _validate_source(source) -> None:
    _text(source.get("recovery_identity"), "recovery identity")
    _text(source.get("case_no"), "case number")
    _positive(source.get("finance_import_row_id"))
    _positive(source.get("batch_id"))
    _positive_or_zero(source.get("recovery_version"))
    if source.get("account_version") is None:
        raise ValueError("client_over_refund_recovery_account_not_found")
    _positive_or_zero(source["account_version"])
    amount = _nonnegative(source.get("amount_due_ntd"))
    status = source.get("status")
    if status in {"open", "partially_recovered"} and amount <= 0:
        raise ValueError("client_over_refund_recovery_root_invalid")
    if status in {"recovered", "adjusted"} and amount != 0:
        raise ValueError("client_over_refund_recovery_root_invalid")
    if status not in {"open", "partially_recovered", "recovered", "adjusted"}:
        raise ValueError("client_over_refund_recovery_root_invalid")
    if source.get("matching_identity") is not None:
        _text(source["matching_identity"], "matching identity")
        _positive(source.get("matching_version"))


def _event_type(event, payload_or_source):
    intent_type = event.get("intent_type")
    if intent_type == "client_over_refund_recovery_matched":
        return intent_type
    if intent_type == "client_over_refund_recovery_collected":
        return "client_over_refund_recovery_updated"
    event_type = payload_or_source.get("event_type")
    if event_type is None and payload_or_source.get("matching_identity") is not None:
        return "client_over_refund_recovery_matched"
    if event_type is None:
        return "client_over_refund_recovery_established"
    if event_type not in _ROOT_EVENT_TYPES:
        raise ValueError("client_over_refund_recovery_event_invalid")
    return event_type


def _event_is_active(event, source) -> bool:
    del event
    return source["status"] in {"open", "partially_recovered"}


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL "
            "WHERE id=%s AND status IN ('pending','failed')",
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("client_recovery_outbox_delivery_conflict")


def _mark_failed(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE client_finance_outbox SET status='failed',attempt_count=attempt_count+1,"
            f"next_attempt_at=CASE WHEN attempt_count+1>={_MAXIMUM_PROJECTION_ATTEMPTS} "
            "THEN NULL ELSE DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND) END,"
            "last_error='client_recovery_anomaly_projection_failed' "
            "WHERE id=%s AND status IN ('pending','failed')",
            (event_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("client_recovery_outbox_failure_conflict")
    connection.commit()


def _payload(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("client recovery payload is invalid")
    return payload


def _text(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is invalid")
    return value


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("client recovery value is invalid")
    return value


def _positive_or_zero(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("client recovery value is invalid")
    return value


def _nonnegative(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("client recovery amount is invalid")
    return value


def _aware(value):
    if not isinstance(value, datetime):
        raise ValueError("client recovery event timestamp is invalid")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

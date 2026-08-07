"""Deliver Finance Import outbox events to the canonical anomaly projector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication


@dataclass(frozen=True, slots=True)
class FinanceImportAnomalyConsumerResult:
    delivered_count: int
    failed_count: int


class BorrowedProjectionUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def consume_finance_import_anomaly_events(connection, *, maximum_events: int = 50) -> FinanceImportAnomalyConsumerResult:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection)
        if outcome is None:
            break
        if outcome:
            delivered += 1
        else:
            failed += 1
    return FinanceImportAnomalyConsumerResult(delivered, failed)


def _consume_next(connection):
    try:
        event = _claim_next_event(connection)
        if event is None:
            connection.rollback()
            return None
        application = _projection_application(connection)
        for root_fact in _root_facts(connection, event):
            application.project(root_fact, CorrelationId(f"finance-anomaly:{event['id']}:{root_fact.finance_import_row_id}"))
        _mark_delivered(connection, int(event["id"]))
        connection.commit()
        return True
    except Exception as error:
        connection.rollback()
        _mark_failed(connection, locals().get("event"), error)
        return False


def _claim_next_event(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,intent_type,payload_snapshot,created_at FROM finance_import_outbox WHERE intent_type IN ('initial_classification_recorded','dispatch_completed','manual_correction_completed','refund_return_review_recorded') AND status IN ('pending','failed') AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED")
        return cursor.fetchone()


def _projection_application(connection):
    return RootFactProjectionApplication(default_anomaly_registry(), MySqlRootFactProjectionRepository(connection), BorrowedProjectionUnitOfWork)


def _root_facts(connection, event):
    payload = _json_object(event["payload_snapshot"])
    if event["intent_type"] == "initial_classification_recorded":
        return (_initial_classification_root_fact(event, payload),)
    if event["intent_type"] == "manual_correction_completed":
        return _manual_correction_root_facts(connection, event, payload)
    if event["intent_type"] == "refund_return_review_recorded":
        return (_refund_return_review_root_fact(event, payload),)
    return _dispatch_root_facts(event, payload)


def _initial_classification_root_fact(event, payload):
    return FinanceManualReviewRootFact(
        source_event_identity=str(payload["source_event_identity"]), source_version=int(payload["source_version"]), origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware_datetime(event["created_at"]), finance_import_row_id=int(payload["finance_import_row_id"]), finance_import_batch_id=int(payload["finance_import_batch_id"]),
        active=bool(payload["active"]), integrity_blocker_active=bool(payload["integrity_blocker_active"]), amount_delta_ntd=int(payload["amount_delta_ntd"]),
        affected_order_identities=_text_tuple(payload["affected_order_identities"]), affected_obligation_identities=_text_tuple(payload["affected_obligation_identities"]),
        domain_blockers=_text_tuple(payload["domain_blockers"]), reason_codes=_text_tuple(payload["reason_codes"]),
    )


def _dispatch_root_facts(event, payload):
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("dispatch outbox results must be an array")
    batch_id = _prefixed_positive_integer(payload.get("batch_identity"), "finance-import-batch:")
    return tuple(_dispatch_root_fact(event, batch_id, result) for result in results)


def _manual_correction_root_facts(connection, event, payload):
    generic = _manual_correction_root_fact(event, payload)
    if payload.get("classification_type") != "client_refund_return":
        return (generic,)
    return (generic, _refund_return_resolution_root_fact(connection, event, payload))


def _manual_correction_root_fact(event, payload):
    row_id = _prefixed_positive_integer(payload.get("row_identity"), "finance-import-row:")
    batch_id = _prefixed_positive_integer(payload.get("batch_identity"), "finance-import-batch:")
    return FinanceManualReviewRootFact(
        source_event_identity=f"finance-import-correction:{event['id']}:{row_id}", source_version=int(event["id"]), origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware_datetime(event["created_at"]), finance_import_row_id=row_id, finance_import_batch_id=batch_id,
        active=False, integrity_blocker_active=False, amount_delta_ntd=0, reason_codes=("manual_correction_completed",),
    )


def _refund_return_resolution_root_fact(connection, event, payload):
    row_id = _prefixed_positive_integer(payload.get("row_identity"), "finance-import-row:")
    batch_id = _prefixed_positive_integer(payload.get("batch_identity"), "finance-import-batch:")
    ledger_id = _prefixed_positive_integer(
        payload.get("refund_ledger_entry_identity"),
        "client-ledger-entry:",
    )
    _require_refund_return_reversal(connection, row_id, ledger_id)
    return FinanceManualReviewRootFact(
        source_event_identity=(
            f"finance-import-refund-return-resolution:{event['id']}:{row_id}:{ledger_id}"
        ),
        source_version=int(event["id"]),
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware_datetime(event["created_at"]),
        finance_import_row_id=row_id,
        finance_import_batch_id=batch_id,
        active=False,
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        reason_codes=("refund_return_reversal_completed",),
        definition_code="CLIENTREFUND-001",
        source_identity_override=(
            f"finance-import-refund-return:{row_id}:{ledger_id}"
        ),
        original_refund_ledger_entry_id=ledger_id,
    )


def _refund_return_review_root_fact(event, payload):
    row_id = _prefixed_positive_integer(payload.get("row_identity"), "finance-import-row:")
    batch_id = _prefixed_positive_integer(payload.get("batch_identity"), "finance-import-batch:")
    ledger_entry_id = _positive_integer(payload.get("original_refund_ledger_entry_id"))
    return FinanceManualReviewRootFact(
        source_event_identity=str(payload["source_event_identity"]),
        source_version=int(payload["source_version"]),
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware_datetime(event["created_at"]),
        finance_import_row_id=row_id,
        finance_import_batch_id=batch_id,
        active=True,
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        affected_order_identities=_text_tuple(payload["affected_order_identities"]),
        affected_obligation_identities=_text_tuple(payload["affected_obligation_identities"]),
        domain_blockers=("refund_return_requires_confirmed_reversal",),
        reason_codes=("refund_return_review_recorded",),
        definition_code="CLIENTREFUND-001",
        source_identity_override=(
            f"finance-import-refund-return:{row_id}:{ledger_entry_id}"
        ),
        original_refund_ledger_entry_id=ledger_entry_id,
    )


def _dispatch_root_fact(event, batch_id, result):
    if not isinstance(result, dict):
        raise ValueError("dispatch outbox result must be an object")
    row_id = _prefixed_positive_integer(result.get("row_identity"), "finance-import-row:")
    outcome = str(result.get("outcome"))
    if outcome not in {"existing", "pending", "reconciled"}:
        raise ValueError("dispatch outbox outcome is invalid")
    active = outcome == "pending"
    return FinanceManualReviewRootFact(
        source_event_identity=f"finance-import-dispatch:{event['id']}:{row_id}", source_version=int(event["id"]), origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=_aware_datetime(event["created_at"]), finance_import_row_id=row_id, finance_import_batch_id=batch_id,
        active=active, integrity_blocker_active=False, amount_delta_ntd=0,
        domain_blockers=("owning_domain_dispatch_pending",) if active else (), reason_codes=(f"dispatch_{outcome}",),
    )


def _prefixed_positive_integer(value, prefix):
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("Finance Import outbox identity is invalid")
    raw_value = value.removeprefix(prefix)
    if not raw_value.isdigit() or int(raw_value) <= 0:
        raise ValueError("Finance Import outbox identity is invalid")
    return int(raw_value)


def _positive_integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("Finance Import outbox positive integer is invalid")
    return value


def _require_refund_return_reversal(connection, row_id, ledger_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 AS present FROM client_ledger_entries "
            "WHERE finance_import_row_id=%s AND entry_type='refund_reversal' "
            "AND reversal_of_entry_id=%s",
            (row_id, ledger_id),
        )
        if cursor.fetchone() is None:
            raise ValueError("refund_return_reversal_not_found")


def _mark_delivered(connection, event_id):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE finance_import_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (event_id,))
        if cursor.rowcount != 1:
            raise RuntimeError("finance_import_outbox_delivery_conflict")


def _mark_failed(connection, event, error):
    if not isinstance(event, dict) or "id" not in event:
        return None
    with connection.cursor() as cursor:
        cursor.execute("UPDATE finance_import_outbox SET status='failed',attempt_count=attempt_count+1,next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL 30 SECOND),last_error=%s WHERE id=%s", ((str(error) or "anomaly projection failed")[:1000], int(event["id"])))
    connection.commit()


def _aware_datetime(value):
    if not isinstance(value, datetime):
        raise ValueError("outbox created_at must be datetime")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _text_tuple(value):
    if not isinstance(value, list):
        raise ValueError("outbox identity collection must be array")
    return tuple(sorted(set(str(item) for item in value)))


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("outbox payload must be object")
    return payload

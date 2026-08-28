"""
File: finance_import_anomaly_consumer.py
Description: 投影 Finance row／source 警示；未具 owner 終態證據時禁止自動解除。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import FinanceManualReviewRootFact, RootFactEventOrigin
from domains.finance_import.source_warning_review import build_finance_source_review
from domains.finance_import.warning_review import (
    build_finance_row_warning_occurrence,
    build_finance_source_warning_occurrences,
)
from infrastructure.mysql.anomaly_root_fact_projection_repository import MySqlRootFactProjectionRepository
from shared_kernel.identities import CorrelationId
from subsystems.anomalies.finance_import_review_alert import (
    project_finance_import_review_alert,
)
from subsystems.anomalies.root_fact_projection_workflow import RootFactProjectionApplication
from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    WARNING_PROJECTION_RETRY_READY_SQL,
    warning_projection_error_code,
)

_OUTBOX_SELECT_SQL = (
    "SELECT id,intent_type,payload_snapshot,created_at FROM finance_import_outbox "
    "WHERE intent_type IN ('initial_classification_recorded','dispatch_completed',"
    "'manual_correction_completed','refund_return_review_recorded',"
    "'historical_reprocess_completed') AND status IN ('pending','failed') "
    f"AND attempt_count<{MAX_WARNING_PROJECTION_ATTEMPTS} "
    "AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) "
    "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
)


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
        if event.get("outbox_kind") == "source_review":
            _project_source_review_occurrences(connection, event)
        elif event["intent_type"] == "historical_reprocess_completed":
            _project_historical_reprocess_integrity(connection, event)
        else:
            application = _projection_application(connection)
            for root_fact in _root_facts(connection, event):
                correlation = CorrelationId(
                    f"finance-anomaly:{event['id']}:"
                    f"{root_fact.finance_import_row_id}"
                )
                application.project(root_fact, correlation)
                _project_warning_occurrence(connection, root_fact)
        _mark_delivered(connection, event)
        connection.commit()
        return True
    except Exception as error:
        connection.rollback()
        _mark_failed(connection, locals().get("event"), error)
        return False


def _claim_next_event(connection):
    source_review = _claim_next_source_review(connection)
    if source_review is not None:
        return source_review
    with connection.cursor() as cursor:
        cursor.execute(_OUTBOX_SELECT_SQL)
        event = cursor.fetchone()
    if event is not None:
        event["outbox_kind"] = "finance_event"
    return event


def _claim_next_source_review(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,review_id,'source_review_opened' AS intent_type,"
            "'source_review' AS outbox_kind,created_at "
            "FROM finance_import_source_review_outbox "
            "WHERE published_at IS NULL "
            f"AND attempts<{MAX_WARNING_PROJECTION_ATTEMPTS} "
            f"AND {WARNING_PROJECTION_RETRY_READY_SQL} "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _projection_application(connection):
    return RootFactProjectionApplication(default_anomaly_registry(), MySqlRootFactProjectionRepository(connection), BorrowedProjectionUnitOfWork)


def _project_historical_reprocess_integrity(connection, event) -> None:
    payload = _json_object(event["payload_snapshot"])
    batch_id = _prefixed_positive_integer(
        payload.get("batch_identity"),
        "finance-import-batch:",
    )
    event_id = _positive_integer(event["id"])
    with connection.cursor() as cursor:
        project_finance_import_review_alert(
            cursor,
            batch_id,
            source_version=event_id,
            source_event_identity=f"finance-import-historical-reprocess:{event_id}",
        )


def _root_facts(connection, event):
    payload = _json_object(event["payload_snapshot"])
    if event["intent_type"] == "initial_classification_recorded":
        return (_initial_classification_root_fact(event, payload),)
    if event["intent_type"] == "manual_correction_completed":
        return _manual_correction_root_facts(connection, event, payload)
    if event["intent_type"] == "refund_return_review_recorded":
        return (_refund_return_review_root_fact(event, payload),)
    return _dispatch_root_facts(event, payload)


def _project_warning_occurrence(connection, root_fact: FinanceManualReviewRootFact) -> None:
    if root_fact.definition_code != "finance_import_manual_review":
        return
    warning = build_finance_row_warning_occurrence(
        finance_import_row_id=root_fact.finance_import_row_id
    )
    if not root_fact.active:
        # A correction/dispatch event is evidence, not the owner terminal oracle.
        # The canonical alert remains guarded until a code-specific root predicate exists.
        return
    evidence = {
        "batch_id": root_fact.finance_import_batch_id,
        "domain_blocker_count": len(root_fact.domain_blockers),
        "reason_code_count": len(root_fact.reason_codes),
    }
    _append_warning_occurrence(
        connection,
        warning,
        source_kind="finance_import_row",
        source_receipt_identity=root_fact.source_event_identity,
        evidence=evidence,
    )


def _project_source_review_occurrences(connection, event) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT review_identity,source_content_digest,format_id,sheet_name,"
            "source_row,issue_codes FROM finance_import_source_reviews "
            "WHERE id=%s FOR UPDATE",
            (int(event["review_id"]),),
        )
        row = cursor.fetchone()
    if not isinstance(row, dict):
        raise RuntimeError("finance_source_review_root_missing")
    review = build_finance_source_review(
        source_content_digest=str(row["source_content_digest"]),
        format_id=str(row["format_id"]),
        sheet_name=str(row["sheet_name"]),
        source_row=int(row["source_row"]),
        issue_codes=_stored_text_tuple(row["issue_codes"]),
    )
    if review.review_identity != str(row["review_identity"]):
        raise RuntimeError("finance_source_review_identity_drift")
    evidence = {"format_id": review.format_id, "source_row": review.source_row}
    for warning in build_finance_source_warning_occurrences(review):
        _append_warning_occurrence(
            connection,
            warning,
            source_kind="finance_source_review",
            source_receipt_identity=review.review_identity,
            evidence=evidence,
        )


def _append_warning_occurrence(
    connection,
    warning,
    *,
    source_kind: str,
    source_receipt_identity: str,
    evidence,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT IGNORE INTO import_warning_occurrences "
            "(occurrence_identity,owning_lane,source_kind,source_event_identity,source_receipt_identity,logical_code,field_path,masked_subject,issue_codes,evidence_snapshot) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                warning.occurrence_identity,
                warning.owning_lane,
                source_kind,
                warning.source_event_identity,
                source_receipt_identity,
                warning.logical_code,
                warning.field_path,
                warning.masked_subject,
                _json(list(warning.issue_codes)),
                _json(evidence),
            ),
        )
        cursor.execute("SELECT id FROM import_warning_occurrences WHERE occurrence_identity=%s FOR UPDATE", (warning.occurrence_identity,))
        occurrence = cursor.fetchone()
        if occurrence is None:
            raise RuntimeError("finance_warning_occurrence_missing")
        occurrence_id = int(occurrence["id"])
        key = _identity("finance-warning-open", warning.occurrence_identity)
        cursor.execute(
            "INSERT IGNORE INTO import_warning_tracking_events "
            "(event_identity,occurrence_id,action,before_status,after_status,expected_version,resulting_version,actor_kind,actor_identity,reason_code,command_fingerprint,idempotency_key,correlation_id) "
            "VALUES (%s,%s,'opened',NULL,'open',0,1,'system','finance-import-projector','source_review_opened',%s,%s,%s)",
            (key, occurrence_id, _identity("finance-warning-fingerprint", warning.occurrence_identity), key, key),
        )
        cursor.execute("SELECT id FROM import_warning_tracking_events WHERE idempotency_key=%s", (key,))
        event = cursor.fetchone()
        if event is None:
            raise RuntimeError("finance_warning_open_event_missing")
        cursor.execute(
            "INSERT IGNORE INTO import_warning_current_tasks "
            "(occurrence_id,tracking_status,tracking_version,last_event_id) VALUES (%s,'open',1,%s)",
            (occurrence_id, int(event["id"])),
        )


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
            "SELECT bank_fact.id AS bank_row_id,bank_fact.transaction_date AS bank_transaction_date,"
            "bank_fact.debit AS bank_debit,bank_fact.credit AS bank_credit,"
            "bank_fact.direction AS bank_direction,bank_fact.currency AS bank_currency,"
            "COALESCE(classification.classification_type,bank_fact.classification_type) "
            "AS bank_classification_type,"
            "bank_fact.reconciliation_status AS bank_reconciliation_status,"
            "target.id AS target_entry_id,target.entry_type AS target_entry_type,"
            "target.case_no AS target_case_no,target.amount_ntd AS target_amount_ntd,"
            "reversal.id AS reversal_entry_id,reversal.entry_type AS reversal_entry_type,"
            "reversal.case_no AS reversal_case_no,reversal.amount_ntd AS reversal_amount_ntd,"
            "reversal.finance_import_row_id AS reversal_row_id,"
            "reversal.reversal_of_entry_id AS reversal_target_id "
            "FROM finance_import_rows AS bank_fact "
            "LEFT JOIN finance_import_classification_events AS classification "
            "ON classification.id=(SELECT MAX(latest.id) "
            "FROM finance_import_classification_events AS latest "
            "WHERE latest.finance_import_row_id=bank_fact.id) "
            "JOIN client_ledger_entries AS target "
            "ON target.id=%s AND target.entry_type='refund' "
            "JOIN client_ledger_entries AS reversal "
            "ON reversal.reversal_of_entry_id=target.id "
            "WHERE bank_fact.id=%s "
            "AND reversal.finance_import_row_id=%s "
            "AND reversal.entry_type='refund_reversal' FOR UPDATE",
            (ledger_id, row_id, row_id),
        )
        reversal = cursor.fetchone()
        if (
            not _is_exact_refund_return_reversal(reversal, row_id, ledger_id)
            or not _is_exact_refund_return_row(
                reversal,
                row_id,
                expected_amount_ntd=reversal.get("target_amount_ntd")
                if isinstance(reversal, Mapping)
                else None,
            )
        ):
            raise ValueError("refund_return_reversal_not_found")


def _is_exact_refund_return_row(row, row_id, *, expected_amount_ntd=None):
    if not isinstance(row, Mapping):
        return False
    required = {
        "bank_row_id",
        "bank_transaction_date",
        "bank_debit",
        "bank_credit",
        "bank_direction",
        "bank_currency",
        "bank_classification_type",
        "bank_reconciliation_status",
    }
    if not required.issubset(row):
        return False
    return (
        _is_positive_integer(row["bank_row_id"])
        and row["bank_row_id"] == row_id
        and row["bank_direction"] == "incoming"
        and _is_positive_integer_money(row["bank_credit"])
        and _is_zero_or_none(row["bank_debit"])
        and (
            expected_amount_ntd is None
            or (
                _is_positive_integer_money(expected_amount_ntd)
                and Decimal(str(row["bank_credit"]))
                == Decimal(str(expected_amount_ntd))
            )
        )
        and row["bank_classification_type"] == "client_refund_return"
        and row["bank_reconciliation_status"] == "reconciled"
        and row["bank_transaction_date"] is not None
        and _is_twd(row["bank_currency"])
    )


def _is_exact_refund_return_reversal(row, row_id, ledger_id):
    if not isinstance(row, Mapping):
        return False
    required = {
        "target_entry_id",
        "target_entry_type",
        "target_case_no",
        "target_amount_ntd",
        "reversal_entry_id",
        "reversal_entry_type",
        "reversal_case_no",
        "reversal_amount_ntd",
        "reversal_row_id",
        "reversal_target_id",
    }
    if not required.issubset(row):
        return False
    return (
        _is_positive_integer(row["target_entry_id"])
        and row["target_entry_id"] == ledger_id
        and row["target_entry_type"] == "refund"
        and _is_positive_integer(row["reversal_entry_id"])
        and row["reversal_entry_id"] != ledger_id
        and row["reversal_entry_type"] == "refund_reversal"
        and _is_positive_integer(row["reversal_row_id"])
        and row["reversal_row_id"] == row_id
        and _is_positive_integer(row["reversal_target_id"])
        and row["reversal_target_id"] == ledger_id
        and row["target_case_no"] == row["reversal_case_no"]
        and row["target_amount_ntd"] == row["reversal_amount_ntd"]
        and isinstance(row["target_case_no"], str)
        and bool(row["target_case_no"].strip())
        and isinstance(row["target_amount_ntd"], int)
        and not isinstance(row["target_amount_ntd"], bool)
        and row["target_amount_ntd"] > 0
    )


def _is_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_positive_integer_money(value):
    if isinstance(value, bool) or value is None:
        return False
    try:
        amount = Decimal(str(value))
        return amount > 0 and amount == amount.to_integral_value()
    except (InvalidOperation, ValueError, TypeError):
        return False


def _is_zero_or_none(value):
    if value is None:
        return True
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def _is_twd(value):
    return isinstance(value, str) and value.strip().upper() in {"TWD", "NTD"}


def _mark_delivered(connection, event):
    if event.get("outbox_kind") == "source_review":
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE finance_import_source_review_outbox "
                "SET published_at=CURRENT_TIMESTAMP,last_error=NULL "
                "WHERE id=%s AND published_at IS NULL",
                (int(event["id"]),),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("finance_source_review_delivery_conflict")
        return
    with connection.cursor() as cursor:
        cursor.execute("UPDATE finance_import_outbox SET status='delivered',delivered_at=CURRENT_TIMESTAMP,last_error=NULL WHERE id=%s AND status IN ('pending','failed')", (int(event["id"]),))
        if cursor.rowcount != 1:
            raise RuntimeError("finance_import_outbox_delivery_conflict")


def _mark_failed(connection, event, error):
    if not isinstance(event, dict) or "id" not in event:
        return None
    with connection.cursor() as cursor:
        message = warning_projection_error_code(error, owning_lane="finance_import")
        if event.get("outbox_kind") == "source_review":
            cursor.execute(
                "UPDATE finance_import_source_review_outbox SET attempts=attempts+1,"
                "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
                f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {WARNING_PROJECTION_RETRY_DELAY_SECONDS} SECOND)),"
                f"'terminal',attempts+1>={MAX_WARNING_PROJECTION_ATTEMPTS}) "
                "WHERE id=%s",
                (message, int(event["id"])),
            )
            connection.commit()
            return
        cursor.execute(
            "UPDATE finance_import_outbox SET status='failed',"
            "attempt_count=attempt_count+1,"
            f"next_attempt_at=DATE_ADD(CURRENT_TIMESTAMP,INTERVAL {WARNING_PROJECTION_RETRY_DELAY_SECONDS} SECOND),"
            "last_error=JSON_OBJECT('error_code',%s,'terminal',"
            f"attempt_count+1>={MAX_WARNING_PROJECTION_ATTEMPTS}) WHERE id=%s",
            (message, int(event["id"])),
        )
    connection.commit()


def _aware_datetime(value):
    if not isinstance(value, datetime):
        raise ValueError("outbox created_at must be datetime")
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _text_tuple(value):
    if not isinstance(value, list):
        raise ValueError("outbox identity collection must be array")
    return tuple(sorted(set(str(item) for item in value)))


def _stored_text_tuple(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("stored issue codes must be array")
    return tuple(sorted(set(str(item) for item in parsed)))


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("outbox payload must be object")
    return payload


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()

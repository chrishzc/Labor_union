"""MySQL source-scan and failed-outbox retry adapter for Anomalies."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Iterator

from pymysql.err import IntegrityError, OperationalError

from domains.anomalies.maintenance import (
    AnomalyDefinitionScanPage,
    ScanAnomalyDefinitionRequest,
)
from domains.anomalies.root_fact_projection import (
    FinanceManualReviewRootFact,
    RootFactEventOrigin,
)
from subsystems.anomalies.root_fact_projection_workflow import (
    ProjectionStorageUnavailable,
)

_SUPPORTED_DEFINITION = "finance_import_manual_review"
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_RETRYABLE_OUTBOX_TYPES = (
    "initial_classification_recorded",
    "dispatch_completed",
    "manual_correction_completed",
)


class MySqlAnomalyMaintenanceRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def scan_definition(self, request):
        if request.definition_code != _SUPPORTED_DEFINITION:
            raise ValueError("recovery_action_not_available")
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _FINANCE_REVIEW_SCAN_SQL,
                (request.after_source_id, request.maximum_items + 1),
            )
            rows = tuple(cursor.fetchall())
        selected_rows = rows[: request.maximum_items]
        next_cursor = _next_cursor(rows, selected_rows)
        return AnomalyDefinitionScanPage(
            tuple(_root_fact(row) for row in selected_rows),
            next_cursor,
        )

    def requeue_failed_projector_events(self, maximum_events):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _FAILED_OUTBOX_SELECT_SQL,
                (*_RETRYABLE_OUTBOX_TYPES, maximum_events),
            )
            event_ids = tuple(int(row["id"]) for row in cursor.fetchall())
            if not event_ids:
                return ()
            _requeue_events(cursor, event_ids)
        return event_ids


@contextmanager
def _cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except (OperationalError, IntegrityError) as error:
        code = int(error.args[0]) if error.args else 0
        retryable = code in _RETRYABLE_MYSQL_CODES or code == 1062
        raise ProjectionStorageUnavailable(
            "anomaly maintenance storage failure",
            retryable=retryable,
        ) from error


def _root_fact(row):
    disposition, integrity_blocker_active, active = _root_condition(row)
    return FinanceManualReviewRootFact(
        source_event_identity=(
            f"finance-import-classification-rescan:"
            f"{int(row['finance_import_row_id'])}:"
            f"{int(row['classification_version'])}:"
            f"{int(row['integrity_revision'])}"
        ),
        source_version=int(row["classification_version"]),
        origin=RootFactEventOrigin.HISTORICAL_RESCAN,
        occurred_at=_aware_datetime(row["created_at"]),
        finance_import_row_id=int(row["finance_import_row_id"]),
        finance_import_batch_id=int(row["batch_id"]),
        active=active,
        integrity_blocker_active=integrity_blocker_active,
        amount_delta_ntd=_integer_bank_amount(row),
        domain_blockers=_domain_blockers(disposition, active),
        reason_codes=_reason_codes(row["evidence"], disposition),
    )


def _requeue_events(cursor, event_ids):
    placeholders = ",".join("%s" for _ in event_ids)
    cursor.execute(
        "UPDATE finance_import_outbox SET status='pending',"
        "next_attempt_at=NULL WHERE status='failed' "
        f"AND id IN ({placeholders})",
        event_ids,
    )
    if int(cursor.rowcount) != len(event_ids):
        raise ProjectionStorageUnavailable(
            "failed projector outbox changed concurrently"
        )


def _root_condition(row):
    integrity_blocker_active = bool(row["integrity_blocker_active"])
    disposition = str(row["disposition"])
    active = (
        disposition in {"manual_review", "business_pending"}
        and not integrity_blocker_active
    )
    return disposition, integrity_blocker_active, active


def _domain_blockers(disposition, active):
    if not active:
        return ()
    if disposition == "manual_review":
        return ("classification_requires_review",)
    return ("classification_target_unresolved",)


def _reason_codes(value, disposition):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("anomaly_source_fact_invalid")
    if not all(isinstance(item, str) and item.strip() for item in parsed):
        raise ValueError("anomaly_source_fact_invalid")
    reasons = tuple(item.strip() for item in parsed)
    if not reasons:
        reasons = (f"classification_{disposition}",)
    return tuple(sorted(set(reasons)))[:20]


def _integer_bank_amount(row):
    amount = row["credit"] if row["credit"] is not None else row["debit"]
    if isinstance(amount, bool) or not isinstance(amount, (int, Decimal)):
        raise ValueError("anomaly_source_fact_invalid")
    integer_amount = int(amount)
    if integer_amount <= 0 or Decimal(integer_amount) != Decimal(amount):
        raise ValueError("anomaly_source_fact_invalid")
    return integer_amount


def _aware_datetime(value):
    if not isinstance(value, datetime):
        raise ValueError("anomaly_source_fact_invalid")
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _next_cursor(rows, selected_rows):
    if len(rows) <= len(selected_rows) or not selected_rows:
        return None
    return int(selected_rows[-1]["finance_import_row_id"])


_FINANCE_REVIEW_SCAN_SQL = (
    "SELECT classification.batch_id,classification.finance_import_row_id,"
    "classification.classification_version,classification.disposition,"
    "classification.evidence,classification.created_at,"
    "bank_fact.credit,bank_fact.debit,"
    "COALESCE((SELECT MAX(integrity_revision.id) "
    "FROM finance_import_integrity_events integrity_revision "
    "WHERE integrity_revision.batch_id=classification.batch_id "
    "AND (integrity_revision.finance_import_row_id IS NULL "
    "OR integrity_revision.finance_import_row_id="
    "classification.finance_import_row_id)),0) AS integrity_revision,"
    "EXISTS(SELECT 1 FROM finance_import_integrity_events integrity_event "
    "WHERE integrity_event.batch_id=classification.batch_id "
    "AND (integrity_event.finance_import_row_id IS NULL "
    "OR integrity_event.finance_import_row_id=classification.finance_import_row_id) "
    "AND integrity_event.id=(SELECT MAX(latest_integrity.id) "
    "FROM finance_import_integrity_events latest_integrity "
    "WHERE latest_integrity.batch_id=integrity_event.batch_id "
    "AND latest_integrity.finance_import_row_id<=>"
    "integrity_event.finance_import_row_id "
    "AND latest_integrity.issue_code=integrity_event.issue_code) "
    "AND integrity_event.active=1) AS integrity_blocker_active "
    "FROM finance_import_classification_events classification "
    "JOIN finance_import_rows bank_fact "
    "ON bank_fact.id=classification.finance_import_row_id "
    "WHERE classification.id=(SELECT MAX(latest.id) "
    "FROM finance_import_classification_events latest "
    "WHERE latest.finance_import_row_id=classification.finance_import_row_id) "
    "AND classification.finance_import_row_id>%s "
    "ORDER BY classification.finance_import_row_id LIMIT %s"
)
_FAILED_OUTBOX_SELECT_SQL = (
    "SELECT id FROM finance_import_outbox "
    "WHERE status='failed' AND intent_type IN (%s,%s,%s) "
    "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
)


__all__ = ["MySqlAnomalyMaintenanceRepository"]

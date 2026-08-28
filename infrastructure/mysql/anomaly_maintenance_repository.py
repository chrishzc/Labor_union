"""
File: anomaly_maintenance_repository.py
Description: 實作異常重掃描、死信查詢與具證據的人工重試 MySQL adapter。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
import re
from typing import Iterator

from pymysql.err import IntegrityError, OperationalError

from domains.anomalies.maintenance import (
    AnomalyReclassificationAlertIdentity,
    AnomalyReclassificationApplyRequest,
    AnomalyReclassificationCandidate,
    AnomalyReclassificationCursor,
    AnomalyReclassificationCursorPageRequest,
    AnomalyReclassificationDisposition,
    AnomalyReclassificationPage,
    AnomalyReclassificationReceipt,
    AnomalyReclassificationResult,
    AnomalyReclassificationBlockedItem,
    AnomalyDefinitionScanPage,
    ProjectorDeadLetter,
    ProjectorDeadLetterIdentity,
    ProjectorDeadLetterSuccessor,
    RetryProjectorDeadLetterReceipt,
    SupersedeProjectorDeadLetterReceipt,
    ScanAnomalyDefinitionRequest,
)
from domains.anomalies.root_fact_projection import (
    FinanceManualReviewRootFact,
    RootFactEventOrigin,
)
from shared_kernel.fingerprints import PreviewFingerprint
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
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
_DEAD_LETTER_COMMAND_FAMILY = "anomaly_projector_dead_letter_retry/v1"
_DEAD_LETTER_SUPERSEDE_COMMAND_FAMILY = (
    "anomaly_projector_dead_letter_supersede/v1"
)
_DEAD_LETTER_SOURCES = {
    "government_overpayment": (
        "government_subsidy_outbox",
        (
            "government_subsidy_overpayment_established",
            "government_subsidy_overpayment_offset",
            "government_overpayment_return_payable",
        ),
    ),
    "client_over_refund_recovery": (
        "client_finance_outbox",
        (
            "projection_refresh",
            "client_over_refund_recovery_matched",
            "client_over_refund_recovery_collected",
        ),
    ),
    "staff_overpayment_recovery": (
        "staff_payables_outbox",
        (
            "staff_overpayment_recovery_updated",
            "staff_overpayment_recovery_matched",
            "staff_overpayment_recovery_collected",
        ),
    ),
}


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

    def query_reclassification_alerts(
        self,
        request: AnomalyReclassificationCursorPageRequest,
        *,
        eligible_definitions=None,
    ) -> AnomalyReclassificationPage:
        """Read the deterministic active-alert page without changing state."""
        if not isinstance(request, AnomalyReclassificationCursorPageRequest):
            raise TypeError("reclassification page request is invalid")
        definitions = _eligible_definitions(eligible_definitions)
        after = request.after
        after_definition = after.definition_code if after else ""
        after_source = after.source_identity if after else ""
        placeholders = ",".join("%s" for _ in definitions)
        sql = _RECLASSIFICATION_ALERT_PAGE_SQL.format(
            definition_placeholders=placeholders
        )
        with _cursor(self._connection) as cursor:
            cursor.execute(
                sql,
                (
                    *definitions,
                    after_definition,
                    after_definition,
                    after_source,
                    request.maximum_items + 1,
                ),
            )
            rows = tuple(cursor.fetchall())
        selected = rows[: request.maximum_items]
        next_cursor = (
            AnomalyReclassificationCursor(
                str(selected[-1]["definition_code"]),
                str(selected[-1]["source_identity"]),
            )
            if len(rows) > len(selected) and selected
            else None
        )
        return AnomalyReclassificationPage(
            tuple(_reclassification_alert(row) for row in selected),
            next_cursor,
        )

    # Query port aliases keep the adapter compatible with migration-runner
    # vocabulary while preserving one read implementation.
    query_reclassification_page = query_reclassification_alerts
    query_reclassification_candidates = query_reclassification_alerts
    query_reclassification = query_reclassification_alerts

    def load_reclassification_alert(
        self, alert, *, for_update: bool
    ) -> AnomalyReclassificationAlertIdentity | None:
        """Fresh-read and optionally lock the exact current alert identity."""
        if not isinstance(alert, AnomalyReclassificationAlertIdentity):
            raise TypeError("reclassification alert is invalid")
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _RECLASSIFICATION_ALERT_SELECT_SQL + suffix,
                (alert.alert_fingerprint.value,),
            )
            row = cursor.fetchone()
        if row is None or not bool(row["predicate_active"]):
            return None
        current = _reclassification_alert(row)
        if (
            current.definition_code != alert.definition_code
            or current.source_identity != alert.source_identity
            or current.source_version != alert.source_version
            or current.workflow_version != alert.workflow_version
        ):
            raise ValueError("anomaly_reclassification_alert_stale")
        return current

    load_reclassification_context = load_reclassification_alert
    load_reclassification = load_reclassification_alert

    def find_reclassification_receipt(self, key, *, for_update: bool = False):
        """Return the stored preview fingerprint and immutable receipt for replay."""
        key_value = key.value if hasattr(key, "value") else key
        if not isinstance(key_value, str) or not key_value.strip():
            raise ValueError("reclassification idempotency key is invalid")
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _RECLASSIFICATION_RECEIPT_SELECT_SQL + suffix,
                (key_value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return PreviewFingerprint(str(row["preview_fingerprint"])), _reclassification_receipt(row)

    find_receipt = find_reclassification_receipt

    def persist_reclassification(
        self,
        request: AnomalyReclassificationApplyRequest,
        candidate: AnomalyReclassificationCandidate | None = None,
        receipt: AnomalyReclassificationReceipt | None = None,
        command_fingerprint: PreviewFingerprint | None = None,
    ) -> AnomalyReclassificationReceipt:
        """Append disposition/event/receipt and deactivate the alert in caller UoW."""
        if not isinstance(request, AnomalyReclassificationApplyRequest):
            raise TypeError("reclassification request is invalid")
        if isinstance(candidate, AnomalyReclassificationReceipt) and receipt is None:
            receipt, candidate = candidate, None
        if candidate is not None and not isinstance(candidate, AnomalyReclassificationCandidate):
            raise TypeError("reclassification candidate is invalid")
        if candidate is not None and candidate.fingerprint != request.preview_fingerprint:
            raise ValueError("anomaly_reclassification_preview_stale")
        if candidate is not None and candidate.disposition_identity != request.disposition_identity:
            raise ValueError("anomaly_reclassification_disposition_identity_mismatch")
        if receipt is not None and not isinstance(receipt, AnomalyReclassificationReceipt):
            raise TypeError("reclassification receipt is invalid")
        if command_fingerprint is not None and not isinstance(
            command_fingerprint, PreviewFingerprint
        ):
            raise TypeError("reclassification command fingerprint is invalid")
        alert = self.load_reclassification_alert(request.alert, for_update=True)
        if alert is None:
            raise ValueError("anomaly_reclassification_alert_not_found")
        now = _utc_now()
        before_fingerprint = _reclassification_state_fingerprint(alert, active=True)
        after_fingerprint = _reclassification_after_fingerprint(alert, request)
        disposition_id = self._insert_reclassification_disposition(request)
        workflow_event_id = self._deactivate_reclassification_alert(request, alert, now)
        receipt_identity = f"anomaly-reclassification-receipt:{request.idempotency_key.value}"
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO anomaly_reclassification_receipts "
                "(receipt_identity,disposition_id,workflow_event_id,before_state_fingerprint,"
                "after_state_fingerprint,before_workflow_version,after_workflow_version,"
                "result_snapshot,correlation_id,created_at) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    receipt_identity,
                    disposition_id,
                    workflow_event_id,
                    before_fingerprint.value,
                    after_fingerprint.value,
                    alert.workflow_version,
                    alert.workflow_version + 1,
                    _json_dump({
                        "disposition": request.disposition.value,
                        "definition_code": alert.definition_code,
                        "source_identity": alert.source_identity,
                        "target_domain": (
                            request.target.target_domain if request.target else None
                        ),
                        "target_reference": (
                            request.target.target_reference if request.target else None
                        ),
                        "target_version": (
                            request.target.target_version if request.target else None
                        ),
                        "reason": request.reason,
                        "evidence_reference": request.evidence_reference,
                    }),
                    request.correlation_id.value,
                    now,
                ),
            )
        return AnomalyReclassificationReceipt(
            request.disposition_identity,
            receipt_identity,
            request.disposition,
            request.alert,
            request.preview_fingerprint,
            request.idempotency_key,
            request.correlation_id,
            request.actor,
            now,
            workflow_event_id,
            alert.workflow_version + 1,
            before_fingerprint,
            after_fingerprint,
        )

    apply_reclassification = persist_reclassification
    save_reclassification = persist_reclassification
    persist_disposition = persist_reclassification
    persist = persist_reclassification

    def create_reclassification_savepoint(self, name="anm_reclass_item") -> None:
        _execute_savepoint(self._connection, "SAVEPOINT", name)

    def rollback_reclassification_savepoint(self, name="anm_reclass_item") -> None:
        _execute_savepoint(self._connection, "ROLLBACK TO SAVEPOINT", name)

    def release_reclassification_savepoint(self, name="anm_reclass_item") -> None:
        _execute_savepoint(self._connection, "RELEASE SAVEPOINT", name)

    def _insert_reclassification_disposition(self, request) -> int:
        target = request.target
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO anomaly_reclassification_dispositions "
                "(disposition_identity,alert_fingerprint,definition_code,disposition,"
                "source_identity,source_version,expected_workflow_version,target_domain,"
                "target_reference,target_version,actor,reason,evidence_reference,"
                "rulebook_reference,release_evidence_reference,preview_fingerprint,"
                "idempotency_key,correlation_id) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    request.disposition_identity,
                    request.alert.alert_fingerprint.value,
                    request.alert.definition_code,
                    request.disposition.value,
                    request.alert.source_identity,
                    request.alert.source_version,
                    request.alert.workflow_version,
                    target.target_domain if target else None,
                    target.target_reference if target else None,
                    target.target_version if target else None,
                    request.actor.actor_id,
                    request.reason,
                    request.evidence_reference,
                    request.rulebook_reference,
                    request.release_evidence_reference,
                    request.preview_fingerprint.value,
                    request.idempotency_key.value,
                    request.correlation_id.value,
                ),
            )
            return int(cursor.lastrowid)

    def _deactivate_reclassification_alert(self, request, alert, created_at) -> int:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "UPDATE anomaly_current_alerts SET predicate_active=0,"
                "workflow_status='resolved',workflow_version=%s,resolved_by=%s,"
                "resolved_at=%s WHERE fingerprint=%s AND predicate_active=1 "
                "AND workflow_version=%s",
                (
                    alert.workflow_version + 1,
                    request.actor.actor_id,
                    created_at,
                    alert.alert_fingerprint.value,
                    alert.workflow_version,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise ValueError("anomaly_reclassification_alert_stale")
            cursor.execute(
                "INSERT INTO anomaly_workflow_events "
                "(alert_fingerprint,action,expected_workflow_version,"
                "resulting_workflow_version,actor,reason,correlation_id,idempotency_key) "
                "VALUES (%s,'auto_resolve',%s,%s,%s,%s,%s,%s)",
                (
                    alert.alert_fingerprint.value,
                    alert.workflow_version,
                    alert.workflow_version + 1,
                    request.actor.actor_id,
                    request.reason,
                    request.correlation_id.value,
                    request.idempotency_key.value,
                ),
            )
            return int(cursor.lastrowid)

    def find_reclassification_batch_receipt(self, key, *, for_update: bool = False):
        key_value = key.value if hasattr(key, "value") else key
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT request_fingerprint,batch_receipt_identity,operation_identity,"
                "eligible_codes,eligible_codes_fingerprint,cursor_definition_code,"
                "cursor_source_identity,next_cursor_definition_code,next_cursor_source_identity,"
                "batch_size,scanned_count,applied_count,blocked_count,blocked_items,status "
                "FROM anomaly_reclassification_batch_receipts WHERE idempotency_key=%s" + suffix,
                (key_value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return PreviewFingerprint(str(row["request_fingerprint"])), _batch_result(row)

    load_reclassification_batch_receipt = find_reclassification_batch_receipt
    find_batch_receipt = find_reclassification_batch_receipt

    def save_reclassification_batch_receipt(
        self,
        request=None,
        result: AnomalyReclassificationResult | None = None,
        before_fingerprints=(),
        after_fingerprints=(),
        *,
        operation_identity: str | None = None,
        request_fingerprint: PreviewFingerprint | None = None,
        actor=None,
        correlation_id=None,
    ) -> str:
        """Persist one append-only bounded-run receipt; no commit is performed."""
        if result is None or not isinstance(result, AnomalyReclassificationResult):
            raise TypeError("reclassification batch result is invalid")
        if request is None or not hasattr(request, "maximum_items"):
            raise TypeError("reclassification batch request is invalid")
        operation_identity = operation_identity or getattr(request, "operation_identity", None)
        request_fingerprint = request_fingerprint or getattr(request, "request_fingerprint", None)
        actor = actor or getattr(request, "actor", None)
        correlation_id = correlation_id or getattr(request, "correlation_id", None)
        if not isinstance(operation_identity, str) or not operation_identity.strip():
            raise ValueError("reclassification operation identity is invalid")
        if not isinstance(request_fingerprint, PreviewFingerprint):
            raise TypeError("reclassification batch request fingerprint is invalid")
        if not hasattr(actor, "actor_id") or not hasattr(correlation_id, "value"):
            raise TypeError("reclassification batch actor or correlation is invalid")
        cursor = getattr(request, "cursor", getattr(request, "after", None))
        next_cursor = result.next_cursor
        eligible_codes = _batch_eligible_codes(request)
        eligible_codes_fingerprint = getattr(request, "eligible_codes_fingerprint", None)
        if eligible_codes_fingerprint is None:
            from shared_kernel.fingerprints import fingerprint_payload

            eligible_codes_fingerprint = fingerprint_payload(
                {"eligible_codes": eligible_codes}
            )
        if not isinstance(eligible_codes_fingerprint, PreviewFingerprint):
            raise TypeError("reclassification eligible codes fingerprint is invalid")
        key = _batch_idempotency_key(operation_identity, request, request_fingerprint)
        receipt_identity = f"anomaly-reclassification-batch:{key}"
        idempotency_key = getattr(request, "idempotency_key", None)
        idempotency_value = (
            idempotency_key.value
            if hasattr(idempotency_key, "value")
            else _batch_idempotency_key(operation_identity, request, request_fingerprint)
        )
        with _cursor(self._connection) as db_cursor:
            db_cursor.execute(
                "INSERT INTO anomaly_reclassification_batch_receipts "
                "(batch_receipt_identity,operation_identity,idempotency_key,request_fingerprint,"
                "actor,correlation_id,eligible_codes,eligible_codes_fingerprint,cursor_definition_code,"
                "cursor_source_identity,next_cursor_definition_code,next_cursor_source_identity,"
                "batch_size,scanned_count,applied_count,blocked_count,before_fingerprints,"
                "after_fingerprints,blocked_items,status) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    receipt_identity,
                    operation_identity,
                    idempotency_value,
                    request_fingerprint.value,
                    actor.actor_id,
                    correlation_id.value,
                    _json_dump(list(eligible_codes)),
                    eligible_codes_fingerprint.value,
                    cursor.definition_code if cursor else "",
                    cursor.source_identity if cursor else "",
                    next_cursor.definition_code if next_cursor else None,
                    next_cursor.source_identity if next_cursor else None,
                    request.maximum_items,
                    result.scanned_count,
                    result.applied_count,
                    result.blocked_count,
                    _json_dump(_fingerprint_values(before_fingerprints)),
                    _json_dump(_fingerprint_values(after_fingerprints)),
                    _json_dump([
                        {
                            "definition_code": item.definition_code,
                            "source_identity": item.source_identity,
                            "reason": item.reason,
                            "alert_fingerprint": item.alert_fingerprint.value
                            if item.alert_fingerprint else None,
                        }
                        for item in result.blocked_items
                    ]),
                    "completed" if result.completed else "blocked" if result.blocked_items else "in_progress",
                ),
            )
        return receipt_identity

    save_batch_receipt = save_reclassification_batch_receipt

    def query_dead_letters(self, maximum_items):
        if isinstance(maximum_items, bool) or not isinstance(maximum_items, int):
            raise ValueError("bounded operation size is invalid")
        if not 1 <= maximum_items <= 100:
            raise ValueError("bounded operation size exceeds maximum")
        result = []
        with _cursor(self._connection) as cursor:
            for projector_identity, (table, intent_types) in _DEAD_LETTER_SOURCES.items():
                placeholders = ",".join("%s" for _ in intent_types)
                cursor.execute(
                    "SELECT id,intent_type,attempt_count,last_error,updated_at "
                    f"FROM {table} WHERE status='failed' AND attempt_count>=3 "
                    f"AND intent_type IN ({placeholders}) ORDER BY id LIMIT %s",
                    (*intent_types, maximum_items),
                )
                result.extend(
                    _dead_letter(projector_identity, row) for row in cursor.fetchall()
                )
        visible = tuple(
            item
            for item in result
            if not self._dead_letter_has_supersede_receipt(item.identity)
        )
        enriched = tuple(
            self.load_dead_letter_with_successor(item.identity, for_update=False)
            or item
            for item in visible
        )
        return tuple(sorted(
            enriched,
            key=lambda item: (item.failed_at, item.identity.projector_identity, item.identity.event_id),
        )[:maximum_items])

    def load_dead_letter(self, identity, *, for_update):
        if self._dead_letter_has_supersede_receipt(identity, for_update=for_update):
            return None
        return self._load_dead_letter_row(identity, for_update=for_update)

    def _load_dead_letter_row(self, identity, *, for_update):
        table, intent_types = _dead_letter_source(identity.projector_identity)
        placeholders = ",".join("%s" for _ in intent_types)
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id,intent_type,attempt_count,last_error,updated_at "
                f"FROM {table} WHERE id=%s AND status='failed' AND attempt_count>=3 "
                f"AND intent_type IN ({placeholders})" + suffix,
                (identity.event_id, *intent_types),
            )
            row = cursor.fetchone()
        return None if row is None else _dead_letter(identity.projector_identity, row)

    def load_dead_letter_with_successor(self, identity, *, for_update):
        if self._dead_letter_has_supersede_receipt(identity, for_update=for_update):
            return None
        dead_letter = self._load_dead_letter_row(identity, for_update=for_update)
        if dead_letter is None:
            return None
        successor = self._load_verified_successor(identity, for_update=for_update)
        return ProjectorDeadLetter(
            dead_letter.identity,
            dead_letter.intent_type,
            dead_letter.attempt_count,
            dead_letter.error_code,
            dead_letter.failed_at,
            successor,
        )

    def requeue_dead_letter(self, dead_letter):
        table, _ = _dead_letter_source(dead_letter.identity.projector_identity)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                f"UPDATE {table} SET status='pending',attempt_count=0,"
                "next_attempt_at=NULL,last_error=NULL,delivered_at=NULL "
                "WHERE id=%s AND status='failed' AND attempt_count=%s",
                (dead_letter.identity.event_id, dead_letter.attempt_count),
            )
            if int(cursor.rowcount) != 1:
                raise ValueError("projector_dead_letter_stale")

    def load_dead_letter_retry_receipt(self, key, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s" + suffix,
                (_DEAD_LETTER_COMMAND_FAMILY, key),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = json.loads(row["result_snapshot"]) if isinstance(row["result_snapshot"], str) else row["result_snapshot"]
        if not isinstance(payload, dict):
            raise ValueError("projector_dead_letter_receipt_invalid")
        receipt = RetryProjectorDeadLetterReceipt(
            ProjectorDeadLetterIdentity(
                str(payload["projector_identity"]), int(payload["event_id"])
            ),
            int(payload["prior_attempt_count"]),
            str(payload["resulting_status"]),
            str(payload["receipt_identity"]),
        )
        return PreviewFingerprint(str(row["request_fingerprint"])), receipt

    def save_dead_letter_retry_receipt(self, request, fingerprint, receipt):
        result = {
            "projector_identity": receipt.identity.projector_identity,
            "event_id": receipt.identity.event_id,
            "prior_attempt_count": receipt.prior_attempt_count,
            "resulting_status": receipt.resulting_status,
            "receipt_identity": receipt.receipt_identity,
            "evidence_reference": request.evidence_reference,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    _DEAD_LETTER_COMMAND_FAMILY,
                    request.idempotency_key.value,
                    fingerprint.value,
                    request.preview_fingerprint.value,
                    request.actor.actor_id,
                    request.reason,
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                ),
            )

    def load_dead_letter_supersede_receipt(self, key, *, for_update):
        row = self._load_command_receipt(
            _DEAD_LETTER_SUPERSEDE_COMMAND_FAMILY, key, for_update=for_update
        )
        if row is None:
            return None
        payload = _receipt_payload(row)
        receipt = SupersedeProjectorDeadLetterReceipt(
            ProjectorDeadLetterIdentity(
                str(payload["projector_identity"]), int(payload["event_id"])
            ),
            int(payload["successor_event_id"]),
            int(payload["successor_source_version"]),
            str(payload["resulting_status"]),
            str(payload["receipt_identity"]),
        )
        return PreviewFingerprint(str(row["request_fingerprint"])), receipt

    def save_dead_letter_supersede_receipt(self, request, fingerprint, receipt):
        result = {
            "projector_identity": receipt.identity.projector_identity,
            "event_id": receipt.identity.event_id,
            "successor_event_id": receipt.successor_event_id,
            "successor_source_version": receipt.successor_source_version,
            "resulting_status": receipt.resulting_status,
            "receipt_identity": receipt.receipt_identity,
            "evidence_reference": request.evidence_reference,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    _DEAD_LETTER_SUPERSEDE_COMMAND_FAMILY,
                    request.idempotency_key.value,
                    fingerprint.value,
                    request.preview_fingerprint.value,
                    request.actor.actor_id,
                    request.reason,
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                ),
            )

    def _load_command_receipt(self, family, key, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s" + suffix,
                (family, key),
            )
            return cursor.fetchone()

    def _dead_letter_has_supersede_receipt(self, identity, *, for_update=False):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id FROM admin_command_receipts WHERE command_family=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.projector_identity'))=%s "
                "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.event_id')) AS UNSIGNED)=%s "
                "LIMIT 1" + suffix,
                (
                    _DEAD_LETTER_SUPERSEDE_COMMAND_FAMILY,
                    identity.projector_identity,
                    identity.event_id,
                ),
            )
            return cursor.fetchone() is not None

    def _load_verified_successor(self, identity, *, for_update):
        table, intent_types = _dead_letter_source(identity.projector_identity)
        payload_key = _owner_payload_key(identity.projector_identity)
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT payload_snapshot FROM " + table + " WHERE id=%s" + suffix,
                (identity.event_id,),
            )
            original = cursor.fetchone()
        if original is None:
            return None
        owner_identity = _payload_identity(original["payload_snapshot"], payload_key)
        placeholders = ",".join("%s" for _ in intent_types)
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id,intent_type,payload_snapshot FROM " + table
                + " WHERE id>%s AND status='delivered' AND intent_type IN ("
                + placeholders
                + ") AND JSON_UNQUOTE(JSON_EXTRACT(payload_snapshot,%s))=%s "
                "ORDER BY id DESC LIMIT 1" + suffix,
                (
                    identity.event_id,
                    *intent_types,
                    f"$.{payload_key}",
                    owner_identity,
                ),
            )
            successor = cursor.fetchone()
        if successor is None:
            return None
        successor_id = int(successor["id"])
        return self._verify_successor_projection(
            identity.projector_identity,
            owner_identity,
            successor_id,
            for_update=for_update,
        )

    def _verify_successor_projection(
        self, projector_identity, owner_identity, successor_id, *, for_update
    ):
        definition_code, source_prefix = _projection_identity(projector_identity)
        source_identity = f"{source_prefix}{owner_identity}"
        source_event_identity = _source_event_identity(
            projector_identity, owner_identity, successor_id
        )
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT receipt.source_version receipt_source_version,"
                "receipt.alert_fingerprint,receipt.predicate_active receipt_predicate_active,"
                "current.source_identity,current.source_version,current.predicate_active,"
                "current.display_snapshot,snapshot.source_event_identity "
                "FROM anomaly_root_fact_projection_receipts receipt "
                "JOIN anomaly_current_alerts current "
                "ON current.fingerprint=receipt.alert_fingerprint "
                "JOIN anomaly_root_fact_snapshots snapshot "
                "ON snapshot.alert_fingerprint=current.fingerprint "
                "WHERE receipt.source_event_identity=%s "
                "AND current.definition_code=%s AND current.source_identity=%s"
                + suffix,
                (source_event_identity, definition_code, source_identity),
            )
            projection = cursor.fetchone()
        if projection is None:
            return None
        if (
            int(projection["receipt_source_version"]) != successor_id
            or int(projection["source_version"]) != successor_id
            or str(projection["source_event_identity"]) != source_event_identity
            or bool(projection["receipt_predicate_active"])
            != bool(projection["predicate_active"])
        ):
            return None
        snapshot = _json_object(projection["display_snapshot"])
        bindings = snapshot.get("recovery_bindings")
        if not isinstance(bindings, dict):
            return None
        if not self._owner_root_matches(
            projector_identity,
            owner_identity,
            bindings,
            snapshot,
            bool(projection["predicate_active"]),
            for_update=for_update,
        ):
            return None
        return ProjectorDeadLetterSuccessor(
            successor_id,
            successor_id,
            PreviewFingerprint(str(projection["alert_fingerprint"])),
            bool(projection["predicate_active"]),
        )

    def _owner_root_matches(
        self,
        projector_identity,
        owner_identity,
        bindings,
        snapshot,
        predicate_active,
        *,
        for_update,
    ):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            if projector_identity == "government_overpayment":
                cursor.execute(
                    "SELECT projection_version,status,remaining_amount_ntd "
                    "FROM government_subsidy_overpayments "
                    "WHERE overpayment_identity=%s" + suffix,
                    (owner_identity,),
                )
            elif projector_identity == "client_over_refund_recovery":
                cursor.execute(
                    "SELECT recovery.projection_version,recovery.status,"
                    "recovery.amount_due_ntd remaining_amount_ntd,"
                    "recovery.case_no,account.aggregate_version account_version "
                    "FROM client_over_refund_recoveries recovery "
                    "LEFT JOIN client_finance_accounts account "
                    "ON account.case_no=recovery.case_no "
                    "WHERE recovery.recovery_identity=%s" + suffix,
                    (owner_identity,),
                )
            elif projector_identity == "staff_overpayment_recovery":
                cursor.execute(
                    "SELECT recovery.aggregate_version projection_version,"
                    "recovery.status,recovery.remaining_amount_ntd,"
                    "recovery.staff_id,account.aggregate_version staff_payables_version "
                    "FROM staff_overpayment_recoveries recovery "
                    "LEFT JOIN staff_payable_accounts account "
                    "ON account.staff_id=recovery.staff_id "
                    "WHERE recovery.recovery_identity=%s" + suffix,
                    (owner_identity,),
                )
            else:
                raise ValueError("projector_identity_not_supported")
            owner = cursor.fetchone()
        if owner is None:
            return False
        if "matching_identity" in bindings:
            matching_identity = bindings.get("matching_identity")
            if not isinstance(matching_identity, str) or not matching_identity:
                return False
            with _cursor(self._connection) as cursor:
                if projector_identity == "client_over_refund_recovery":
                    cursor.execute(
                        "SELECT recovery_identity,matching_version FROM "
                        "client_over_refund_recovery_matchings "
                        "WHERE matching_identity=%s" + suffix,
                        (matching_identity,),
                    )
                elif projector_identity == "staff_overpayment_recovery":
                    cursor.execute(
                        "SELECT recovery_identity,matching_version,staff_id FROM "
                        "staff_overpayment_recovery_matchings "
                        "WHERE matching_identity=%s" + suffix,
                        (matching_identity,),
                    )
                else:
                    return False
                matching = cursor.fetchone()
            if matching is None or not _matching_projection_equivalent(
                projector_identity,
                owner_identity,
                matching,
                bindings,
            ):
                return False
        return _owner_projection_equivalent(
            projector_identity,
            owner_identity,
            owner,
            bindings,
            snapshot,
            predicate_active,
        )


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


def _dead_letter_source(projector_identity):
    source = _DEAD_LETTER_SOURCES.get(projector_identity)
    if source is None:
        raise ValueError("projector_identity_not_supported")
    return source


def _reclassification_alert(row):
    return AnomalyReclassificationAlertIdentity(
        PreviewFingerprint(str(row["fingerprint"])),
        str(row["definition_code"]),
        str(row["source_identity"]),
        int(row["source_version"]),
        int(row["workflow_version"]),
    )


def _reclassification_after_fingerprint(alert, request):
    # The resulting state fingerprint is deliberately derived from the exact
    # locked state and command payload; it is not a replacement for the alert
    # fingerprint and never mutates the source/root history.
    target = request.target
    from shared_kernel.fingerprints import fingerprint_payload

    return fingerprint_payload({
        "alert_fingerprint": alert.alert_fingerprint.value,
        "predicate_active": False,
        "workflow_version": alert.workflow_version + 1,
        "disposition": request.disposition.value,
        "target_domain": target.target_domain if target else None,
        "target_reference": target.target_reference if target else None,
        "target_version": target.target_version if target else None,
    })


def _reclassification_state_fingerprint(alert, *, active):
    from shared_kernel.fingerprints import fingerprint_payload

    return fingerprint_payload({
        "alert_fingerprint": alert.alert_fingerprint.value,
        "definition_code": alert.definition_code,
        "source_identity": alert.source_identity,
        "source_version": alert.source_version,
        "workflow_version": alert.workflow_version,
        "predicate_active": active,
    })


def _eligible_definitions(values):
    if isinstance(values, str) or values is None:
        raise TypeError("eligible anomaly definitions must be an explicit collection")
    is_set = isinstance(values, (set, frozenset))
    try:
        values = tuple(values)
    except TypeError as error:
        raise TypeError("eligible anomaly definitions must be an explicit collection") from error
    if not values or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("eligible anomaly definitions are invalid")
    normalized = tuple(sorted(set(values)))
    if not is_set and normalized != values:
        raise ValueError("eligible anomaly definitions must be sorted and unique")
    return normalized


def _execute_savepoint(connection, operation, name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,30}", name):
        raise ValueError("reclassification savepoint name is invalid")
    if operation not in {"SAVEPOINT", "ROLLBACK TO SAVEPOINT", "RELEASE SAVEPOINT"}:
        raise ValueError("reclassification savepoint operation is invalid")
    with _cursor(connection) as cursor:
        cursor.execute(f"{operation} `{name}`")


def _batch_definition_code(request, result):
    cursor = getattr(request, "cursor", getattr(request, "after", None))
    eligible = getattr(request, "eligible_codes", None)
    if eligible is not None:
        definitions = _eligible_definitions(eligible)
        if cursor is not None and cursor.definition_code not in definitions:
            raise ValueError("reclassification batch cursor definition is ineligible")
        if result.next_cursor is not None and result.next_cursor.definition_code not in definitions:
            raise ValueError("reclassification batch next cursor definition is ineligible")
        if cursor is not None:
            return cursor.definition_code
        if result.next_cursor is not None:
            return result.next_cursor.definition_code
        if result.blocked_items:
            return result.blocked_items[0].definition_code
        return definitions[0]
    if cursor is not None:
        return cursor.definition_code
    if result.next_cursor is not None:
        return result.next_cursor.definition_code
    if result.blocked_items:
        definitions = {item.definition_code for item in result.blocked_items}
        if len(definitions) == 1:
            return next(iter(definitions))
    raise ValueError("reclassification batch cursor definition is unavailable")


def _batch_eligible_codes(request):
    values = getattr(request, "eligible_codes", None)
    if values is None:
        values = getattr(request, "eligible_definitions", None)
    if values is None:
        raise ValueError("reclassification eligible definitions are unavailable")
    return _eligible_definitions(values)


def _batch_idempotency_key(operation_identity, request, request_fingerprint):
    from hashlib import sha256

    cursor = getattr(request, "cursor", getattr(request, "after", None))
    payload = "\x1f".join(
        (
            operation_identity,
            cursor.definition_code if cursor else "",
            cursor.source_identity if cursor else "",
            request_fingerprint.value,
        )
    )
    return "anomaly-reclassification-batch-key:" + sha256(
        payload.encode("utf-8")
    ).hexdigest()


def _reclassification_receipt(row):
    payload = _json_object(row["result_snapshot"])
    target = None
    if payload.get("target_domain") is not None:
        from domains.anomalies.maintenance import AnomalyReclassificationTargetBinding

        target = AnomalyReclassificationTargetBinding(
            str(payload["target_domain"]),
            str(payload["target_reference"]),
            int(payload["target_version"]),
        )
    disposition = AnomalyReclassificationDisposition(str(row["disposition"]))
    alert = AnomalyReclassificationAlertIdentity(
        PreviewFingerprint(str(row["alert_fingerprint"])),
        str(row["definition_code"]),
        str(row["source_identity"]),
        int(row["source_version"]),
        int(row["before_workflow_version"]),
    )
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey

    return AnomalyReclassificationReceipt(
        str(row["disposition_identity"]),
        str(row["receipt_identity"]),
        disposition,
        alert,
        PreviewFingerprint(str(row["preview_fingerprint"])),
        IdempotencyKey(str(row["idempotency_key"])),
        CorrelationId(str(row["correlation_id"])),
        ActorContext(str(row["actor"])),
        _aware_datetime(row["created_at"]),
        int(row["workflow_event_id"]),
        int(row["after_workflow_version"]),
        PreviewFingerprint(str(row["before_state_fingerprint"])),
        PreviewFingerprint(str(row["after_state_fingerprint"])),
    )


def _batch_result(row):
    blocked_payload = _json_object_list(row["blocked_items"])
    blocked = tuple(
        AnomalyReclassificationBlockedItem(
            str(item["definition_code"]),
            str(item["source_identity"]),
            str(item["reason"]),
            PreviewFingerprint(str(item["alert_fingerprint"]))
            if item.get("alert_fingerprint")
            else None,
        )
        for item in blocked_payload
    )
    next_definition = row.get("next_cursor_definition_code")
    next_source = row.get("next_cursor_source_identity")
    next_cursor = (
        AnomalyReclassificationCursor(str(next_definition), str(next_source))
        if next_definition and next_source
        else None
    )
    return AnomalyReclassificationResult(
        int(row["scanned_count"]),
        int(row["applied_count"]),
        blocked,
        next_cursor,
        str(row["batch_receipt_identity"]),
    )


def _json_object_list(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError("anomaly_reclassification_batch_snapshot_invalid")
    return parsed


def _fingerprint_values(values):
    normalized = []
    for value in values:
        if isinstance(value, PreviewFingerprint):
            normalized.append(value.value)
        elif isinstance(value, str):
            normalized.append(PreviewFingerprint(value).value)
        else:
            raise TypeError("reclassification state fingerprint is invalid")
    return normalized


class AnomalyReclassificationMySqlUnitOfWork(MySqlUnitOfWork):
    """Marker UoW; commit ownership remains with the application workflow."""

    _SAVEPOINT_NAME = "anm_reclass_item"

    def savepoint(self):
        _execute_savepoint(self._connection, "SAVEPOINT", self._SAVEPOINT_NAME)
        return self._SAVEPOINT_NAME

    def rollback_to_savepoint(self, token) -> None:
        _execute_savepoint(self._connection, "ROLLBACK TO SAVEPOINT", token)

    def release_savepoint(self, token) -> None:
        _execute_savepoint(self._connection, "RELEASE SAVEPOINT", token)


def _dead_letter(projector_identity, row):
    error_code = str(row.get("last_error") or "projector_failure_unknown")
    if len(error_code) > 191 or not error_code.replace("_", "").isalnum():
        error_code = "projector_failure_redacted"
    return ProjectorDeadLetter(
        ProjectorDeadLetterIdentity(projector_identity, int(row["id"])),
        str(row["intent_type"]),
        int(row["attempt_count"]),
        error_code,
        _aware_datetime(row["updated_at"]),
    )


def _receipt_payload(row):
    payload = (
        json.loads(row["result_snapshot"])
        if isinstance(row["result_snapshot"], str)
        else row["result_snapshot"]
    )
    if not isinstance(payload, dict):
        raise ValueError("projector_dead_letter_receipt_invalid")
    return payload


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("projector_dead_letter_projection_invalid")
    return parsed


def _json_dump(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def _owner_payload_key(projector_identity):
    return {
        "government_overpayment": "overpayment_identity",
        "client_over_refund_recovery": "recovery_identity",
        "staff_overpayment_recovery": "recovery_identity",
    }.get(projector_identity) or _unsupported_projector()


def _projection_identity(projector_identity):
    return {
        "government_overpayment": (
            "GOVSUB-006",
            "government-overpayment:",
        ),
        "client_over_refund_recovery": (
            "client_over_refund_recovery_open",
            "client-over-refund-recovery:",
        ),
        "staff_overpayment_recovery": (
            "staff_overpayment_recovery_open",
            "staff-overpayment-recovery:",
        ),
    }.get(projector_identity) or _unsupported_projector()


def _source_event_identity(projector_identity, owner_identity, event_id):
    prefix = {
        "government_overpayment": "government-overpayment:",
        "client_over_refund_recovery": "client-recovery:",
        "staff_overpayment_recovery": "staff-overpayment-recovery:",
    }.get(projector_identity)
    if prefix is None:
        _unsupported_projector()
    return f"{prefix}{owner_identity}:{event_id}"


def _payload_identity(value, key):
    payload = _json_object(value)
    identity = payload.get(key)
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("projector_dead_letter_owner_identity_invalid")
    return identity.strip()


def _owner_projection_equivalent(
    projector_identity,
    owner_identity,
    owner,
    bindings,
    snapshot,
    predicate_active,
):
    status = str(owner["status"])
    remaining = int(owner["remaining_amount_ntd"])
    if remaining != int(snapshot.get("amount_delta_ntd", -1)):
        return False
    if projector_identity == "government_overpayment":
        valid_remaining = (
            remaining > 0
            if status
            in {
                "pending_review",
                "offset_reserved",
                "return_payable",
                "partially_returned",
            }
            else remaining == 0
        )
        return (
            bindings == {
                "overpayment_identity": owner_identity,
                "overpayment_version": int(owner["projection_version"]),
            }
            and predicate_active == (status == "pending_review")
            and valid_remaining
        )
    if projector_identity == "client_over_refund_recovery":
        if owner["account_version"] is None:
            return False
        required = {
            "recovery_identity": owner_identity,
            "recovery_version": int(owner["projection_version"]),
            "case_no": str(owner["case_no"]),
            "account_version": int(owner["account_version"]),
        }
        return (
            all(bindings.get(key) == value for key, value in required.items())
            and predicate_active == (status in {"open", "partially_recovered"})
            and ((status in {"open", "partially_recovered"}) == (remaining > 0))
        )
    if projector_identity == "staff_overpayment_recovery":
        if owner["staff_payables_version"] is None:
            return False
        required = {
            "recovery_identity": owner_identity,
            "recovery_version": int(owner["projection_version"]),
            "staff_id": int(owner["staff_id"]),
            "staff_payables_version": int(owner["staff_payables_version"]),
        }
        return (
            all(bindings.get(key) == value for key, value in required.items())
            and predicate_active == (status in {"open", "partially_recovered"})
            and ((status in {"open", "partially_recovered"}) == (remaining > 0))
        )
    _unsupported_projector()


def _matching_projection_equivalent(
    projector_identity, owner_identity, matching, bindings
):
    if str(matching["recovery_identity"]) != owner_identity:
        return False
    if int(matching["matching_version"]) != bindings.get("matching_version"):
        return False
    if projector_identity == "staff_overpayment_recovery":
        return int(matching["staff_id"]) == bindings.get("staff_id")
    return projector_identity == "client_over_refund_recovery"


def _unsupported_projector():
    raise ValueError("projector_identity_not_supported")


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


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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

_RECLASSIFICATION_ALERT_PAGE_SQL = (
    "SELECT fingerprint,definition_code,source_identity,source_version,"
    "workflow_version,predicate_active FROM anomaly_current_alerts "
    "WHERE predicate_active=1 AND definition_code IN ({definition_placeholders}) "
    "AND (definition_code>%s OR "
    "(definition_code=%s AND source_identity>%s)) "
    "ORDER BY definition_code,source_identity LIMIT %s"
)
_RECLASSIFICATION_ALERT_SELECT_SQL = (
    "SELECT fingerprint,definition_code,source_identity,source_version,"
    "workflow_version,predicate_active FROM anomaly_current_alerts "
    "WHERE fingerprint=%s"
)
_RECLASSIFICATION_RECEIPT_SELECT_SQL = (
    "SELECT disposition.disposition_identity,disposition.alert_fingerprint,"
    "disposition.definition_code,disposition.disposition,disposition.source_identity,"
    "disposition.source_version,disposition.actor,disposition.idempotency_key,"
    "disposition.preview_fingerprint,receipt.receipt_identity,receipt.workflow_event_id,"
    "receipt.before_state_fingerprint,receipt.after_state_fingerprint,"
    "receipt.before_workflow_version,receipt.after_workflow_version,"
    "receipt.correlation_id,receipt.created_at,receipt.result_snapshot "
    "FROM anomaly_reclassification_receipts receipt "
    "JOIN anomaly_reclassification_dispositions disposition "
    "ON disposition.id=receipt.disposition_id "
    "WHERE disposition.idempotency_key=%s"
)
_FAILED_OUTBOX_SELECT_SQL = (
    "SELECT id FROM finance_import_outbox "
    "WHERE status='failed' AND intent_type IN (%s,%s,%s) "
    "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
)


__all__ = [
    "AnomalyReclassificationMySqlUnitOfWork",
    "MySqlAnomalyMaintenanceRepository",
]

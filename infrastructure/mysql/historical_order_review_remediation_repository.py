"""
File: historical_order_review_remediation_repository.py
Description: 以單一 MySQL 交易保存歷史 review 更正 receipt、disposition 與 outbox。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
import json
from typing import Iterator

from domains.orders.historical_review_remediation import (
    HistoricalReviewContext,
    HistoricalReviewCorrectionCandidate,
    HistoricalReviewCorrectionSource,
    conflict_for_issue,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionWorkflow,
)
from subsystems.orders.historical_review_remediation_workflow import (
    ApplyHistoricalReviewRemediation,
    HistoricalReviewRemediationReceipt,
    historical_review_remediation_command_fingerprint,
)


class HistoricalOrderReviewRemediationMySqlUnitOfWork(MySqlUnitOfWork):
    pass


class MySqlHistoricalOrderReviewRemediationRepository:
    def __init__(self, connection, adoption_workflow: HistoricalOrderAdoptionWorkflow):
        self._connection = connection
        self._adoption_workflow = adoption_workflow

    def load_context(self, review_identity: str, *, for_update: bool) -> HistoricalReviewContext | None:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT review.review_identity,review.source_event_identity,review.source_fingerprint,"
                "review.case_identity,review.issue_codes,adoption.id AS adoption_id,"
                "adoption.outcome,adoption.case_no,adoption.lifecycle_event_id,"
                "CASE WHEN remediation.id IS NULL THEN 0 ELSE 1 END AS remediation_version,"
                "CASE WHEN alert.fingerprint IS NULL THEN 1 "
                "ELSE alert.predicate_active END AS prior_alert_active "
                "FROM historical_order_adoption_reviews review "
                "JOIN historical_order_adoption_receipts adoption ON adoption.review_identity=review.review_identity "
                "LEFT JOIN historical_order_review_remediation_events remediation "
                "ON remediation.prior_review_identity=review.review_identity "
                "LEFT JOIN anomaly_current_alerts alert "
                "ON alert.definition_code='HISTORICAL-ORDER-001' "
                "AND alert.source_identity=review.review_identity "
                "WHERE review.review_identity=%s" + suffix,
                (review_identity,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "SELECT o.case_no,c.name,o.status,o.actual_start_date,o.actual_end_date "
                "FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s" + suffix,
                (row["case_no"],),
            )
            order = cursor.fetchone()
        if order is None:
            raise ValueError("historical_order_remediation_order_root_missing")
        issues = _json_text_tuple(row["issue_codes"])
        current_values = {
            "status": order.get("status"),
            "actual_start_date": order.get("actual_start_date"),
            "actual_end_date": order.get("actual_end_date"),
        }
        conflicts = tuple(
            conflict_for_issue(
                code,
                current_value=current_values.get(
                    "status" if "status" in code else
                    "actual_start_date" if "start_date" in code else
                    "actual_end_date" if "end_date" in code else ""
                ),
            )
            for code in issues
        )
        return HistoricalReviewContext(
            str(row["review_identity"]),
            str(row["source_event_identity"]),
            str(row["source_fingerprint"]),
            str(row["case_identity"]),
            str(row["case_no"]),
            int(row["adoption_id"]),
            str(row["outcome"]),
            None if row["lifecycle_event_id"] is None else int(row["lifecycle_event_id"]),
            0,
            int(row["remediation_version"]),
            conflicts,
            str(order["name"]),
            bool(row["prior_alert_active"]),
        )

    def evaluate_source(
        self,
        context: HistoricalReviewContext,
        source: HistoricalReviewCorrectionSource,
        *,
        for_update: bool,
    ) -> HistoricalReviewCorrectionSource:
        del context
        preview = self._adoption_workflow.preview_in_current_unit_of_work(
            source.source_row, for_update=for_update
        )
        if preview.outcome.value == "unmatched_case":
            raise ValueError("historical_order_correction_case_mismatch")
        return replace(source, issue_codes=preview.issue_codes)

    def find_receipt(self, key) -> tuple[PreviewFingerprint, HistoricalReviewRemediationReceipt] | None:
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT receipt.command_fingerprint,prior_review_identity,remediation_receipt_identity,"
                "disposition,successor_review_identity,event.source_content_digest,"
                "resulting_remediation_version,preview_fingerprint "
                "FROM historical_order_review_remediation_receipts receipt "
                "JOIN historical_order_review_remediation_events event ON event.id=receipt.event_id "
                "WHERE receipt.idempotency_key=%s",
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return (
            PreviewFingerprint(str(row["command_fingerprint"])),
            HistoricalReviewRemediationReceipt(
                str(row["prior_review_identity"]),
                str(row["remediation_receipt_identity"]),
                str(row["disposition"]),
                row["successor_review_identity"],
                str(row["source_content_digest"]),
                int(row["resulting_remediation_version"]),
                PreviewFingerprint(str(row["preview_fingerprint"])),
                False,
            ),
        )

    def persist(self, command, context, candidate):
        row = candidate.source.source_row
        # Reuse the existing typed adoption calculation while keeping this
        # repository inside the caller's single outer Unit of Work.
        adoption_preview = self._adoption_workflow.preview_in_current_unit_of_work(
            row, for_update=True
        )
        if adoption_preview.outcome.value == "unmatched_case":
            raise ValueError("historical_order_correction_case_mismatch")
        if tuple(adoption_preview.issue_codes) != tuple(candidate.blockers):
            raise ValueError("historical_order_remediation_candidate_stale")
        adoption_request = HistoricalOrderAdoptionRequest(
            row,
            adoption_preview.fingerprint,
            _identity("historical-order-adoption", command.idempotency_key.value),
            command.actor.actor_id,
            command.reason,
            command.correlation_id.value,
        )
        adoption_receipt = self._adoption_workflow.apply_in_current_unit_of_work(
            adoption_request
        )
        if adoption_receipt.case_no != context.case_no:
            raise ValueError("historical_order_remediation_case_binding_mismatch")
        if candidate.successor_required != (adoption_receipt.review_identity is not None):
            raise ValueError("historical_order_remediation_disposition_stale")
        replacement_id = self._receipt_id(adoption_request.idempotency_key)
        if replacement_id is None:
            raise RuntimeError("historical_order_replacement_receipt_missing")
        event_identity = _identity(
            "historical-order-remediation-event", command.idempotency_key.value
        )
        command_fingerprint = historical_review_remediation_command_fingerprint(
            command, candidate.source
        )
        orders_terminal_snapshot = _load_orders_terminal_snapshot(
            self._connection, context.case_no
        )
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_order_review_remediation_events "
                "(event_identity,prior_review_identity,original_adoption_receipt_id,replacement_adoption_receipt_id,"
                "disposition,successor_review_identity,source_content_digest,review_fingerprint,command_fingerprint,"
                "actor,reason,evidence_snapshot,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_identity,
                    context.review_identity,
                    context.original_adoption_receipt_id,
                    replacement_id,
                    candidate.disposition.value,
                    adoption_receipt.review_identity,
                    candidate.source.workbook_digest,
                    candidate.fingerprint.value,
                    command_fingerprint.value,
                    command.actor.actor_id,
                    command.reason,
                    _json({
                        "evidence": command.evidence,
                        "blockers": candidate.blockers,
                        "orders_terminal_snapshot": orders_terminal_snapshot,
                    }),
                    command.correlation_id.value,
                ),
            )
            event_id = int(cursor.lastrowid)
            receipt_identity = _identity(
                "historical-order-remediation-receipt",
                command.idempotency_key.value,
            )
            cursor.execute(
                "INSERT INTO historical_order_review_remediation_receipts "
                "(remediation_receipt_identity,event_id,idempotency_key,command_fingerprint,preview_fingerprint,"
                "expected_remediation_version,resulting_remediation_version,result_snapshot,actor,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,0,1,%s,%s,%s)",
                (
                    receipt_identity,
                    event_id,
                    command.idempotency_key.value,
                    command_fingerprint.value,
                    command.preview_fingerprint.value,
                    _json({
                        "disposition": candidate.disposition.value,
                        "successor_review_identity": adoption_receipt.review_identity,
                        "orders_terminal_snapshot": orders_terminal_snapshot,
                    }),
                    command.actor.actor_id,
                    command.correlation_id.value,
                ),
            )
            receipt_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO historical_order_review_remediation_outbox "
                "(event_id,remediation_receipt_id,intent_key,intent_type,bounded_snapshot) VALUES (%s,%s,%s,'historical_order_review_remediated',%s)",
                (
                    event_id,
                    receipt_id,
                    event_identity,
                    _json({
                        "event_id": event_id,
                        "prior_review_identity": context.review_identity,
                        "disposition": candidate.disposition.value,
                        "successor_review_identity": adoption_receipt.review_identity,
                        "orders_terminal_snapshot": orders_terminal_snapshot,
                    }),
                ),
            )
        return HistoricalReviewRemediationReceipt(
            context.review_identity,
            receipt_identity,
            candidate.disposition.value,
            adoption_receipt.review_identity,
            candidate.source.workbook_digest,
            1,
            command.preview_fingerprint,
            False,
        )

    def _receipt_id(self, key: str) -> int | None:
        with _cursor(self._connection) as cursor:
            cursor.execute("SELECT id FROM historical_order_adoption_receipts WHERE idempotency_key=%s", (key,))
            row = cursor.fetchone()
        return None if row is None else int(row["id"])


@contextmanager
def _cursor(connection) -> Iterator[object]:
    with connection.cursor() as cursor:
        yield cursor


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_text_tuple(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("historical_order_review_issue_codes_invalid")
    return tuple(sorted(set(parsed)))


def _load_orders_terminal_snapshot(connection, case_no: str) -> dict[str, object]:
    if not isinstance(case_no, str) or not case_no.strip():
        raise ValueError("historical_order_remediation_case_binding_missing")
    with _cursor(connection) as cursor:
        cursor.execute(
            "SELECT case_no,status,lifecycle_version,actual_start_date,actual_end_date "
            "FROM orders WHERE case_no=%s FOR UPDATE",
            (case_no,),
        )
        order = cursor.fetchone()
        if order is None:
            raise ValueError("historical_order_remediation_order_root_missing")
        cursor.execute(
            "SELECT id,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status "
            "FROM case_staff_assignments WHERE case_no=%s AND status<>'cancelled' "
            "ORDER BY assignment_sequence,id FOR UPDATE",
            (case_no,),
        )
        assignments = cursor.fetchall()
    if not isinstance(order, dict):
        raise ValueError("historical_order_remediation_order_root_malformed")
    snapshot = {
        "case_no": _required_text(order.get("case_no"), "case_no"),
        "status": _required_text(order.get("status"), "status"),
        "lifecycle_version": _required_int(order.get("lifecycle_version"), "lifecycle_version"),
        "actual_start_date": _snapshot_date(order.get("actual_start_date"), "actual_start_date"),
        "actual_end_date": _snapshot_date(order.get("actual_end_date"), "actual_end_date"),
        "active_assignments": _assignment_snapshots(assignments),
    }
    if snapshot["case_no"] != case_no:
        raise ValueError("historical_order_remediation_case_binding_mismatch")
    return snapshot


def _assignment_snapshots(rows) -> list[dict[str, object]]:
    if rows is None:
        raise ValueError("historical_order_remediation_assignments_malformed")
    snapshots = []
    seen_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("historical_order_remediation_assignment_malformed")
        assignment_id = _required_int(row.get("id"), "assignment_id")
        if assignment_id in seen_ids:
            raise ValueError("historical_order_remediation_assignment_duplicate")
        seen_ids.add(assignment_id)
        snapshots.append({
            "assignment_id": assignment_id,
            "staff_id": _required_int(row.get("staff_id"), "staff_id"),
            "assignment_sequence": _required_int(row.get("assignment_sequence"), "assignment_sequence"),
            "assigned_start_date": _snapshot_date(row.get("assigned_start_date"), "assigned_start_date"),
            "assigned_end_date": _snapshot_date(row.get("assigned_end_date"), "assigned_end_date"),
            "status": _required_text(row.get("status"), "status"),
        })
    return snapshots


def _required_text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"historical_order_remediation_{field}_malformed")
    return value


def _required_int(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"historical_order_remediation_{field}_malformed")
    return value


def _snapshot_date(value, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        try:
            datetime.fromisoformat(value)
        except ValueError:
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise ValueError(
                    f"historical_order_remediation_{field}_malformed"
                ) from error
        return value
    raise ValueError(f"historical_order_remediation_{field}_malformed")


def _identity(namespace: str, value: str) -> str:
    return f"{namespace}:{sha256(value.encode('utf-8')).hexdigest()}"


__all__ = [
    "HistoricalOrderReviewRemediationMySqlUnitOfWork",
    "MySqlHistoricalOrderReviewRemediationRepository",
]

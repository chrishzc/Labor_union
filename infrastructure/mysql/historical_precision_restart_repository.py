"""MySQL adapter for one-transaction historical precision restart."""

from __future__ import annotations

from contextlib import contextmanager
import json

from pymysql.err import IntegrityError

from domains.orders.historical_precision_restart import (
    HistoricalPrecisionRestartAssignmentFacts,
    HistoricalPrecisionRestartFacts,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.historical_precision_restart_workflow import (
    HistoricalPrecisionRestartContext,
    HistoricalPrecisionRestartReceipt,
    StoredHistoricalPrecisionRestartReceipt,
)
from subsystems.orders.terms_workflow import SchedulingReplacementCommand
from infrastructure.mysql.order_terms_read_model import (
    load_locked_facts,
    load_preview_facts,
    preflight_staff_ids,
)
from infrastructure.mysql.scheduling_replacement_writer import persist_scheduling_replacement


_FAMILY = "orders_historical_precision_restart"


class MySqlHistoricalPrecisionRestartRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def preflight_staff_ids(self, case_no):
        with _cursor(self._connection) as cursor:
            return tuple(sorted(set((*preflight_staff_ids(cursor, case_no), *_evidence_staff_ids(cursor, case_no)))))

    def load(self, case_no, *, for_update):
        with _cursor(self._connection) as cursor:
            if for_update:
                terms = load_locked_facts(cursor, case_no, self.preflight_staff_ids(case_no))
            else:
                terms = load_preview_facts(cursor, case_no)
            lock = " FOR UPDATE" if for_update else ""
            cursor.execute(
                "SELECT COALESCE(day_revision,0) AS day_revision FROM historical_service_day_projections WHERE case_no=%s" + lock,
                (case_no,),
            )
            day_row = cursor.fetchone()
            cursor.execute(_ASSIGNMENTS_SQL + lock, (case_no,))
            rows = tuple(cursor.fetchall())
            cursor.execute(_ADOPTION_SQL + lock, (case_no,))
            adoption = cursor.fetchone()
            cursor.execute(
                "SELECT version,service_date_fingerprint FROM confirmed_service_date_versions "
                "WHERE case_no=%s AND is_current=1" + lock,
                (case_no,),
            )
            confirmed_dates = cursor.fetchone()
            cursor.execute("SELECT holiday_date FROM holidays WHERE is_double_pay_default=1 ORDER BY holiday_date" + lock)
            holidays = tuple(row["holiday_date"] for row in cursor.fetchall())
        assignments = tuple(
            HistoricalPrecisionRestartAssignmentFacts(
                f"assignment:{int(row['assignment_id'])}" if row["assignment_id"] is not None else f"pairing:{int(row['pairing_ordinal'])}",
                None if row["assignment_id"] is None else int(row["assignment_id"]),
                int(row["staff_id"]),
                str(row["staff_name"]),
                int(row["assignment_sequence"] or row["pairing_ordinal"]),
            )
            for row in rows if row["staff_id"] is not None
        )
        root = terms.lifecycle
        scheduling = terms.scheduling
        facts = HistoricalPrecisionRestartFacts(
            terms.order.case_no,
            root.current_status,
            terms.order.version,
            scheduling.aggregate_version,
            scheduling.generation_number,
            terms.client_finance.account_version,
            terms.payroll.payroll_version,
            int(day_row["day_revision"]) if day_row else 0,
            terms.order.terms.planned_start_date,
            root.actual_start_date,
            terms.order.terms.service_days,
            terms.order.terms.service_hours_per_day,
            terms.order.service_data_locked,
            assignments,
            tuple(segment.assignment_id for segment in scheduling.segments),
            holidays,
            terms.client_finance.open_nonstage_obligation_count,
            None if adoption is None else int(adoption["id"]),
            None if adoption is None else str(adoption["source_event_identity"]),
            None if confirmed_dates is None else int(confirmed_dates["version"]),
            None if confirmed_dates is None else str(confirmed_dates["service_date_fingerprint"]),
            len(terms.payroll.existing_obligations),
        )
        return HistoricalPrecisionRestartContext(facts, terms)

    def find_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT c.command_fingerprint,e.facts_snapshot FROM application_command_claims c "
                "JOIN order_lifecycle_state_events e ON e.idempotency_key=c.idempotency_key "
                "WHERE c.idempotency_key=%s AND c.command_family=%s AND e.trigger_event=%s FOR UPDATE",
                (key.value, _FAMILY, _FAMILY),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _object(row["facts_snapshot"])["precision_restart_receipt"]
        return StoredHistoricalPrecisionRestartReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])), _receipt(payload)
        )

    def claim(self, request, command_fingerprint):
        with _cursor(self._connection) as cursor:
            try:
                cursor.execute(
                    "INSERT INTO application_command_claims (idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)",
                    (request.idempotency_key.value, _FAMILY, request.intent.case_no, command_fingerprint.value, request.correlation_id.value),
                )
                return None
            except IntegrityError as error:
                if error.args[0] != 1062:
                    raise
                cursor.execute(
                    "SELECT command_family,aggregate_identity,command_fingerprint FROM application_command_claims WHERE idempotency_key=%s FOR UPDATE",
                    (request.idempotency_key.value,),
                )
                row = cursor.fetchone()
                if not row or row["command_family"] != _FAMILY or row["aggregate_identity"] != request.intent.case_no or row["command_fingerprint"] != command_fingerprint.value:
                    raise ValueError("idempotency_conflict") from error
                cursor.execute(
                    "SELECT facts_snapshot FROM order_lifecycle_state_events WHERE idempotency_key=%s AND trigger_event=%s FOR UPDATE",
                    (request.idempotency_key.value, _FAMILY),
                )
                event = cursor.fetchone()
                if event is None:
                    raise RuntimeError("historical_precision_restart_receipt_incomplete") from error
                payload = _object(event["facts_snapshot"])["precision_restart_receipt"]
                return StoredHistoricalPrecisionRestartReceipt(command_fingerprint, _receipt(payload))

    def persist(self, request, preview):
        domain = preview.domain
        scheduling = domain.scheduling
        lifecycle = preview.lifecycle_impact
        assert scheduling is not None and lifecycle is not None
        receipt = HistoricalPrecisionRestartReceipt(
            domain.facts.case_no,
            lifecycle.after_status.value,
            domain.facts.order_version + 1,
            scheduling.resulting_aggregate_version,
            scheduling.generation_number,
            domain.facts.client_finance_version,
            domain.facts.payroll_version,
            domain.facts.historical_day_revision,
            preview.fingerprint,
        )
        snapshot = {
            "correlation_id": request.correlation_id.value,
            "reason": request.reason,
            "provenance": {
                "family": "historical_order_adoption",
                "receipt_id": domain.facts.adoption_receipt_id,
                "source_event_identity": domain.facts.adoption_source_identity,
            },
            "source_actual_start_date": (
                None
                if domain.facts.actual_start_date is None
                else domain.facts.actual_start_date.isoformat()
            ),
            "precision_restart_receipt": _receipt_payload(receipt),
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events (case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (domain.facts.case_no, _FAMILY, lifecycle.before_status.value, lifecycle.after_status.value, request.actor.actor_id, lifecycle.business_date, domain.facts.order_version, request.idempotency_key.value, _json(snapshot)),
            )
            lifecycle_event_id = int(cursor.lastrowid)
            _invalidate_confirmed_dates(cursor, domain.facts.case_no)
            persist_scheduling_replacement(cursor, SchedulingReplacementCommand(
                scheduling, _FAMILY, domain.facts.order_version, preview.fingerprint,
                preview.fingerprint, request.idempotency_key, request.actor, request.reason, request.correlation_id,
            ))
            cursor.execute(
                "UPDATE orders SET status=%s,actual_start_date=NULL,actual_end_date=NULL,lifecycle_version=%s "
                "WHERE case_no=%s AND lifecycle_version=%s",
                (lifecycle.after_status.value, receipt.order_version, domain.facts.case_no, domain.facts.order_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("order_version_conflict")
            cursor.execute(
                "INSERT INTO orders_domain_outbox (case_no,lifecycle_event_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,%s,'lifecycle_projection_changed',%s)",
                (domain.facts.case_no, lifecycle_event_id, f"{request.idempotency_key.value}:orders", _json(snapshot)),
            )
        return receipt


def _invalidate_confirmed_dates(cursor, case_no):
    cursor.execute(
        "UPDATE confirmed_service_date_versions SET is_current=NULL,invalidated_at_utc=UTC_TIMESTAMP(6) "
        "WHERE case_no=%s AND is_current=1",
        (case_no,),
    )


def _evidence_staff_ids(cursor, case_no):
    cursor.execute(_ASSIGNMENTS_SQL, (case_no,))
    return tuple(sorted({int(row["staff_id"]) for row in cursor.fetchall() if row["staff_id"] is not None}))


def _receipt(payload):
    return HistoricalPrecisionRestartReceipt(
        str(payload["case_no"]), str(payload["lifecycle_status"]), int(payload["order_version"]),
        int(payload["scheduling_version"]), int(payload["scheduling_generation"]),
        int(payload["client_finance_version"]), int(payload["payroll_version"]),
        int(payload["historical_day_revision"]), PreviewFingerprint(str(payload["preview_fingerprint"])),
    )


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no, "lifecycle_status": receipt.lifecycle_status,
        "order_version": receipt.order_version, "scheduling_version": receipt.scheduling_version,
        "scheduling_generation": receipt.scheduling_generation, "client_finance_version": receipt.client_finance_version,
        "payroll_version": receipt.payroll_version, "historical_day_revision": receipt.historical_day_revision,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _object(value):
    return json.loads(value) if isinstance(value, str) else value


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


_ASSIGNMENTS_SQL = (
    "SELECT evidence.caregiver_ordinal AS pairing_ordinal,evidence.assignment_id,evidence.staff_id,staff.name AS staff_name,assignment.assignment_sequence "
    "FROM historical_order_adoption_receipts receipt JOIN historical_order_pairing_evidence evidence ON evidence.receipt_id=receipt.id "
    "LEFT JOIN case_staff_assignments assignment ON assignment.id=evidence.assignment_id LEFT JOIN staff ON staff.id=evidence.staff_id "
    "WHERE receipt.id=(SELECT MAX(r.id) FROM historical_order_adoption_receipts r WHERE r.case_no=%s AND r.outcome='adopted') ORDER BY evidence.caregiver_ordinal"
)
_ADOPTION_SQL = (
    "SELECT id,source_event_identity FROM historical_order_adoption_receipts "
    "WHERE id=(SELECT MAX(r.id) FROM historical_order_adoption_receipts r WHERE r.case_no=%s AND r.outcome='adopted')"
)


__all__ = ["MySqlHistoricalPrecisionRestartRepository"]

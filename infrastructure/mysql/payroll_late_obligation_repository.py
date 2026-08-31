"""MySQL adapter for PAYOUT-002 Payroll lineage corrections.

The adapter deliberately does not alter old events. Each adjudicated branch is
recorded in the immutable disposition table and the current obligation is
advanced with an append-only event when the legal amount changes.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
import hashlib
import json

from domains.payroll.late_obligation import (
    LateObligationDisposition,
    LatePayrollObligationFacts,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.money import MoneyNTD


class PayrollLateObligationMySqlUnitOfWork(MySqlUnitOfWork):
    pass


class MySqlPayrollLateObligationRepository:
    """Read and append the current Payroll obligation lineage."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, intent, *, for_update: bool) -> LatePayrollObligationFacts:
        with _cursor(self._connection) as cursor:
            return _load_fact(cursor, intent, for_update)

    def find_receipt(self, key):
        # Receipts are shared with the existing Payroll adjustment writer.
        from infrastructure.mysql.payroll_adjustment_repository import (
            _RECEIPT_SELECT_SQL,
        )

        with _cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        # A late receipt has a distinct result snapshot discriminator.
        payload = _json_object(row["result_snapshot"])
        if payload.get("command_type") != "payroll.late_obligation.v1":
            return None
        from subsystems.payroll.late_obligation_workflow import (
            LatePayrollObligationReceipt,
            StoredLatePayrollObligationReceipt,
        )
        from shared_kernel.fingerprints import PreviewFingerprint

        receipt = LatePayrollObligationReceipt(
            str(payload["case_no"]), str(payload["obligation_identity"]),
            str(payload["source_event_identity"]), str(payload["disposition"]),
            int(payload["delta_amount_ntd"]), int(payload["corrected_amount_ntd"]),
            int(payload["recovery_amount_ntd"]), int(payload["payroll_version"]),
            int(payload["obligation_version"]), str(payload["correction_identity"]),
            PreviewFingerprint(str(payload["preview_fingerprint"])),
        )
        return StoredLatePayrollObligationReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])), receipt
        )

    def persist_payroll_disposition(self, request, preview, receipt, command_fingerprint) -> None:
        candidate = preview.candidate
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO payroll_late_obligation_dispositions "
                "(correction_identity,case_no,obligation_identity,source_event_identity,"
                "assignment_id,staff_id,disposition,before_amount_ntd,corrected_amount_ntd,"
                "delta_amount_ntd,recovery_amount_ntd,expected_payroll_version,"
                "resulting_payroll_version,expected_obligation_version,"
                "resulting_obligation_version,idempotency_key,command_fingerprint,"
                "preview_fingerprint,actor,reason,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    candidate.correction_identity, candidate.case_no,
                    candidate.obligation_identity, candidate.source_event_identity,
                    candidate.assignment_id, candidate.staff_id,
                    candidate.disposition.value, candidate.current_amount.amount,
                    candidate.corrected_amount.amount, candidate.delta_amount.amount,
                    candidate.recovery_amount.amount, preview.payroll_version,
                    receipt.payroll_version, preview.obligation_version,
                    receipt.obligation_version, request.idempotency_key.value,
                    command_fingerprint.value, receipt.preview_fingerprint.value,
                    request.actor.actor_id, request.reason, request.correlation_id.value,
                ),
            )
            if candidate.delta_amount.amount != 0:
                cursor.execute(
                    "INSERT INTO staff_obligation_events "
                    "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
                    "direction,source_obligation_identity,event_type,before_amount_ntd,"
                    "after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,"
                    "resulting_payroll_version,idempotency_key,actor,reason) "
                    "VALUES (%s,%s,%s,%s,%s,'payable_to_staff',NULL,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s)",
                    (
                        candidate.obligation_identity, candidate.assignment_id,
                        candidate.case_no, candidate.staff_id,
                        "adjustment" if candidate.delta_amount.amount > 0 else "reversal",
                        "adjustment" if candidate.delta_amount.amount > 0 else "reversal",
                        candidate.current_amount.amount, candidate.corrected_amount.amount,
                        candidate.fingerprint.value, preview.payroll_version,
                        receipt.payroll_version, request.idempotency_key.value,
                        request.actor.actor_id, request.reason,
                    ),
                )
                event_id = int(cursor.lastrowid)
                cursor.execute(
                    "UPDATE staff_obligations SET amount_due_ntd=%s,status=%s,"
                    "current_event_id=%s,payroll_version=%s WHERE obligation_identity=%s "
                    "AND payroll_version=%s",
                    (
                        candidate.corrected_amount.amount,
                        "open" if candidate.corrected_amount.amount > 0 else "cancelled",
                        event_id, receipt.obligation_version,
                        candidate.obligation_identity, preview.obligation_version,
                    ),
                )
            else:
                # No amount event is legal for delta=0; the immutable row is
                # the review evidence while only the current version advances.
                cursor.execute(
                    "UPDATE staff_obligations SET payroll_version=%s "
                    "WHERE obligation_identity=%s AND payroll_version=%s",
                    (receipt.obligation_version, candidate.obligation_identity,
                     preview.obligation_version),
                )
            if cursor.rowcount != 1:
                raise RuntimeError("payout002_obligation_stale")
            cursor.execute(
                "UPDATE payroll_case_accounts SET aggregate_version=%s WHERE case_no=%s AND aggregate_version=%s",
                (receipt.payroll_version, candidate.case_no, preview.payroll_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("payout002_payroll_stale")
            payload = _receipt_payload(receipt)
            payload["command_type"] = "payroll.late_obligation.v1"
            cursor.execute(
                "INSERT INTO payroll_apply_receipts "
                "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,resulting_payroll_version,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    request.idempotency_key.value, command_fingerprint.value,
                    receipt.preview_fingerprint.value, candidate.case_no,
                    receipt.payroll_version, _canonical_json(payload),
                ),
            )

    persist_late_obligation = persist_payroll_disposition

    def readback_late_obligation(self, intent):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT corrected_amount_ntd FROM payroll_late_obligation_dispositions "
                "WHERE case_no=%s AND obligation_identity=%s "
                "AND source_event_identity=%s ORDER BY id DESC LIMIT 1",
                (intent.case_no, intent.obligation_identity, intent.source_event_identity),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("payout002_disposition_not_found")
            corrected = MoneyNTD(int(row["corrected_amount_ntd"]))
            fresh_intent = type(intent)(
                intent.case_no, intent.obligation_identity,
                intent.source_event_identity, corrected,
            )
            return _load_fact(cursor, fresh_intent, False)


def _load_fact(cursor, intent, for_update):
    lock = " FOR UPDATE" if for_update else ""
    cursor.execute(
        "SELECT o.obligation_identity,o.assignment_id,o.case_no,o.staff_id,o.amount_due_ntd,"
        "o.payroll_version,o.updated_at,account.aggregate_version,ev.id AS source_event_id,"
        "ev.created_at,ev.before_amount_ntd,ev.after_amount_ntd,o.due_date "
        "FROM staff_obligations o JOIN payroll_case_accounts account ON account.case_no=o.case_no "
        "JOIN staff_obligation_events ev ON ev.obligation_identity=o.obligation_identity "
        "WHERE o.case_no=%s AND o.obligation_identity=%s AND ev.id=%s " + lock,
        (intent.case_no, intent.obligation_identity, _event_id(intent.source_event_identity)),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("payout002_source_not_found")
    cursor.execute(
        "SELECT COALESCE(SUM(CASE WHEN event_type='payout' THEN links.allocated_amount_ntd "
        "WHEN event_type IN ('return','reversal') THEN -links.allocated_amount_ntd ELSE 0 END),0) AS paid "
        "FROM staff_payout_obligation_links links JOIN staff_payout_events events "
        "ON events.id=links.payout_event_id WHERE links.obligation_identity=%s",
        (intent.obligation_identity,),
    )
    paid = int(cursor.fetchone()["paid"])
    event_at = _datetime(row["created_at"])
    due_date = _date(row["due_date"])
    return LatePayrollObligationFacts(
        str(row["case_no"]), str(row["obligation_identity"]), intent.source_event_identity,
        int(row["assignment_id"]), int(row["staff_id"]), MoneyNTD(int(row["amount_due_ntd"])),
        intent.corrected_amount, MoneyNTD(max(paid, 0)), int(row["aggregate_version"]),
        int(row["payroll_version"]), due_date, event_at,
        event_at.date() > due_date,
    )


def _event_id(identity):
    prefix = "staff-obligation-event:"
    if not isinstance(identity, str) or not identity.startswith(prefix) or not identity[len(prefix):].isdigit():
        raise ValueError("payout002_source_event_identity_invalid")
    value = int(identity[len(prefix):])
    if value <= 0:
        raise ValueError("payout002_source_event_identity_invalid")
    return value


def _correction_obligation_identity(candidate):
    return "staff-obligation:payout002:" + candidate.correction_identity.rsplit(":", 1)[-1]


def _child_key(value):
    return "payroll-obligation:" + hashlib.sha256((value + ":payout002").encode()).hexdigest()


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "obligation_identity": receipt.obligation_identity,
        "source_event_identity": receipt.source_event_identity,
        "disposition": receipt.disposition,
        "delta_amount_ntd": receipt.delta_amount_ntd,
        "corrected_amount_ntd": receipt.corrected_amount_ntd,
        "recovery_amount_ntd": receipt.recovery_amount_ntd,
        "payroll_version": receipt.payroll_version,
        "obligation_version": receipt.obligation_version,
        "correction_identity": receipt.correction_identity,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise RuntimeError("payout002 receipt snapshot must be object")
    return payload


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


@contextmanager
def _cursor(connection):
    with connection.cursor() as cursor:
        yield cursor


__all__ = ["MySqlPayrollLateObligationRepository", "PayrollLateObligationMySqlUnitOfWork"]

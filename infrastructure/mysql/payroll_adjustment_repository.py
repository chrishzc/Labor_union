"""MySQL facts and atomic persistence for Payroll adjustment commands."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
import hashlib
import json
from typing import Iterator

from pymysql.err import OperationalError

from domains.payroll.adjustment import (
    EffectivePayrollAssignment,
    PayrollAdjustmentFacts,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.payroll.adjustment_workflow import (
    PayrollAdjustmentReceipt,
    StoredPayrollAdjustmentReceipt,
)

_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class PayrollAdjustmentMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_if_transient(error)
            raise

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_if_transient(error)
            raise


class MySqlPayrollAdjustmentRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no: str, *, for_update: bool):
        with _mysql_cursor(self._connection) as cursor:
            return _load_facts(cursor, case_no, for_update)

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def persist(self, request, preview, command_fingerprint, receipt) -> None:
        with _mysql_cursor(self._connection) as cursor:
            adjustment_event_id = _insert_adjustment_event(
                cursor,
                request,
                preview,
            )
            _insert_allocation_obligations(
                cursor,
                request,
                preview,
                adjustment_event_id,
            )
            _advance_payroll_version(cursor, request, receipt)
            _insert_outbox(cursor, request, preview, receipt)
            _insert_receipt(cursor, request, command_fingerprint, receipt)

    def query_case_payroll(self, case_no: str):
        with _mysql_cursor(self._connection) as cursor:
            version, due_date = _query_case_header(cursor, case_no)
            cursor.execute(_CASE_OBLIGATIONS_SQL, (case_no,))
            obligations = tuple(_obligation_view(row) for row in cursor.fetchall())
            cursor.execute(_CASE_ADJUSTMENTS_SQL, (case_no,))
            adjustments = tuple(_adjustment_view(row) for row in cursor.fetchall())
        return {
            "case_no": case_no,
            "payroll_version": version,
            "staff_payment_due_date": due_date,
            "obligations": obligations,
            "adjustments": adjustments,
        }

    def query_staff_obligations(self, staff_id: int):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_STAFF_OBLIGATIONS_SQL, (staff_id,))
            obligations = tuple(_obligation_view(row) for row in cursor.fetchall())
        return {"staff_id": staff_id, "obligations": obligations}


def _load_facts(cursor, case_no, for_update):
    if for_update:
        _ensure_payroll_account(cursor, case_no)
    version, due_date = _query_case_header(cursor, case_no, for_update)
    cursor.execute(_EFFECTIVE_ASSIGNMENTS_SQL, (case_no,))
    assignments = tuple(
        _effective_assignment(cursor, row)
        for row in cursor.fetchall()
    )
    return PayrollAdjustmentFacts(case_no, version, due_date, assignments)


def _query_case_header(cursor, case_no, for_update=False):
    locking = " FOR UPDATE" if for_update else ""
    cursor.execute(_CASE_HEADER_SQL + locking, (case_no,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("invalid_payroll_facts")
    return int(row["payroll_version"]), _date_value(row["staff_payment_due_date"])


def _effective_assignment(cursor, row):
    cursor.execute(_SOURCE_OBLIGATION_SQL, (row["assignment_id"],))
    obligation = cursor.fetchone()
    return EffectivePayrollAssignment(
        int(row["assignment_id"]),
        int(row["staff_id"]),
        None if obligation is None else str(obligation["obligation_identity"]),
        False if obligation is None else bool(obligation["payout_history_exists"]),
    )


def _ensure_payroll_account(cursor, case_no) -> None:
    cursor.execute(
        "INSERT IGNORE INTO payroll_case_accounts(case_no) VALUES (%s)",
        (case_no,),
    )


def _insert_adjustment_event(cursor, request, preview):
    candidate = preview.candidate
    cursor.execute(
        _ADJUSTMENT_EVENT_INSERT_SQL,
        (
            candidate.case_no,
            candidate.adjustment_identity,
            candidate.amount.amount,
            candidate.source_event_identity,
            request.actor.actor_id,
            request.reason,
            request.idempotency_key.value,
        ),
    )
    return int(cursor.lastrowid)


def _insert_allocation_obligations(cursor, request, preview, event_id):
    for ordinal, allocation in enumerate(
        preview.candidate.allocations,
        start=1,
    ):
        _insert_allocation(cursor, event_id, allocation, ordinal)
        obligation_event_id = _insert_obligation_event(
            cursor,
            request,
            preview,
            allocation,
            ordinal,
        )
        _insert_obligation_projection(
            cursor,
            preview,
            allocation,
            obligation_event_id,
        )


def _insert_allocation(cursor, event_id, allocation, ordinal) -> None:
    cursor.execute(
        _ALLOCATION_INSERT_SQL,
        (
            event_id,
            allocation.assignment_id,
            allocation.signed_amount.amount,
            ordinal,
        ),
    )


# Kept whole so the immutable event row is visibly bound to one command version.
def _insert_obligation_event(cursor, request, preview, allocation, ordinal):
    candidate = preview.candidate
    cursor.execute(
        _OBLIGATION_EVENT_INSERT_SQL,
        (
            allocation.obligation_identity,
            allocation.assignment_id,
            candidate.case_no,
            allocation.staff_id,
            allocation.obligation_kind.value,
            allocation.direction.value,
            allocation.source_obligation_identity,
            allocation.obligation_kind.value,
            allocation.amount_due.amount,
            candidate.due_date,
            preview.fingerprint.value,
            preview.payroll_version,
            preview.payroll_version + 1,
            _child_idempotency_key(request.idempotency_key.value, ordinal),
            request.actor.actor_id,
            request.reason,
        ),
    )
    return int(cursor.lastrowid)


def _insert_obligation_projection(cursor, preview, allocation, event_id):
    candidate = preview.candidate
    cursor.execute(
        _OBLIGATION_INSERT_SQL,
        (
            allocation.obligation_identity,
            allocation.assignment_id,
            candidate.case_no,
            allocation.staff_id,
            allocation.obligation_kind.value,
            allocation.direction.value,
            allocation.source_obligation_identity,
            allocation.amount_due.amount,
            candidate.due_date,
            event_id,
            preview.payroll_version + 1,
        ),
    )


def _advance_payroll_version(cursor, request, receipt) -> None:
    cursor.execute(
        _ADVANCE_VERSION_SQL,
        (
            receipt.payroll_version,
            request.intent.case_no,
            request.expected_payroll_version.value,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("payroll_candidate_stale")


def _insert_outbox(cursor, request, preview, receipt) -> None:
    payload = {
        "case_no": receipt.case_no,
        "payroll_version": receipt.payroll_version,
        "adjustment_identity": receipt.adjustment_identity,
        "amount_ntd": receipt.amount_ntd,
        "allocation_count": receipt.allocation_count,
        "correlation_id": request.correlation_id.value,
    }
    cursor.execute(
        _OUTBOX_INSERT_SQL,
        (
            receipt.case_no,
            _hashed_identity("payroll-outbox", request.idempotency_key.value),
            _canonical_json(payload),
        ),
    )


def _insert_receipt(cursor, request, command_fingerprint, receipt) -> None:
    cursor.execute(
        _RECEIPT_INSERT_SQL,
        (
            request.idempotency_key.value,
            command_fingerprint.value,
            receipt.preview_fingerprint.value,
            receipt.case_no,
            receipt.payroll_version,
            _canonical_json(_receipt_payload(receipt)),
        ),
    )


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = PayrollAdjustmentReceipt(
        str(payload["case_no"]),
        int(payload["payroll_version"]),
        str(payload["adjustment_identity"]),
        int(payload["allocation_count"]),
        int(payload["amount_ntd"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
    )
    return StoredPayrollAdjustmentReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "payroll_version": receipt.payroll_version,
        "adjustment_identity": receipt.adjustment_identity,
        "allocation_count": receipt.allocation_count,
        "amount_ntd": receipt.amount_ntd,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _obligation_view(row):
    return {
        "obligation_identity": str(row["obligation_identity"]),
        "assignment_id": int(row["assignment_id"]),
        "case_no": str(row["case_no"]),
        "staff_id": int(row["staff_id"]),
        "obligation_kind": str(row["obligation_kind"]),
        "direction": str(row["direction"]),
        "source_obligation_identity": row["source_obligation_identity"],
        "amount_due_ntd": int(row["amount_due_ntd"]),
        "due_date": _date_value(row["due_date"]),
        "status": str(row["status"]),
        "payout_history_exists": bool(row["payout_history_exists"]),
    }


def _adjustment_view(row):
    return {
        "adjustment_identity": str(row["adjustment_identity"]),
        "amount_ntd": int(row["amount_ntd"]),
        "source_event_identity": str(row["source_event_identity"]),
        "actor": str(row["actor"]),
        "reason": str(row["reason"]),
        "created_at": _datetime_value(row["created_at"]),
    }


def _child_idempotency_key(parent_key, ordinal):
    return _hashed_identity(
        "payroll-obligation",
        f"{parent_key}:{ordinal}",
    )


def _hashed_identity(prefix, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise RuntimeError("payroll receipt snapshot must be an object")
    return payload


def _date_value(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _datetime_value(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError as error:
        _raise_if_transient(error)
        raise


def _raise_if_transient(error) -> None:
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        raise


_CASE_HEADER_SQL = (
    "SELECT COALESCE(account.aggregate_version,0) AS payroll_version,"
    "orders.staff_payment_due_date "
    "FROM orders LEFT JOIN payroll_case_accounts AS account "
    "ON account.case_no=orders.case_no WHERE orders.case_no=%s"
)
_EFFECTIVE_ASSIGNMENTS_SQL = (
    "SELECT assignment.id AS assignment_id,assignment.staff_id "
    "FROM scheduling_aggregates AS aggregate "
    "JOIN case_staff_assignments AS assignment "
    "ON assignment.case_no=aggregate.case_no "
    "AND assignment.generation_id=aggregate.effective_generation_id "
    "WHERE aggregate.case_no=%s AND assignment.status<>'cancelled' "
    "ORDER BY assignment.id"
)
_SOURCE_OBLIGATION_SQL = (
    "SELECT obligation_identity,payout_history_exists "
    "FROM staff_obligations WHERE assignment_id=%s "
    "AND obligation_kind='service_pay' "
    "ORDER BY payroll_version DESC,obligation_identity DESC LIMIT 1"
)
_ADJUSTMENT_EVENT_INSERT_SQL = (
    "INSERT INTO payroll_adjustment_events("
    "case_no,adjustment_identity,amount_ntd,source_event_identity,actor,"
    "reason,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s)"
)
_ALLOCATION_INSERT_SQL = (
    "INSERT INTO payroll_adjustment_allocations("
    "adjustment_event_id,assignment_id,amount_ntd,allocation_ordinal) "
    "VALUES (%s,%s,%s,%s)"
)
_OBLIGATION_EVENT_INSERT_SQL = (
    "INSERT INTO staff_obligation_events("
    "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,event_type,before_amount_ntd,"
    "after_amount_ntd,due_date,payroll_fingerprint,"
    "expected_payroll_version,resulting_payroll_version,idempotency_key,"
    "actor,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,"
    "%s,%s,%s)"
)
_OBLIGATION_INSERT_SQL = (
    "INSERT INTO staff_obligations("
    "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,amount_due_ntd,due_date,status,"
    "current_event_id,payroll_version,payout_history_exists) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s,0)"
)
_ADVANCE_VERSION_SQL = (
    "UPDATE payroll_case_accounts SET aggregate_version=%s "
    "WHERE case_no=%s AND aggregate_version=%s"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO payroll_outbox(case_no,intent_key,intent_type,"
    "payload_snapshot) VALUES (%s,%s,'staff_obligation_changed',%s)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO payroll_apply_receipts(idempotency_key,command_fingerprint,"
    "preview_fingerprint,case_no,resulting_payroll_version,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot FROM payroll_apply_receipts "
    "WHERE idempotency_key=%s"
)
_OBLIGATION_COLUMNS = (
    "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,amount_due_ntd,due_date,status,"
    "payout_history_exists"
)
_CASE_OBLIGATIONS_SQL = (
    f"SELECT {_OBLIGATION_COLUMNS} FROM staff_obligations "
    "WHERE case_no=%s ORDER BY staff_id,due_date,obligation_identity"
)
_STAFF_OBLIGATIONS_SQL = (
    f"SELECT {_OBLIGATION_COLUMNS} FROM staff_obligations "
    "WHERE staff_id=%s ORDER BY due_date,case_no,obligation_identity"
)
_CASE_ADJUSTMENTS_SQL = (
    "SELECT adjustment_identity,amount_ntd,source_event_identity,actor,"
    "reason,created_at FROM payroll_adjustment_events "
    "WHERE case_no=%s ORDER BY id"
)

__all__ = [
    "MySqlPayrollAdjustmentRepository",
    "PayrollAdjustmentMySqlUnitOfWork",
]

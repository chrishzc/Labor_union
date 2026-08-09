"""MySQL adapter for atomic financial adjustments."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import hashlib
import json
from typing import Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.client_finance.financial_adjustment import (
    FinancialAdjustmentAssignmentFact,
    FinancialAdjustmentFacts,
    FinancialAdjustmentReversalTarget,
    FinancialAdjustmentScope,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.financial_adjustment_workflow import (
    FinancialAdjustmentApplyRequest,
    FinancialAdjustmentReceipt,
    FinancialAdjustmentStorageError,
    StoredFinancialAdjustmentReceipt,
)

_RETRYABLE_MYSQL_CODES = frozenset({1062, 1205, 1213})


class FinancialAdjustmentMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_storage_error(error)

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_storage_error(error)


class MySqlFinancialAdjustmentRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    # Kept whole so both Domain versions and selected roots share one snapshot.
    def load(self, intent, *, for_update):
        with _mysql_cursor(self._connection) as cursor:
            if for_update:
                _ensure_accounts(cursor, intent.case_no, intent.scope)
            account_row = _load_account_row(cursor, intent.case_no, for_update)
            if account_row is None:
                raise ValueError("client_finance_case_not_found")
            assignments = _load_assignments(
                cursor,
                intent.case_no,
                intent.assignment_allocations,
                for_update,
            )
            reversal_target = _load_reversal_target(
                cursor,
                intent.case_no,
                intent.reversal_of_adjustment_identity,
                for_update,
            )
        return FinancialAdjustmentFacts(
            intent.case_no,
            int(account_row["client_account_version"]),
            int(account_row["payroll_version"]),
            assignments,
            reversal_target,
        )

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    # Kept cohesive because all rows form one immutable accounting event.
    def persist(self, request, preview, command_fingerprint, receipt) -> None:
        candidate = preview.candidate
        with _mysql_cursor(self._connection) as cursor:
            reversal_target_id = _reversal_target_id(cursor, candidate)
            adjustment_id = _insert_adjustment(
                cursor,
                request,
                candidate,
                reversal_target_id,
            )
            _insert_staff_allocations(cursor, adjustment_id, candidate)
            _insert_client_obligation(cursor, request, preview)
            _insert_payroll_side(cursor, request, preview)
            _advance_versions(cursor, request, receipt)
            _insert_outboxes(cursor, request, receipt)
            _insert_receipt(cursor, request, command_fingerprint, receipt)

    def query(self, case_no):
        with _mysql_cursor(self._connection) as cursor:
            account = _load_account_row(cursor, case_no, False)
            if account is None:
                raise ValueError("client_finance_case_not_found")
            assignments = _query_effective_assignments(cursor, case_no)
            adjustments = _query_adjustments(cursor, case_no)
        return {
            "case_no": case_no,
            "client_account_version": int(account["client_account_version"]),
            "payroll_version": int(account["payroll_version"]),
            "effective_assignments": assignments,
            "adjustments": adjustments,
        }


@contextmanager
def _mysql_cursor(connection) -> Iterator:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except (IntegrityError, OperationalError) as error:
        _raise_storage_error(error)


def _ensure_accounts(cursor, case_no, scope) -> None:
    cursor.execute(
        "INSERT IGNORE INTO client_finance_accounts(case_no) VALUES (%s)",
        (case_no,),
    )
    if scope is FinancialAdjustmentScope.CLIENT_ONLY:
        return
    cursor.execute(
        "INSERT IGNORE INTO payroll_case_accounts(case_no) VALUES (%s)",
        (case_no,),
    )


def _load_account_row(cursor, case_no, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT o.case_no,"
        "COALESCE(client.aggregate_version,0) AS client_account_version,"
        "COALESCE(payroll.aggregate_version,0) AS payroll_version "
        "FROM orders o LEFT JOIN client_finance_accounts client "
        "ON client.case_no=o.case_no LEFT JOIN payroll_case_accounts payroll "
        "ON payroll.case_no=o.case_no WHERE o.case_no=%s" + suffix,
        (case_no,),
    )
    return cursor.fetchone()


def _load_assignments(cursor, case_no, allocation_intents, lock):
    assignment_ids = tuple(item.assignment_id for item in allocation_intents)
    placeholders = _placeholders(assignment_ids)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT assignment.id,assignment.staff_id,assignment.status,"
        "orders.staff_payment_due_date FROM case_staff_assignments assignment "
        "JOIN orders ON orders.case_no=assignment.case_no "
        f"WHERE assignment.id IN ({placeholders}) "
        f"AND assignment.case_no=%s ORDER BY assignment.id{suffix}",
        (*assignment_ids, case_no),
    )
    return tuple(_assignment_fact(row) for row in cursor.fetchall())


def _assignment_fact(row):
    return FinancialAdjustmentAssignmentFact(
        int(row["id"]),
        int(row["staff_id"]),
        row.get("staff_payment_due_date"),
        str(row["status"]) == "cancelled",
    )


# Kept whole so reversal capacity is read from one locked aggregate query.
def _load_reversal_target(cursor, case_no, identity, lock):
    if identity is None:
        return None
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT target.adjustment_identity,target.case_no,target.adjustment_scope,"
        "target.amount_delta_ntd,"
        "COALESCE(SUM(reversal.amount_delta_ntd),0) AS reversed_amount_ntd "
        "FROM financial_adjustments target "
        "LEFT JOIN financial_adjustments reversal "
        "ON reversal.reversal_of_adjustment_id=target.id "
        "AND reversal.cancelled_at IS NULL "
        "WHERE target.adjustment_identity=%s AND target.case_no=%s "
        "AND target.cancelled_at IS NULL "
        "GROUP BY target.id,target.adjustment_identity,target.case_no,"
        "target.amount_delta_ntd,target.adjustment_scope" + suffix,
        (identity, case_no),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return FinancialAdjustmentReversalTarget(
        str(row["adjustment_identity"]),
        str(row["case_no"]),
        MoneyNTD(int(row["amount_delta_ntd"])),
        MoneyNTD(int(row["reversed_amount_ntd"])),
        FinancialAdjustmentScope(str(row["adjustment_scope"])),
    )


def _reversal_target_id(cursor, candidate):
    identity = candidate.reversal_of_adjustment_identity
    if identity is None:
        return None
    cursor.execute(
        "SELECT id FROM financial_adjustments "
        "WHERE adjustment_identity=%s AND case_no=%s FOR UPDATE",
        (identity, candidate.case_no),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("financial_adjustment_reversal_target_invalid")
    return int(row["id"])


def _insert_adjustment(cursor, request, candidate, reversal_target_id):
    cursor.execute(
        _ADJUSTMENT_INSERT_SQL,
        (
            candidate.adjustment_identity,
            candidate.case_no,
            candidate.source_type.value,
            candidate.scope.value,
            candidate.source_event_identity,
            candidate.amount_delta.amount,
            candidate.reason,
            reversal_target_id,
            request.idempotency_key.value,
        ),
    )
    return int(cursor.lastrowid)


def _insert_staff_allocations(cursor, adjustment_id, candidate) -> None:
    for allocation in candidate.assignment_allocations:
        cursor.execute(
            _STAFF_ALLOCATION_INSERT_SQL,
            (
                adjustment_id,
                allocation.assignment_id,
                allocation.amount_delta.amount,
            ),
        )


def _insert_payroll_side(cursor, request, preview) -> None:
    if preview.candidate.scope is FinancialAdjustmentScope.CLIENT_ONLY:
        return
    payroll_event_id = _insert_payroll_adjustment(cursor, request, preview)
    _insert_staff_obligations(
        cursor,
        request,
        preview,
        payroll_event_id,
    )


# Kept whole so the immutable event and its projection cannot drift.
def _insert_client_obligation(cursor, request, preview) -> None:
    candidate = preview.candidate
    amount_due = abs(candidate.amount_delta.amount)
    cursor.execute(
        _CLIENT_OBLIGATION_EVENT_INSERT_SQL,
        (
            candidate.client_obligation_identity,
            candidate.case_no,
            candidate.client_direction.value,
            amount_due,
            candidate.source_event_identity,
            preview.client_account_version,
            _child_key(request, "client-obligation-event", 0),
            request.actor.actor_id,
            _audit_reason(candidate),
        ),
    )
    event_id = int(cursor.lastrowid)
    cursor.execute(
        _CLIENT_OBLIGATION_INSERT_SQL,
        (
            candidate.client_obligation_identity,
            candidate.case_no,
            candidate.client_direction.value,
            amount_due,
            event_id,
            preview.client_account_version + 1,
        ),
    )


def _insert_payroll_adjustment(cursor, request, preview):
    candidate = preview.candidate
    cursor.execute(
        _PAYROLL_ADJUSTMENT_INSERT_SQL,
        (
            candidate.case_no,
            candidate.adjustment_identity,
            candidate.amount_delta.amount,
            candidate.source_event_identity,
            request.actor.actor_id,
            _audit_reason(candidate),
            _child_key(request, "payroll-adjustment", 0),
        ),
    )
    return int(cursor.lastrowid)


# Kept whole so each allocation creates its ledger and obligation pair together.
def _insert_staff_obligations(cursor, request, preview, payroll_event_id) -> None:
    for ordinal, allocation in enumerate(
        preview.candidate.assignment_allocations,
        start=1,
    ):
        _insert_payroll_allocation(
            cursor,
            payroll_event_id,
            allocation,
            ordinal,
        )
        obligation_event_id = _insert_staff_obligation_event(
            cursor,
            request,
            preview,
            allocation,
            ordinal,
        )
        _insert_staff_obligation(
            cursor,
            preview,
            allocation,
            obligation_event_id,
        )


def _insert_payroll_allocation(cursor, event_id, allocation, ordinal) -> None:
    cursor.execute(
        _PAYROLL_ALLOCATION_INSERT_SQL,
        (
            event_id,
            allocation.assignment_id,
            allocation.amount_delta.amount,
            ordinal,
        ),
    )


# Kept whole so event direction and version share one candidate snapshot.
def _insert_staff_obligation_event(
    cursor,
    request,
    preview,
    allocation,
    ordinal,
):
    positive = allocation.amount_delta.amount > 0
    obligation_kind = "adjustment" if positive else "reversal"
    cursor.execute(
        _STAFF_OBLIGATION_EVENT_INSERT_SQL,
        (
            allocation.obligation_identity,
            allocation.assignment_id,
            preview.candidate.case_no,
            allocation.staff_id,
            obligation_kind,
            allocation.direction.value,
            obligation_kind,
            abs(allocation.amount_delta.amount),
            allocation.due_date,
            preview.fingerprint.value,
            preview.payroll_version,
            preview.payroll_version + 1,
            _child_key(request, "staff-obligation-event", ordinal),
            request.actor.actor_id,
            _audit_reason(preview.candidate),
        ),
    )
    return int(cursor.lastrowid)


def _insert_staff_obligation(cursor, preview, allocation, event_id) -> None:
    positive = allocation.amount_delta.amount > 0
    obligation_kind = "adjustment" if positive else "reversal"
    cursor.execute(
        _STAFF_OBLIGATION_INSERT_SQL,
        (
            allocation.obligation_identity,
            allocation.assignment_id,
            preview.candidate.case_no,
            allocation.staff_id,
            obligation_kind,
            allocation.direction.value,
            abs(allocation.amount_delta.amount),
            allocation.due_date,
            event_id,
            preview.payroll_version + 1,
        ),
    )


# Kept whole because applicable Domain compare-and-swap checks are one invariant.
def _advance_versions(cursor, request, receipt) -> None:
    cursor.execute(
        "UPDATE client_finance_accounts SET aggregate_version=%s "
        "WHERE case_no=%s AND aggregate_version=%s",
        (
            receipt.client_account_version,
            receipt.case_no,
            request.expected_client_account_version.value,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("financial_adjustment_candidate_stale")
    if receipt.payroll_version is None:
        return
    cursor.execute(
        "UPDATE payroll_case_accounts SET aggregate_version=%s "
        "WHERE case_no=%s AND aggregate_version=%s",
        (
            receipt.payroll_version,
            receipt.case_no,
            request.expected_payroll_version.value,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("financial_adjustment_candidate_stale")


def _insert_outboxes(cursor, request, receipt) -> None:
    payload = _canonical_json(_receipt_payload(receipt))
    cursor.execute(
        _CLIENT_OUTBOX_INSERT_SQL,
        (
            receipt.case_no,
            _child_key(request, "client-outbox", 0),
            payload,
        ),
    )
    if receipt.payroll_version is None:
        return
    cursor.execute(
        _PAYROLL_OUTBOX_INSERT_SQL,
        (
            receipt.case_no,
            _child_key(request, "payroll-outbox", 0),
            payload,
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
            receipt.client_account_version,
            receipt.payroll_version,
            _canonical_json(_receipt_payload(receipt)),
        ),
    )


def _query_effective_assignments(cursor, case_no):
    cursor.execute(
        "SELECT assignment.id AS assignment_id,assignment.staff_id,"
        "assignment.status,orders.staff_payment_due_date "
        "FROM case_staff_assignments assignment JOIN orders "
        "ON orders.case_no=assignment.case_no WHERE assignment.case_no=%s "
        "AND assignment.status<>'cancelled' ORDER BY assignment.id",
        (case_no,),
    )
    return tuple(
        {
            "assignment_id": int(row["assignment_id"]),
            "staff_id": int(row["staff_id"]),
            "status": str(row["status"]),
            "staff_payment_due_date": _date_text(
                row.get("staff_payment_due_date")
            ),
        }
        for row in cursor.fetchall()
    )


# Kept as one read model so UI never reconstructs cross-domain balances.
def _query_adjustments(cursor, case_no):
    cursor.execute(
        "SELECT adjustment.id,adjustment.adjustment_identity,"
        "adjustment.adjustment_scope,"
        "adjustment.adjustment_source_type,adjustment.source_event_identity,"
        "adjustment.amount_delta_ntd,adjustment.reason,"
        "target.adjustment_identity AS reversal_of_adjustment_identity,"
        "adjustment.cancelled_at,adjustment.created_at,"
        "client_obligation.amount_due_ntd AS client_amount_due_ntd,"
        "client_obligation.status AS client_status "
        "FROM financial_adjustments adjustment "
        "LEFT JOIN financial_adjustments target "
        "ON target.id=adjustment.reversal_of_adjustment_id "
        "LEFT JOIN client_obligation_events client_event "
        "ON client_event.case_no=adjustment.case_no "
        "AND client_event.source_event_identity="
        "adjustment.source_event_identity "
        "LEFT JOIN client_obligations client_obligation "
        "ON client_obligation.current_event_id=client_event.id "
        "WHERE adjustment.case_no=%s ORDER BY adjustment.created_at,adjustment.id",
        (case_no,),
    )
    rows = tuple(cursor.fetchall())
    return tuple(_adjustment_view(cursor, row) for row in rows)


# Kept whole so each adjustment read model includes its complete allocation set.
def _adjustment_view(cursor, row):
    adjustment_id = int(row["id"])
    cursor.execute(
        "SELECT allocation.assignment_id,assignment.staff_id,"
        "allocation.amount_delta_ntd FROM "
        "financial_adjustment_staff_allocations allocation "
        "JOIN case_staff_assignments assignment "
        "ON assignment.id=allocation.assignment_id "
        "WHERE allocation.financial_adjustment_id=%s "
        "ORDER BY allocation.assignment_id",
        (adjustment_id,),
    )
    allocations = tuple(
        {
            "assignment_id": int(item["assignment_id"]),
            "staff_id": int(item["staff_id"]),
            "amount_delta_ntd": int(item["amount_delta_ntd"]),
        }
        for item in cursor.fetchall()
    )
    return {
        "adjustment_identity": str(row["adjustment_identity"]),
        "scope": str(row["adjustment_scope"]),
        "source_type": str(row["adjustment_source_type"]),
        "source_event_identity": str(row["source_event_identity"]),
        "amount_delta_ntd": int(row["amount_delta_ntd"]),
        "reason": row.get("reason"),
        "reversal_of_adjustment_identity": row.get(
            "reversal_of_adjustment_identity"
        ),
        "cancelled_at": _datetime_text(row.get("cancelled_at")),
        "created_at": _datetime_text(row.get("created_at")),
        "client_amount_due_ntd": int(row["client_amount_due_ntd"]),
        "client_status": str(row["client_status"]),
        "assignment_allocations": allocations,
    }


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = FinancialAdjustmentReceipt(
        str(payload["case_no"]),
        str(payload["adjustment_identity"]),
        int(payload["amount_delta_ntd"]),
        int(payload["client_account_version"]),
        _optional_integer(payload.get("payroll_version")),
        int(payload["assignment_allocation_count"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
    )
    return StoredFinancialAdjustmentReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "adjustment_identity": receipt.adjustment_identity,
        "amount_delta_ntd": receipt.amount_delta_ntd,
        "client_account_version": receipt.client_account_version,
        "payroll_version": receipt.payroll_version,
        "assignment_allocation_count": receipt.assignment_allocation_count,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _audit_reason(candidate):
    if candidate.reason is not None:
        return candidate.reason
    return f"preview_recalculation:{candidate.source_event_identity}"


def _child_key(request, purpose, ordinal):
    seed = f"{request.idempotency_key.value}:{purpose}:{ordinal}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"financial-adjustment:{digest}"


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value) -> Mapping[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, Mapping) else {}


def _date_text(value):
    return value.isoformat() if isinstance(value, date) else None


def _datetime_text(value):
    return value.isoformat() if value is not None else None


def _optional_integer(value):
    return None if value is None else int(value)


def _placeholders(values):
    return ",".join("%s" for _ in values) if values else "NULL"


def _raise_storage_error(error):
    code = int(error.args[0]) if error.args and str(error.args[0]).isdigit() else -1
    raise FinancialAdjustmentStorageError(
        "financial adjustment storage failed",
        retryable=code in _RETRYABLE_MYSQL_CODES,
    ) from error


_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot "
    "FROM financial_adjustment_apply_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_ADJUSTMENT_INSERT_SQL = (
    "INSERT INTO financial_adjustments "
    "(adjustment_identity,case_no,adjustment_source_type,adjustment_scope,"
    "source_event_identity,amount_delta_ntd,reason,"
    "reversal_of_adjustment_id,apply_idempotency_key) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_STAFF_ALLOCATION_INSERT_SQL = (
    "INSERT INTO financial_adjustment_staff_allocations "
    "(financial_adjustment_id,assignment_id,amount_delta_ntd) "
    "VALUES (%s,%s,%s)"
)
_CLIENT_OBLIGATION_EVENT_INSERT_SQL = (
    "INSERT INTO client_obligation_events "
    "(obligation_identity,case_no,obligation_type,direction,event_type,"
    "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
    "source_event_identity,source_obligation_identity,"
    "expected_account_version,idempotency_key,actor,reason) "
    "VALUES (%s,%s,'adjustment',%s,'adjusted',0,%s,NULL,NULL,%s,NULL,%s,%s,%s,%s)"
)
_CLIENT_OBLIGATION_INSERT_SQL = (
    "INSERT INTO client_obligations "
    "(obligation_identity,case_no,obligation_type,direction,"
    "source_obligation_identity,amount_due_ntd,due_date,status,"
    "current_event_id,projection_version) "
    "VALUES (%s,%s,'adjustment',%s,NULL,%s,NULL,'open',%s,%s)"
)
_PAYROLL_ADJUSTMENT_INSERT_SQL = (
    "INSERT INTO payroll_adjustment_events "
    "(case_no,adjustment_identity,amount_ntd,source_event_identity,"
    "actor,reason,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s)"
)
_PAYROLL_ALLOCATION_INSERT_SQL = (
    "INSERT INTO payroll_adjustment_allocations "
    "(adjustment_event_id,assignment_id,amount_ntd,allocation_ordinal) "
    "VALUES (%s,%s,%s,%s)"
)
_STAFF_OBLIGATION_EVENT_INSERT_SQL = (
    "INSERT INTO staff_obligation_events "
    "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,event_type,before_amount_ntd,"
    "after_amount_ntd,due_date,payroll_fingerprint,"
    "expected_payroll_version,resulting_payroll_version,idempotency_key,"
    "actor,reason) VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,0,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_STAFF_OBLIGATION_INSERT_SQL = (
    "INSERT INTO staff_obligations "
    "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
    "direction,source_obligation_identity,amount_due_ntd,due_date,status,"
    "current_event_id,payroll_version,payout_history_exists) "
    "VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,'open',%s,%s,0)"
)
_CLIENT_OUTBOX_INSERT_SQL = (
    "INSERT INTO client_finance_outbox "
    "(case_no,intent_type,intent_key,payload_snapshot) "
    "VALUES (%s,'projection_refresh',%s,%s)"
)
_PAYROLL_OUTBOX_INSERT_SQL = (
    "INSERT INTO payroll_outbox "
    "(case_no,intent_key,intent_type,payload_snapshot) "
    "VALUES (%s,%s,'staff_obligation_changed',%s)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO financial_adjustment_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "resulting_client_account_version,resulting_payroll_version,"
    "result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)"
)

__all__ = [
    "FinancialAdjustmentMySqlUnitOfWork",
    "MySqlFinancialAdjustmentRepository",
]

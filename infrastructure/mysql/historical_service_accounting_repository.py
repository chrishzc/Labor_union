"""
File: historical_service_accounting_repository.py
Description: 支援計次歷史服務帳務的 MySQL 持久化儲存與查詢配接器。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import json

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import AssignmentRateSnapshot, PayrollPolicyKind
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalServiceAccountingFacts,
    HistoricalServiceAccountingReceipt,
    StoredHistoricalServiceAccountingReceipt,
    _command_fingerprint,
)

class MySqlHistoricalServiceAccountingRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no: str, *, for_update: bool) -> HistoricalServiceAccountingFacts:
        lock = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(_ROOT_SQL + lock, (case_no,))
            root = cursor.fetchone()
            if root is None:
                raise ValueError("historical_order_not_found")
            if (
                root["client_policy_version"] is None
                or root["client_hourly_rate_ntd"] is None
            ):
                raise ValueError("historical_client_payment_terms_missing")
            cursor.execute(_ASSIGNMENTS_SQL + lock, (int(root["adoption_receipt_id"]),))
            rows = tuple(cursor.fetchall())
            if any(
                row["payroll_policy_version"] is None
                or row["payroll_policy_kind"] is None
                or row["payroll_hourly_rate_ntd"] is None
                for row in rows
            ):
                raise ValueError("historical_payroll_rate_policy_missing")
            adjustment_rows = _load_adjustments(
                cursor,
                tuple(int(row["assignment_id"]) for row in rows),
                lock,
            )
        adjustments = {
            int(row["assignment_id"]): MoneyNTD(int(row["amount_ntd"]))
            for row in adjustment_rows
        }
        assignments = tuple(
            HistoricalServiceAccountingAssignmentFacts(
                f"assignment:{int(row['assignment_id'])}",
                int(row["staff_id"]),
                str(row["staff_name"]),
                AssignmentRateSnapshot(
                    f"assignment:{int(row['assignment_id'])}",
                    str(row["payroll_policy_version"]),
                    PayrollPolicyKind(str(row["payroll_policy_kind"])),
                    MoneyNTD(int(row["payroll_hourly_rate_ntd"])),
                ),
                adjustments.get(int(row["assignment_id"]), MoneyNTD(0)),
            )
            for row in rows
        )
        return HistoricalServiceAccountingFacts(
            str(root["case_no"]),
            OrderLifecycleStatus(str(root["status"])),
            int(root["lifecycle_version"]),
            int(root["adoption_receipt_id"]),
            str(root["source_event_identity"]),
            int(root["historical_day_revision"]),
            int(root["client_finance_version"]),
            int(root["payroll_version"]),
            int(root["service_days"]),
            Decimal(str(root["service_hours_per_day"])),
            MoneyNTD(int(root["floor_fee"])),
            str(root["identity_status"]),
            assignments,
            str(root["client_policy_version"]),
            MoneyNTD(int(root["client_hourly_rate_ntd"])),
            _date_value(root["completed_on"]),
            _optional_date_value(root["staff_payment_due_date"]),
        )

    def find_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM historical_service_day_events "
                "WHERE idempotency_key=%s FOR UPDATE",
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _object(row["result_snapshot"])
        return StoredHistoricalServiceAccountingReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])),
            HistoricalServiceAccountingReceipt(
                str(payload["case_no"]),
                int(payload["resulting_historical_day_revision"]),
                int(payload["resulting_client_finance_version"]),
                int(payload["resulting_payroll_version"]),
                int(payload["total_actual_service_days"]),
                int(payload["client_obligation_amount_ntd"]),
                int(payload["staff_obligation_amount_ntd"]),
                PreviewFingerprint(str(payload["preview_fingerprint"])),
            ),
        )

    def persist(self, request, candidate):
        resulting_day_revision = candidate.facts.historical_day_revision + 1
        receipt = HistoricalServiceAccountingReceipt(
            candidate.facts.case_no,
            resulting_day_revision,
            candidate.facts.client_finance_version,
            candidate.facts.payroll_version,
            candidate.service_days.total_actual_service_days,
            candidate.client_finance.total_receivable.amount,
            candidate.payroll.total_payable.amount,
            candidate.fingerprint,
        )
        result_snapshot = _receipt_payload(receipt)
        command_fingerprint = _command_fingerprint(request).value
        event_identity = f"historical-service-days:{command_fingerprint}"
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_service_day_events "
                "(event_identity,case_no,historical_adoption_receipt_id,expected_day_revision,"
                "resulting_day_revision,total_actual_service_days,total_actual_service_hours,"
                "historical_floor_fee_ntd,client_obligation_amount_ntd,staff_obligation_amount_ntd,"
                "preview_fingerprint,command_fingerprint,idempotency_key,actor_id,reason,correlation_id,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_identity,
                    candidate.facts.case_no,
                    candidate.facts.adoption_receipt_id,
                    candidate.facts.historical_day_revision,
                    resulting_day_revision,
                    candidate.service_days.total_actual_service_days,
                    candidate.service_days.total_actual_service_hours,
                    candidate.service_days.historical_floor_fee_ntd,
                    candidate.client_finance.total_receivable.amount,
                    candidate.payroll.total_payable.amount,
                    candidate.fingerprint.value,
                    command_fingerprint,
                    request.idempotency_key.value,
                    request.actor.actor_id,
                    request.reason,
                    request.correlation_id.value,
                    _json(result_snapshot),
                ),
            )
            event_id = int(cursor.lastrowid)
            _insert_items(cursor, event_id, candidate)
            cursor.execute(
                "INSERT INTO historical_service_day_projections "
                "(case_no,current_event_id,historical_adoption_receipt_id,day_revision,total_actual_service_days,total_actual_service_hours) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "current_event_id=VALUES(current_event_id),historical_adoption_receipt_id=VALUES(historical_adoption_receipt_id),"
                "day_revision=VALUES(day_revision),total_actual_service_days=VALUES(total_actual_service_days),"
                "total_actual_service_hours=VALUES(total_actual_service_hours)",
                (
                    candidate.facts.case_no,
                    event_id,
                    candidate.facts.adoption_receipt_id,
                    resulting_day_revision,
                    candidate.service_days.total_actual_service_days,
                    candidate.service_days.total_actual_service_hours,
                ),
            )
            cursor.execute(
                "INSERT INTO historical_service_accounting_outbox "
                "(event_id,intent_key,intent_type,bounded_snapshot) VALUES (%s,%s,'historical_service_accounting_applied',%s)",
                (event_id, f"{request.idempotency_key.value}:applied", _json(result_snapshot)),
            )
        return receipt


def _insert_items(cursor, event_id, candidate):
    payroll = {item.assignment_identity: item for item in candidate.payroll.assignments}
    facts = {item.assignment_identity: item for item in candidate.facts.assignments}
    rows = []
    for ordinal, allocation in enumerate(candidate.service_days.allocations, start=1):
        assignment = facts[allocation.assignment_identity]
        payable = payroll[allocation.assignment_identity]
        rows.append((
            event_id,
            _assignment_id(allocation.assignment_identity),
            allocation.staff_id,
            ordinal,
            allocation.actual_service_days,
            allocation.actual_service_hours,
            allocation.floor_fee_ntd,
            payable.total_payable.amount,
            assignment.rate_snapshot.policy_version,
            assignment.rate_snapshot.policy_kind.value,
            assignment.rate_snapshot.hourly_rate.amount,
        ))
    cursor.executemany(
        "INSERT INTO historical_service_day_items "
        "(event_id,assignment_id,staff_id,item_ordinal,actual_service_days,actual_service_hours,"
        "floor_fee_allocated_ntd,staff_obligation_amount_ntd,payroll_policy_version,payroll_policy_kind,hourly_rate_ntd) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        rows,
    )


def _assignment_id(identity):
    value = str(identity).removeprefix("assignment:")
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    return int(value)


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "resulting_historical_day_revision": receipt.resulting_historical_day_revision,
        "resulting_client_finance_version": receipt.resulting_client_finance_version,
        "resulting_payroll_version": receipt.resulting_payroll_version,
        "total_actual_service_days": receipt.total_actual_service_days,
        "client_obligation_amount_ntd": receipt.client_obligation_amount_ntd,
        "staff_obligation_amount_ntd": receipt.staff_obligation_amount_ntd,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _object(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict):
        raise ValueError("historical_accounting_obligation_binding_invalid")
    return result


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _date_value(value) -> date:
    if not isinstance(value, date):
        raise ValueError("historical_order_completion_date_missing")
    return value


def _optional_date_value(value) -> date | None:
    if value is None:
        return None
    return _date_value(value)


_ROOT_SQL = (
    "SELECT o.case_no,o.status,o.lifecycle_version,o.service_days,o.service_hours_per_day,o.floor_fee,"
    "COALESCE(o.actual_end_date,o.end_date) AS completed_on,o.staff_payment_due_date,"
    "c.identity_status,COALESCE(client_account.aggregate_version,0) AS client_finance_version,"
    "COALESCE(payroll_account.aggregate_version,0) AS payroll_version,receipt.id AS adoption_receipt_id,"
    "receipt.source_event_identity,COALESCE(day_projection.day_revision,0) AS historical_day_revision,"
    "client_terms.policy_version AS client_policy_version,client_terms.client_hourly_rate_ntd "
    "FROM orders o JOIN clients c ON c.id=o.client_id "
    "LEFT JOIN client_finance_accounts client_account ON client_account.case_no=o.case_no "
    "LEFT JOIN payroll_case_accounts payroll_account ON payroll_account.case_no=o.case_no "
    "LEFT JOIN client_payment_terms client_terms ON client_terms.case_no=o.case_no "
    "JOIN historical_order_adoption_receipts receipt ON receipt.id=("
    "SELECT MAX(r.id) FROM historical_order_adoption_receipts r WHERE r.case_no=o.case_no AND r.outcome='adopted') "
    "LEFT JOIN historical_service_day_projections day_projection ON day_projection.case_no=o.case_no "
    "WHERE o.case_no=%s"
)
_ASSIGNMENTS_SQL = (
    "SELECT evidence.assignment_id,evidence.staff_id,staff.name AS staff_name,"
    "COALESCE(rate.policy_version,case_rate.policy_version) AS payroll_policy_version,"
    "COALESCE(rate.policy_kind,case_rate.policy_kind) AS payroll_policy_kind,"
    "COALESCE(rate.hourly_rate_ntd,case_rate.hourly_rate_ntd) AS payroll_hourly_rate_ntd "
    "FROM historical_order_pairing_evidence evidence "
    "JOIN case_staff_assignments assignment ON assignment.id=evidence.assignment_id "
    "AND assignment.staff_id=evidence.staff_id AND assignment.status IN ('planned','active','completed') "
    "JOIN historical_order_adoption_receipts receipt ON receipt.id=evidence.receipt_id "
    "AND receipt.case_no=assignment.case_no AND receipt.outcome='adopted' "
    "JOIN staff ON staff.id=evidence.staff_id "
    "LEFT JOIN case_payroll_rate_policy_snapshots case_rate ON case_rate.case_no=assignment.case_no "
    "LEFT JOIN assignment_payroll_rate_snapshots rate ON rate.assignment_id=evidence.assignment_id "
    "WHERE evidence.receipt_id=%s AND evidence.assignment_id IS NOT NULL "
    "ORDER BY evidence.assignment_id"
)


def _load_adjustments(cursor, assignment_ids, lock):
    if not assignment_ids:
        return ()
    placeholders = ",".join("%s" for _ in assignment_ids)
    cursor.execute(
        "SELECT assignment_id,COALESCE(SUM(amount_ntd),0) AS amount_ntd "
        "FROM payroll_adjustment_allocations WHERE assignment_id IN ("
        + placeholders
        + ") GROUP BY assignment_id"
        + lock,
        assignment_ids,
    )
    return tuple(cursor.fetchall())


__all__ = ["MySqlHistoricalServiceAccountingRepository"]

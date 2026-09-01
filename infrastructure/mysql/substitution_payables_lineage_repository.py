"""Read-only MySQL projection for Scheduling substitution payroll lineage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Iterator, Mapping

from subsystems.scheduling.substitution_payables_lineage import (
    StaffPayablesEvidence,
    SubstitutionPayablesLineageItem,
    SubstitutionPayablesLineageReadback,
)


class MySqlSubstitutionPayablesLineageRepository:
    """Compose immutable owner rows without writing or opening a transaction."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def query(self, case_no: str, batch_key: str) -> SubstitutionPayablesLineageReadback:
        with _cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SQL, (case_no, batch_key))
            receipt = cursor.fetchone()
            if receipt is None:
                raise ValueError("substitution_payables_lineage_not_found")
            cursor.execute(_OUTCOMES_SQL, (batch_key, case_no))
            outcomes = tuple(cursor.fetchall())

            items = tuple(
                self._item(cursor, receipt, outcome)
                for outcome in outcomes
            )

        root_blockers = _root_blockers(receipt, items)
        return SubstitutionPayablesLineageReadback(
            case_no=str(receipt["case_no"]),
            batch_key=str(receipt["batch_key"]),
            scheduling_receipt_id=int(receipt["scheduling_receipt_id"]),
            scheduling_version=int(receipt["resulting_scheduling_version"]),
            scheduling_generation=int(receipt["resulting_generation_number"]),
            expected_payroll_version=int(receipt["expected_payroll_version"]),
            resulting_payroll_version=int(receipt["resulting_payroll_version"]),
            items=items,
            authoritative_complete=not root_blockers and all(not item.blockers for item in items),
            blockers=root_blockers,
        )

    def _item(self, cursor, receipt: Mapping[str, object], outcome: Mapping[str, object]):
        case_no = str(receipt["case_no"])
        resulting_assignment_id = int(outcome["resulting_assignment_id"])
        resulting_staff_id = int(outcome["resulting_staff_id"])
        resulting_payroll_version = int(receipt["resulting_payroll_version"])
        cursor.execute(
            _PAYROLL_EVENT_SQL,
            (case_no, resulting_assignment_id, resulting_staff_id, resulting_payroll_version),
        )
        events = tuple(cursor.fetchall())
        blockers: list[str] = []
        event = events[0] if len(events) == 1 else None
        if not events:
            blockers.append("payroll_obligation_event_missing")
        elif len(events) > 1:
            blockers.append("payroll_obligation_event_ambiguous")

        evidence = None
        payroll_event_id = None
        expected_version = None
        event_resulting_version = None
        payroll_fingerprint = None
        if event is not None:
            payroll_event_id = int(event["id"])
            expected_version = int(event["expected_payroll_version"])
            event_resulting_version = int(event["resulting_payroll_version"])
            payroll_fingerprint = str(event["payroll_fingerprint"])
            if event_resulting_version != resulting_payroll_version:
                blockers.append("payroll_obligation_version_mismatch")
            if expected_version + 1 != event_resulting_version:
                blockers.append("payroll_obligation_version_invalid")
            if int(event["assignment_id"]) != resulting_assignment_id or int(event["staff_id"]) != resulting_staff_id:
                blockers.append("payroll_obligation_assignment_mismatch")
            cursor.execute(_OBLIGATION_SQL, (str(event["obligation_identity"]), case_no))
            obligation = cursor.fetchone()
            if obligation is None:
                blockers.append("payroll_obligation_projection_missing")
            else:
                if int(obligation["current_event_id"]) != payroll_event_id:
                    blockers.append("payroll_obligation_current_event_mismatch")
                if str(obligation["status"]) != "open" or int(obligation["amount_due_ntd"]) <= 0:
                    blockers.append("payroll_obligation_not_payable")
                cursor.execute(_PAYABLE_PROJECTION_SQL, (str(event["obligation_identity"]), resulting_staff_id))
                projection = cursor.fetchone()
                if projection is None:
                    blockers.append("staff_payables_projection_missing")
                else:
                    evidence = _evidence(obligation, projection, payroll_event_id, blockers)

        subject = f"substitution:{receipt['batch_key']}:outcome:{outcome['id']}"
        return SubstitutionPayablesLineageItem(
            item_index=int(outcome["item_index"]),
            outcome_event_id=int(outcome["id"]),
            original_assignment_id=int(outcome["original_assignment_id"]),
            original_schedule_id=int(outcome["original_schedule_id"]),
            original_staff_id=int(outcome["original_staff_id"]),
            original_work_date=_date(outcome["original_work_date"]),
            resolution_type=str(outcome["resolution_type"]),
            resulting_assignment_id=resulting_assignment_id,
            resulting_staff_id=resulting_staff_id,
            resulting_service_date=_date(outcome["resulting_service_date"]),
            payroll_event_id=payroll_event_id,
            payroll_event_expected_version=expected_version,
            payroll_event_resulting_version=event_resulting_version,
            payroll_fingerprint=payroll_fingerprint,
            payables_evidence=evidence,
            lineage_subject=subject,
            blockers=tuple(dict.fromkeys(blockers)),
        )


def _evidence(obligation, projection, payroll_event_id: int, blockers: list[str]):
    amount = int(obligation["amount_due_ntd"])
    projection_amount = int(projection["obligation_amount_ntd"])
    net_paid = int(projection["net_paid_ntd"])
    balance = int(projection["balance_ntd"])
    if projection_amount != amount:
        blockers.append("staff_payables_amount_mismatch")
    if balance != projection_amount - net_paid:
        blockers.append("staff_payables_balance_mismatch")
    if str(projection["status"]) not in {"payable", "completed", "anomaly"}:
        blockers.append("staff_payables_status_invalid")
    return StaffPayablesEvidence(
        obligation_identity=str(obligation["obligation_identity"]),
        assignment_id=int(obligation["assignment_id"]),
        staff_id=int(obligation["staff_id"]),
        amount_due_ntd=amount,
        due_date=_date_or_none(obligation["due_date"]),
        obligation_status=str(obligation["status"]),
        obligation_payroll_version=int(obligation["payroll_version"]),
        obligation_event_id=payroll_event_id,
        projection_status=str(projection["status"]),
        projection_amount_ntd=projection_amount,
        projection_net_paid_ntd=net_paid,
        projection_balance_ntd=balance,
        projection_version=int(projection["aggregate_version"]),
        projection_event_id=int(projection["current_event_id"]),
        blockers=(),
    )


def _root_blockers(receipt, items):
    blockers = []
    if int(receipt["resulting_payroll_version"]) != int(receipt["expected_payroll_version"]) + 1:
        blockers.append("scheduling_payroll_version_invalid")
    if not items:
        blockers.append("substitution_outcome_missing")
    return tuple(dict.fromkeys(blockers))


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _date_or_none(value):
    return None if value is None else _date(value)


@contextmanager
def _cursor(connection) -> Iterator[object]:
    with connection.cursor() as cursor:
        yield cursor


_RECEIPT_SQL = (
    "SELECT batch_key,case_no,scheduling_receipt_id,resulting_scheduling_version,"
    "resulting_generation_number,expected_payroll_version,resulting_payroll_version "
    "FROM scheduling_leave_substitution_receipts WHERE case_no=%s AND batch_key=%s"
)
_OUTCOMES_SQL = (
    "SELECT id,item_index,original_assignment_id,original_schedule_id,original_staff_id,"
    "original_work_date,resolution_type,resulting_assignment_id,resulting_staff_id,"
    "resulting_service_date FROM scheduling_leave_substitution_outcomes "
    "WHERE batch_key=%s AND EXISTS (SELECT 1 FROM scheduling_leave_substitution_receipts "
    "WHERE case_no=%s AND batch_key=scheduling_leave_substitution_outcomes.batch_key) "
    "ORDER BY item_index"
)
_PAYROLL_EVENT_SQL = (
    "SELECT id,obligation_identity,assignment_id,staff_id,payroll_fingerprint,"
    "expected_payroll_version,resulting_payroll_version FROM staff_obligation_events "
    "WHERE case_no=%s AND assignment_id=%s AND staff_id=%s "
    "AND resulting_payroll_version=%s ORDER BY id"
)
_OBLIGATION_SQL = (
    "SELECT obligation_identity,assignment_id,staff_id,amount_due_ntd,due_date,status,"
    "current_event_id,payroll_version FROM staff_obligations "
    "WHERE obligation_identity=%s AND case_no=%s"
)
_PAYABLE_PROJECTION_SQL = (
    "SELECT obligation_amount_ntd,net_paid_ntd,balance_ntd,status,aggregate_version,current_event_id "
    "FROM staff_payable_projections WHERE obligation_identity=%s AND staff_id=%s"
)


__all__ = ["MySqlSubstitutionPayablesLineageRepository"]

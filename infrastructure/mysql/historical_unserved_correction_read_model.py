"""Read historical correction evidence under the Orders cancellation lock policy."""

from __future__ import annotations

import json

from domains.client_finance.obligation_planning import PriorClientCancellationBalance
from domains.client_finance.reconciliation import PaymentStage
from domains.orders.historical_unserved_correction import (
    HistoricalCancellationSettlement,
    HistoricalUnservedEvidence,
    is_historical_unserved_correctable,
)
from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.order_establishment_read_model import (
    load_order_establishment_evidence,
)
from shared_kernel.money import MoneyNTD


_ESTABLISHED_ADOPTION_STATUSES = (
    OrderLifecycleStatus.HISTORICAL_UNSERVED.value,
    OrderLifecycleStatus.HISTORICAL_IN_SERVICE.value,
    OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED.value,
    OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED.value,
)


def load_historical_unserved_evidence(
    cursor, case_no, lifecycle_status, *, lock, actual_start_date=None, actual_end_date=None,
):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT r.id,e.after_status FROM historical_order_adoption_receipts r "
        "JOIN order_lifecycle_state_events e ON e.id=r.lifecycle_event_id AND e.case_no=r.case_no "
        "WHERE r.case_no=%s AND r.outcome='adopted' "
        "AND e.trigger_event='historical_order_adoption' ORDER BY r.id" + suffix,
        (case_no,),
    )
    adoption_rows = cursor.fetchall()
    adoption_ids = tuple(int(row["id"]) for row in adoption_rows)
    established_ids = tuple(
        int(row["id"]) for row in adoption_rows
        if row["after_status"] in _ESTABLISHED_ADOPTION_STATUSES
    )
    cursor.execute(
        "SELECT id FROM order_lifecycle_state_events WHERE case_no=%s "
        "AND trigger_event='historical_order_adoption' "
        "AND JSON_UNQUOTE(JSON_EXTRACT(facts_snapshot,'$.lifecycle_origin'))"
        "='historical_order_authoritative_workbook_absence' ORDER BY id" + suffix,
        (case_no,),
    )
    absence_ids = tuple(int(row["id"]) for row in cursor.fetchall())
    current_status = OrderLifecycleStatus(lifecycle_status)
    if not (adoption_ids or absence_ids or is_historical_unserved_correctable(current_status)):
        if current_status is not OrderLifecycleStatus.ESTABLISHED_UNSERVED or not _has_confirmed_correction(
            cursor, case_no, suffix,
        ):
            return None

    establishment = load_order_establishment_evidence(
        cursor, case_no, lifecycle_status, lock=lock, historical_adoption_ids=established_ids
    )
    actual_service = _actual_service_evidence(cursor, case_no, suffix)
    if actual_start_date is not None:
        actual_service += ("actual_start_date",)
    if actual_end_date is not None:
        actual_service += ("actual_end_date",)
    settlement, settlement_blockers = _prior_settlement(cursor, case_no, suffix)
    blockers = list(settlement_blockers)
    if _invalid_cash_reversal(cursor, case_no, suffix):
        blockers.append("historical_unserved_cash_ledger_invalid")
    review_codes = (
        ("historical_unserved_cash_evidence_requires_review",)
        if _cash_evidence_requires_review(cursor, case_no, suffix) else ()
    )
    assignments, staff = _standalone_assignment_identities(cursor, case_no, suffix)
    return HistoricalUnservedEvidence(
        establishment, adoption_ids, absence_ids, actual_service, settlement,
        tuple(sorted(set(blockers))), actual_end_date, assignments, staff, review_codes,
    )


def preflight_historical_unserved_staff_ids(cursor, case_no):
    return _standalone_assignment_identities(cursor, case_no, "")[1]


def _has_confirmed_correction(cursor, case_no, suffix):
    cursor.execute(
        "SELECT id FROM order_lifecycle_state_events WHERE case_no=%s "
        "AND trigger_event='order_cancellation_applied' AND after_status=%s "
        "AND JSON_UNQUOTE(JSON_EXTRACT(facts_snapshot,'$.historical_unserved_correction.confirmed_established'))='true' "
        "LIMIT 1" + suffix,
        (case_no, OrderLifecycleStatus.ESTABLISHED_UNSERVED.value),
    )
    return cursor.fetchone() is not None


def _standalone_assignment_identities(cursor, case_no, suffix):
    cursor.execute(
        "SELECT a.id,a.staff_id FROM case_staff_assignments a WHERE a.case_no=%s "
        "AND a.generation_id IS NULL AND a.status IN ('planned','active','completed') "
        "ORDER BY a.id" + suffix,
        (case_no,),
    )
    rows = cursor.fetchall()
    return tuple(int(row["id"]) for row in rows), tuple(sorted({int(row["staff_id"]) for row in rows}))


def _actual_service_evidence(cursor, case_no, suffix):
    sources = (
        ("historical_service_day_confirmation", "historical_service_day_projections", "AND total_actual_service_days>0"),
        ("service_day_log", "scheduling_service_day_logs", ""),
        ("confirmed_cancellation_service_days", "order_cancellation_events", "AND official_service_day_count>0"),
        ("irreversible_service_data_lock", "order_service_data_locks", ""),
    )
    present = []
    for source, table, predicate in sources:
        cursor.execute(
            f"SELECT case_no FROM {table} WHERE case_no=%s {predicate} LIMIT 1" + suffix,
            (case_no,),
        )
        if cursor.fetchone() is not None:
            present.append(source)
    return tuple(present)


def _prior_settlement(cursor, case_no, suffix):
    cursor.execute(
        "SELECT c.id AS cancellation_event_id,c.official_service_day_count,"
        "r.cancellation_control_event_id FROM order_lifecycle_control_state s "
        "JOIN order_cancellation_apply_receipts r ON r.case_no=s.case_no "
        "AND r.cancellation_control_event_id=s.current_event_id "
        "JOIN order_cancellation_events c ON c.id=r.cancellation_event_id AND c.case_no=r.case_no "
        "WHERE s.case_no=%s AND s.control_type='cancellation' "
        "AND s.control_key='order_cancelled' AND s.state='active' "
        "ORDER BY r.order_version LIMIT 1" + suffix,
        (case_no,),
    )
    cancellation = cursor.fetchone()
    if cancellation is None:
        return None, ()
    event_id = int(cancellation["cancellation_event_id"])
    cursor.execute(
        "SELECT id,JSON_EXTRACT(result_snapshot,'$.cancellation_settlement') AS settlement "
        "FROM client_finance_apply_receipts WHERE case_no=%s AND "
        "JSON_EXTRACT(result_snapshot,'$.cancellation_settlement.cancellation_event_id')=%s "
        "ORDER BY id LIMIT 2" + suffix,
        (case_no, event_id),
    )
    receipts = tuple(cursor.fetchall())
    reference = (
        event_id,
        int(cancellation["cancellation_control_event_id"]),
        int(cancellation["official_service_day_count"]),
    )
    if not receipts:
        return HistoricalCancellationSettlement(*reference, None), ()
    try:
        if len(receipts) != 1:
            raise ValueError("ambiguous cancellation settlement")
        row = receipts[0]
        raw = row["settlement"]
        payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        fee = payload["fee_ntd"]
        fee_reason = payload["fee_reason"]
        service_due = payload["service_due_ntd"]
        obligation_identity = payload["obligation_identity"]
        if (
            any(type(value) is not int or value < 0 for value in (fee, service_due))
            or not isinstance(fee_reason, str)
            or fee_reason != fee_reason.strip()
            or bool(fee) != bool(fee_reason)
            or (obligation_identity is not None and not isinstance(obligation_identity, str))
        ):
            raise ValueError("invalid cancellation settlement")
        settlement = HistoricalCancellationSettlement(
            *reference, int(row["id"]), fee, fee_reason, service_due, obligation_identity,
            _prior_cancellation_balance(cursor, case_no, obligation_identity, suffix)
            if obligation_identity is not None else None,
        )
    except (KeyError, TypeError, ValueError):
        return None, ("historical_unserved_prior_settlement_invalid",)
    return settlement, ()


def _prior_cancellation_balance(cursor, case_no, identity, suffix):
    cursor.execute(
        "SELECT o.obligation_type,o.direction,o.amount_due_ntd,o.due_date,o.status,"
        "o.source_obligation_identity,e.after_amount_ntd,"
        "EXISTS(SELECT 1 FROM client_finance_amount_controls control "
        "WHERE control.obligation_identity=o.obligation_identity) AS amount_controlled "
        "FROM client_obligations o JOIN client_obligation_events e "
        "ON e.id=o.current_event_id AND e.case_no=o.case_no AND e.obligation_identity=o.obligation_identity "
        "WHERE o.case_no=%s AND o.obligation_identity=%s" + suffix,
        (case_no, identity),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("historical_unserved_prior_settlement_invalid")
    stage = PaymentStage(row["obligation_type"])
    direction = "payable_to_client" if stage is PaymentStage.REFUND else "receivable_from_client"
    outstanding = row["amount_due_ntd"]
    nominal = row["after_amount_ntd"]
    if (
        row["direction"] != direction
        or type(outstanding) is not int or type(nominal) is not int
        or bool(outstanding) != (row["status"] == "open")
    ):
        raise ValueError("historical_unserved_prior_settlement_invalid")
    balance = PriorClientCancellationBalance(
        identity, stage, MoneyNTD(nominal), MoneyNTD(outstanding),
        row["due_date"], row["source_obligation_identity"],
    )
    # Amount controls own their effective projection. Keep an open controlled
    # balance available for the same manual review as other unidentified cash.
    return None if row["amount_controlled"] else balance


def _cash_evidence_requires_review(cursor, case_no, suffix):
    cursor.execute(
        "SELECT case_no FROM finance_case_accounting_markers WHERE case_no=%s" + suffix,
        (case_no,),
    )
    if cursor.fetchone() is not None:
        return True
    # A historical paid/settled marker explicitly has no reliable bank source.
    cursor.execute(
        "SELECT p.current_event_id FROM historical_client_payment_projections p "
        "JOIN client_obligations o ON o.obligation_identity=p.obligation_identity "
        "AND o.case_no=p.case_no AND o.projection_version=p.obligation_projection_version "
        "WHERE p.case_no=%s LIMIT 1" + suffix,
        (case_no,),
    )
    if cursor.fetchone() is not None:
        return True
    cursor.execute(
        "SELECT p.current_event_id FROM historical_staff_payout_projections p "
        "JOIN staff_obligations o ON o.obligation_identity=p.obligation_identity "
        "AND o.case_no=p.case_no AND o.payroll_version=p.obligation_payroll_version "
        "WHERE p.case_no=%s AND o.status<>'cancelled' LIMIT 1" + suffix,
        (case_no,),
    )
    return cursor.fetchone() is not None


def _invalid_cash_reversal(cursor, case_no, suffix):
    cursor.execute(
        "SELECT entry.id FROM client_ledger_entries entry "
        "LEFT JOIN client_ledger_entries original ON original.id=entry.reversal_of_entry_id "
        "WHERE entry.case_no=%s AND entry.entry_type IN ('reversal','refund_reversal') AND "
        "(original.id IS NULL OR original.case_no<>entry.case_no "
        "OR original.entry_type NOT IN ('receipt','refund') "
        "OR (entry.entry_type='refund_reversal' AND original.entry_type<>'refund')) "
        "LIMIT 1" + suffix,
        (case_no,),
    )
    return cursor.fetchone() is not None

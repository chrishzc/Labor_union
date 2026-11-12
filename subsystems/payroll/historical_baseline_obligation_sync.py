"""Synchronize completed historical payroll from adopted and registered facts."""

from decimal import Decimal

from domains.payroll.calculation import AssignmentRateSnapshot, PayrollPolicyKind, PayrollTerms
from domains.payroll.historical_calculation import HistoricalAssignmentServiceFacts, build_historical_case_payroll_candidate
from domains.payroll.installments import confirmed_subsidy_installments
from domains.payroll.tiered_rates import funding_due_date
from infrastructure.mysql.payroll_rebuild_repository import (
    MySqlPayrollRebuildRepository, _load_adjustments, _amount_index, _payroll_adjustments,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.payroll.rebuild_workflow import (
    PayrollRebuildWorkflow, StaffObligationAction, StaffObligationActionKind, build_source_preview,
)

_COMPLETED = ("歷史訂單－服務完成", "歷史訂單－帳務完成")


def sync_historical_staff_baseline_obligations(connection, case_no=None, *, dry_run=False, actor=None):
    """Keep the existing maintenance entry points on the same writer as adoption."""
    with connection.cursor() as cursor:
        sql = "SELECT case_no FROM orders WHERE status IN (%s,%s)"
        params = _COMPLETED
        if case_no is not None:
            sql += " AND case_no=%s"
            params += (case_no,)
        cursor.execute(sql + " ORDER BY case_no", params)
        case_numbers = tuple(row["case_no"] for row in cursor.fetchall())
    details = [
        {"case_no": number, **synchronize_historical_payroll(connection, number, dry_run=dry_run, actor=actor)}
        for number in case_numbers
    ]
    return {
        "scanned_orders": len(details),
        **{f"{action}_count": sum(row["action"] == action for row in details)
           for action in ("created", "updated", "skipped")},
        "details": details,
    }


def synchronize_historical_payroll(connection, case_no, *, dry_run=False, actor=None):
    """Borrow the caller's transaction. The order lock serializes first establishment."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,service_days,service_hours_per_day,floor_fee,actual_end_date,staff_payment_due_date "
            "FROM orders WHERE case_no=%s" + ("" if dry_run else " FOR UPDATE"), (case_no,),
        )
        order = cursor.fetchone()
        if order is None or order["status"] not in _COMPLETED:
            return _skipped("historical_service_not_completed")
        cursor.execute(_ADOPTED_ASSIGNMENT_SQL, (case_no,))
        assignments = tuple(cursor.fetchall())
        if len(assignments) != 1:
            return _skipped("historical_payroll_unique_assignment_required")
        assignment = assignments[0]
        assignment_id = assignment["id"]
        staff_id = assignment["staff_id"]
        cursor.execute(
            "SELECT obligation_identity,assignment_id,staff_id,amount_due_ntd,due_date,status,payout_history_exists,"
            "EXISTS(SELECT 1 FROM staff_payout_obligation_links payment "
            "WHERE payment.obligation_identity=o.obligation_identity) "
            "OR EXISTS(SELECT 1 FROM historical_staff_payout_projections payment "
            "WHERE payment.obligation_identity=o.obligation_identity) AS has_payment "
            "FROM staff_obligations o WHERE case_no=%s AND obligation_kind='service_pay' "
            "AND direction='payable_to_staff' AND status<>'cancelled'" + ("" if dry_run else " FOR UPDATE"),
            (case_no,),
        )
        existing = tuple(cursor.fetchall())
        if existing and (len(existing) != 1 or existing[0]["assignment_id"] != assignment_id
                         or existing[0]["staff_id"] != staff_id):
            return _skipped("historical_payroll_obligation_binding_conflict")
        original = existing[0] if existing else None
        if original and original["due_date"] is not None:
            return _skipped("already_synced")
        if original and (original["status"] != "open" or original["payout_history_exists"] or original["has_payment"]):
            return _skipped("historical_payroll_original_payment_preserved")
        if not original and order["status"] == _COMPLETED[1]:
            return _skipped("historical_payroll_settled_source_required")
        order = {**order, "actual_end_date": assignment["source_end_date"] or order["actual_end_date"]}
        if not all(order[name] for name in ("service_days", "service_hours_per_day", "actual_end_date")):
            return _skipped("historical_payroll_service_basis_missing")
        if not assignment["hourly_rate_ntd"]:
            return _skipped("payroll_rate_policy_not_found")
        identity = f"assignment:{assignment_id}"
        days = int(order["service_days"])
        terms = PayrollTerms(days, Decimal(str(order["service_hours_per_day"])), MoneyNTD(int(order["floor_fee"] or 0)))
        payroll = build_historical_case_payroll_candidate(
            (HistoricalAssignmentServiceFacts(identity, staff_id, days),),
            (AssignmentRateSnapshot(identity, assignment["policy_version"], PayrollPolicyKind(assignment["policy_kind"]),
                                    MoneyNTD(int(assignment["hourly_rate_ntd"]))),),
            terms,
            _payroll_adjustments(_amount_index(_load_adjustments(cursor, assignments, not dry_run))),
        )
        amount = MoneyNTD(int(original["amount_due_ntd"])) if original else payroll.total_payable
        if amount.amount <= 0:
            return _skipped("historical_payroll_nonpositive_amount")
        funding = _funding_schedule(connection, case_no, order, amount.amount)
        if funding is None:
            return _skipped("historical_payroll_funding_conflict")
        due_date, portions = funding
        result = {"action": "updated" if original else "created", "staff_id": staff_id,
                  "amount_ntd": amount.amount, "due_date": due_date.isoformat()}
        if dry_run:
            return result
        cursor.execute("INSERT IGNORE INTO payroll_case_accounts (case_no) VALUES (%s)", (case_no,))
        cursor.execute("SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
        version = int(cursor.fetchone()["aggregate_version"])
        cursor.execute("UPDATE orders SET staff_payment_due_date=%s WHERE case_no=%s AND staff_payment_due_date IS NULL",
                       (due_date, case_no))
        obligation_identity = original["obligation_identity"] if original else f"staff-obligation:{identity}"
        before = amount if original else MoneyNTD(0)
        action = StaffObligationAction(identity, obligation_identity,
                                       StaffObligationActionKind.REPLACE_UNPAID if original else StaffObligationActionKind.CREATE,
                                       before, amount, amount - before, due_date)
        preview = build_source_preview(case_no, version, payroll, (action,))
        key = f"historical-payroll:{case_no}:{version}"
        PayrollRebuildWorkflow(MySqlPayrollRebuildRepository(connection), None).persist_source_preview(
            case_no, preview, actor=actor or ActorContext("system:historical-payroll"),
            key=IdempotencyKey(key), correlation_id=CorrelationId(key),
        )
        if portions:
            from infrastructure.mysql.payroll_installments import establish_confirmed_subsidy_installments
            cursor.execute(
                "SELECT obligation_identity FROM staff_obligations WHERE case_no=%s AND assignment_id=%s "
                "AND obligation_kind='service_pay' AND direction='payable_to_staff' AND status='open'",
                (case_no, assignment_id),
            )
            current = cursor.fetchone()
            establish_confirmed_subsidy_installments(cursor, current["obligation_identity"], portions)
        return result


def _funding_schedule(connection, case_no, order, amount):
    from infrastructure.mysql.accounting_workspace_repository import query_subsidy_payable_handoff

    funding = query_subsidy_payable_handoff(connection, case_no)
    completed_on = order["actual_end_date"]
    subsidy = funding.subsidy_ntd if funding.scheme == "split" else 0
    if funding.staff_subsidy_reason or subsidy is None or not 0 <= subsidy <= amount:
        return None
    due_date = order["staff_payment_due_date"] or funding_due_date(completed_on, directly_subsidized=subsidy == amount)
    portions = confirmed_subsidy_installments(amount, subsidy, due_date, completed_on) if subsidy else ()
    return due_date, portions


def _skipped(reason):
    return {"action": "skipped", "reason": reason}


_ADOPTED_ASSIGNMENT_SQL = """
SELECT a.id,a.staff_id,e.source_end_date,
       COALESCE(rate.policy_version,base.policy_version) AS policy_version,
       COALESCE(rate.policy_kind,base.policy_kind) AS policy_kind,
       COALESCE(rate.hourly_rate_ntd,base.hourly_rate_ntd) AS hourly_rate_ntd
FROM historical_order_pairing_evidence e
JOIN historical_order_adoption_receipts r ON r.id=e.receipt_id
JOIN case_staff_assignments a ON a.id=e.assignment_id AND a.staff_id=e.staff_id AND a.case_no=r.case_no
LEFT JOIN assignment_payroll_rate_snapshots rate ON rate.assignment_id=a.id
LEFT JOIN case_payroll_rate_policy_snapshots base ON base.case_no=a.case_no
WHERE r.id=(SELECT id FROM historical_order_adoption_receipts WHERE case_no=%s AND outcome='adopted'
            ORDER BY id DESC LIMIT 1)
  AND a.status IN ('planned','active','completed')
"""

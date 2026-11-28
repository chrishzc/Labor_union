"""Synchronize completed historical payroll from adopted and registered facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from domains.payroll.calculation import AssignmentRateSnapshot, PayrollPolicyKind, PayrollTerms
from domains.payroll.historical_calculation import (
    HistoricalAssignmentServiceFacts,
    allocate_historical_floor_fee,
    build_historical_case_payroll_candidate,
)
from domains.payroll.installments import PayrollInstallment, confirmed_subsidy_installments
from domains.payroll.tiered_rates import funding_due_date
from infrastructure.mysql.payroll_rebuild_repository import (
    MySqlPayrollRebuildRepository,
    _amount_index,
    _load_adjustments,
    _payroll_adjustments,
)
from infrastructure.mysql.staff_payable_correction_sql import effective_staff_obligation_amount
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import require_positive_half_hour
from subsystems.payroll.rebuild_workflow import (
    PayrollRebuildWorkflow,
    StaffObligationAction,
    StaffObligationActionKind,
    build_source_preview,
)

_COMPLETED = ("歷史訂單－服務完成", "歷史訂單－帳務完成")
_SKIP_DETAILS = {
    "historical_service_not_completed": "本案尚未達到歷史服務完成條件。",
    "historical_payroll_unique_assignment_required": "請查核原歷史採納紀錄及月嫂指派歸屬。",
    "historical_payroll_obligation_binding_conflict": "現有應付與歷史指派不一致，請查核原應付歸屬。",
    "historical_payroll_original_payment_preserved": "原款項已有付款或結清紀錄，請查核原付款證據。",
    "historical_payroll_settled_source_required": "本案已標記帳務完成，請查核原付款及應付證據。",
    "historical_payroll_service_basis_missing": "請查核可證實之月嫂服務天數及每日服務時數。",
    "payroll_rate_policy_not_found": "請查核本案保存的月嫂費率。",
    "historical_payroll_nonpositive_amount": "月嫂應付金額須大於零，請查核計算依據。",
}


@dataclass(frozen=True, slots=True)
class HistoricalFundingSchedule:
    due_date: date | None
    portions: tuple[PayrollInstallment, ...] = ()
    pending_reason: str | None = None
    pending_detail: str | None = None


@dataclass(frozen=True, slots=True)
class _PlannedAssignmentSync:
    assignment_id: int
    staff_id: int
    service_fact: HistoricalAssignmentServiceFacts
    rate_snapshot: AssignmentRateSnapshot
    action: StaffObligationAction
    effective_amount: MoneyNTD
    source_end_date: date | None
    original: dict[str, Any] | None


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


def synchronize_historical_payroll(connection, case_no, *, dry_run=False, actor=None) -> dict[str, Any]:
    """Borrow the caller's transaction. The order lock serializes first establishment."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT status,service_days,service_hours_per_day,floor_fee,actual_end_date,staff_payment_due_date "
            "FROM orders WHERE case_no=%s" + ("" if dry_run else " FOR UPDATE"),
            (case_no,),
        )
        order = cursor.fetchone()
        if order is None or order["status"] not in _COMPLETED:
            return _skipped("historical_service_not_completed")
        cursor.execute(
            "SELECT e.id AS event_id, JSON_LENGTH(e.result_snapshot, '$.accounting_pending') AS pending_count "
            "FROM historical_service_day_projections p "
            "JOIN historical_service_day_events e ON e.id=p.current_event_id "
            "WHERE p.case_no=%s AND JSON_CONTAINS_PATH(e.result_snapshot,'one','$.service_attribution_evidence')",
            (case_no,),
        )
        attribution = cursor.fetchone()
        if attribution:
            return _read_attributed_payables(cursor, case_no, attribution)
        cursor.execute(_ADOPTED_ASSIGNMENT_SQL, (case_no,))
        assignments = tuple(cursor.fetchall())
        if not assignments:
            return _skipped("historical_payroll_unique_assignment_required")
        cursor.execute(
            "SELECT obligation_identity,assignment_id,staff_id,amount_due_ntd,due_date,status,payout_history_exists,"
            f"{effective_staff_obligation_amount('o')} AS effective_amount_due_ntd,"
            f"{_FORMED_DUE_DATE_SQL} AS has_formed_due_date,"
            "EXISTS(SELECT 1 FROM staff_obligation_installments part "
            "WHERE part.obligation_identity=o.obligation_identity AND part.amount_ntd>0) AS has_positive_installments,"
            "EXISTS(SELECT 1 FROM staff_payout_obligation_links payment "
            "WHERE payment.obligation_identity=o.obligation_identity) "
            "OR EXISTS(SELECT 1 FROM historical_staff_payout_projections payment "
            "WHERE payment.obligation_identity=o.obligation_identity) AS has_payment "
            "FROM staff_obligations o WHERE case_no=%s AND obligation_kind='service_pay' "
            "AND direction='payable_to_staff' AND status<>'cancelled'" + ("" if dry_run else " FOR UPDATE"),
            (case_no,),
        )
        existing = tuple(cursor.fetchall())
        if len(assignments) == 1:
            return _synchronize_single_assignment(
                connection, cursor, case_no, order, assignments[0], existing, dry_run=dry_run, actor=actor,
            )
        return _synchronize_multiple_assignments(
            connection, cursor, case_no, order, assignments, existing, dry_run=dry_run, actor=actor,
        )


def _synchronize_single_assignment(connection, cursor, case_no, order, assignment, existing, *, dry_run, actor):
    assignment_id = assignment.get("id")
    staff_id = assignment.get("staff_id")
    if assignment_id is None or staff_id is None:
        return _skipped("historical_payroll_unique_assignment_required")
    if existing and (len(existing) != 1 or existing[0]["assignment_id"] != assignment_id
                     or existing[0]["staff_id"] != staff_id):
        return _skipped("historical_payroll_obligation_binding_conflict")
    original = existing[0] if existing else None
    if original is not None:
        preserved = _preserved_existing_result(original)
        if preserved is not None:
            return _original_sync_outcome(original, preserved)
    if original is None and order["status"] == _COMPLETED[1]:
        return _skipped("historical_payroll_settled_source_required")

    days = _positive_int_or_zero(
        assignment.get("item_service_days")
        or order.get("service_days")
        or assignment.get("schedule_service_days")
    )
    service_hours = _historical_service_hours(order.get("service_hours_per_day"))
    if days <= 0 or service_hours is None:
        return _skipped("historical_payroll_service_basis_missing")
    identity = f"assignment:{assignment_id}"
    rate = _historical_assignment_rate(identity, assignment)
    if rate is None:
        return _skipped("payroll_rate_policy_not_found")

    person_order = {**order, "actual_end_date": assignment.get("source_end_date")}
    terms = PayrollTerms(
        days,
        service_hours,
        MoneyNTD(int(order.get("floor_fee") or 0)),
    )
    payroll = build_historical_case_payroll_candidate(
        (HistoricalAssignmentServiceFacts(identity, staff_id, days),),
        (rate,),
        terms,
        _payroll_adjustments(_amount_index(_load_adjustments(cursor, (assignment,), not dry_run))),
    )
    source_amount = MoneyNTD(int(original["amount_due_ntd"])) if original else payroll.total_payable
    effective_amount = MoneyNTD(int(original["effective_amount_due_ntd"])) if original else source_amount
    if effective_amount.amount <= 0:
        return _skipped("historical_payroll_nonpositive_amount")

    funding = _funding_schedule(connection, case_no, person_order, effective_amount.amount, allow_split_installments=True)
    if original and funding.due_date is None:
        return _original_sync_outcome(original, _already_synced_pending(funding))

    obligation_identity = original["obligation_identity"] if original else f"staff-obligation:{identity}"
    before = source_amount if original else MoneyNTD(0)
    action = StaffObligationAction(
        identity,
        obligation_identity,
        StaffObligationActionKind.REPLACE_UNPAID if original else StaffObligationActionKind.CREATE,
        before,
        source_amount,
        source_amount - before,
        funding.due_date,
    )
    result = _single_sync_outcome(
        action_name="updated" if original else "created",
        assignment_id=assignment_id,
        staff_id=staff_id,
        obligation_identity=obligation_identity,
        amount_ntd=effective_amount.amount,
        funding=funding,
    )
    if dry_run:
        return result

    _persist_historical_batch(
        connection,
        cursor,
        case_no,
        payroll=payroll,
        actions=(action,),
        actor=actor,
        case_due_date=funding.due_date,
        installments=((obligation_identity, funding.portions),) if funding.portions else (),
    )
    return result


def _synchronize_multiple_assignments(connection, cursor, case_no, order, assignments, existing, *, dry_run, actor):
    existing_by_assignment: dict[int, list[dict[str, Any]]] = {}
    orphans: list[dict[str, Any]] = []
    valid_pairs = {
        (row.get("id"), row.get("staff_id"))
        for row in assignments
        if row.get("id") is not None and row.get("staff_id") is not None
    }
    assignment_ids = [row.get("id") for row in assignments if row.get("id") is not None]
    duplicate_assignments = {aid for aid in assignment_ids if assignment_ids.count(aid) > 1}
    for row in existing:
        aid = row.get("assignment_id")
        if aid in duplicate_assignments or (aid, row.get("staff_id")) not in valid_pairs:
            orphans.append(row)
        else:
            existing_by_assignment.setdefault(int(aid), []).append(row)
    orphan_staff_ids = {
        int(row["staff_id"]) for row in orphans if row.get("staff_id") is not None
    }

    valid_entries = [
        row for row in assignments
        if row.get("id") is not None and row.get("staff_id") is not None and row.get("id") not in duplicate_assignments
    ]
    adjustments_by_identity = _amount_index(_load_adjustments(cursor, tuple(valid_entries), not dry_run))

    floor_fee_ntd = int(order.get("floor_fee") or 0)
    floor_fee_blocked = False
    if floor_fee_ntd > 0:
        has_incomplete_peer = len(valid_entries) != len(assignments) or any(
            _positive_int_or_zero(entry.get("item_service_days") or entry.get("schedule_service_days")) <= 0
            for entry in valid_entries
        )
        floor_fee_blocked = has_incomplete_peer

    service_hours = _historical_service_hours(order.get("service_hours_per_day"))
    case_floor_allocations: dict[str, MoneyNTD] = {}
    if floor_fee_ntd > 0 and not floor_fee_blocked and valid_entries:
        floor_facts = tuple(
            HistoricalAssignmentServiceFacts(
                f"assignment:{entry['id']}",
                int(entry["staff_id"]),
                _positive_int_or_zero(entry.get("item_service_days") or entry.get("schedule_service_days")),
            )
            for entry in valid_entries
        )
        _, case_floor_allocations = allocate_historical_floor_fee(
            floor_facts,
            int(order.get("service_days") or sum(item.actual_service_days for item in floor_facts)),
            MoneyNTD(floor_fee_ntd),
        )

    outcomes: list[dict[str, Any] | _PlannedAssignmentSync] = []
    effective_amounts_by_assignment: dict[int, MoneyNTD] = {}
    for entry in assignments:
        assignment_id = entry.get("id")
        staff_id = entry.get("staff_id") or entry.get("evidence_staff_id")
        if assignment_id is None or entry.get("staff_id") is None or assignment_id in duplicate_assignments:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                **_skipped("historical_payroll_unique_assignment_required"),
            })
            continue
        assignment_id = int(assignment_id)
        staff_id = int(entry["staff_id"])
        if staff_id in orphan_staff_ids:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                **_skipped("historical_payroll_obligation_binding_conflict"),
            })
            continue
        existing_rows = existing_by_assignment.get(assignment_id, [])
        if len(existing_rows) > 1:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                "obligation_identity": existing_rows[0]["obligation_identity"],
                **_skipped("historical_payroll_obligation_binding_conflict"),
            })
            continue
        original = existing_rows[0] if existing_rows else None
        original_effective_amount = None
        if original is not None:
            original_effective_amount = MoneyNTD(int(original["effective_amount_due_ntd"]))
            if original_effective_amount.amount > 0:
                effective_amounts_by_assignment[assignment_id] = original_effective_amount
            preserved = _preserved_existing_result(original)
            if preserved is not None:
                outcomes.append(_original_sync_outcome(original, preserved))
                continue
        if original is None and order["status"] == _COMPLETED[1]:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                **_skipped("historical_payroll_settled_source_required"),
            })
            continue
        days = _positive_int_or_zero(entry.get("item_service_days") or entry.get("schedule_service_days"))
        if days <= 0 or service_hours is None:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                **_skipped("historical_payroll_service_basis_missing"),
            })
            continue
        identity = f"assignment:{assignment_id}"
        person_rate = _historical_assignment_rate(identity, entry)
        if person_rate is None:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                **_skipped("payroll_rate_policy_not_found"),
            })
            continue
        item_floor = entry.get("item_floor_fee_ntd")
        if floor_fee_ntd > 0 and floor_fee_blocked and item_floor is None:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                **_skipped(
                    "historical_payroll_service_basis_missing",
                    "本案含最低簽約／床邊指導費，須待同案所有採納月嫂服務天數確認後方可計算各人應付。",
                ),
            })
            continue
        allocated_floor = (
            MoneyNTD(int(item_floor))
            if item_floor is not None
            else case_floor_allocations.get(identity, MoneyNTD(0))
        )
        person_fact = HistoricalAssignmentServiceFacts(identity, staff_id, days)
        person_adjustments = _payroll_adjustments(
            {identity: adjustments_by_identity[identity]} if identity in adjustments_by_identity else {},
        )
        person_payroll = build_historical_case_payroll_candidate(
            (person_fact,),
            (person_rate,),
            PayrollTerms(days, service_hours, allocated_floor),
            person_adjustments,
        )
        source_amount = MoneyNTD(int(original["amount_due_ntd"])) if original else person_payroll.total_payable
        effective_amount = original_effective_amount if original_effective_amount is not None else source_amount
        if effective_amount.amount <= 0:
            outcomes.append({
                "assignment_id": assignment_id,
                "staff_id": staff_id,
                **_skipped("historical_payroll_nonpositive_amount"),
            })
            continue
        if original is None:
            effective_amounts_by_assignment[assignment_id] = effective_amount
        obligation_identity = original["obligation_identity"] if original else f"staff-obligation:{identity}"
        before = source_amount if original else MoneyNTD(0)
        action = StaffObligationAction(
            identity,
            obligation_identity,
            StaffObligationActionKind.REPLACE_UNPAID if original else StaffObligationActionKind.CREATE,
            before,
            source_amount,
            source_amount - before,
            None,
        )
        outcomes.append(_PlannedAssignmentSync(
            assignment_id, staff_id, person_fact, person_rate, action, effective_amount,
            entry.get("source_end_date"), original,
        ))

    case_payroll_total = (
        sum(amount.amount for amount in effective_amounts_by_assignment.values())
        if not orphans and len(effective_amounts_by_assignment) == len(assignments)
        else None
    )
    items: list[dict[str, Any]] = []
    planned: list[_PlannedAssignmentSync] = []
    for outcome in outcomes:
        if not isinstance(outcome, _PlannedAssignmentSync):
            items.append(outcome)
            continue
        funding = _funding_schedule(
            connection,
            case_no,
            {**order, "actual_end_date": outcome.source_end_date},
            outcome.effective_amount.amount,
            complete_payroll_total=case_payroll_total,
            allow_split_installments=False,
        )
        original = outcome.original
        if original is not None and funding.due_date is None:
            items.append(_original_sync_outcome(original, _already_synced_pending(funding)))
            continue
        planned.append(replace(outcome, action=replace(outcome.action, due_date=funding.due_date)))
        items.append(_single_sync_outcome(
            action_name="updated" if original else "created",
            assignment_id=outcome.assignment_id,
            staff_id=outcome.staff_id,
            obligation_identity=outcome.action.obligation_identity,
            amount_ntd=outcome.effective_amount.amount,
            funding=funding,
        ))

    for row in orphans:
        items.append({
            "assignment_id": row.get("assignment_id"),
            "staff_id": row.get("staff_id"),
            "obligation_identity": row.get("obligation_identity"),
            **_skipped("historical_payroll_obligation_binding_conflict"),
        })

    if planned and service_hours is not None and not dry_run:
        ordered = sorted(planned, key=lambda item: item.service_fact.assignment_identity)
        batch_terms = (
            PayrollTerms(int(order.get("service_days") or sum(i.service_fact.actual_service_days for i in ordered)),
                         service_hours, MoneyNTD(floor_fee_ntd))
            if floor_fee_ntd > 0 and not floor_fee_blocked and len(ordered) == len(valid_entries)
            else PayrollTerms(ordered[0].service_fact.actual_service_days, service_hours, MoneyNTD(0))
        )
        batch_adjustments = _payroll_adjustments({
            item.service_fact.assignment_identity: adjustments_by_identity[item.service_fact.assignment_identity]
            for item in ordered
            if item.service_fact.assignment_identity in adjustments_by_identity
        })
        batch_payroll = build_historical_case_payroll_candidate(
            tuple(item.service_fact for item in ordered),
            tuple(item.rate_snapshot for item in ordered),
            batch_terms,
            batch_adjustments,
        )
        all_dates = {item.action.due_date for item in ordered}
        has_skipped = any(item["action"] == "skipped" for item in items)
        case_due_date = next(iter(all_dates)) if not has_skipped and len(all_dates) == 1 else None
        _persist_historical_batch(
            connection,
            cursor,
            case_no,
            payroll=batch_payroll,
            actions=tuple(item.action for item in ordered),
            actor=actor,
            case_due_date=case_due_date,
            installments=(),
        )

    created_or_updated = [item for item in items if item["action"] in {"created", "updated"}]
    if any(item["action"] == "created" for item in created_or_updated):
        summary_action = "created"
    elif any(item["action"] == "updated" for item in created_or_updated):
        summary_action = "updated"
    else:
        summary_action = "skipped"

    unresolved = [
        item for item in items
        if (item["action"] == "skipped" and item.get("reason") != "already_synced") or item.get("pending_reason")
    ]
    summary: dict[str, Any] = {
        "action": summary_action,
        "items": items,
    }
    if len(created_or_updated) == 1:
        only = created_or_updated[0]
        summary["staff_id"] = only["staff_id"]
        summary["amount_ntd"] = only["amount_ntd"]
        summary["due_date"] = only["due_date"]
        if only.get("payment_arrangement_pending"):
            summary["payment_arrangement_pending"] = True
    elif created_or_updated:
        summary["amount_ntd"] = sum(int(item["amount_ntd"]) for item in created_or_updated)
        due_dates = {item["due_date"] for item in created_or_updated}
        summary["due_date"] = next(iter(due_dates)) if len(due_dates) == 1 else None
        if summary["due_date"] is None:
            summary["payment_arrangement_pending"] = True

    if summary_action == "skipped":
        first_reason = next(
            (item.get("reason") for item in items if item.get("reason") and item.get("reason") != "already_synced"),
            "already_synced",
        )
        first_match = next((item for item in items if item.get("reason") == first_reason), {})
        summary["reason"] = first_reason
        if first_match.get("pending_reason"):
            summary["pending_reason"] = first_match["pending_reason"]
            summary["payment_arrangement_pending"] = True
        if first_match.get("detail"):
            summary["detail"] = first_match["detail"]
    elif unresolved:
        blocked = next((item for item in unresolved if item["action"] == "skipped"
                        and item.get("reason") != "already_synced"), None)
        first_issue = blocked or unresolved[0]
        issue_code = first_issue.get("pending_reason") or first_issue.get("reason")
        if issue_code:
            summary["pending_reason"] = issue_code
        detail = first_issue.get("detail")
        if blocked:
            summary["reason"] = blocked["reason"]
            summary["detail"] = "已有部分月嫂款項同步，其餘仍待查核。" + (detail or "")
        elif detail:
            summary["detail"] = detail
    return summary


def _persist_historical_batch(
    connection,
    cursor,
    case_no,
    *,
    payroll,
    actions,
    actor,
    case_due_date,
    installments,
):
    cursor.execute("INSERT IGNORE INTO payroll_case_accounts (case_no) VALUES (%s)", (case_no,))
    cursor.execute("SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
    version = int(cursor.fetchone()["aggregate_version"])
    if case_due_date is not None:
        cursor.execute(
            "UPDATE orders SET staff_payment_due_date=%s WHERE case_no=%s AND staff_payment_due_date IS NULL",
            (case_due_date, case_no),
        )
    preview = build_source_preview(case_no, version, payroll, actions)
    key = f"historical-payroll:{case_no}:{version}"
    PayrollRebuildWorkflow(MySqlPayrollRebuildRepository(connection), cast(Any, None)).persist_source_preview(
        case_no,
        preview,
        actor=actor or ActorContext("system:historical-payroll"),
        key=IdempotencyKey(key),
        correlation_id=CorrelationId(key),
    )
    if installments:
        from infrastructure.mysql.payroll_installments import establish_confirmed_subsidy_installments

        for obligation_identity, portions in installments:
            cursor.execute(
                "SELECT obligation_identity FROM staff_obligations WHERE obligation_identity=%s "
                "AND case_no=%s AND obligation_kind='service_pay' AND direction='payable_to_staff' AND status='open'",
                (obligation_identity, case_no),
            )
            current = cursor.fetchone()
            if current is not None:
                establish_confirmed_subsidy_installments(cursor, current["obligation_identity"], portions)


def _preserved_existing_result(original: dict[str, Any]) -> dict[str, Any] | None:
    if original["has_formed_due_date"] and (
        original["status"] == "open" or original["payout_history_exists"] or original["has_payment"]
    ):
        return _skipped("already_synced")
    if original["status"] != "open" or original["payout_history_exists"] or original["has_payment"]:
        return _skipped("historical_payroll_original_payment_preserved")
    if original["has_positive_installments"]:
        return _skipped(
            "historical_payroll_installment_date_pending",
            "原應付已有分期，請從原付款安排查核分期日期。",
        )
    return None


def _original_sync_outcome(original: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    due_date = original["due_date"]
    return {
        **result,
        "assignment_id": original["assignment_id"],
        "staff_id": original["staff_id"],
        "obligation_identity": original["obligation_identity"],
        "amount_ntd": int(original["effective_amount_due_ntd"]),
        "due_date": due_date.isoformat() if due_date is not None else None,
    }


def _already_synced_pending(funding: HistoricalFundingSchedule) -> dict[str, Any]:
    result = _skipped("already_synced", funding.pending_detail)
    result["payment_arrangement_pending"] = True
    if funding.pending_reason:
        result["pending_reason"] = funding.pending_reason
    return result


def _single_sync_outcome(
    *,
    action_name: str,
    assignment_id: int,
    staff_id: int,
    obligation_identity: str,
    amount_ntd: int,
    funding: HistoricalFundingSchedule,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action": action_name,
        "assignment_id": assignment_id,
        "staff_id": staff_id,
        "obligation_identity": obligation_identity,
        "amount_ntd": amount_ntd,
        "due_date": funding.due_date.isoformat() if funding.due_date is not None else None,
    }
    if funding.due_date is None:
        result["payment_arrangement_pending"] = True
        if funding.pending_reason:
            result["pending_reason"] = funding.pending_reason
        if funding.pending_detail:
            result["detail"] = funding.pending_detail
    return result


def _read_attributed_payables(cursor, case_no, attribution):
    reason = "historical_payroll_attribution_pending"
    if attribution["pending_count"]:
        return _skipped(reason, "原付款證據仍待核對，請從歷史服務歸屬更正補證後重查。")
    cursor.execute(_ATTRIBUTED_PAYABLES_SQL, (case_no, attribution["event_id"]))
    payables = tuple(cursor.fetchall())
    detail = "請從歷史服務歸屬更正查核各月嫂的應付、付款日或結清證據。"
    items = [
        {
            "assignment_id": row["assignment_id"],
            "staff_id": row["staff_id"],
            "obligation_identity": row["obligation_identity"],
            **(_skipped("already_synced") if row["obligation_identity"] else _skipped(reason, detail)),
        }
        for row in payables
    ]
    outcome = _skipped("already_synced") if items and all(
        item["obligation_identity"] for item in items
    ) else _skipped(reason, detail)
    return {**outcome, "items": items}


def _funding_schedule(
    connection,
    case_no: str,
    order: Mapping[str, Any],
    amount: int,
    *,
    allow_split_installments: bool = True,
    complete_payroll_total: int | None = None,
) -> HistoricalFundingSchedule:
    from infrastructure.mysql.accounting_workspace_repository import query_subsidy_payable_handoff

    completed_on = order.get("actual_end_date")
    if completed_on is None:
        return HistoricalFundingSchedule(
            due_date=None,
            pending_reason="historical_payroll_end_date_missing",
            pending_detail="缺少實際結束日，正式應付預計付款日與分期保留待確認。",
        )
    if complete_payroll_total is not None:
        funding = query_subsidy_payable_handoff(
            connection, case_no, complete_payroll_total=complete_payroll_total,
        )
    else:
        funding = query_subsidy_payable_handoff(
            connection, case_no, payroll_candidate_total=amount if allow_split_installments else None,
        )
    if funding.staff_subsidy_reason:
        return HistoricalFundingSchedule(
            due_date=None,
            pending_reason="historical_payroll_funding_conflict",
            pending_detail=funding.staff_subsidy_reason,
        )
    if funding.scheme not in {"split", "advance", "direct"} and funding.subsidy_ntd != 0:
        return HistoricalFundingSchedule(
            due_date=None,
            pending_reason="historical_payroll_funding_pending",
            pending_detail="月嫂付款來源與補助流向尚未確認，預計付款日與分期保留待確認。",
        )
    subsidy = funding.subsidy_ntd if funding.scheme == "split" else 0
    if funding.scheme == "split" and not allow_split_installments and subsidy != 0:
        return HistoricalFundingSchedule(
            due_date=None,
            pending_reason="historical_payroll_funding_pending",
            pending_detail="多人歷史案補助分攤歸屬待確認，預計付款日與分期保留待確認。",
        )
    if subsidy is None:
        return HistoricalFundingSchedule(
            due_date=None,
            pending_reason="historical_payroll_funding_conflict",
            pending_detail="缺少正式補助金額，預計付款日與分期保留待確認。",
        )
    if not 0 <= subsidy <= amount:
        return HistoricalFundingSchedule(
            due_date=None,
            pending_reason="historical_payroll_funding_conflict",
            pending_detail="正式補助金額與月嫂應付總額不相容，預計付款日與分期保留待確認。",
        )
    due_date = order.get("staff_payment_due_date") or funding_due_date(
        completed_on,
        directly_subsidized=subsidy == amount,
    )
    portions = confirmed_subsidy_installments(amount, subsidy, due_date, completed_on) if subsidy else ()
    return HistoricalFundingSchedule(due_date=due_date, portions=portions)


def _positive_int_or_zero(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if not isinstance(value, (int, float, Decimal, str)):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _historical_service_hours(value: object) -> Decimal | None:
    try:
        hours = Decimal(str(value))
        require_positive_half_hour(hours, "service hours per day")
    except (InvalidOperation, ValueError):
        return None
    return hours


def _historical_assignment_rate(identity: str, row: Mapping[str, Any]) -> AssignmentRateSnapshot | None:
    version = row.get("policy_version")
    kind = row.get("policy_kind")
    amount = row.get("hourly_rate_ntd")
    if not isinstance(version, str) or not isinstance(kind, str) or not isinstance(amount, int):
        return None
    try:
        return AssignmentRateSnapshot(
            identity,
            version,
            PayrollPolicyKind(kind),
            MoneyNTD(amount),
        )
    except (TypeError, ValueError):
        return None


def _skipped(reason, detail=None) -> dict[str, Any]:
    result: dict[str, Any] = {"action": "skipped", "reason": reason}
    explanation = detail or _SKIP_DETAILS.get(reason)
    if explanation:
        result["detail"] = explanation
    return result


_FORMED_DUE_DATE_SQL = """
COALESCE((SELECT MIN(part.due_date IS NOT NULL) FROM staff_obligation_installments part
          WHERE part.obligation_identity=o.obligation_identity AND part.amount_ntd>0), o.due_date IS NOT NULL)
"""


_ATTRIBUTED_PAYABLES_SQL = """
SELECT item.assignment_id,item.staff_id,o.obligation_identity
FROM historical_service_day_items item
LEFT JOIN case_staff_assignments a
  ON a.id=item.assignment_id AND a.staff_id=item.staff_id AND a.case_no=%s
  AND a.status IN ('planned','active','completed')
LEFT JOIN staff_obligations o
  ON o.case_no=a.case_no AND o.assignment_id=a.id AND o.staff_id=a.staff_id
  AND o.obligation_kind='service_pay' AND o.direction='payable_to_staff'
  AND ((o.status='open' AND o.amount_due_ntd>0)
       OR (o.status='settled' AND o.payout_history_exists=1))
WHERE item.event_id=%s
ORDER BY item.assignment_id,o.obligation_identity
"""


_ADOPTED_ASSIGNMENT_SQL = """
SELECT a.id,a.staff_id,e.staff_id AS evidence_staff_id,e.caregiver_ordinal,e.resolution,
       e.source_end_date,
       COALESCE(rate.policy_version,base.policy_version) AS policy_version,
       COALESCE(rate.policy_kind,base.policy_kind) AS policy_kind,
       COALESCE(rate.hourly_rate_ntd,base.hourly_rate_ntd) AS hourly_rate_ntd,
       (SELECT item.actual_service_days
        FROM historical_service_day_projections day_proj
        JOIN historical_service_day_items item ON item.event_id=day_proj.current_event_id
        WHERE day_proj.case_no=r.case_no AND item.assignment_id=a.id AND item.staff_id=a.staff_id
        LIMIT 1) AS item_service_days,
       (SELECT item.floor_fee_allocated_ntd
        FROM historical_service_day_projections day_proj
        JOIN historical_service_day_items item ON item.event_id=day_proj.current_event_id
        WHERE day_proj.case_no=r.case_no AND item.assignment_id=a.id AND item.staff_id=a.staff_id
        LIMIT 1) AS item_floor_fee_ntd,
       (SELECT COUNT(DISTINCT sched.work_date)
        FROM staff_schedule sched
        WHERE sched.case_no=r.case_no AND sched.assignment_id=a.id AND sched.staff_id=a.staff_id
          AND sched.effective_marker=1 AND sched.is_work_day=1) AS schedule_service_days
FROM historical_order_pairing_evidence e
JOIN historical_order_adoption_receipts r ON r.id=e.receipt_id
LEFT JOIN case_staff_assignments a ON a.id=e.assignment_id AND a.staff_id=e.staff_id
  AND a.case_no=r.case_no AND a.status IN ('planned','active','completed')
LEFT JOIN assignment_payroll_rate_snapshots rate ON rate.assignment_id=a.id
LEFT JOIN case_payroll_rate_policy_snapshots base ON base.case_no=r.case_no
WHERE r.id=(SELECT id FROM historical_order_adoption_receipts WHERE case_no=%s AND outcome='adopted'
            ORDER BY id DESC LIMIT 1)
  AND e.resolution <> 'blank'
ORDER BY e.caregiver_ordinal
"""

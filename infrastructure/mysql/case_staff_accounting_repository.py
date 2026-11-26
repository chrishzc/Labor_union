"""Staff owner projection for one case, including effective historical facts."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pymysql.connections import Connection

from domains.payroll.tiered_rates import funding_due_date
from infrastructure.mysql.staff_payable_correction_sql import effective_staff_obligation_amount, selectable_staff_obligation
from subsystems.staff_payables.case_accounting_query import (
    StaffAccountingAvailability, StaffAccountingItem, StaffAccountingTransaction,
)


def query_case_staff_accounting_availability(
    connection: Connection, case_no: str,
) -> tuple[StaffAccountingAvailability, ...]:
    """Read each person's historical basis without running Payroll synchronization."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.status,"
            "o.staff_payment_due_date,p.current_event_id AS day_event_id,"
            "(SELECT receipt.id FROM historical_order_adoption_receipts receipt "
            "WHERE receipt.case_no=o.case_no AND receipt.outcome='adopted' "
            "ORDER BY receipt.id DESC LIMIT 1) AS adoption_receipt_id "
            "FROM orders o LEFT JOIN historical_service_day_projections p ON p.case_no=o.case_no "
            "WHERE o.case_no=%s", (case_no,),
        )
        root = cursor.fetchone()
        if root is None or (root["adoption_receipt_id"] is None and root["day_event_id"] is None
                            and not str(root["status"]).startswith("歷史")):
            return ()
        if root["day_event_id"] is not None:
            cursor.execute(
                "SELECT item.assignment_id,item.staff_id,s.name AS staff_name,"
                "a.id IS NOT NULL AS assignment_valid,"
                "(SELECT CASE WHEN COUNT(*)=1 THEN MIN(evidence.source_end_date) END "
                "FROM historical_order_pairing_evidence evidence "
                "WHERE evidence.receipt_id=%s AND evidence.assignment_id=item.assignment_id "
                "AND evidence.staff_id=item.staff_id) AS source_end_date,"
                "(SELECT COUNT(*) FROM historical_order_pairing_evidence evidence "
                "WHERE evidence.receipt_id=%s AND evidence.assignment_id=item.assignment_id "
                "AND evidence.staff_id=item.staff_id) AS pairing_evidence_count "
                "FROM historical_service_day_items item "
                "LEFT JOIN case_staff_assignments a ON a.id=item.assignment_id "
                "AND a.staff_id=item.staff_id AND a.case_no=%s "
                "LEFT JOIN staff s ON s.id=item.staff_id "
                "WHERE item.event_id=%s ORDER BY item.item_ordinal",
                (root["adoption_receipt_id"], root["adoption_receipt_id"], case_no, root["day_event_id"]),
            )
        else:
            cursor.execute(
                "SELECT evidence.assignment_id,evidence.staff_id,s.name AS staff_name,"
                "a.id IS NOT NULL AS assignment_valid,evidence.source_end_date,1 AS pairing_evidence_count "
                "FROM historical_order_pairing_evidence evidence "
                "JOIN historical_order_adoption_receipts receipt ON receipt.id=evidence.receipt_id "
                "LEFT JOIN case_staff_assignments a ON a.id=evidence.assignment_id "
                "AND a.staff_id=evidence.staff_id AND a.case_no=receipt.case_no "
                "LEFT JOIN staff s ON s.id=evidence.staff_id "
                "WHERE evidence.receipt_id=%s AND evidence.resolution <> 'blank' ORDER BY evidence.assignment_id",
                (root["adoption_receipt_id"],),
            )
        sources = tuple(cursor.fetchall())
        cursor.execute(
            "SELECT o.assignment_id,o.staff_id,s.name AS staff_name,o.obligation_identity,o.due_date,"
            + effective_staff_obligation_amount("o") + " AS expected_ntd,"
            "EXISTS(SELECT 1 FROM staff_obligation_installments part "
            "WHERE part.obligation_identity=o.obligation_identity AND part.amount_ntd>0) AS has_installments,"
            "EXISTS(SELECT 1 FROM staff_obligation_installments part "
            "WHERE part.obligation_identity=o.obligation_identity AND part.amount_ntd>0 "
            "AND part.due_date IS NULL) AS missing_installment_date,"
            "EXISTS(SELECT 1 FROM staff_obligation_installments part "
            "WHERE part.obligation_identity=o.obligation_identity AND part.amount_ntd>0 "
            "AND part.funding_kind='client' AND part.due_date IS NULL) AS missing_client_date,"
            "EXISTS(SELECT 1 FROM staff_obligation_installments part "
            "WHERE part.obligation_identity=o.obligation_identity AND part.amount_ntd>0 "
            "AND part.funding_kind='subsidy' AND part.due_date IS NULL) AS missing_subsidy_date "
            "FROM staff_obligations o JOIN staff s ON s.id=o.staff_id "
            "WHERE o.case_no=%s AND o.direction='payable_to_staff' AND o.status<>'cancelled' "
            "AND " + selectable_staff_obligation("o") + " ORDER BY o.obligation_identity", (case_no,),
        )
        obligations = tuple(cursor.fetchall())

    source_by_person = {}
    for row in sources:
        source_by_person.setdefault((row["assignment_id"], row["staff_id"]), []).append(row)
    people = tuple(dict.fromkeys((*source_by_person, *((row["assignment_id"], row["staff_id"]) for row in obligations))))
    if not people:
        return (StaffAccountingAvailability(
            None, None, "", (), "needs_review", ("historical_payroll_unique_assignment_required",),
        ),)
    result: list[StaffAccountingAvailability] = []
    baseline_preview = None
    for assignment_id, staff_id in people:
        person_sources = source_by_person.get((assignment_id, staff_id), ())
        source = person_sources[0] if len(person_sources) == 1 else None
        formal = tuple(row for row in obligations if (row["assignment_id"], row["staff_id"]) == (assignment_id, staff_id))
        party = str((source or (formal[0] if formal else {})).get("staff_name") or "")
        pairing_evidence_count = int(source["pairing_evidence_count"]) if source is not None else 0
        source_is_unique = source is not None and bool(source["assignment_valid"]) and pairing_evidence_count == 1
        end_date = _availability_date(source["source_end_date"]) if source is not None and source_is_unique else None
        reasons: list[str] = []
        if len(person_sources) > 1 or pairing_evidence_count > 1:
            reasons.append("historical_payroll_assignment_source_ambiguous")
        estimated_self_pay = estimated_subsidy = None
        if formal:
            if not person_sources or (source is not None and (not source["assignment_valid"] or pairing_evidence_count == 0)):
                reasons.append("historical_payroll_assignment_source_missing")
            if any(row["missing_installment_date"] for row in formal):
                reasons.append("historical_payroll_installment_date_pending")
                if end_date is not None:
                    if any(row["missing_client_date"] for row in formal):
                        estimated_self_pay = funding_due_date(end_date, directly_subsidized=False).isoformat()
                    if any(row["missing_subsidy_date"] for row in formal):
                        estimated_subsidy = funding_due_date(end_date, directly_subsidized=True).isoformat()
                else:
                    reasons.append("historical_payroll_end_date_missing")
            recorded_due = None
            if any(not row["has_installments"] and row["due_date"] is None for row in formal):
                reasons.append("historical_payroll_due_date_missing")
                recorded_due = _availability_date(root["staff_payment_due_date"])
                if recorded_due is None:
                    funding_known = False
                    if (len(people) == len(obligations) == 1 and source_is_unique and end_date is not None
                            and _positive_number(formal[0].get("expected_ntd"))):
                        from infrastructure.mysql.accounting_workspace_repository import query_subsidy_payable_handoff

                        handoff = query_subsidy_payable_handoff(connection, case_no)
                        total = int(formal[0]["expected_ntd"])
                        subsidy = handoff.subsidy_ntd
                        if (handoff.staff_subsidy_reason is None
                                and handoff.scheme in {"split", "advance", "direct"}
                                and subsidy is not None and 0 <= subsidy <= total):
                            funding_known = True
                            if handoff.scheme == "split" and subsidy:
                                estimated_subsidy = funding_due_date(end_date, directly_subsidized=True).isoformat()
                            if handoff.scheme != "split" or subsidy < total:
                                estimated_self_pay = funding_due_date(end_date, directly_subsidized=False).isoformat()
                    if not funding_known:
                        reasons.append("historical_payroll_funding_source_missing")
                        if end_date is None:
                            reasons.append("historical_payroll_end_date_missing")
            result.append(StaffAccountingAvailability(
                assignment_id, staff_id, party, tuple(str(row["obligation_identity"]) for row in formal),
                "formal", tuple(reasons), estimated_self_pay, estimated_subsidy,
                recorded_due_date=recorded_due.isoformat() if recorded_due is not None else None,
            ))
            continue
        if not person_sources or (source is not None and (not source["assignment_valid"] or pairing_evidence_count == 0)):
            reasons.append("historical_payroll_assignment_source_missing")
        estimated_amount = None
        if not reasons:
            if root["status"] == "歷史訂單－帳務完成":
                reasons.append("historical_payroll_settled_source_required")
            elif root["status"] != "歷史訂單－服務完成":
                reasons.append("historical_service_not_completed")
            else:
                if baseline_preview is None:
                    from subsystems.payroll.historical_baseline_obligation_sync import synchronize_historical_payroll

                    baseline_preview = synchronize_historical_payroll(connection, case_no, dry_run=True)
                outcomes = baseline_preview.get("items") or [baseline_preview]
                matching = [row for row in outcomes if row.get("assignment_id") == assignment_id and row.get("staff_id") == staff_id]
                outcome = matching[0] if len(matching) == 1 else {}
                if outcome.get("action") == "created" and _positive_number(outcome.get("amount_ntd")):
                    estimated_amount = int(outcome["amount_ntd"])
                    if outcome.get("pending_reason"):
                        reasons.append(outcome["pending_reason"])
                else:
                    reasons.append(outcome.get("reason") or (
                        baseline_preview.get("reason") if not baseline_preview.get("items") else None
                    ) or "historical_payroll_baseline_preview_unmatched")
        result.append(StaffAccountingAvailability(
            assignment_id, staff_id, party, (), "not_established" if estimated_amount is not None else "needs_review",
            tuple(reasons), estimated_amount_ntd=estimated_amount,
        ))
    return tuple(result)


def _availability_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _positive_number(value: object) -> bool:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return False
    return number.is_finite() and number > 0


def query_case_staff_accounting(connection, case_no, *, for_update=False):
    lock = " FOR UPDATE" if for_update else ""
    with connection.cursor() as cursor:
        if for_update:
            cursor.execute("SELECT case_no FROM payroll_case_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
            cursor.fetchall()
            cursor.execute("SELECT a.staff_id FROM staff_payable_accounts a WHERE a.staff_id IN (SELECT staff_id FROM staff_obligations WHERE case_no=%s) ORDER BY a.staff_id FOR UPDATE", (case_no,))
            cursor.fetchall()
            cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s FOR UPDATE", (case_no,))
            cursor.fetchall()
        amount = effective_staff_obligation_amount("o")
        cursor.execute(
            "SELECT o.obligation_identity,o.due_date,o.payroll_version,s.name AS staff_name,"
            "EXISTS(SELECT 1 FROM staff_obligation_installments i WHERE i.obligation_identity=o.obligation_identity) AS has_installments,"
            + amount + " AS expected_ntd,p.net_paid_ntd,p.aggregate_version,p.status AS payout_status,"
            "h.confirmation_kind,h.amount_snapshot_ntd,h.current_event_id AS historical_event,"
            "COALESCE(a.aggregate_version,0) AS account_version "
            "FROM staff_obligations o JOIN staff s ON s.id=o.staff_id "
            "LEFT JOIN staff_payable_projections p ON p.obligation_identity=o.obligation_identity "
            "LEFT JOIN staff_payable_accounts a ON a.staff_id=o.staff_id "
            "LEFT JOIN historical_staff_payout_projections h ON h.obligation_identity=o.obligation_identity "
            "AND h.amount_snapshot_ntd=" + amount + " AND h.obligation_payroll_version=o.payroll_version "
            "WHERE o.case_no=%s AND o.direction='payable_to_staff' AND o.status<>'cancelled' AND "
            + selectable_staff_obligation("o") + " ORDER BY o.obligation_identity" + lock, (case_no,),
        )
        obligations = cursor.fetchall()
        cursor.execute(
            "SELECT e.id,e.event_type,e.occurred_on,l.obligation_identity,l.allocated_amount_ntd,b.format_id,e.reconciliation_reference,b.summary "
            ",CASE WHEN e.event_type='payout' THEN e.amount_ntd ELSE NULL END AS bank_amount_ntd,CASE WHEN e.event_type='payout' THEN GREATEST(0,"
            "(SELECT SUM(all_links.allocated_amount_ntd) FROM staff_payout_obligation_links all_links WHERE all_links.payout_event_id=e.id)-e.amount_ntd) ELSE 0 END AS transfer_fee_ntd "
            "FROM staff_payout_obligation_links l JOIN staff_obligations o ON o.obligation_identity=l.obligation_identity "
            "JOIN staff_payout_events e ON e.id=l.payout_event_id "
            "LEFT JOIN finance_import_rows b ON b.id=e.finance_import_row_id "
            "WHERE o.case_no=%s ORDER BY e.id,l.obligation_identity" + lock, (case_no,),
        )
        rows = cursor.fetchall()
        cursor.execute(
            "SELECT d.payout_difference_identity,d.bank_total_ntd,d.obligation_total_ntd,"
            "x.obligation_identity,d.staff_id,d.resulting_staff_payables_version,"
            "(SELECT GROUP_CONCAT(DISTINCT all_o.case_no ORDER BY all_o.case_no) "
            "FROM staff_payout_difference_source_obligations all_x JOIN staff_obligations all_o "
            "ON all_o.obligation_identity=all_x.obligation_identity "
            "WHERE all_x.payout_difference_identity=d.payout_difference_identity) AS related_cases,"
            "(SELECT COUNT(*) FROM staff_payout_difference_source_obligations all_x "
            "WHERE all_x.payout_difference_identity=d.payout_difference_identity) AS source_count "
            "FROM staff_payout_difference_sources d "
            "JOIN staff_payout_difference_source_obligations x ON x.payout_difference_identity=d.payout_difference_identity "
            "JOIN staff_obligations o ON o.obligation_identity=x.obligation_identity "
            "WHERE o.case_no=%s AND d.difference_mode='overpayment' "
            "AND NOT EXISTS (SELECT 1 FROM staff_payout_difference_source_bank_rows source_row "
            "JOIN staff_payout_events payout ON payout.finance_import_row_id=source_row.finance_import_row_id "
            "JOIN staff_payout_events reversal ON reversal.reversal_of_event_id=payout.id "
            "WHERE source_row.payout_difference_identity=d.payout_difference_identity)" + lock,
            (case_no,),
        )
        overages = cursor.fetchall()
    surplus = {}
    for row in overages:
        if int(row["source_count"]) == 1:
            identity = row["obligation_identity"]
            surplus[identity] = surplus.get(identity, 0) + int(row["bank_total_ntd"]) - int(row["obligation_total_ntd"])
    transactions = tuple(StaffAccountingTransaction(
        f"staff-event:{row['id']}:{row['obligation_identity']}", row["obligation_identity"],
        str(row["occurred_on"]), row["event_type"], int(row["allocated_amount_ntd"]) * (
            -1 if row["event_type"] in {"return", "reversal"} else 1
        ), "manual" if ((row.get("reconciliation_reference") or "").startswith("manual") or row.get("summary") == "人工補登") else row["format_id"],
        None if row.get('bank_amount_ntd') is None else int(row['bank_amount_ntd']),
        None if row.get('transfer_fee_ntd') is None else int(row['transfer_fee_ntd']),
    ) for row in rows)
    paid_ids = {row.item_identity for row in transactions}
    items = []
    from infrastructure.mysql.staff_payout_repository import query_staff_funding_portions
    with connection.cursor() as cursor:
        funding = {row['obligation_identity']: query_staff_funding_portions(cursor, row['obligation_identity'], lock=for_update)
            if row.get('has_installments') else () for row in obligations}
    for row in obligations:
        identity = row["obligation_identity"]
        if identity in paid_ids and row["net_paid_ntd"] is None:
            raise ValueError("staff_payment_projection_missing")
        actual = int(row["net_paid_ntd"] or 0)
        actual += surplus.get(identity, 0)
        if row["confirmation_kind"] == "paid":
            actual += int(row["amount_snapshot_ntd"])
        if funding[identity] and (sum(p.settled_ntd or 0 for p in funding[identity]) != actual
                or sum(p.amount_ntd for p in funding[identity]) != int(row['expected_ntd'])):
            from dataclasses import replace
            funding[identity] = tuple(replace(p, settled_ntd=None, remaining_ntd=None) for p in funding[identity])
        items.append(StaffAccountingItem(
            identity, "payable", "月嫂付款", str(row["staff_name"]), int(row["expected_ntd"]), actual,
            identity in paid_ids or row["confirmation_kind"] == "paid",
            f"{row['account_version']}:{row['payroll_version']}:{row['aggregate_version'] or 0}:{row['historical_event'] or 0}",
            None if row["due_date"] is None else str(row["due_date"]),
            settled=row["confirmation_kind"] == "settled" or row.get("payout_status") == "completed",
            funding_portions=funding[identity],
        ))
    seen = set()
    for row in overages:
        source = row["payout_difference_identity"]
        if int(row["source_count"]) <= 1 or source in seen:
            continue
        seen.add(source)
        related = str(row["related_cases"]).split(",")
        counterpart = next(item for item in items if item.identity == row["obligation_identity"])
        items.append(StaffAccountingItem(
            f"staff-overpayment:{source}", "payable", "跨項付款來源（" + "、".join(related) + "）",
            counterpart.party, int(row["obligation_total_ntd"]), int(row["bank_total_ntd"]), True,
            counterpart.version, None, False,
            int(row["bank_total_ntd"]) - int(row["obligation_total_ntd"]) if related == [case_no] else 0,
        ))
    from infrastructure.mysql.staff_recovery_disposition_repository import query_case_staff_recoveries
    recoveries,recovery_cash=query_case_staff_recoveries(connection,case_no)
    return (*items,*recoveries),(*transactions,*recovery_cash)

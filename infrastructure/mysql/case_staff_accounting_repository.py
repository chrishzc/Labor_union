"""Staff owner projection for one case, including effective historical facts."""
from infrastructure.mysql.staff_payable_correction_sql import effective_staff_obligation_amount, selectable_staff_obligation
from subsystems.staff_payables.case_accounting_query import StaffAccountingItem, StaffAccountingTransaction


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
            + amount + " AS expected_ntd,p.net_paid_ntd,p.aggregate_version,"
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
            "SELECT e.id,e.event_type,e.occurred_on,l.obligation_identity,l.allocated_amount_ntd,b.format_id "
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
        ), row["format_id"],
    ) for row in rows)
    paid_ids = {row.item_identity for row in transactions}
    items = []
    for row in obligations:
        identity = row["obligation_identity"]
        if identity in paid_ids and row["net_paid_ntd"] is None:
            raise ValueError("staff_payment_projection_missing")
        actual = int(row["net_paid_ntd"] or 0)
        actual += surplus.get(identity, 0)
        if row["confirmation_kind"] == "paid":
            actual += int(row["amount_snapshot_ntd"])
        items.append(StaffAccountingItem(
            identity, "payable", "月嫂付款", str(row["staff_name"]), int(row["expected_ntd"]), actual,
            identity in paid_ids or row["confirmation_kind"] == "paid",
            f"{row['account_version']}:{row['payroll_version']}:{row['aggregate_version'] or 0}:{row['historical_event'] or 0}",
            None if row["due_date"] is None else str(row["due_date"]),
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
    return tuple(items), transactions

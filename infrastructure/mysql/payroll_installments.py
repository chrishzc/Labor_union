"""Current installment projection derived from canonical Payroll obligations."""

from domains.payroll.installments import payroll_installments


def query_subsidy_completion_date(cursor, case_no, *, for_update=False):
    """Read the completion date used by subsidy confirmation after its lifecycle check."""
    cursor.execute(
        "SELECT COALESCE(actual_end_date, end_date) AS completed_on FROM orders WHERE case_no=%s"
        + (" FOR UPDATE" if for_update else ""),
        (case_no,),
    )
    row = cursor.fetchone()
    return row["completed_on"] if row else None


def establish_confirmed_subsidy_installments(cursor, identity, portions):
    """Insert only a previewed, absent schedule under the caller's owner locks/UoW."""
    cursor.execute('SELECT funding_kind,amount_ntd,due_date FROM staff_obligation_installments '
        'WHERE obligation_identity=%s FOR UPDATE', (identity,))
    existing = tuple(cursor.fetchall())
    expected = {(p.funding_kind, p.amount, p.due_date) for p in portions}
    if existing:
        if {(r['funding_kind'], int(r['amount_ntd']), r['due_date']) for r in existing} != expected:
            raise ValueError('staff_subsidy_split_schedule_changed')
        return
    cursor.executemany('INSERT INTO staff_obligation_installments(obligation_identity,funding_kind,amount_ntd,due_date) VALUES(%s,%s,%s,%s)',
        tuple((identity, p.funding_kind, p.amount, p.due_date) for p in portions))


def payment_date_projection(portions):
    dated = tuple((kind, amount, due) for kind, amount, due in portions if amount > 0)
    if not dated or any(due is None for _, _, due in dated):
        return None
    if len({due for _, _, due in dated}) == 1:
        return dated[0][2]
    return "；".join(f"{'客戶負擔' if kind == 'client' else '直接補助'} {amount:,} 元：{due.isoformat()}" for kind, amount, due in dated)


def hourly_rate_projection(pricing):
    if pricing.payroll.covered == pricing.payroll.excess or pricing.subsidy_hours == 0:
        return pricing.payroll.excess
    return f"補助內 {pricing.payroll.covered} 元／時；用盡後 {pricing.payroll.excess} 元／時"


def persist_payroll_installments(cursor, case_no, candidate, identities=None):
    tiered = tuple(item for item in candidate.assignments if item.tiered_pricing)
    if not tiered:
        return
    # Scheduling has already saved this generation; Orders' end-date projection
    # is persisted later in the same outer transaction.
    cursor.execute("SELECT COALESCE((SELECT MAX(day.work_date) FROM scheduling_aggregates schedule "
        "JOIN staff_schedule day ON day.generation_id=schedule.effective_generation_id "
        "WHERE schedule.case_no=o.case_no AND day.effective_marker=1 AND day.is_work_day=1),"
        "o.actual_end_date) AS actual_end_date FROM orders o WHERE o.case_no=%s", (case_no,))
    row = cursor.fetchone()
    completed_on = row["actual_end_date"] if row else None
    for item in tiered:
        assignment_id = int(item.assignment_identity.rsplit(":", 1)[-1]) if identities is None else identities[item.assignment_identity]
        cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s AND assignment_id=%s "
            "AND obligation_kind='service_pay' AND direction='payable_to_staff' AND status<>'cancelled' FOR UPDATE", (case_no, assignment_id))
        roots = tuple(cursor.fetchall())
        if len(roots) != 1:
            if not roots and item.total_payable.amount == 0:
                continue
            raise ValueError("payroll_installment_root_ambiguous")
        identity = roots[0]["obligation_identity"]
        cursor.execute('SELECT effective_ntd,settlement_base_ntd FROM payroll_amount_controls WHERE obligation_identity=%s',(identity,))
        control=cursor.fetchone()
        if control and control['settlement_base_ntd'] is not None:
            # Paid source schedules stay attached to their original evidence;
            # correction payables have their own identities and dates.
            continue
        effective=int(control['effective_ntd']) if control else None
        portions = {portion.funding_kind: portion for portion in payroll_installments(item, completed_on,effective_total=effective)}
        for kind in ("client", "subsidy"):
            portion = portions.get(kind)
            cursor.execute("INSERT INTO staff_obligation_installments(obligation_identity,funding_kind,amount_ntd,due_date) "
                "VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE amount_ntd=VALUES(amount_ntd),"
                "due_date=COALESCE(due_date,VALUES(due_date))",
                (identity, kind, portion.amount if portion else 0, portion.due_date if portion else None))


def installment_export_sql(statement):
    """Select funding candidates; the payout owner's projection supplies balances."""
    original_balance = "COALESCE(projection.balance_ntd, obligations.amount_due_ntd)"
    from infrastructure.mysql.staff_payable_correction_sql import effective_staff_obligation_amount
    effective=effective_staff_obligation_amount('obligations')
    controlled_balance=f'COALESCE(projection.balance_ntd,{effective})'
    remaining = ("CASE WHEN installments.obligation_identity IS NULL THEN " + original_balance +
        " ELSE installments.amount_ntd END")
    amount = f"CASE WHEN installments.obligation_identity IS NULL THEN {effective} ELSE installments.amount_ntd END"
    due = "CASE WHEN installments.obligation_identity IS NULL THEN obligations.due_date ELSE installments.due_date END"
    # Replace complete select expressions before their component columns.
    select, separator, grouped = statement.partition('GROUP BY')
    select = select.replace("COALESCE(projection.obligation_amount_ntd, obligations.amount_due_ntd) AS amount_due_ntd", amount + " AS amount_due_ntd")
    select = select.replace("       obligations.amount_due_ntd,", "       " + amount + " AS amount_due_ntd,", 1)
    select = select.replace("       obligations.due_date,", "       __INSTALLMENT_DUE__ AS due_date,", 1)
    statement = (select + separator + grouped).replace('obligations.due_date', due)
    statement = statement.replace('__INSTALLMENT_DUE__', due)
    statement = statement.replace(original_balance, remaining.replace(original_balance,controlled_balance))
    statement = statement.replace("FROM staff_obligations obligations", "FROM staff_obligations obligations LEFT JOIN staff_obligation_installments installments ON installments.obligation_identity=obligations.obligation_identity AND installments.amount_ntd>0")
    statement = statement.replace("GROUP BY obligations.obligation_identity,", "GROUP BY installments.funding_kind,installments.amount_ntd,installments.due_date,obligations.obligation_identity,")
    statement = statement.replace("SELECT obligations.obligation_identity,", "SELECT installments.funding_kind AS installment_funding,"
        + f"MAX({effective}) AS funding_root_total,MAX(COALESCE(projection.net_paid_ntd,0)) AS funding_settled_total,"
        + "obligations.obligation_identity,", 1)
    return statement

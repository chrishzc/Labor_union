"""Strict MySQL readers for Orders Terms transaction facts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time, timedelta
from decimal import Decimal
from typing import Any, Callable

from domains.client_finance.obligation_planning import (
    ClientChargeDay,
    ClientFinanceTermsFacts,
    ClientFinanceTermsSourceFacts,
    ClientPaymentTerms,
    ExistingClientStageObligation,
)
from domains.client_finance.reconciliation import PaymentStage
from domains.orders.terms import (
    OrderAggregateFacts,
    OrderTerms,
    ServiceTimeTerms,
)
from domains.orders.lifecycle import (
    OrderLifecycleRootFacts,
    OrderLifecycleStatus,
)
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import (
    EffectiveAssignmentSegment,
    SchedulingGenerationFacts,
)
from shared_kernel.money import MoneyNTD
from subsystems.orders.terms_workflow import TermsWorkflowFacts
from subsystems.payroll.terms_impact import (
    CasePayrollPolicyTerms,
    ExistingStaffObligationTermsFact,
    PayrollTermsSourceFacts,
    SourceAssignmentPayrollTerms,
    StaffObligationDirection,
    StaffObligationKind,
)


def load_preview_facts(cursor: Any, case_no: str) -> TermsWorkflowFacts:
    order_row = select_order(cursor, case_no, lock=False)
    aggregate_row = select_scheduling_aggregate(cursor, case_no, lock=False)
    return _assemble_facts(cursor, order_row, aggregate_row, lock=False)


# Kept cohesive because schedule and Finance roots must share one cursor snapshot.
def load_contract_client_finance_facts(
    cursor: Any,
    order_row: Mapping[str, Any],
    *,
    lock: bool,
) -> ClientFinanceTermsFacts:
    case_no = str(order_row["case_no"])
    aggregate_row = select_scheduling_aggregate(cursor, case_no, lock=lock)
    generation_row = _select_generation(cursor, aggregate_row, lock)
    schedule_rows = _select_schedules(cursor, generation_row, lock)
    charge_days = _contract_charge_days(cursor, case_no, schedule_rows, lock)
    source = _load_client_finance(cursor, order_row, schedule_rows, lock)
    return ClientFinanceTermsFacts(
        case_no=case_no,
        account_version=source.account_version,
        service_hours_per_day=int(order_row["service_hours_per_day"]),
        floor_fee=MoneyNTD(_integer_ntd(order_row["floor_fee"])),
        charge_days=charge_days,
        payment_terms=source.payment_terms,
        existing_obligations=source.existing_obligations,
        open_nonstage_obligation_count=source.open_nonstage_obligation_count,
    )


def _contract_charge_days(cursor, case_no, schedule_rows, lock):
    scheduled_days = tuple(
        ClientChargeDay(row["work_date"], bool(row["is_double_pay"]))
        for row in schedule_rows
        if bool(row["is_work_day"])
    )
    if scheduled_days:
        return scheduled_days
    return _committed_charge_days(cursor, case_no, lock)


def _committed_charge_days(cursor, case_no, lock):
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT day.service_date FROM precontract_service_commitment_days day "
        "JOIN precontract_service_commitments commitment ON commitment.id=day.commitment_id "
        "WHERE commitment.case_no=%s AND NOT EXISTS (SELECT 1 "
        "FROM precontract_service_commitment_events event "
        "WHERE event.commitment_id=commitment.id) "
        "ORDER BY day.service_date,day.id" + lock_clause,
        (case_no,),
    )
    return tuple(
        ClientChargeDay(row["service_date"], False)
        for row in cursor.fetchall()
    )


def load_locked_facts(
    cursor: Any,
    case_no: str,
    preflight_staff_ids: tuple[int, ...],
    after_staff_lock: Callable[[Any], None] | None = None,
) -> TermsWorkflowFacts:
    order_row = select_order(cursor, case_no, lock=True)
    aggregate_row = select_scheduling_aggregate(cursor, case_no, lock=True)
    lock_staff_mutexes(cursor, preflight_staff_ids)
    if after_staff_lock is not None:
        after_staff_lock(cursor)
    return _assemble_facts(cursor, order_row, aggregate_row, lock=True)


def select_order(cursor: Any, case_no: str, *, lock: bool) -> Mapping[str, Any]:
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_ORDER_SQL + lock_clause, (case_no,))
    order_row = cursor.fetchone()
    if not isinstance(order_row, Mapping):
        raise ValueError("order_not_found")
    return order_row


def select_scheduling_aggregate(
    cursor: Any,
    case_no: str,
    *,
    lock: bool,
) -> Mapping[str, Any]:
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(_SCHEDULING_AGGREGATE_SQL + lock_clause, (case_no,))
    aggregate_row = cursor.fetchone()
    if not isinstance(aggregate_row, Mapping):
        return _empty_scheduling_aggregate(case_no)
    _validate_scheduling_aggregate_state(aggregate_row)
    return aggregate_row


def preflight_staff_ids(cursor: Any, case_no: str) -> tuple[int, ...]:
    cursor.execute(_PREFLIGHT_STAFF_SQL, (case_no, case_no))
    return tuple(sorted({int(row["staff_id"]) for row in cursor.fetchall()}))


def lock_staff_mutexes(cursor: Any, staff_ids: tuple[int, ...]) -> None:
    if staff_ids != tuple(sorted(set(staff_ids))):
        raise ValueError("staff mutex ids must be canonical")
    if not staff_ids:
        raise ValueError("scheduling_impacted_staff_required")
    placeholders = ",".join("%s" for _ in staff_ids)
    cursor.execute(
        f"SELECT id FROM staff WHERE id IN ({placeholders}) ORDER BY id FOR UPDATE",
        staff_ids,
    )
    locked_ids = tuple(int(row["id"]) for row in cursor.fetchall())
    if locked_ids != staff_ids:
        raise ValueError("scheduling_staff_not_found")


# Kept cohesive because every reader must share one locking snapshot.
def _assemble_facts(
    cursor: Any,
    order_row: Mapping[str, Any],
    aggregate_row: Mapping[str, Any],
    *,
    lock: bool,
) -> TermsWorkflowFacts:
    generation_row = _select_generation(cursor, aggregate_row, lock)
    assignment_rows = _select_assignments(cursor, generation_row, lock)
    schedule_rows = _select_schedules(cursor, generation_row, lock)
    client_finance = _load_client_finance(cursor, order_row, schedule_rows, lock)
    payroll = _load_payroll(cursor, order_row, assignment_rows, lock)
    lifecycle = _load_lifecycle(cursor, order_row, lock)
    if lock and generation_row is not None:
        _lock_dated_occupancy(cursor, generation_row)
    return _facts_from_rows(
        order_row,
        aggregate_row,
        generation_row,
        assignment_rows,
        schedule_rows,
        client_finance,
        payroll,
        lifecycle,
    )


def _select_generation(cursor: Any, aggregate_row, lock: bool):
    if aggregate_row["effective_generation_id"] is None:
        return None
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT id,generation_number FROM scheduling_generations "
        "WHERE id=%s AND case_no=%s AND status='effective'" + lock_clause,
        (
            aggregate_row["effective_generation_id"],
            aggregate_row["case_no"],
        ),
    )
    generation_row = cursor.fetchone()
    if not isinstance(generation_row, Mapping):
        raise ValueError("scheduling_effective_generation_invalid")
    return generation_row


def _select_assignments(cursor: Any, generation_row, lock: bool):
    if generation_row is None:
        return ()
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT id,staff_id,assignment_sequence,assigned_start_date,"
        "assigned_end_date FROM case_staff_assignments "
        "WHERE generation_id=%s AND status NOT IN ('cancelled','replaced') "
        "ORDER BY id" + lock_clause,
        (generation_row["id"],),
    )
    return tuple(cursor.fetchall())


def _select_schedules(cursor: Any, generation_row, lock: bool):
    if generation_row is None:
        return ()
    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT id,assignment_id,work_date,is_work_day,is_double_pay "
        "FROM staff_schedule "
        "WHERE generation_id=%s AND effective_marker=1 "
        "ORDER BY work_date,id" + lock_clause,
        (generation_row["id"],),
    )
    return tuple(cursor.fetchall())


def _lock_dated_occupancy(cursor: Any, generation_row) -> None:
    cursor.execute(
        "SELECT id FROM scheduling_buffer_days WHERE generation_id=%s "
        "ORDER BY buffer_date,id FOR UPDATE",
        (generation_row["id"],),
    )
    cursor.fetchall()
    cursor.execute(
        "SELECT staff_id,occupancy_date FROM scheduling_effective_occupancy "
        "WHERE generation_id=%s ORDER BY occupancy_date,staff_id FOR UPDATE",
        (generation_row["id"],),
    )
    cursor.fetchall()


# Kept cohesive because these rows form one immutable cross-Domain snapshot.
def _facts_from_rows(
    order_row,
    aggregate_row,
    generation_row,
    assignment_rows,
    schedule_rows,
    client_finance,
    payroll,
    lifecycle,
) -> TermsWorkflowFacts:
    service_dates_by_assignment = _service_dates_by_assignment(schedule_rows)
    segments = _segments(assignment_rows, service_dates_by_assignment)
    official_dates = tuple(
        row["work_date"] for row in schedule_rows if bool(row["is_work_day"])
    )
    return TermsWorkflowFacts(
        order=_order_facts(order_row),
        scheduling=SchedulingGenerationFacts(
            case_no=str(order_row["case_no"]),
            aggregate_version=int(aggregate_row["aggregate_version"]),
            generation_number=(
                int(generation_row["generation_number"])
                if generation_row is not None
                else 0
            ),
            segments=segments,
            service_started=order_row["actual_start_date"] is not None,
        ),
        planned_service_dates=official_dates,
        client_finance=client_finance,
        payroll=payroll,
        lifecycle=lifecycle,
    )


def _empty_scheduling_aggregate(case_no: str) -> dict[str, object]:
    return {
        "case_no": case_no,
        "aggregate_version": 0,
        "generation_counter": 0,
        "effective_generation_id": None,
    }


def _validate_scheduling_aggregate_state(aggregate_row) -> None:
    if aggregate_row["effective_generation_id"] is not None:
        return
    if (
        int(aggregate_row["aggregate_version"]) == 0
        and int(aggregate_row["generation_counter"]) == 0
    ):
        return
    raise ValueError("scheduling_generation_conflict")


def _load_client_finance(cursor, order_row, schedule_rows, lock):
    terms_row = _select_client_payment_terms(
        cursor,
        str(order_row["case_no"]),
        lock,
    )
    obligation_rows = _select_client_obligations(
        cursor,
        str(order_row["case_no"]),
        lock,
    )
    double_pay_dates = tuple(
        row["work_date"]
        for row in schedule_rows
        if bool(row["is_work_day"]) and bool(row["is_double_pay"])
    )
    return _client_finance_source(terms_row, obligation_rows, double_pay_dates)


def _select_client_payment_terms(cursor, case_no, lock):
    cursor.execute(
        _CLIENT_PAYMENT_TERMS_SQL + _lock_clause(lock),
        (case_no,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("client_finance_bootstrap_required")
    return row


def _select_client_obligations(cursor, case_no, lock):
    cursor.execute(
        _CLIENT_OBLIGATIONS_SQL + _lock_clause(lock),
        (case_no,),
    )
    return tuple(cursor.fetchall())


def _client_finance_source(terms_row, obligation_rows, double_pay_dates):
    return ClientFinanceTermsSourceFacts(
        case_no=str(terms_row["case_no"]),
        account_version=int(terms_row["aggregate_version"]),
        payment_terms=ClientPaymentTerms(
            int(terms_row["deposit_service_days"]),
            MoneyNTD(_integer_ntd(terms_row["client_hourly_rate_ntd"])),
            terms_row["deposit_due_date"],
            terms_row["first_payment_due_date"],
            terms_row["second_payment_due_date"],
        ),
        double_pay_dates=double_pay_dates,
        existing_obligations=tuple(
            _client_obligation(row) for row in obligation_rows
        ),
        open_nonstage_obligation_count=int(
            terms_row["open_nonstage_obligation_count"]
        ),
    )


def _client_obligation(row):
    stage = PaymentStage(str(row["obligation_type"]))
    if str(row["direction"]) != "receivable_from_client":
        raise ValueError("invalid_client_finance_facts")
    return ExistingClientStageObligation(
        obligation_identity=str(row["obligation_identity"]),
        payment_stage=stage,
        contracted_amount=MoneyNTD(_integer_ntd(row["contracted_amount_ntd"])),
        net_settled_amount=MoneyNTD(_integer_ntd(row["net_settled_amount_ntd"])),
        due_date=row["due_date"],
        formal_history_exists=bool(row["formal_history_exists"]),
    )


def _load_payroll(cursor, order_row, assignment_rows, lock):
    case_no = str(order_row["case_no"])
    account_row = _select_payroll_account(cursor, case_no, lock)
    case_policy = _select_case_payroll_policy(
        cursor,
        case_no,
        lock,
        required=not assignment_rows,
    )
    assignment_ids = tuple(int(row["id"]) for row in assignment_rows)
    rate_rows = _select_assignment_rates(cursor, assignment_ids, lock)
    special_dates = _select_special_pay_dates(cursor, assignment_ids, lock)
    adjustments = _select_payroll_adjustments(cursor, assignment_ids, lock)
    obligations = _select_staff_obligations(cursor, case_no, lock)
    return _payroll_source(
        order_row,
        account_row,
        assignment_rows,
        rate_rows,
        special_dates,
        adjustments,
        obligations,
        case_policy,
    )


def _select_payroll_account(cursor, case_no, lock):
    cursor.execute(
        "SELECT case_no,aggregate_version FROM payroll_case_accounts "
        "WHERE case_no=%s" + _lock_clause(lock),
        (case_no,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("payroll_bootstrap_required")
    return row


def _select_case_payroll_policy(cursor, case_no, lock, *, required):
    cursor.execute(
        "SELECT policy_version,policy_kind "
        "FROM case_payroll_rate_policy_snapshots WHERE case_no=%s"
        + _lock_clause(lock),
        (case_no,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        if required:
            raise ValueError("payroll_case_policy_bootstrap_required")
        return None
    return CasePayrollPolicyTerms(
        str(row["policy_version"]),
        PayrollPolicyKind(str(row["policy_kind"])),
    )


def _select_assignment_rates(cursor, assignment_ids, lock):
    return _select_for_assignment_ids(
        cursor,
        "SELECT assignment_id,policy_version,policy_kind,hourly_rate_ntd "
        "FROM assignment_payroll_rate_snapshots WHERE assignment_id IN ({})",
        assignment_ids,
        lock,
    )


def _select_special_pay_dates(cursor, assignment_ids, lock):
    rows = _select_for_assignment_ids(
        cursor,
        "SELECT assignment_id,service_date FROM payroll_special_pay_events "
        "WHERE assignment_id IN ({}) ORDER BY assignment_id,service_date",
        assignment_ids,
        lock,
    )
    result: dict[int, list] = {}
    for row in rows:
        result.setdefault(int(row["assignment_id"]), []).append(row["service_date"])
    return {key: tuple(values) for key, values in result.items()}


def _select_payroll_adjustments(cursor, assignment_ids, lock):
    rows = _select_for_assignment_ids(
        cursor,
        "SELECT a.assignment_id,COALESCE(SUM(a.amount_ntd),0) amount_ntd "
        "FROM payroll_adjustment_allocations a "
        "WHERE a.assignment_id IN ({}) GROUP BY a.assignment_id",
        assignment_ids,
        lock,
    )
    return {
        int(row["assignment_id"]): MoneyNTD(_integer_ntd(row["amount_ntd"]))
        for row in rows
    }


def _select_staff_obligations(cursor, case_no, lock):
    cursor.execute(
        _STAFF_OBLIGATIONS_SQL + _lock_clause(lock),
        (case_no,),
    )
    return tuple(cursor.fetchall())


def _select_for_assignment_ids(cursor, sql_template, assignment_ids, lock):
    if not assignment_ids:
        return ()
    placeholders = ",".join("%s" for _ in assignment_ids)
    cursor.execute(
        sql_template.format(placeholders) + _lock_clause(lock),
        assignment_ids,
    )
    return tuple(cursor.fetchall())


def _payroll_source(
    order_row,
    account_row,
    assignment_rows,
    rate_rows,
    special_dates,
    adjustments,
    obligations,
    case_policy,
):
    rates = {int(row["assignment_id"]): row for row in rate_rows}
    return PayrollTermsSourceFacts(
        case_no=str(order_row["case_no"]),
        payroll_version=int(account_row["aggregate_version"]),
        source_terms=tuple(
            _source_assignment_terms(row, rates, special_dates, adjustments)
            for row in assignment_rows
        ),
        existing_obligations=tuple(
            _staff_obligation(row) for row in obligations
        ),
        staff_payment_due_date=order_row["staff_payment_due_date"],
        case_policy=case_policy,
    )


def _source_assignment_terms(row, rates, special_dates, adjustments):
    assignment_id = int(row["id"])
    rate = rates.get(assignment_id)
    if not isinstance(rate, Mapping):
        raise ValueError("payroll_rate_policy_not_found")
    return SourceAssignmentPayrollTerms(
        assignment_id,
        int(row["staff_id"]),
        str(rate["policy_version"]),
        PayrollPolicyKind(str(rate["policy_kind"])),
        special_dates.get(assignment_id, ()),
        adjustments.get(assignment_id, MoneyNTD(0)),
    )


def _staff_obligation(row):
    return ExistingStaffObligationTermsFact(
        obligation_identity=str(row["obligation_identity"]),
        source_assignment_id=int(row["assignment_id"]),
        staff_id=int(row["staff_id"]),
        obligation_kind=StaffObligationKind(str(row["obligation_kind"])),
        direction=StaffObligationDirection(str(row["direction"])),
        contractual_amount=MoneyNTD(_integer_ntd(row["contracted_amount_ntd"])),
        outstanding_amount=MoneyNTD(_integer_ntd(row["amount_due_ntd"])),
        paid_net_amount=MoneyNTD(_integer_ntd(row["paid_net_amount_ntd"])),
        payout_history_exists=bool(row["payout_history_exists"]),
        due_date=row["due_date"],
    )


def _lock_clause(lock: bool) -> str:
    return " FOR UPDATE" if lock else ""


def _load_lifecycle(cursor, order_row, lock):
    contract_completed = _contract_completed(
        cursor,
        str(order_row["case_no"]),
        lock,
    )
    control_rows = _lifecycle_control_rows(
        cursor,
        str(order_row["case_no"]),
        lock,
    )
    controls = {str(row["control_type"]): row for row in control_rows}
    return OrderLifecycleRootFacts(
        case_no=str(order_row["case_no"]),
        current_status=OrderLifecycleStatus(str(order_row["status"])),
        contract_completed=contract_completed,
        actual_start_date=order_row["actual_start_date"],
        actual_start_reconfirmed=_actual_start_reconfirmed(order_row, controls),
        cancellation_effective=_cancellation_effective(controls),
        service_data_locked=bool(order_row["service_data_locked"]),
    )


def _contract_completed(cursor, case_no, lock):
    cursor.execute(
        "SELECT id FROM order_contract_flow_events "
        "WHERE case_no=%s AND event_type='contract_completed'"
        + _lock_clause(lock),
        (case_no,),
    )
    return cursor.fetchone() is not None


def _lifecycle_control_rows(cursor, case_no, lock):
    cursor.execute(
        "SELECT control_type,state,confirmed_start_date "
        "FROM order_lifecycle_control_state "
        "WHERE case_no=%s AND control_type IN "
        "('cancellation','actual_start_reconfirmation') "
        "ORDER BY control_type" + _lock_clause(lock),
        (case_no,),
    )
    return tuple(cursor.fetchall())


def _actual_start_reconfirmed(order_row, controls):
    actual_start_date = order_row["actual_start_date"]
    if actual_start_date is None:
        return False
    control = controls.get("actual_start_reconfirmation")
    if control is None:
        return True
    return (
        str(control["state"]) == "cleared"
        and control["confirmed_start_date"] == actual_start_date
    )


def _cancellation_effective(controls):
    control = controls.get("cancellation")
    return control is not None and str(control["state"]) == "active"


def _service_dates_by_assignment(schedule_rows) -> dict[int, tuple]:
    service_dates: dict[int, list] = {}
    for row in schedule_rows:
        if not bool(row["is_work_day"]):
            continue
        assignment_id = int(row["assignment_id"])
        service_dates.setdefault(assignment_id, []).append(row["work_date"])
    return {
        assignment_id: tuple(dates)
        for assignment_id, dates in service_dates.items()
    }


def _segments(assignment_rows, service_dates_by_assignment):
    ordered_rows = sorted(
        assignment_rows,
        key=lambda row: int(row["assignment_sequence"]),
    )
    return tuple(
        _segment(row, service_dates_by_assignment)
        for row in ordered_rows
    )


def _segment(row, service_dates_by_assignment) -> EffectiveAssignmentSegment:
    assignment_id = int(row["id"])
    service_dates = service_dates_by_assignment.get(assignment_id, ())
    if not service_dates:
        raise ValueError("assignment_service_days_required")
    return EffectiveAssignmentSegment(
        assignment_id=assignment_id,
        staff_id=int(row["staff_id"]),
        sequence=int(row["assignment_sequence"]),
        service_day_count=len(service_dates),
        assigned_start_date=row["assigned_start_date"],
        assigned_end_date=row["assigned_end_date"],
        official_service_dates=service_dates,
    )


def _order_facts(row: Mapping[str, Any]) -> OrderAggregateFacts:
    terms = OrderTerms(
        planned_start_date=row["start_date"],
        service_days=int(row["service_days"]),
        service_hours_per_day=int(row["service_hours_per_day"]),
        floor_fee=MoneyNTD(_integer_ntd(row["floor_fee"])),
        service_time=ServiceTimeTerms(
            _mysql_time(row.get("service_start_time")),
            _mysql_time(row.get("service_end_time")),
            row.get("service_end_day_offset"),
        ),
        requires_cooking=(
            None
            if row.get("requires_cooking") is None
            else bool(row["requires_cooking"])
        ),
    )
    return OrderAggregateFacts(
        str(row["case_no"]),
        int(row["lifecycle_version"]),
        terms,
        bool(row["service_data_locked"]),
        str(row["client_identity_status"]),
    )


def _integer_ntd(value: Any) -> int:
    decimal_value = Decimal(str(value))
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError("non_integer_order_money")
    return int(decimal_value)


def _mysql_time(value: Any) -> time | None:
    if value is None or isinstance(value, time):
        return value
    if not isinstance(value, timedelta):
        raise TypeError("unsupported MySQL TIME value")
    seconds = int(value.total_seconds())
    if seconds < 0 or seconds >= 86_400:
        raise ValueError("invalid MySQL TIME value")
    return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)


_ORDER_SQL = (
    "SELECT o.case_no,o.status,o.lifecycle_version,o.start_date,o.service_days,"
    "o.service_hours_per_day,o.requires_cooking,o.floor_fee,o.service_start_time,"
    "o.service_end_time,o.service_end_day_offset,o.actual_start_date,"
    "o.staff_payment_due_date,clients.identity_status AS client_identity_status,"
    "EXISTS(SELECT 1 FROM order_service_data_locks l "
    "WHERE l.case_no=o.case_no) AS service_data_locked "
    "FROM orders o JOIN clients ON clients.case_no=o.case_no WHERE o.case_no=%s"
)

_SCHEDULING_AGGREGATE_SQL = (
    "SELECT case_no,aggregate_version,generation_counter,"
    "effective_generation_id FROM scheduling_aggregates WHERE case_no=%s"
)

_PREFLIGHT_STAFF_SQL = (
    "SELECT a.staff_id FROM scheduling_aggregates g "
    "JOIN case_staff_assignments a "
    "ON a.generation_id=g.effective_generation_id "
    "WHERE g.case_no=%s AND a.status NOT IN ('cancelled','replaced') "
    "UNION SELECT d.staff_id FROM caregiver_availability_lock_days d "
    "JOIN caregiver_availability_locks l ON l.id=d.lock_id "
    "JOIN caregiver_matching_plans p ON p.id=l.plan_id "
    "WHERE p.case_no=%s AND d.active_marker=1"
)

_CLIENT_PAYMENT_TERMS_SQL = (
    "SELECT a.case_no,a.aggregate_version,t.policy_version,"
    "t.client_hourly_rate_ntd,t.deposit_service_days,t.deposit_due_date,"
    "t.first_payment_due_date,t.second_payment_due_date,"
    "(SELECT COUNT(*) FROM client_obligations o "
    "WHERE o.case_no=a.case_no AND o.status='open' "
    "AND o.obligation_type NOT IN ('deposit','first','second')) "
    "AS open_nonstage_obligation_count "
    "FROM client_finance_accounts a "
    "JOIN client_payment_terms t ON t.case_no=a.case_no "
    "WHERE a.case_no=%s"
)

_CLIENT_OBLIGATIONS_SQL = (
    "SELECT o.obligation_identity,o.obligation_type,o.direction,o.due_date,"
    "e.after_amount_ntd AS contracted_amount_ntd,"
    "COALESCE((SELECT SUM(CASE l.entry_type "
    "WHEN 'receipt' THEN a.amount_ntd WHEN 'adjustment' THEN a.amount_ntd "
    "WHEN 'refund' THEN -a.amount_ntd WHEN 'reversal' THEN -a.amount_ntd "
    "END) FROM client_ledger_obligation_allocations a "
    "JOIN client_ledger_entries l ON l.id=a.ledger_entry_id "
    "WHERE a.obligation_identity=o.obligation_identity),0) "
    "AS net_settled_amount_ntd,"
    "EXISTS(SELECT 1 FROM client_ledger_obligation_allocations a "
    "WHERE a.obligation_identity=o.obligation_identity) "
    "AS formal_history_exists "
    "FROM client_obligations o "
    "JOIN client_obligation_events e ON e.id=o.current_event_id "
    "WHERE o.case_no=%s AND o.obligation_type IN ('deposit','first','second') "
    "ORDER BY o.obligation_type,o.obligation_identity"
)

_STAFF_OBLIGATIONS_SQL = (
    "SELECT o.obligation_identity,o.assignment_id,o.staff_id,"
    "o.obligation_kind,o.direction,o.amount_due_ntd,o.due_date,"
    "o.payout_history_exists,e.after_amount_ntd AS contracted_amount_ntd,"
    "COALESCE((SELECT SUM(CASE p.event_type WHEN 'payout' "
    "THEN l.allocated_amount_ntd WHEN 'return' THEN -l.allocated_amount_ntd "
    "WHEN 'reversal' THEN -l.allocated_amount_ntd END) "
    "FROM staff_payout_obligation_links l "
    "JOIN staff_payout_events p ON p.id=l.payout_event_id "
    "WHERE l.obligation_identity=o.obligation_identity),0) "
    "AS paid_net_amount_ntd "
    "FROM staff_obligations o "
    "JOIN staff_obligation_events e ON e.id=o.current_event_id "
    "WHERE o.case_no=%s ORDER BY o.assignment_id,o.obligation_identity"
)

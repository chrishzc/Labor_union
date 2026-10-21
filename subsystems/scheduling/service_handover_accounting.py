"""Typed, read-only handover money view from the owning finance candidates."""

from dataclasses import dataclass
from datetime import date

from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from subsystems.payroll.terms_impact import PayrollTermsActionKind, calculate_assignment_payroll


@dataclass(frozen=True, slots=True)
class HandoverPayBreakdown:
    salary_ntd: int
    floor_fee_ntd: int
    adjustment_ntd: int
    total_ntd: int


@dataclass(frozen=True, slots=True)
class HandoverStaffAccounting:
    staff_id: int
    before: HandoverPayBreakdown
    after: HandoverPayBreakdown
    paid_net_ntd: int
    payable_after_ntd: int
    recovery_increase_ntd: int
    recovery_after_ntd: int
    payment_due_date: date | None


@dataclass(frozen=True, slots=True)
class HandoverClientAccounting:
    before_ntd: int
    after_ntd: int
    difference_ntd: int
    settled_ntd: int


@dataclass(frozen=True, slots=True)
class HandoverAccounting:
    staff: tuple[HandoverStaffAccounting, ...]
    client: HandoverClientAccounting


def build_handover_accounting(facts, scheduling, payroll_impact, finance_impact):
    if payroll_impact.blockers or finance_impact.blockers:
        return None
    before_generation = SchedulingGenerationCandidate(
        scheduling.case_no, scheduling.generation_number, scheduling.expected_aggregate_version,
        scheduling.resulting_aggregate_version, (), tuple(AssignmentCandidate(
            f"before:{item.assignment_id}", item.assignment_id, item.staff_id, item.sequence,
            item.assigned_start_date, item.assigned_end_date, item.official_service_dates,
            len(item.official_service_dates) * facts.assignment_plan.service_hours_per_day,
            (item.assignment_id,),
        ) for item in facts.assignment_plan.effective_assignments), (),
    )
    before = calculate_assignment_payroll(facts.payroll, before_generation, facts.order_terms)
    after = payroll_impact.payload.payroll
    people = sorted({item.staff_id for item in before.assignments + after.assignments}
                    | {item.staff_id for item in facts.payroll.existing_obligations})
    rows = []
    for staff_id in people:
        paid = sum(item.paid_net_amount.amount for item in facts.payroll.existing_obligations
                   if item.staff_id == staff_id)
        settlements = tuple(item for item in payroll_impact.payload.frozen_settlements if item.staff_id == staff_id)
        payable = sum(max(0, item.revised_entitlement.amount - item.paid_net_amount.amount) for item in settlements)
        payable += sum(item.amount.amount for item in payroll_impact.payload.actions
                       if item.staff_id == staff_id and item.action is PayrollTermsActionKind.ESTABLISH)
        recovery_increase = sum(item.recovery_increase.amount for item in settlements)
        outstanding_recovery = sum(item.remaining_amount.amount for item in facts.payroll.recovery_balances
                                   if item.staff_id == staff_id)
        rows.append(HandoverStaffAccounting(staff_id, _breakdown(before, staff_id), _breakdown(after, staff_id),
                    paid, payable, recovery_increase, outstanding_recovery + recovery_increase,
                    facts.payroll.staff_payment_due_date))
    client_before = sum(item.contracted_amount.amount for item in facts.client_finance.existing_obligations)
    client_after = sum(item.amount.amount for item in finance_impact.payload.stage_plans)
    return HandoverAccounting(tuple(rows), HandoverClientAccounting(client_before, client_after,
        client_after - client_before, sum(item.net_settled_amount.amount for item in facts.client_finance.existing_obligations)))


def _breakdown(payroll, staff_id):
    assignments = tuple(item for item in payroll.assignments if item.staff_id == staff_id)
    return HandoverPayBreakdown(
        sum(item.service_salary.amount for item in assignments),
        sum(item.floor_fee_allocated.amount for item in assignments),
        sum(item.effective_adjustments.amount for item in assignments),
        sum(item.total_payable.amount for item in assignments),
    )

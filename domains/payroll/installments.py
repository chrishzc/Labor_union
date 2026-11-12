"""Funding portions are schedules of one entitlement, not additional salary."""

from dataclasses import dataclass
from datetime import date

from domains.payroll.calculation import AssignmentPayrollCandidate
from domains.payroll.tiered_rates import funding_due_date


@dataclass(frozen=True, slots=True)
class PayrollInstallment:
    funding_kind: str
    amount: int
    due_date: date | None


def confirmed_subsidy_installments(total: int, subsidy: int, client_due: date | None, completed_on: date) -> tuple[PayrollInstallment, ...]:
    """Schedule a confirmed split of one existing entitlement; never add salary."""
    if any(not isinstance(v, int) or isinstance(v, bool) for v in (total, subsidy)) or total <= 0 or not 0 <= subsidy <= total:
        raise ValueError('staff_subsidy_split_amount_conflict')
    return (PayrollInstallment('client', total - subsidy, client_due),
            PayrollInstallment('subsidy', subsidy, funding_due_date(completed_on, directly_subsidized=True)))


def allocate_historical_subsidy(subsidy: int, days: dict[int, int]) -> dict[int, int]:
    """Allocate a confirmed case subsidy by service-day share, in whole NTD."""
    total_days = sum(days.values())
    shares = {staff_id: divmod(subsidy * count, total_days) for staff_id, count in days.items()}
    allocated = {staff_id: share[0] for staff_id, share in shares.items()}
    remainder = subsidy - sum(allocated.values())
    for staff_id in sorted(shares, key=lambda item: (-shares[item][1], item))[:remainder]:
        allocated[staff_id] += 1
    return allocated


def payroll_installments(candidate: AssignmentPayrollCandidate, completed_on: date | None, *, effective_total: int | None = None) -> tuple[PayrollInstallment, ...]:
    total = candidate.total_payable.amount if effective_total is None else effective_total
    if not isinstance(total,int) or isinstance(total,bool) or total<0:
        raise ValueError('payroll_installment_amount_invalid')
    subsidy = min(total, candidate.covered_salary) if candidate.directly_subsidized else 0
    client = total - subsidy
    return tuple(PayrollInstallment(kind, amount,
        funding_due_date(completed_on, directly_subsidized=kind == "subsidy") if completed_on else None)
        for kind, amount in (("client", client), ("subsidy", subsidy)) if amount > 0)

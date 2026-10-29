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


def payroll_installments(candidate: AssignmentPayrollCandidate, completed_on: date | None) -> tuple[PayrollInstallment, ...]:
    total = candidate.total_payable.amount
    subsidy = min(total, candidate.covered_salary) if candidate.directly_subsidized else 0
    client = total - subsidy
    return tuple(PayrollInstallment(kind, amount,
        funding_due_date(completed_on, directly_subsidized=kind == "subsidy") if completed_on else None)
        for kind, amount in (("client", client), ("subsidy", subsidy)) if amount > 0)


def installment_balances(client: int, subsidy: int, paid: int) -> tuple[int, int]:
    """Allocate immutable actual net payouts to the earlier client portion first."""
    return max(0, client - max(0, paid)), max(0, subsidy - max(0, paid - client))

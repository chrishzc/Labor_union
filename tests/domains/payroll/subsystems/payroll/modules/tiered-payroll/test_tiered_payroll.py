from datetime import date
from decimal import Decimal

from domains.payroll.calculation import AssignmentRateSnapshot, OfficialAssignmentServiceFacts, PayrollPolicyKind, PayrollTerms, build_case_payroll_candidate
from domains.payroll.tiered_rates import TieredPayrollRate, funding_due_date
from shared_kernel.money import MoneyNTD


def test_subsidy_budget_is_shared_across_assignments_in_service_date_order():
    tier = TieredPayrollRate(350, 300, Decimal(10), True)
    # Assignment identity sort differs from chronological ownership.
    assignments = (OfficialAssignmentServiceFacts("a", 1, (date(2026, 10, 2),)),
        OfficialAssignmentServiceFacts("b", 2, (date(2026, 10, 1),)))
    rates = tuple(AssignmentRateSnapshot(item.assignment_identity, "pricing-1", PayrollPolicyKind.SUBSIDIZED_CITIZEN, MoneyNTD(350), tier) for item in assignments)
    result = build_case_payroll_candidate(assignments, rates, PayrollTerms(2, 8, MoneyNTD(0)))
    by_identity = {item.assignment_identity: item for item in result.assignments}
    assert by_identity["b"].total_payable.amount == 8 * 350
    assert by_identity["a"].total_payable.amount == 2 * 350 + 6 * 300
    assert result.total_payable.amount == 10 * 350 + 6 * 300


def test_due_dates_use_service_end_month_and_roll_year_independently():
    assert funding_due_date(date(2026, 12, 31), directly_subsidized=False) == date(2027, 1, 15)
    assert funding_due_date(date(2026, 12, 31), directly_subsidized=True) == date(2027, 2, 15)


def test_installment_cash_closes_only_due_portion_and_preserves_whole_entitlement():
    from domains.payroll.installments import installment_balances
    from domains.staff_payables.reconciliation import (OutgoingBankFact, StaffPrimaryBankAccount,
        StaffPayableFacts, StaffPayableStatus, build_staff_payout_candidate)
    assert installment_balances(12000,42000,12000) == (0,42000)
    assert installment_balances(12000,42000,14000) == (0,40000)
    payable = StaffPayableFacts('salary-root',1,MoneyNTD(54000),installment_limit=MoneyNTD(12000))
    bank = OutgoingBankFact('bank-fixture',1,MoneyNTD(12000),'account-fixture')
    account = StaffPrimaryBankAccount('account-fixture',1)
    candidate = build_staff_payout_candidate((bank,),(payable,),bank_accounts=(account,))
    assert candidate.obligation_total.amount == 12000
    assert candidate.resulting_status is StaffPayableStatus.PARTIALLY_PAID
    assert sum(link.allocated_amount.amount for link in candidate.obligation_links) == 12000

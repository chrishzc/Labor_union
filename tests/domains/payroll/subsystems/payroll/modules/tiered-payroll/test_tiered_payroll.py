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


def test_first_assignment_installment_uses_saved_schedule_before_order_projection_is_updated():
    from infrastructure.mysql.payroll_installments import persist_payroll_installments

    service_dates = tuple(date(2026, 11, day) for day in range(4, 10))
    service = OfficialAssignmentServiceFacts('assignment:1', 1, service_dates)
    rate = AssignmentRateSnapshot('assignment:1', 'pricing-1', PayrollPolicyKind.SUBSIDIZED_CITIZEN,
        MoneyNTD(400), TieredPayrollRate(400, 500, Decimal(40), False))
    candidate = build_case_payroll_candidate((service,), (rate,), PayrollTerms(6, 7, MoneyNTD(500)))
    class Cursor:
        def __init__(self): self.installments = []
        def execute(self, sql, params):
            self.sql = sql
            if sql.startswith('INSERT INTO staff_obligation_installments'):
                self.installments.append(params)
        def fetchone(self):
            if 'AS actual_end_date' in self.sql:
                return {'actual_end_date': service_dates[-1] if 'staff_schedule' in self.sql else None}
            return None
        def fetchall(self): return [{'obligation_identity': 'salary:CASE:1'}]
    cursor = Cursor()
    persist_payroll_installments(cursor, 'CASE', candidate)
    assert cursor.installments == [
        ('salary:CASE:1', 'client', 17500, date(2026, 12, 15)),
        ('salary:CASE:1', 'subsidy', 0, None),
    ]


def test_zero_subsidy_uses_self_pay_rate_without_zeroing_salary():
    import pytest
    tier = TieredPayrollRate(0, 310, Decimal(0), False)
    assignment = OfficialAssignmentServiceFacts('non-citizen', 1, (date(2026, 10, 1),))
    rate = AssignmentRateSnapshot('non-citizen', 'pricing-1', PayrollPolicyKind.NON_CITIZEN, MoneyNTD(310), tier)
    result = build_case_payroll_candidate((assignment,), (rate,), PayrollTerms(1, 8, MoneyNTD(0)))
    assert result.total_payable.amount == 2480
    with pytest.raises(ValueError, match='payroll_tiered_rate_invalid'):
        TieredPayrollRate(0, 310, Decimal(1), False)


def test_installment_cash_closes_only_due_portion_and_preserves_whole_entitlement():
    from domains.staff_payables.reconciliation import (OutgoingBankFact, StaffPrimaryBankAccount,
        StaffPayableFacts, StaffPayableStatus, build_staff_payout_candidate)
    payable = StaffPayableFacts('salary-root',1,MoneyNTD(54000),installment_limit=MoneyNTD(12000))
    bank = OutgoingBankFact('bank-fixture',1,MoneyNTD(12000),'account-fixture')
    account = StaffPrimaryBankAccount('account-fixture',1)
    candidate = build_staff_payout_candidate((bank,),(payable,),bank_accounts=(account,))
    assert candidate.obligation_total.amount == 12000
    assert candidate.resulting_status is StaffPayableStatus.PARTIALLY_PAID
    assert sum(link.allocated_amount.amount for link in candidate.obligation_links) == 12000

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


def test_enabled_holiday_uses_payroll_rate_and_preserves_hours_and_fixed_fees():
    """S: noncitizen 8h; T: holiday salary; A: enable; R: 5120 plus unchanged fees."""
    day = date(2026, 10, 10)
    assignment = OfficialAssignmentServiceFacts("a", 1, (day,), (day,))
    rate = AssignmentRateSnapshot("a", "policy", PayrollPolicyKind.NON_CITIZEN, MoneyNTD(320))
    result = build_case_payroll_candidate((assignment,), (rate,), PayrollTerms(1, 8, MoneyNTD(100)))
    assert result.assignments[0].service_salary.amount == 5120
    assert result.assignments[0].actual_hours == 8
    assert result.assignments[0].double_pay_hours == 8
    assert result.total_payable.amount == 5220


def test_merged_holiday_premium_keeps_original_financial_dates_and_tier_consumption():
    """S: two 4h days merge to holiday 8h; A: map premium; R: salary doubles, volume stays 8."""
    first, second = date(2026, 10, 1), date(2026, 10, 2)
    assignment = OfficialAssignmentServiceFacts("a", 1, (first, second),
        holiday_hour_segments=((first, Decimal(0), Decimal(4)), (second, Decimal(0), Decimal(4))))
    rate = AssignmentRateSnapshot("a", "policy", PayrollPolicyKind.CITIZEN, MoneyNTD(300),
        TieredPayrollRate(300, 500, Decimal(4), False))
    result = build_case_payroll_candidate((assignment,), (rate,), PayrollTerms(2, 4, MoneyNTD(100)))
    assert result.assignments[0].service_salary.amount == 6400
    assert result.assignments[0].actual_hours == result.assignments[0].double_pay_hours == 8
    assert result.earned_floor_fee.amount == 100


def test_partial_holiday_after_tier_boundary_uses_segment_offset():
    day = date(2026, 10, 1)
    assignment = OfficialAssignmentServiceFacts("a", 1, (day,),
        holiday_hour_segments=((day, Decimal(4), Decimal(4)),))
    rate = AssignmentRateSnapshot("a", "policy", PayrollPolicyKind.CITIZEN, MoneyNTD(300),
        TieredPayrollRate(300, 500, Decimal(4), False))
    result = build_case_payroll_candidate((assignment,), (rate,), PayrollTerms(1, 8, MoneyNTD(0)))
    assert result.assignments[0].service_salary.amount == 4 * 300 + 8 * 500
    assert result.assignments[0].actual_hours == 8


def test_disabling_holiday_removes_only_salary_premium():
    from dataclasses import replace
    day = date(2026, 10, 10)
    enabled = OfficialAssignmentServiceFacts("a", 1, (day,), (day,))
    rate = AssignmentRateSnapshot("a", "policy", PayrollPolicyKind.CITIZEN, MoneyNTD(300))
    terms = PayrollTerms(1, 8, MoneyNTD(100))
    before = build_case_payroll_candidate((enabled,), (rate,), terms)
    after = build_case_payroll_candidate((replace(enabled, double_pay_dates=()),), (rate,), terms)
    assert before.total_payable.amount == 4900
    assert after.total_payable.amount == 2500
    assert before.assignments[0].actual_hours == after.assignments[0].actual_hours == 8


def test_mixed_plain_and_enabled_holiday_only_adds_holiday_service_salary():
    first, second = date(2026, 10, 9), date(2026, 10, 10)
    assignment = OfficialAssignmentServiceFacts("a", 1, (first, second), (second,))
    rate = AssignmentRateSnapshot("a", "policy", PayrollPolicyKind.NON_CITIZEN, MoneyNTD(320))
    result = build_case_payroll_candidate((assignment,), (rate,), PayrollTerms(2, 8, MoneyNTD(0)))
    assert result.total_payable.amount == 8 * 320 + 8 * 640
    assert result.assignments[0].actual_hours == 16
    assert result.assignments[0].double_pay_hours == 8


def test_overlapping_holiday_segments_are_rejected():
    import pytest
    day = date(2026, 10, 10)
    with pytest.raises(ValueError, match="payroll_holiday_segments_overlap"):
        OfficialAssignmentServiceFacts("a", 1, (day,), holiday_hour_segments=(
            (day, Decimal(0), Decimal(4)), (day, Decimal(2), Decimal(4)),
        ))


def test_tiered_double_pay_multiplier_does_not_consume_extra_subsidy_hours():
    from domains.payroll.tiered_rates import price_hours
    tier = TieredPayrollRate(300, 500, Decimal(8), False)
    assert price_hours(((Decimal(4), True), (Decimal(8), False)), tier) == (3600, 2000)


def test_holiday_covered_premium_does_not_increase_government_funding_portion():
    from domains.payroll.installments import payroll_installments
    days = (date(2026, 10, 1), date(2026, 10, 2))
    facts = OfficialAssignmentServiceFacts("a", 1, days, (days[0],))
    rate = AssignmentRateSnapshot("a", "policy", PayrollPolicyKind.SUBSIDIZED_CITIZEN, MoneyNTD(350),
        TieredPayrollRate(350, 350, Decimal(8), True))
    result = build_case_payroll_candidate((facts,), (rate,), PayrollTerms(2, 8, MoneyNTD(0))).assignments[0]
    portions = {item.funding_kind: item.amount for item in payroll_installments(result, days[-1])}
    assert result.total_payable.amount == 8400
    assert result.covered_holiday_salary == 2800
    assert portions == {"client": 5600, "subsidy": 2800}

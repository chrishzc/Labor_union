from domains.payroll.calculation import PayrollPolicyKind, PayrollTerms, rate_snapshot
from domains.payroll.historical_calculation import (
    HistoricalAssignmentServiceFacts,
    build_historical_case_payroll_candidate,
)
from shared_kernel.money import MoneyNTD


def test_historical_payroll_uses_single_pay_and_actual_days_beyond_contract():
    candidate = build_historical_case_payroll_candidate(
        service_facts=(
            HistoricalAssignmentServiceFacts("assignment-a", 3, 15),
            HistoricalAssignmentServiceFacts("assignment-b", 7, 11),
        ),
        rate_snapshots=(
            rate_snapshot("assignment-a", "policy-v1", PayrollPolicyKind.CITIZEN),
            rate_snapshot("assignment-b", "policy-v1", PayrollPolicyKind.NON_CITIZEN),
        ),
        terms=PayrollTerms(25, 24, MoneyNTD(1000)),
    )

    assert candidate.earned_floor_fee == MoneyNTD(1040)
    assert tuple(item.double_pay_hours for item in candidate.assignments) == (0, 0)
    assert candidate.assignments[0].service_salary == MoneyNTD(108000)
    assert candidate.assignments[1].service_salary == MoneyNTD(84480)
    assert tuple(item.floor_fee_allocated.amount for item in candidate.assignments) == (600, 440)
    assert candidate.total_payable == MoneyNTD(193520)

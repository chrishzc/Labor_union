from datetime import date, timedelta

import pytest

from domains.payroll.calculation import (
    AssignmentRateSnapshot,
    OfficialAssignmentServiceFacts,
    PayrollPolicyKind,
    PayrollTerms,
    build_case_payroll_candidate,
    rate_snapshot,
)
from shared_kernel.money import MoneyNTD


def test_twin_rate_is_legal_and_forty_hours_pay_18000():
    service_dates = tuple(date(2026, 1, 1) + timedelta(days=offset) for offset in range(5))
    candidate = build_case_payroll_candidate(
        (OfficialAssignmentServiceFacts("assignment-1", 7, service_dates),),
        (rate_snapshot("assignment-1", "approved-rates-v1", PayrollPolicyKind.TWINS),),
        PayrollTerms(5, 8, MoneyNTD(0)),
    )

    assert candidate.assignments[0].hourly_rate == MoneyNTD(450)
    assert candidate.assignments[0].service_salary == MoneyNTD(18_000)


def test_twin_rate_snapshot_rejects_a_nonapproved_rate():
    with pytest.raises(ValueError, match="payroll_rate_snapshot_mismatch"):
        AssignmentRateSnapshot(
            "assignment-1",
            "approved-rates-v1",
            PayrollPolicyKind.TWINS,
            MoneyNTD(350),
        )

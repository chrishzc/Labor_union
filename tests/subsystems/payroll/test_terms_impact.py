from datetime import date

from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import (
    AssignmentCandidate,
    SchedulingGenerationCandidate,
)
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import (
    ExistingStaffObligationTermsFact,
    PayrollTermsActionKind,
    PayrollTermsSourceFacts,
    SourceAssignmentPayrollTerms,
    StaffObligationDirection,
    StaffObligationKind,
    build_payroll_cancellation_impact,
)


def test_cancellation_establishes_a_service_obligation_from_canonical_facts():
    candidate = build_payroll_cancellation_impact(
        _source_facts(), _scheduling(), _terms(), "cancel-1"
    )

    action = candidate.actions[0]
    assert candidate.expected_payroll_version == 3
    assert candidate.resulting_payroll_version == 4
    assert action.action is PayrollTermsActionKind.ESTABLISH
    assert action.obligation_kind is StaffObligationKind.SERVICE_PAY
    assert action.direction is StaffObligationDirection.PAYABLE_TO_STAFF
    assert action.amount == MoneyNTD(5800)
    assert action.due_date == date(2026, 1, 31)


def test_cancellation_closes_removed_unpaid_service_obligation():
    source = _source_facts(
        obligations=(
            ExistingStaffObligationTermsFact(
                "old-service", 1, 7, StaffObligationKind.SERVICE_PAY,
                StaffObligationDirection.PAYABLE_TO_STAFF, MoneyNTD(2400),
                MoneyNTD(2400), MoneyNTD(0), False, date(2026, 1, 31),
            ),
        )
    )
    scheduling = SchedulingGenerationCandidate("CASE-1", 2, 1, 2, (1,), (), ())

    candidate = build_payroll_cancellation_impact(source, scheduling, _terms(), "cancel-2")

    assert candidate.actions[0].action is PayrollTermsActionKind.CLOSE_UNPAID
    assert candidate.actions[0].obligation_identity == "old-service"
    assert candidate.actions[0].amount == MoneyNTD(2400)


def test_cancellation_reverses_paid_removed_service_obligation():
    source = _source_facts(
        obligations=(
            ExistingStaffObligationTermsFact(
                "paid-service", 1, 7, StaffObligationKind.SERVICE_PAY,
                StaffObligationDirection.PAYABLE_TO_STAFF, MoneyNTD(2400),
                MoneyNTD(0), MoneyNTD(2400), True, date(2026, 1, 31),
            ),
        )
    )
    scheduling = SchedulingGenerationCandidate("CASE-1", 2, 1, 2, (1,), (), ())

    candidate = build_payroll_cancellation_impact(source, scheduling, _terms(), "cancel-3")

    action = candidate.actions[0]
    assert action.action is PayrollTermsActionKind.APPEND_FROZEN_DIFFERENCE
    assert action.obligation_kind is StaffObligationKind.REVERSAL
    assert action.direction is StaffObligationDirection.RECEIVABLE_FROM_STAFF
    assert action.amount == MoneyNTD(2400)


def _source_facts(obligations=()):
    return PayrollTermsSourceFacts(
        "CASE-1", 3,
        (SourceAssignmentPayrollTerms(1, 7, "policy-v1", PayrollPolicyKind.CITIZEN),),
        obligations, date(2026, 1, 31),
    )


def _scheduling():
    assignment = AssignmentCandidate(
        "CASE-1:g2:a1", 1, 7, 1, date(2026, 1, 1), date(2026, 1, 2),
        (date(2026, 1, 1), date(2026, 1, 2)), 16,
    )
    return SchedulingGenerationCandidate("CASE-1", 2, 1, 2, (1,), (assignment,), ())


def _terms():
    return OrderTerms(
        date(2026, 1, 1), 2, 8, MoneyNTD(1000),
        ServiceTimeTerms(None, None, None),
    )

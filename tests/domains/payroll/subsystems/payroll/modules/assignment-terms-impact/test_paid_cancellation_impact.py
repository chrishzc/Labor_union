"""Paid cancellation preserves one salary root and corrects its entitlement."""
from datetime import date

import pytest

from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import (
    ExistingStaffObligationTermsFact, PayrollTermsSourceFacts, SourceAssignmentPayrollTerms,
    StaffObligationDirection, StaffObligationKind, PayrollTermsActionKind,
    build_payroll_cancellation_impact, build_payroll_terms_impact,
)


@pytest.mark.parametrize('paid', (0, 1000, 8000))
def test_cancellation_updates_paid_entitlement_without_a_second_payable(paid):
    start, end, due = date(2026, 10, 21), date(2026, 10, 22), date(2026, 11, 30)
    root = ExistingStaffObligationTermsFact('original', 1, 7, StaffObligationKind.SERVICE_PAY,
        StaffObligationDirection.PAYABLE_TO_STAFF, MoneyNTD(8000), MoneyNTD(8000-paid),
        MoneyNTD(paid), True, due)
    facts = PayrollTermsSourceFacts('CANCEL', 3,
        (SourceAssignmentPayrollTerms(1, 7, 'frozen-rate', PayrollPolicyKind.CITIZEN),), (root,), due)
    assignment = AssignmentCandidate('CANCEL:g2:a1', 1, 7, 1, start, end, (start, end), 16)
    scheduling = SchedulingGenerationCandidate('CANCEL', 2, 1, 2, (1,), (assignment,), ())
    terms = OrderTerms(start, 2, 8, MoneyNTD(1000), ServiceTimeTerms(None, None, None))

    candidate = build_payroll_cancellation_impact(facts, scheduling, terms, 'early-end')

    assert len(candidate.actions) == 1
    action = candidate.actions[0]
    assert action.obligation_identity.startswith('staff-handover:')
    assert action.source_obligation_identity == root.obligation_identity
    assert action.direction is StaffObligationDirection.RECEIVABLE_FROM_STAFF
    assert action.amount == MoneyNTD(2200)
    settlement = candidate.frozen_settlements[0]
    assert settlement.previous_entitlement == MoneyNTD(8000)
    assert settlement.revised_entitlement == MoneyNTD(5800)
    assert settlement.paid_net_amount == MoneyNTD(paid)
    assert settlement.recovery_increase == MoneyNTD(max(0, paid-5800))
    assert action.due_date == due


@pytest.mark.parametrize('paid', (0, 1000, 8000))
def test_terms_shortening_preserves_paid_root_and_corrects_entitlement_once(paid):
    start, end = date(2026, 10, 1), date(2026, 10, 2)
    root = ExistingStaffObligationTermsFact(
        'original-paid', 1, 7, StaffObligationKind.SERVICE_PAY,
        StaffObligationDirection.PAYABLE_TO_STAFF, MoneyNTD(13000),
        MoneyNTD(13000-paid), MoneyNTD(paid), True, None,
    )
    facts = PayrollTermsSourceFacts(
        'TERMS', 2,
        (SourceAssignmentPayrollTerms(1, 7, 'frozen-rate', PayrollPolicyKind.CITIZEN,
                                      hourly_rate=MoneyNTD(300)),),
        (root,), None,
    )
    assignment = AssignmentCandidate('TERMS:g2:a1', 1, 7, 1, start, end, (start, end), 16)
    scheduling = SchedulingGenerationCandidate('TERMS', 2, 1, 2, (1,), (assignment,), ())
    terms = OrderTerms(start, 2, 8, MoneyNTD(1000), ServiceTimeTerms(None, None, None))

    candidate = build_payroll_terms_impact(facts, scheduling, terms, 'terms-early-end')

    action, = candidate.actions
    assert action.action is PayrollTermsActionKind.APPEND_FROZEN_DIFFERENCE
    assert action.source_obligation_identity == root.obligation_identity
    assert action.direction is StaffObligationDirection.RECEIVABLE_FROM_STAFF
    assert action.amount == MoneyNTD(7200)
    settlement, = candidate.frozen_settlements
    assert settlement.previous_entitlement == MoneyNTD(13000)
    assert settlement.revised_entitlement == MoneyNTD(5800)
    assert settlement.paid_net_amount == MoneyNTD(paid)
    assert settlement.recovery_increase == MoneyNTD(max(0, paid-5800))
    assert root.contractual_amount == MoneyNTD(13000)
    assert root.paid_net_amount == MoneyNTD(paid)
    assert action.due_date is None

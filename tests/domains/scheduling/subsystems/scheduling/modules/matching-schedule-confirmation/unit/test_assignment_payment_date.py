from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import CasePayrollPolicyTerms, PayrollTermsSourceFacts
from subsystems.scheduling.assignment_plan_impacts import (
    _staff_payment_due_date,
    build_payroll_assignment_impact,
)


def _inputs(identity, payable, *, hours=8, floor=0, existing=None):
    days = (date(2026, 12, 30), date(2027, 1, 2))
    scheduling = SchedulingGenerationCandidate(
        'CASE-DATE', 1, 0, 1, (),
        (AssignmentCandidate('segment-1', None, 1, 1, days[0], days[-1], days, hours * 2),), (),
    )
    facts = SimpleNamespace(
        payroll=PayrollTermsSourceFacts(
            'CASE-DATE', 0, (), (), existing,
            CasePayrollPolicyTerms('approved-rates-v1', PayrollPolicyKind.CITIZEN),
        ),
        client_finance=SimpleNamespace(identity_status=identity),
        order_terms=OrderTerms(days[0], 2, hours, MoneyNTD(floor), ServiceTimeTerms(None, None, None)),
    )
    finance = SimpleNamespace(payload=SimpleNamespace(
        stage_plans=(SimpleNamespace(amount=MoneyNTD(payable)),),
    ))
    return facts, scheduling, finance


@pytest.mark.parametrize('identity,payable,hours,floor,expected', [
    ('一般市民', 4800, 8, 0, date(2027, 2, 15)),
    ('補助市民', 0, 8, 0, date(2027, 3, 15)),
    ('補助市民', 1000, 8, 1000, date(2027, 2, 15)),
    ('補助市民', 2400, 80, 0, date(2027, 2, 15)),
])
def test_first_assignment_forms_payment_date_before_service_starts(identity, payable, hours, floor, expected):
    facts, scheduling, finance = _inputs(identity, payable, hours=hours, floor=floor)
    assert _staff_payment_due_date(facts, scheduling, finance) == expected
    # Payroll receives that date in its formal obligation candidate, before completion.
    if hours == 8:
        impact = build_payroll_assignment_impact(facts, scheduling, finance)
        assert impact.payload.actions
        assert all(action.due_date == expected for action in impact.payload.actions)


def test_established_payment_date_survives_later_schedule_changes():
    facts, scheduling, finance = _inputs('一般市民', 4800, existing=date(2026, 11, 15))
    assert _staff_payment_due_date(facts, scheduling, finance) == date(2026, 11, 15)


def test_no_assignment_does_not_invent_payment_date():
    facts, scheduling, finance = _inputs('一般市民', 4800)
    assert _staff_payment_due_date(facts, replace(scheduling, assignments=()), finance) is None

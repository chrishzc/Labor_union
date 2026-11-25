import pytest
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


@pytest.mark.parametrize("rebuilt", [False, True])
def test_cancellation_floor_fee_follows_source_assignment_instead_of_candidate_order(rebuilt):
    from dataclasses import replace
    from types import SimpleNamespace
    from subsystems.payroll.terms_impact import _service_facts
    from domains.payroll.calculation import build_case_payroll_candidate, PayrollTerms, rate_snapshot

    assignments = tuple(AssignmentCandidate(
        f"CASE-1:g2:a{sequence}", source_id, staff_id, sequence,
        date(2026, 1, staff_id), date(2026, 1, staff_id),
        (date(2026, 1, staff_id),), 8,
    ) for sequence, source_id, staff_id in ((1, 20 if rebuilt else 10, 1), (2, 30 if rebuilt else 2, 2)))
    scheduling = SchedulingGenerationCandidate("CASE-1", 2, 1, 2, (20, 30) if rebuilt else (2, 10), assignments, ())
    source = replace(_source_facts(), source_terms=tuple(
        SourceAssignmentPayrollTerms(
            source_id, staff_id, "policy-v1", PayrollPolicyKind.CITIZEN,
            financial_assignment_identity=f"assignment:{10 if staff_id == 1 else 2}" if rebuilt else None,
        )
        for source_id, staff_id in ((20 if rebuilt else 10, 1), (30 if rebuilt else 2, 2))
    ))
    impact = build_payroll_cancellation_impact(source, scheduling, replace(_terms(), floor_fee=MoneyNTD(1)), "tie")
    preview = {item.staff_id: item.floor_fee_allocated.amount for item in impact.payroll.assignments}
    assert preview == {1: 0, 2: 1}
    formal_facts = tuple(replace(item, assignment_identity=f"assignment:{40 + item.staff_id}")
                         for item in _service_facts(SimpleNamespace(scheduling=scheduling, source_terms=source.source_terms)))
    formal = build_case_payroll_candidate(formal_facts, tuple(
        rate_snapshot(item.assignment_identity, "policy-v1", PayrollPolicyKind.CITIZEN) for item in formal_facts
    ), PayrollTerms(2, 8, MoneyNTD(1)))
    assert {item.staff_id: item.floor_fee_allocated.amount for item in formal.assignments} == preview


@pytest.mark.parametrize("kind,expected", [(PayrollPolicyKind.CITIZEN, 8200), (PayrollPolicyKind.NON_CITIZEN, 8680)])
def test_first_formal_candidate_includes_enabled_holiday_without_extra_writer(kind, expected):
    from dataclasses import replace
    from subsystems.payroll.terms_impact import build_payroll_handover_impact
    source = replace(_source_facts(), double_pay_dates=(date(2026, 1, 1),),
        source_terms=(replace(_source_facts().source_terms[0], policy_kind=kind),))
    candidate = build_payroll_handover_impact(source, _scheduling(), _terms(), "holiday-first-formal")
    assert candidate.expected_payroll_version == 3
    assert candidate.resulting_payroll_version == 4
    assert sum(action.amount.amount for action in candidate.actions) == expected


@pytest.mark.parametrize("bound_policy", [False, True])
def test_full_subsidy_initial_holiday_recomputes_entitlement_without_assigning_funding(bound_policy):
    from dataclasses import replace
    from decimal import Decimal
    from domains.payroll.tiered_rates import TieredPayrollRate
    from subsystems.payroll.terms_impact import build_payroll_handover_impact
    item = replace(_source_facts().source_terms[0], policy_kind=PayrollPolicyKind.SUBSIDIZED_CITIZEN)
    if bound_policy:
        item = replace(item, hourly_rate=MoneyNTD(350),
            tiered=TieredPayrollRate(350, 350, Decimal(120), True))
    source = replace(_source_facts(), source_terms=(item,), double_pay_dates=(date(2026, 1, 1),))
    candidate = build_payroll_handover_impact(source, _scheduling(), _terms(), "full-holiday-pending")
    assert sum(action.amount.amount for action in candidate.actions) == 9400
    assert candidate.resulting_payroll_version == candidate.expected_payroll_version + 1


@pytest.mark.parametrize("identity", ["補助市民", "原住民"])
def test_legacy_initial_holiday_recomputes_entitlement_even_when_funding_limit_is_missing(identity):
    from dataclasses import replace
    from subsystems.payroll.terms_impact import build_payroll_handover_impact
    source = replace(_source_facts(), identity_status=identity, double_pay_dates=(date(2026, 1, 1),))
    candidate = build_payroll_handover_impact(source, _scheduling(), replace(_terms(), floor_fee=MoneyNTD(500)), "unknown-limit")
    assert sum(action.amount.amount for action in candidate.actions) == 7700
    assert candidate.resulting_payroll_version == candidate.expected_payroll_version + 1

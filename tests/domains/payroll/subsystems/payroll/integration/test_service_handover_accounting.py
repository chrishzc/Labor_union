from dataclasses import replace
from datetime import date

import pytest

from domains.orders.terms import OrderTerms, ServiceTimeTerms
from domains.payroll.calculation import PayrollPolicyKind
from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import (
    ExistingStaffObligationTermsFact, PayrollTermsActionKind, PayrollTermsSourceFacts,
    SourceAssignmentPayrollTerms, StaffObligationDirection, StaffObligationKind,
    build_payroll_handover_impact,
    build_payroll_cancellation_impact,
)

DAY = date(2026, 10, 21)
DUE = date(2026, 11, 30)
TERMS = OrderTerms(DAY, 2, 8, MoneyNTD(1000), ServiceTimeTerms(None, None, None))


def root(paid=2000):
    return ExistingStaffObligationTermsFact("original", 1, 7, StaffObligationKind.SERVICE_PAY,
        StaffObligationDirection.PAYABLE_TO_STAFF, MoneyNTD(8000), MoneyNTD(8000 - paid),
        MoneyNTD(paid), True, DUE)


def source(paid=2000, *, current_id=1, corrections=(), adjustment=0):
    return PayrollTermsSourceFacts("HANDOVER", 3,
        (SourceAssignmentPayrollTerms(current_id, 7, "frozen-rate", PayrollPolicyKind.CITIZEN,
                                     adjustment_total=MoneyNTD(adjustment),
                                     ancestor_assignment_ids=(1,) if current_id != 1 else ()),),
        (root(paid),) + corrections, DUE)


def scheduling(*, source_id=1, days=2):
    dates = (DAY, date(2026, 10, 22))[:days]
    assignment = AssignmentCandidate("HANDOVER:g2:a1", source_id, 7, 1, dates[0], dates[-1], dates, 8 * days)
    return SchedulingGenerationCandidate("HANDOVER", 2, 1, 2, (source_id,), (assignment,), ())


def correction(action):
    return ExistingStaffObligationTermsFact(action.obligation_identity, 2, 7,
        action.obligation_kind, action.direction, action.amount, action.amount,
        MoneyNTD(0), False, DUE, action.source_obligation_identity)


@pytest.mark.parametrize("paid", (0, 2000))
def test_partial_or_fully_returned_payout_reduces_entitlement_without_adding_a_second_payable(paid):
    candidate = build_payroll_handover_impact(source(paid), scheduling(), TERMS, "handover-1")
    assert len(candidate.actions) == 1
    action = candidate.actions[0]
    assert action.obligation_kind is StaffObligationKind.REVERSAL
    assert action.source_obligation_identity == "original"
    assert action.amount == MoneyNTD(2200)
    settlement = candidate.frozen_settlements[0]
    assert settlement.revised_entitlement == MoneyNTD(5800)
    assert settlement.revised_entitlement - settlement.paid_net_amount == MoneyNTD(5800 - paid)
    assert settlement.recovery_increase == MoneyNTD(0)
    assert all(item.action is not PayrollTermsActionKind.ESTABLISH for item in candidate.actions)
    assert action.due_date == DUE


def test_only_actual_overpayment_creates_recovery_and_later_generations_consume_prior_delta_once():
    first = build_payroll_handover_impact(source(8000), scheduling(), TERMS, "handover-1")
    assert first.frozen_settlements[0].recovery_increase == MoneyNTD(2200)
    successor = source(8000, current_id=2, corrections=(correction(first.actions[0]),))
    unchanged = build_payroll_handover_impact(successor, scheduling(source_id=2), TERMS, "handover-2")
    assert unchanged.actions == ()
    assert unchanged.frozen_settlements[0].previous_entitlement == MoneyNTD(5800)
    assert unchanged.frozen_settlements[0].recovery_increase == MoneyNTD(0)
    next_change = build_payroll_handover_impact(successor, scheduling(source_id=2, days=1), TERMS, "handover-3")
    assert len(next_change.actions) == 1
    assert next_change.actions[0].source_obligation_identity == "original"
    assert next_change.actions[0].amount == MoneyNTD(2900)
    assert next_change.frozen_settlements[0].recovery_increase == MoneyNTD(2900)


def test_an_already_removed_frozen_family_does_not_repeat_its_reversal():
    first = build_payroll_handover_impact(source(8000), replace(scheduling(), assignments=()), TERMS, "handover-1")
    assert first.actions[0].amount == MoneyNTD(8000)
    second = build_payroll_handover_impact(source(8000, current_id=2, corrections=(correction(first.actions[0]),)),
        replace(scheduling(source_id=2), assignments=()), TERMS, "handover-2")
    assert second.actions == ()
    assert second.frozen_settlements[0].recovery_increase == MoneyNTD(0)


def test_fixed_adjustment_is_retained_once_by_original_caregiver():
    generation = scheduling(days=1)
    replacement = AssignmentCandidate("HANDOVER:g2:a2", 1, 8, 2,
        date(2026, 10, 22), date(2026, 10, 22), (date(2026, 10, 22),), 8)
    generation = replace(generation, assignments=generation.assignments + (replacement,))
    candidate = build_payroll_handover_impact(source(adjustment=100), generation, TERMS, "handover-1")
    assert [(item.staff_id, item.effective_adjustments.amount) for item in candidate.payroll.assignments] == [(7, 100), (8, 0)]
    assert sum(item.effective_adjustments.amount for item in candidate.payroll.assignments) == 100
    assert candidate.frozen_settlements[0].revised_entitlement == MoneyNTD(3000)
    assert next(action for action in candidate.actions if action.staff_id == 8).amount == MoneyNTD(2900)


def test_inconsistent_frozen_rate_blocks_instead_of_silently_replacing_it_with_policy_default():
    facts = source()
    facts = replace(facts, source_terms=(replace(facts.source_terms[0], hourly_rate=MoneyNTD(451)),))
    with pytest.raises(ValueError, match="payroll_rate_snapshot_mismatch"):
        build_payroll_handover_impact(facts, scheduling(), TERMS, "handover-1")


def test_paid_independent_adjustment_blocks_instead_of_guessing_its_settlement():
    adjustment = ExistingStaffObligationTermsFact("staff-obligation:adjustment:paid", 1, 7,
        StaffObligationKind.ADJUSTMENT, StaffObligationDirection.PAYABLE_TO_STAFF,
        MoneyNTD(100), MoneyNTD(0), MoneyNTD(100), True, DUE, "original")
    with pytest.raises(ValueError, match="handover_paid_adjustment_review_required"):
        build_payroll_handover_impact(source(corrections=(adjustment,)), scheduling(), TERMS, "handover-1")


def test_unpaid_adjustment_projection_is_closed_once_and_allocation_stays_in_new_entitlement():
    adjustment = ExistingStaffObligationTermsFact("staff-obligation:adjustment:unpaid", 1, 7,
        StaffObligationKind.ADJUSTMENT, StaffObligationDirection.PAYABLE_TO_STAFF,
        MoneyNTD(100), MoneyNTD(100), MoneyNTD(0), False, DUE, "original")
    candidate = build_payroll_handover_impact(source(corrections=(adjustment,), adjustment=100), scheduling(), TERMS, "handover-1")
    assert candidate.actions[0].action is PayrollTermsActionKind.CLOSE_UNPAID
    assert candidate.actions[0].obligation_identity == adjustment.obligation_identity
    assert candidate.frozen_settlements[0].revised_entitlement == MoneyNTD(5900)


def test_prior_unclassified_correction_is_blocked_instead_of_creating_duplicate_recovery():
    prior = ExistingStaffObligationTermsFact("other-correction", 1, 7,
        StaffObligationKind.REVERSAL, StaffObligationDirection.RECEIVABLE_FROM_STAFF,
        MoneyNTD(2200), MoneyNTD(2200), MoneyNTD(0), False, DUE, "original")
    with pytest.raises(ValueError, match="handover_obligation_lineage_ambiguous"):
        build_payroll_handover_impact(source(8000, corrections=(prior,)), scheduling(), TERMS, "handover-1")


def test_later_substitution_reuses_the_handover_settlement_and_rate_lineage_even_when_money_is_unchanged():
    from types import SimpleNamespace
    from infrastructure.mysql.payroll_terms_writer import _rate_source_identity

    first = build_payroll_handover_impact(source(8000), scheduling(), TERMS, "handover-1")
    successor = source(8000, current_id=2, corrections=(correction(first.actions[0]),))
    next_change = build_payroll_cancellation_impact(successor, scheduling(source_id=2), TERMS, "later-substitution")
    assert next_change.actions == ()
    assert next_change.frozen_settlements[0].recovery_increase.is_zero
    assert _rate_source_identity(SimpleNamespace(candidate=next_change), next_change.carried_rate_snapshots[0]) == "carried-from:2"


def test_returning_caregiver_starts_a_new_payment_family_without_offsetting_prior_paid_service():
    dates = (DAY, date(2026, 10, 22))
    old_family = AssignmentCandidate("HANDOVER:g3:a1", 3, 7, 1, dates[0], dates[0], (dates[0],), 8)
    returning = AssignmentCandidate("HANDOVER:g3:a2", 4, 7, 2, dates[1], dates[1], (dates[1],), 8)
    generation = SchedulingGenerationCandidate("HANDOVER", 3, 2, 3, (3, 4), (old_family, returning), ())
    facts = replace(source(), source_terms=(
        SourceAssignmentPayrollTerms(3, 7, "policy-v1", PayrollPolicyKind.CITIZEN, ancestor_assignment_ids=(1,)),
        SourceAssignmentPayrollTerms(4, 8, "policy-v1", PayrollPolicyKind.CITIZEN),
    ))
    candidate = build_payroll_handover_impact(facts, generation, TERMS, "returning-caregiver")
    created = [action for action in candidate.actions if action.action is PayrollTermsActionKind.ESTABLISH]
    assert len(created) == 1
    assert created[0].candidate_assignment_key == "HANDOVER:g3:a2"
    assert created[0].amount == MoneyNTD(2900)
    assert candidate.frozen_settlements[0].revised_entitlement == MoneyNTD(2900)


def test_historical_settlement_is_never_treated_as_unpaid_or_reopened_by_handover():
    facts = source()
    facts = replace(facts, existing_obligations=(replace(facts.existing_obligations[0], historically_settled=True),))
    with pytest.raises(ValueError, match="handover_historical_payment_review_required"):
        build_payroll_handover_impact(facts, scheduling(), TERMS, "handover-1")


def test_successor_keeps_the_original_double_pay_salary_instead_of_losing_the_special_day():
    facts = source()
    special_day = date(2026, 10, 22)
    facts = replace(facts, source_terms=(replace(facts.source_terms[0], double_pay_dates=(special_day,)),),
                    existing_obligations=(replace(facts.existing_obligations[0], contractual_amount=MoneyNTD(8200)),))
    generation = scheduling(days=1)
    successor = AssignmentCandidate("HANDOVER:g2:a2", 1, 8, 2, special_day, special_day, (special_day,), 8,
                                    double_pay_dates=(special_day,))
    generation = replace(generation, assignments=generation.assignments + (successor,))
    candidate = build_payroll_handover_impact(facts, generation, TERMS, "handover-1")
    replacement_pay = next(item for item in candidate.payroll.assignments if item.staff_id == 8)
    assert replacement_pay.service_salary == MoneyNTD(4800)
    assert replacement_pay.double_pay_hours == 8
    assert replacement_pay.total_payable == MoneyNTD(5300)


def test_negative_adjustment_cannot_turn_reduced_service_into_a_negative_payable():
    with pytest.raises(ValueError, match="handover_adjustment_review_required"):
        build_payroll_handover_impact(source(adjustment=-5000), scheduling(days=1), TERMS, "handover-1")

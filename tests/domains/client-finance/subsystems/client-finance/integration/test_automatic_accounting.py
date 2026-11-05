"""Automatic payable eligibility follows source facts, never a manual posting stage."""
from dataclasses import replace
from datetime import date, timedelta

from domains.client_finance.obligation_planning import (
    ClientChargeDay, ClientFinanceTermsFacts, ClientPaymentTerms, ExistingClientStageObligation,
    automatic_subsidy_return_plan, build_client_finance_terms_candidate,
)
from shared_kernel.money import MoneyNTD


def facts(*, paid=True):
    result = ClientFinanceTermsFacts('AUTO-1', 4, 8, MoneyNTD(0),
        tuple(ClientChargeDay(date(2026,9,1)+timedelta(days=i),False) for i in range(30)),
        ClientPaymentTerms(5,MoneyNTD(300),date(2026,8,20),date(2026,9,1),date(2026,9,16)),())
    plan=build_client_finance_terms_candidate(result,'source:1')
    return replace(result, existing_obligations=tuple(ExistingClientStageObligation(
        f'AUTO-1:{stage.payment_stage.value}',stage.payment_stage,stage.amount,
        stage.amount if paid else MoneyNTD(0),stage.due_date,paid) for stage in plan.stage_plans))


def test_service_terms_automatically_determine_subsidy_return():
    plan=automatic_subsidy_return_plan(replace(facts(),subsidy_return_confirmed=True,confirmed_subsidy_amount=MoneyNTD(12000)),identity_status='一般市民',
        completed_on=date(2026,9,30),existing_return_count=0)
    assert plan.amount==MoneyNTD(12000)
    assert plan.obligation_identity=='client-subsidy-return:AUTO-1:terminal'


def test_calculation_does_not_wait_for_collection_or_a_manual_creation_stage():
    common=dict(identity_status='一般市民',completed_on=date(2026,9,30),existing_return_count=0)
    assert automatic_subsidy_return_plan(facts(paid=False),**common) is None
    assert automatic_subsidy_return_plan(replace(facts(paid=False),subsidy_return_confirmed=True,confirmed_subsidy_amount=MoneyNTD(12000)),**common).amount==MoneyNTD(12000)
    assert automatic_subsidy_return_plan(facts(),**{**common,'completed_on':None}) is None
    assert automatic_subsidy_return_plan(facts(),**{**common,'existing_return_count':1}) is None
    assert automatic_subsidy_return_plan(facts(),**{**common,'identity_status':'非市民'}) is None
    assert automatic_subsidy_return_plan(facts(),**{**common,'identity_status':None}) is None


def test_canonical_identity_caps_and_social_welfare_self_pay_excess():
    from decimal import Decimal
    from domains.client_finance.subsidy_coverage import derive_subsidy_coverage
    assert derive_subsidy_coverage('一般市民',Decimal(240),Decimal(0)).subsidy_hours==40
    assert derive_subsidy_coverage('補助市民',Decimal(240),Decimal(0)).subsidy_hours==120
    source=replace(facts(paid=False),existing_obligations=(),identity_status='補助市民')
    candidate=build_client_finance_terms_candidate(source,'social:terms')
    assert sum(stage.amount.amount for stage in candidate.stage_plans)==36000
    assert candidate.subsidy_return_plan is None


def test_pending_terms_candidate_contains_current_refund_and_tracks_end_date():
    source=replace(facts(paid=False),identity_status='一般市民',existing_obligations=(),existing_subsidy_return_count=1,subsidy_return_confirmed=True,confirmed_subsidy_amount=MoneyNTD(12000))
    candidate=build_client_finance_terms_candidate(source,'auto:pending')
    assert candidate.subsidy_return_plan.amount==MoneyNTD(12000)
    assert candidate.subsidy_return_plan.due_date==date(2026,11,15)
    moved=replace(source,charge_days=tuple(replace(day,service_date=day.service_date+timedelta(days=31)) for day in source.charge_days))
    assert build_client_finance_terms_candidate(moved,'auto:moved').subsidy_return_plan.due_date==date(2026,12,15)


def test_full_subsidy_without_customer_funding_never_creates_customer_refund():
    source=replace(facts(),charge_days=facts().charge_days[:15],client_service_charge_waived=True)
    assert automatic_subsidy_return_plan(source,identity_status='低收入戶',
        completed_on=date(2026,9,15),existing_return_count=0) is None


def test_full_subsidy_rule_uses_effective_limit_and_includes_the_fee_without_customer_collection():
    from decimal import Decimal
    from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule
    for identity in ('補助市民', '原住民'):
        pricing = CasePricingTerms(identity, IdentityRule.SOCIAL, Decimal(12), HourlyRates(300,350), HourlyRates(300,350))
        for hours in (11, 12, 13):
            source = replace(facts(paid=False), service_hours_per_day=1,
                charge_days=tuple(ClientChargeDay(date(2026,9,1)+timedelta(days=i),False) for i in range(hours)),
                identity_status=identity, pricing=pricing, floor_fee=MoneyNTD(500), existing_obligations=())
            candidate = build_client_finance_terms_candidate(source, f'full:{identity}:{hours}')
            assert sum(stage.amount.amount for stage in candidate.stage_plans) == (0 if hours <= 12 else 850)
            assert candidate.subsidy_return_plan is None


def test_eligibility_alone_does_not_create_a_customer_refund():
    source=replace(facts(), identity_status='一般市民', existing_obligations=())
    assert build_client_finance_terms_candidate(source,'no-confirmed-payee').subsidy_return_plan is None


def test_confirmed_customer_refund_uses_government_owner_amount_not_client_identity_rate():
    source=replace(facts(),identity_status='補助市民',subsidy_return_confirmed=True,confirmed_subsidy_amount=MoneyNTD(9876))
    result=automatic_subsidy_return_plan(source,identity_status='補助市民',completed_on=date(2026,9,30),existing_return_count=0)
    assert result.amount == MoneyNTD(9876)


def test_full_subsidy_keeps_formed_dates_and_blocks_automatic_conversion_of_paid_history():
    from decimal import Decimal
    from domains.client_finance.pricing_policy import CasePricingTerms,HourlyRates,IdentityRule
    source=replace(facts(), identity_status='原住民',service_hours_per_day=1,charge_days=facts().charge_days[:12],
        pricing=CasePricingTerms('原住民',IdentityRule.SOCIAL,Decimal(12),HourlyRates(300,350),HourlyRates(300,350)))
    result=build_client_finance_terms_candidate(source,'protected-full')
    assert result.blockers == ('full_subsidy_existing_financial_history_conflict',)
    assert [stage.due_date for stage in result.stage_plans] == [item.due_date for item in source.existing_obligations]
    assert all(item.net_settled_amount == item.contracted_amount for item in source.existing_obligations)

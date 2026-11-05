"""Automatic payable eligibility follows source facts, never a manual posting stage."""
from dataclasses import replace
from datetime import date, timedelta

from domains.client_finance.obligation_planning import (
    ClientChargeDay, ClientFinanceTermsFacts, ClientPaymentTerms, ExistingClientStageObligation,
    automatic_subsidy_return_plan, build_client_finance_terms_candidate,
    confirmed_zero_payment_stages,
)
from domains.client_finance.reconciliation import PaymentStage
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


def test_zero_deposit_subsidized_case_fills_first_installment_before_second():
    source = facts(paid=False)
    start = source.charge_days[0].service_date
    for days, amounts in ((20, [0, 14000, 0]), (35, [0, 42000, 14000])):
        case = replace(
            source, identity_status="補助市民", existing_obligations=(),
            payment_terms=replace(source.payment_terms, deposit_service_days=0,
                                  client_hourly_rate=MoneyNTD(350)),
            charge_days=tuple(ClientChargeDay(start + timedelta(days=i), False) for i in range(days)),
        )
        candidate = build_client_finance_terms_candidate(case, f"subsidized-installments:{days}")
        assert [stage.amount.amount for stage in candidate.stage_plans] == amounts
        assert candidate.stage_plans[-1].due_date == (start + timedelta(days=15) if amounts[-1] else None)


def test_zero_stage_proof_excludes_positive_missing_and_conflicting_obligations():
    source = facts(paid=False)
    short_case = replace(source, charge_days=source.charge_days[:10], existing_obligations=())
    assert confirmed_zero_payment_stages(short_case) == {PaymentStage.SECOND}

    recorded_deposit = replace(source.existing_obligations[0], contracted_amount=MoneyNTD(100))
    assert not confirmed_zero_payment_stages(replace(short_case, existing_obligations=(recorded_deposit,)))


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


def test_manual_handoff_writer_waits_for_formal_end_and_never_rewrites_an_existing_payable(monkeypatch):
    from types import SimpleNamespace
    import infrastructure.mysql.automatic_client_accounting as writer
    import infrastructure.mysql.accounting_workspace_repository as workspace
    from domains.staff_payables.subsidy_handoff import SubsidyPayableHandoff
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from datetime import datetime

    class Cursor:
        connection = object()
        def execute(self, sql, params):
            assert sql.startswith('SELECT 1 FROM client_finance_accounts')
        def fetchone(self): return {'present': 1}

    order = dict(status='服務中', start_date=date(2026,9,1),service_days=30,service_hours_per_day=8,floor_fee=0)
    source = SimpleNamespace(identity_status='一般市民', existing_subsidy_return_count=0)
    captures, loads = [], []
    decision = SubsidyPayableHandoff('advance',True,True,12000,False,True)
    monkeypatch.setattr(writer,'select_order',lambda *_a,**_k:order)
    def load(*args, **options):
        loads.append(options)
        assert options['allow_planned'] is False
        return facts(), source
    monkeypatch.setattr(writer,'load_calculable_client_finance_facts',load)
    monkeypatch.setattr(workspace,'query_subsidy_payable_handoff',lambda *_:decision)
    monkeypatch.setattr(writer,'persist_client_finance_terms_impact',lambda *_: captures.append(_[-1]))
    options=dict(actor=ActorContext('test:handoff'),key=IdempotencyKey('handoff:test'),
        correlation_id=CorrelationId('handoff:test'),source_family='service-completion',source_id=1)
    writer.synchronize_terminal_subsidy_return(Cursor(),'AUTO-1',**options)
    assert not loads and not captures  # Planned dates and early choice never authorize a refund.
    order['status']='訂單完成'
    writer.synchronize_terminal_subsidy_return(Cursor(),'AUTO-1',**options)
    assert len(captures)==1 and captures[0].candidate.subsidy_return_plan.amount==MoneyNTD(12000)
    source.existing_subsidy_return_count=1
    writer.synchronize_terminal_subsidy_return(Cursor(),'AUTO-1',**options)
    assert len(captures)==1  # Formed amounts, snapshots and dates are left to the original correction flow.
    source.existing_subsidy_return_count=0
    decision=SubsidyPayableHandoff('direct',True,True,12000,False,True,client_subsidy_reason='原退款與新安排不符')
    writer.synchronize_terminal_subsidy_return(Cursor(),'AUTO-1',**options)
    assert len(captures)==1

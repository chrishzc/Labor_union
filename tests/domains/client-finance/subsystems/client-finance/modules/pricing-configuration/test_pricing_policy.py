"""
File: test_pricing_policy.py
Description: 驗證帳務計價規則、試算不可變性、延遲連線唯讀目錄快取與儲存後失效邊界。
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from dataclasses import replace

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, PricingPolicy
from subsystems.client_finance.pricing_configuration import (
    CasePricingFacts, PricingServiceDay, pricing_impact, PricingConfigurationApplication, PricingConflict, pricing_payload,
)


def terms(rule=IdentityRule.SOCIAL):
    return CasePricingTerms("補助市民", rule, Decimal(120), HourlyRates(350, 300), HourlyRates(350, 310))


def test_historical_volume_preserves_original_installments_and_manual_amounts():
    from subsystems.client_finance.pricing_configuration import HistoricalAmountFacts, build_historical_repricing_plan
    current=CasePricingTerms('一般市民',IdentityRule.CITIZEN,Decimal(40),HourlyRates(300,400),HourlyRates(300,400))
    facts=CasePricingFacts('historical',0,(1,1,1,0,3,5),current,'manual',(),0,historical_service_hours=Decimal(160))
    assert pricing_impact(current,facts).client_amount==60000
    candidate=replace(current,subsidy_hours=Decimal(80))
    plan=build_historical_repricing_plan(facts,candidate,
        (HistoricalAmountFacts('original-first',59000,59000,'automatic'),HistoricalAmountFacts('original-second',1000,900,'manual')),
        HistoricalAmountFacts('original-payable',60000,60000,'automatic'))
    updates={item.identity:item for item in plan.client_updates}
    assert (updates['original-first'].computed,updates['original-first'].effective)==(56000,56000)
    assert (updates['original-second'].computed,updates['original-second'].effective)==(0,900)
    assert plan.staff_updates[0].effective==56000
    assert plan.source_versions==facts.versions
    assert facts.days==() and facts.historical_service_hours==160


def test_historical_repricing_preserves_original_customer_funding():
    from subsystems.client_finance.pricing_configuration import HistoricalAmountFacts, build_historical_repricing_plan

    rates = HourlyRates(350, 350)
    current = CasePricingTerms("原住民", IdentityRule.CITIZEN, Decimal(80), rates, rates)
    facts = CasePricingFacts("historical", 0, (1, 1, 1), current, "policy", (), 1000,
                             historical_service_hours=Decimal(80))
    candidate = replace(current, subsidy_hours=Decimal(79))
    plan = build_historical_repricing_plan(
        facts, candidate,
        (HistoricalAmountFacts("original-first", 29000, 29000, "automatic"),),
        HistoricalAmountFacts("original-payable", 29000, 29000, "automatic"),
        subsidy_source=HistoricalAmountFacts("original-refund", 28000, 28000, "automatic"),
    )
    assert pricing_impact(current, facts).client_amount == 29000
    assert [(item.identity, item.effective) for item in plan.client_updates] == [
        ("original-first", 29000), ("original-refund", 27650),
    ]


def test_citizen_identities_are_distinct_through_import_subsidy_and_payment_rules():
    from domains.client_finance.subsidy_coverage import derive_subsidy_coverage, normalize_subsidy_policy_identity
    from subsystems.case_import.hcm_adapter import _client_attributes, build_approved_case_architecture_bootstrap_intent
    from domains.bootstrap.case_architecture import policy_kind_for_identity, PayrollPolicyKind
    from subsystems.government_subsidy.reconciliation_register_query import _subsidy_terms
    for identity, cap, deposit, kind in (
        ('一般市民', 40, 5, PayrollPolicyKind.CITIZEN),
        ('補助市民', 120, 0, PayrollPolicyKind.SUBSIDIZED_CITIZEN),
    ):
        assert normalize_subsidy_policy_identity(identity) == identity
        assert _client_attributes({'identity_status': identity})[0].value == identity
        assert derive_subsidy_coverage(identity, Decimal(160), Decimal(0)).subsidy_hours == cap
        assert _subsidy_terms(identity, Decimal(160), 350)[0] == cap
        assert policy_kind_for_identity(identity) is kind
        candidate = build_approved_case_architecture_bootstrap_intent('synthetic', identity, datetime(2026, 11, 3), date(2026, 12, 1))
        assert candidate.client_payment_terms.deposit_service_days == deposit
    for alias in ('社福', '低收入戶', '中低收入戶'):
        assert normalize_subsidy_policy_identity(alias) == '補助市民'


def test_indigenous_identity_aliases_use_80h_350_rate_defaults():
    from domains.client_finance.subsidy_coverage import derive_subsidy_coverage, normalize_subsidy_policy_identity
    from subsystems.case_import.hcm_adapter import _client_attributes, build_approved_case_architecture_bootstrap_intent
    from subsystems.government_subsidy.reconciliation_register_query import _subsidy_terms
    for raw in ('原住民', '原民', '原住民市民'):
        assert normalize_subsidy_policy_identity(raw) == '原住民'
        assert _client_attributes({'identity_status': raw})[0].value == '原住民'
        coverage = derive_subsidy_coverage(raw, Decimal(160), Decimal(0))
        assert (coverage.identity_status, coverage.subsidy_hours, coverage.subsidy_claim_hourly_rate) == ('原住民', 80, 350)
        assert _subsidy_terms(raw, Decimal(160), 350) == (Decimal(80), Decimal(350))
        candidate = build_approved_case_architecture_bootstrap_intent('synthetic', raw, datetime(2026, 11, 3), date(2026, 12, 1))
        assert candidate.client_payment_terms.client_hourly_rate.amount == 350


def test_current_policy_selects_40_and_120_without_merging_names():
    policy = PricingPolicy(date(2026, 11, 3), (
        CasePricingTerms('一般市民', IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 300), HourlyRates(300, 300)),
        terms(), CasePricingTerms('非市民', IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 320), HourlyRates(0, 320)),
    ), HourlyRates(450, 450), HourlyRates(450, 450))
    policy.validate_current_identity_names()
    general, subsidized = policy.for_case('一般市民'), policy.for_case('補助市民')
    assert (general.subsidy_hours, subsidized.subsidy_hours) == (40, 120)
    assert (general.client_charge(Decimal(100)), subsidized.client_charge(Decimal(100))) == (30000, 0)
    assert (general.subsidy_return(Decimal(100)), subsidized.subsidy_return(Decimal(100))) == (12000, 0)


def test_bound_legacy_policy_keeps_original_rules_and_cannot_be_published_again():
    from dataclasses import replace
    policy = PricingPolicy(date(2026, 10, 29), (
        CasePricingTerms('補助市民', IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 300), HourlyRates(300, 300)),
        replace(terms(), identity_name='社福'),
        CasePricingTerms('非市民', IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 320), HourlyRates(0, 320)),
    ), HourlyRates(450, 450), HourlyRates(450, 450))
    assert policy.uses_legacy_identity_names
    assert policy.for_case('補助市民').rule is IdentityRule.CITIZEN
    assert policy.for_case('補助市民').subsidy_hours == 40
    assert policy.for_case('社福').subsidy_hours == 120
    with pytest.raises(ValueError, match='pricing_policy_identity_names_outdated'):
        policy.validate_current_identity_names()


def test_new_case_cannot_silently_bind_the_old_merged_identity_policy():
    from infrastructure.mysql.pricing_configuration_repository import bind_initial_pricing
    from domains.case_import.case_import import CaseImportDomainError, CaseImportIssue
    legacy = {'effective_on': '2026-10-29', 'identities': [
        {'identity_name': '補助市民', 'rule': 'citizen', 'subsidy_hours': 40, 'client': {'covered': 300, 'excess': 300}, 'payroll': {'covered': 300, 'excess': 300}},
        {'identity_name': '社福', 'rule': 'social', 'subsidy_hours': 120, 'client': {'covered': 350, 'excess': 350}, 'payroll': {'covered': 350, 'excess': 350}},
        {'identity_name': '非市民', 'rule': 'non_citizen', 'subsidy_hours': 0, 'client': {'covered': 0, 'excess': 320}, 'payroll': {'covered': 0, 'excess': 320}},
    ], 'twins_client': {'covered': 450, 'excess': 450}, 'twins_payroll': {'covered': 450, 'excess': 450}}
    class Cursor:
        sql = ''
        def execute(self, sql, params):
            assert not sql.startswith('UPDATE')
            self.sql = sql
        def fetchone(self):
            return {'id': 1, 'policy_json': legacy} if 'accounting_pricing_policies' in self.sql else {'identity_status': '補助市民'}
    with pytest.raises(CaseImportDomainError, match='pricing_policy_identity_names_outdated') as caught:
        bind_initial_pricing(Cursor(), 'new-supplement-case')
    assert caught.value.issue is CaseImportIssue.BOOTSTRAP_BLOCKED


def test_covered_rates_match_and_excess_tiers_remain_independent():
    facts = CasePricingFacts("case-1", 0, (1, 2, 3), terms(), "policy",
        tuple(PricingServiceDay(date(2026, 10, day), Decimal(8)) for day in range(1, 21)), 1000)
    impact = pricing_impact(terms(), facts)
    assert (impact.covered_hours, impact.excess_hours) == (120, 40)
    assert impact.client_amount == 40 * 300 + 1000
    assert impact.staff_total_amount == 120 * 350 + 40 * 310 + 1000
    assert impact.subsidy_amount == 120 * 350
    assert impact.subsidy_return_amount == 0


@pytest.mark.parametrize(("identity", "rule", "limit", "partial_due", "partial_return"), [
    ("補助市民", IdentityRule.SOCIAL, 120, 1350, 0),
    ("原住民", IdentityRule.CITIZEN, 80, 29000, 27650),
])
def test_case_pricing_query_and_preview_use_full_subsidy_funding(
    identity, rule, limit, partial_due, partial_return,
):
    rates = HourlyRates(350, 350)
    current = CasePricingTerms(identity, rule, Decimal(limit), rates, rates)
    facts = CasePricingFacts("case-1", 0, (1, 2, 3), current, "policy",
        tuple(PricingServiceDay(date(2026, 10, day), Decimal(8)) for day in range(1, 11)), 1000)

    class Repository:
        accounting_pending = ()
        def case(self, case_no, *, lock=False):
            assert not lock
            return facts

    application = PricingConfigurationApplication(Repository(), lambda: pytest.fail("preview opened transaction"))
    _, impact = application.query_case("case-1")
    assert (impact.client_amount, impact.subsidy_amount, impact.subsidy_return_amount) == (0, 29000, 0)
    assert impact.staff_total_amount == 29000

    candidate = replace(current, subsidy_hours=Decimal(79))
    preview = application.preview_case("case-1", candidate, 0)
    assert preview.before == impact
    assert (preview.after.client_amount, preview.after.subsidy_amount, preview.after.subsidy_return_amount) == (
        partial_due, 27650, partial_return,
    )


def test_cutoff_inside_a_service_day_and_customer_advance_refund():
    pricing = CasePricingTerms("一般市民", IdentityRule.CITIZEN, Decimal(10), HourlyRates(300, 320), HourlyRates(300, 330))
    assert pricing.client_charge(Decimal(8), Decimal(8)) == 2 * 300 + 6 * 320
    assert pricing.subsidy_return(Decimal(16)) == 10 * 300
    from domains.government_subsidy.pricing import subsidy_claim_amount
    assert subsidy_claim_amount(Decimal(16), pricing.subsidy_hours, pricing.payroll.covered) == 10 * 300


def test_policy_birth_override_preserves_identity_subsidy_cap():
    policy = PricingPolicy(date(2026, 11, 1), (
        CasePricingTerms("一般市民", IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 300), HourlyRates(300, 300)),
        terms(), CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(320, 320), HourlyRates(320, 320))),
        HourlyRates(450, 400), HourlyRates(450, 410))
    case = policy.for_case("低收入戶", twins=True)
    assert case.subsidy_hours == 120
    assert case.client.excess == 400
    assert case.payroll.excess == 410


def test_non_citizen_cannot_acquire_subsidy_through_numeric_override():
    with pytest.raises(ValueError, match="non_citizen"):
        CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(40), HourlyRates(320, 320), HourlyRates(320, 320))


@pytest.mark.parametrize('rule', [IdentityRule.CITIZEN, IdentityRule.SOCIAL])
def test_new_case_settings_reject_unequal_covered_rates_but_legacy_is_readable(rule):
    from dataclasses import replace
    invalid = replace(terms(), rule=rule, client=HourlyRates(301, 330), payroll=HourlyRates(300, 310))
    class Repository:
        accounting_pending = ()
        def case(self, case_no, *, lock=False):
            return CasePricingFacts(case_no, 0, (1, 2, 3), invalid, 'manual', (), 0)
    application = PricingConfigurationApplication(Repository(), lambda: pytest.fail('preview wrote'))
    assert application.query_case('legacy-unequal')[0].terms == invalid
    with pytest.raises(ValueError, match='pricing_covered_rates_must_match'):
        application.preview_case('legacy-unequal', invalid, 0)
    fixed = replace(invalid, payroll=HourlyRates(301, 310))
    assert application.preview_case('legacy-unequal', fixed, 0).candidate == fixed


def test_non_citizen_unused_covered_rates_are_zero_and_self_pay_is_preserved():
    legacy = CasePricingTerms('非市民', IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(320, 330), HourlyRates(320, 310))
    assert legacy.client == HourlyRates(0, 330) and legacy.payroll == HourlyRates(0, 310)
    legacy.validate_subsidy_rates()
    facts = CasePricingFacts('non-citizen', 0, (1,), legacy, 'policy', (PricingServiceDay(date(2026, 10, 1), Decimal(8)),), 0)
    impact = pricing_impact(legacy, facts)
    assert (impact.covered_hours, impact.subsidy_amount, impact.subsidy_return_amount, impact.staff_covered_amount) == (0, 0, 0, 0)
    assert (impact.client_amount, impact.staff_total_amount) == (2640, 2480)


def test_policy_guards_identity_and_twins_covered_rates():
    from dataclasses import replace
    valid = PricingPolicy(date(2026, 11, 1), (
        CasePricingTerms('一般市民', IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 330), HourlyRates(300, 310)),
        terms(), CasePricingTerms('非市民', IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 320), HourlyRates(0, 310))),
        HourlyRates(450, 460), HourlyRates(450, 420))
    valid.validate_subsidy_rates()
    for invalid in (replace(valid, twins_payroll=HourlyRates(451, 420)), replace(valid, identities=valid.identities + (replace(terms(), identity_name='新增社福', payroll=HourlyRates(351, 310)),))):
        with pytest.raises(ValueError, match='pricing_covered_rates_must_match'):
            invalid.validate_subsidy_rates()
    non_citizen_twins = valid.for_case('非市民', twins=True)
    assert non_citizen_twins.client == HourlyRates(0, 460) and non_citizen_twins.payroll == HourlyRates(0, 420)


def test_case_preview_changes_when_owner_facts_change_and_is_read_only():
    class Repository:
        accounting_pending = ()
        facts = CasePricingFacts("case-1", 0, (1, 2, 3), terms(), "policy", (), 0)
        def case(self, case_no, *, lock=False):
            assert lock is False
            return self.facts
    repository = Repository()
    application = PricingConfigurationApplication(repository, lambda: pytest.fail("preview opened transaction"))
    before = application.preview_case("case-1", terms(), 0)
    from dataclasses import replace
    repository.facts = replace(repository.facts, versions=(1, 3, 3))
    assert application.preview_case("case-1", terms(), 0).fingerprint != before.fingerprint
    with pytest.raises(PricingConflict):
        application.preview_case("case-1", terms(), 1)


def test_reading_legacy_case_preserves_original_client_charge_until_explicit_apply():
    from subsystems.client_finance.pricing_configuration import current_pricing_impact
    facts = CasePricingFacts('legacy',0,(1,2,3),terms(),'legacy',
        tuple(PricingServiceDay(date(2026,10,day),Decimal(8)) for day in range(1,21)),0,
        legacy_client_amount=56000)
    assert current_pricing_impact(facts).client_amount == 56000
    assert pricing_impact(terms(),facts).client_amount == 12000


def test_unauthenticated_pricing_read_is_rejected_before_opening_database(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.accounting_pricing import router
    from api.dependencies.accounting_pricing import get_pricing_application
    monkeypatch.setenv('ACCESS_CONTROL_PROFILE','production')
    monkeypatch.setenv('ENABLE_ADMIN_AUTH','true')
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pricing_application] = lambda: pytest.fail('unauthenticated request opened pricing repository')
    with TestClient(app) as client:
        assert client.get('/api/v1/accounting-pricing').status_code == 401


def test_direct_save_accepts_omitted_reason_without_preview_and_preserves_stale_replay_guards(monkeypatch):
    from contextlib import contextmanager
    from dataclasses import replace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.accounting_pricing import router
    from api.dependencies.admin_auth import require_system_admin
    from api.dependencies.accounting_pricing import get_pricing_application
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.client_finance.pricing_configuration import pricing_payload
    from contextlib import contextmanager
    from subsystems.client_finance.pricing_configuration import pricing_payload

    class Repository:
        accounting_pending = ()
        facts = CasePricingFacts('direct-case', 0, (1, 2, 3), terms(), 'policy', (), 0)
        receipts = {}
        saved = []
        def case(self, case_no, *, lock=False):
            assert case_no == 'direct-case' and lock
            return self.facts
        def receipt(self, key, actor, command):
            old = self.receipts.get(key)
            if old is not None:
                if old[:2] != (actor, command):
                    raise PricingConflict('pricing_command_mismatch')
                return old[2]
        def save_case(self, facts, candidate, actor, reason, key):
            self.saved.append((candidate, reason))
            self.facts = replace(facts, terms=candidate, revision=facts.revision + 1)
        def save_receipt(self, key, actor, command, revision):
            self.receipts[key] = (actor, command, revision)
    class Unit:
        def commit(self): pass
    @contextmanager
    def unit():
        yield Unit()
    repository = Repository()
    application = PricingConfigurationApplication(repository, unit)
    monkeypatch.setattr(application, '_preview', lambda *args: pytest.fail('direct save invoked preview'))
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_pricing_application] = lambda: application
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, 'synthetic', 'Synthetic', 'system_admin')
    candidate = replace(terms(), client=HourlyRates(350, 280))
    body = {'terms': pricing_payload(candidate), 'expected_revision': 0}
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post('/api/v1/accounting-pricing/cases/direct-case/apply', json=body, headers={'Idempotency-Key': 'direct-save'})
            assert response.status_code == 200, response.text
            assert response.json()['data']['revision'] == 1
        stale = client.post('/api/v1/accounting-pricing/cases/direct-case/apply', json=body, headers={'Idempotency-Key': 'another-save'})
        assert stale.status_code == 409
        changed = client.post('/api/v1/accounting-pricing/cases/direct-case/apply', json={**body, 'reason': 'new content'}, headers={'Idempotency-Key': 'direct-save'})
        assert changed.status_code == 409
    assert repository.saved == [(candidate, '')]


@pytest.mark.parametrize('reason', [None, '', '   '])
def test_policy_http_to_owner_writer_accepts_optional_reason(reason):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.accounting_pricing import router
    from api.dependencies.admin_auth import require_system_admin
    from api.dependencies.accounting_pricing import get_pricing_application
    from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.client_finance.pricing_configuration import pricing_payload

    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args=()):
            self.sql = sql
            connection.calls.append((sql, args))
        def fetchone(self): return {'revision': 0} if 'accounting_pricing_state' in self.sql else None
        def fetchall(self): return []
    class Connection:
        def __init__(self): self.calls, self.commits = [], 0
        def cursor(self): return Cursor()
        def begin(self): pass
        def commit(self): self.commits += 1
        def rollback(self): pytest.fail('valid optional reason rolled back')
    connection = Connection()
    application = PricingConfigurationApplication(MySqlPricingConfigurationRepository(connection), lambda: MySqlUnitOfWork(connection))
    policy = PricingPolicy(date(2026, 11, 1), (
        CasePricingTerms('一般市民', IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 300), HourlyRates(300, 300)),
        terms(), CasePricingTerms('非市民', IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(320, 320), HourlyRates(320, 320))),
        HourlyRates(450, 450), HourlyRates(450, 450))
    body = {'policy': pricing_payload(policy), 'expected_revision': 0}
    if reason is not None: body['reason'] = reason
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_pricing_application] = lambda: application
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, 'synthetic', 'Synthetic', 'system_admin')
    with TestClient(app) as client:
        response = client.post('/api/v1/accounting-pricing/policies', json=body, headers={'Idempotency-Key': 'optional-policy-reason'})
        assert response.status_code == 200, response.text
        assert response.json()['data']['revision'] == 1
    writes = [args for sql, args in connection.calls if sql.startswith('INSERT INTO accounting_pricing_policies')]
    assert len(writes) == 1 and writes[0][-1] == ''
    assert connection.commits == 1


def test_pricing_catalog_endpoint_uses_lazy_connection_redis_cache_and_post_commit_invalidation(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies import accounting_pricing as pricing_deps
    from api.dependencies.admin_auth import require_system_admin
    from api.routes.accounting_pricing import router
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.client_finance.pricing_configuration import pricing_payload

    state = {'revision': 0, 'policies': [], 'opens': 0, 'commits': 0}
    redis_store: dict[str, str] = {}

    class FakeBackend:
        def get(self, key: str) -> str | None:
            return redis_store.get(key)

        def set(self, key: str, payload: str, ttl_seconds: float) -> None:
            del ttl_seconds
            redis_store[key] = payload

        def delete(self, keys: tuple[str, ...]) -> None:
            for key in keys:
                redis_store.pop(key, None)

        def delete_prefix(self, prefix: str) -> None:
            for key in [item for item in redis_store if item.startswith(prefix)]:
                redis_store.pop(key, None)

    class Cursor:
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args=()):
            self.sql = sql
            if sql.startswith('UPDATE accounting_pricing_state'):
                state['revision'] += 1
            elif sql.startswith('INSERT INTO accounting_pricing_policies'):
                state['policies'].append({
                    'id': args[0],
                    'policy_json': args[2],
                    'actor': args[3],
                    'reason': args[4],
                })
        def fetchone(self):
            return {'revision': state['revision']} if 'accounting_pricing_state' in self.sql else None
        def fetchall(self):
            return list(state['policies']) if 'accounting_pricing_policies' in self.sql else []

    class Connection:
        def cursor(self): return Cursor()
        def begin(self): pass
        def commit(self): state['commits'] += 1
        def rollback(self): pass
        def close(self): pass

    def fake_get_connection():
        state['opens'] += 1
        return Connection()

    monkeypatch.setattr(pricing_deps, 'get_connection', fake_get_connection)
    pricing_deps._pricing_catalog_cache.configure_backend(lambda: FakeBackend())
    pricing_deps.invalidate_pricing_catalog_cache()
    try:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
            1, 'synthetic', 'Synthetic', 'system_admin'
        )
        with TestClient(app) as client:
            first = client.get('/api/v1/accounting-pricing')
            second = client.get('/api/v1/accounting-pricing')
            assert first.status_code == second.status_code == 200
            assert first.json()['data'] == {'revision': 0, 'versions': []}
            assert state['opens'] == 1
            assert len(redis_store) == 1

            # Evict L1 only: L2 Redis should serve GET with zero new DB connections
            with pricing_deps._pricing_catalog_cache._lock:
                pricing_deps._pricing_catalog_cache._entries.clear()
            third = client.get('/api/v1/accounting-pricing')
            assert third.status_code == 200
            assert state['opens'] == 1

            policy = PricingPolicy(
                date(2026, 11, 1),
                (
                    CasePricingTerms('一般市民', IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 300), HourlyRates(300, 300)),
                    terms(),
                    CasePricingTerms('非市民', IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(320, 320), HourlyRates(320, 320)),
                ),
                HourlyRates(450, 450),
                HourlyRates(450, 450),
            )
            saved = client.post(
                '/api/v1/accounting-pricing/policies',
                json={'policy': pricing_payload(policy), 'expected_revision': 0},
                headers={'Idempotency-Key': 'catalog-cache-invalidate-01'},
            )
            assert saved.status_code == 200
            assert redis_store == {}
            assert state['opens'] == 2

            refreshed = client.get('/api/v1/accounting-pricing')
            assert refreshed.status_code == 200
            assert refreshed.json()['data']['revision'] == 1
            assert len(refreshed.json()['data']['versions']) == 1
            assert state['opens'] == 3
    finally:
        pricing_deps._pricing_catalog_cache.configure_backend(pricing_deps.default_redis_cache_backend)
        pricing_deps.invalidate_pricing_catalog_cache()


def test_case_apply_missing_refund_recipient_snapshot_returns_informative_validation_error():
    from contextlib import contextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.accounting_pricing import router
    from api.dependencies.admin_auth import require_system_admin
    from api.dependencies.accounting_pricing import get_pricing_application
    from subsystems.access.authentication_session import AdminPrincipal

    class Repository:
        accounting_pending = ()
        def case(self, case_no, *, lock=False):
            return CasePricingFacts('direct-case', 0, (0,), terms(), 'policy', (), 1000)
        def receipt(self, key, actor, command): return None
        def save_case(self, facts, candidate, actor, reason, key):
            raise ValueError('client_refund_recipient_snapshot_missing')
    @contextmanager
    def unit(): yield None
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_pricing_application] = lambda: PricingConfigurationApplication(Repository(), unit)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, 'synthetic', 'Synthetic', 'system_admin')
    body = {'terms': pricing_payload(terms()), 'expected_revision': 0}
    with TestClient(app) as client:
        response = client.post('/api/v1/accounting-pricing/cases/direct-case/apply', json=body, headers={'Idempotency-Key': 'key-1'})
        assert response.status_code == 422
        payload = response.json()['detail']['error']
        assert payload['code'] == 'client_refund_recipient_snapshot_missing'
        assert '缺少客戶退款銀行帳號' in payload['message']


def test_historical_completed_pricing_keeps_unknown_staff_amount_nullable():
    from subsystems.client_finance.pricing_configuration import HistoricalPricingPerson, pricing_impact
    facts = CasePricingFacts('unknown-person', 0, (1, 1, 1), terms(), 'manual', (), 0,
        historical_service_hours=Decimal(80), historical=True,
        historical_people=(HistoricalPricingPerson('assignment:1', 1, 'Synthetic', None, 0),))
    impact = pricing_impact(facts.terms, facts)
    assert impact.client_amount == 0
    assert impact.staff_total_amount is None
    assert impact.staff_covered_amount is None and impact.staff_excess_amount is None
    assert impact.union_income_amount is None


def test_historical_completed_pricing_replay_precedes_source_parsing():
    from contextlib import contextmanager
    class Repository:
        accounting_pending = ()
        def receipt(self, key, actor, command):
            return 7
        def case(self, case_no, *, lock=False):
            raise AssertionError('Replayed commands must not parse current source')
    @contextmanager
    def unit():
        yield None
    application = PricingConfigurationApplication(Repository(), unit)
    assert application.apply_case('replayed', terms(), 6, 'f' * 64, 'synthetic', 'original reason', 'original-key') == 7


@pytest.mark.parametrize('service_first', [False, True])
def test_pending_historical_client_difference_survives_other_corrections_and_noop(service_first):
    from infrastructure.mysql.pricing_configuration_repository import _partial_historical_repricing_plan
    initial = CasePricingTerms('一般市民', IdentityRule.CITIZEN, Decimal(40),
        HourlyRates(300, 300), HourlyRates(300, 300))
    revised = replace(initial, client=HourlyRates(400, 400))
    facts = CasePricingFacts('carry', 0, (1, 1, 1, 0, 1, 1), initial, 'manual', (), 0,
        historical_service_hours=Decimal(10), historical=True)
    def plan(before, candidate, after, rows=()):
        return _partial_historical_repricing_plan(before, candidate, after,
            rows, (), (), False, 'original-evidence', True)
    first_terms = initial if service_first else revised
    first_facts = replace(facts, historical_service_hours=Decimal(8)) if service_first else facts
    first = plan(facts, first_terms, first_facts)
    assert first.client_delta == (-600 if service_first else 1000)
    saved = replace(first_facts, terms=first_terms, accounting_carry=first.carry)
    second = plan(saved, revised, replace(saved, historical_service_hours=Decimal(8)))
    assert second.client_delta == 200
    assert 'historical_pricing_original_installments_required' in second.pending
    saved = replace(saved, terms=revised, historical_service_hours=Decimal(8), accounting_carry=second.carry)
    noop = plan(saved, revised, saved)
    assert noop.client_delta == 200 and noop.pending == second.pending
    row = {'obligation_identity': 'original', 'obligation_type': 'first',
        'computed_ntd': 3000, 'effective_ntd': 3000, 'nominal': 3000, 'amount_mode': 'automatic'}
    resolved = plan(saved, revised, saved, (row,))
    assert resolved.client_updates[0].computed == 3200
    assert not any(item.component == 'client' for item in resolved.carry)
    assert facts.terms == initial


def test_pending_historical_subsidy_and_unknown_birth_basis_survive_noop():
    from infrastructure.mysql.pricing_configuration_repository import _partial_historical_repricing_plan
    from subsystems.client_finance.pricing_configuration import HistoricalAccountingCarry, HistoricalPricingPerson
    initial = terms()
    facts = CasePricingFacts('carry-subsidy', 0, (1, 1, 1, 0, 1, 1), initial, 'manual', (), 0,
        historical_service_hours=Decimal(80), historical=True)
    def plan(current, candidate):
        return _partial_historical_repricing_plan(current, candidate, current,
            (), (), (), True, 'current-evidence', True, client_exempt=True)
    payroll_only = plan(facts, replace(initial, payroll=HourlyRates(400, 310)))
    assert 'case_pricing_settled_subsidy_correction_required' not in payroll_only.pending
    assert not any(item.component == 'subsidy' for item in payroll_only.carry)
    revised = replace(initial, client=HourlyRates(400, 300), payroll=HourlyRates(400, 310))
    first = plan(facts, revised)
    assert 'case_pricing_settled_subsidy_correction_required' in first.pending
    saved = replace(facts, terms=revised, accounting_carry=first.carry)
    repeated = plan(saved, revised)
    assert 'case_pricing_settled_subsidy_correction_required' in repeated.pending
    subsidy = next(item for item in repeated.carry if item.component == 'subsidy')
    assert subsidy.subsidy_claim_basis == 28000
    assert subsidy.financial_sources_digest == 'current-evidence'
    blocker = 'historical_pricing_birth_original_value_required'
    saved = replace(saved, historical_people=(HistoricalPricingPerson('assignment:1', 1, 'Synthetic', Decimal(80), 10),),
        accounting_carry=(HistoricalAccountingCarry('client', facts.case_no, 0, (blocker,), 'birth-evidence'),
            HistoricalAccountingCarry('payroll', 'assignment:1', None, (blocker,), 'birth-evidence')))
    unknown_birth = plan(saved, revised)
    assert blocker in unknown_birth.pending
    assert unknown_birth.client_updates == () and unknown_birth.staff_updates == ()
    assert all(item.financial_sources_digest == 'birth-evidence' for item in unknown_birth.carry
        if item.component in {'client', 'payroll'})


@pytest.mark.parametrize('authority', ['legacy', 'policy', 'manual', None])
def test_historical_accounting_event_rate_authority_is_explicit(authority):
    from infrastructure.mysql.pricing_configuration_repository import _event_rate_authority
    payload = {'historical_accounting': {'rate_authority': authority}}
    assert _event_rate_authority(payload) == (authority or 'manual')
    assert _event_rate_authority({}) == 'manual'


@pytest.mark.parametrize('authority', ['suggested', True, 1, [], {}])
def test_historical_accounting_event_rate_authority_rejects_unknown_metadata(authority):
    from infrastructure.mysql.pricing_configuration_repository import _event_rate_authority
    with pytest.raises(ValueError, match='case_pricing_rate_authority_invalid'):
        _event_rate_authority({'historical_accounting': {'rate_authority': authority}})


def test_historical_unknown_total_stays_nullable_while_confirmed_person_can_reprice():
    from api.schemas.accounting_pricing import HistoricalRepricingPlanView, PricingImpactView
    from infrastructure.mysql.pricing_configuration_repository import _partial_historical_repricing_plan
    from subsystems.client_finance.pricing_configuration import HistoricalPricingPerson
    facts = CasePricingFacts('unknown-total', 0, (1, 1, 1, 0, 1, 1), terms(), 'manual', (), 0,
        historical=True, historical_people=(
            HistoricalPricingPerson('assignment:1', 1, 'Confirmed', Decimal(40), 5),
            HistoricalPricingPerson('assignment:2', 2, 'Unconfirmed', None, None)))
    impact = pricing_impact(facts.terms, facts)
    view = PricingImpactView.model_validate(impact)
    assert (view.covered_hours, view.excess_hours, view.client_amount, view.subsidy_amount,
        view.subsidy_return_amount, view.case_total_amount) == (None,) * 6
    row = {'obligation_identity': 'original', 'assignment_id': 1, 'staff_id': 1,
        'computed_ntd': 14000, 'effective_ntd': 14000, 'nominal': 14000, 'amount_mode': 'automatic'}
    plan = _partial_historical_repricing_plan(facts, replace(facts.terms, payroll=HourlyRates(400, 310)),
        facts, (), (row,), (), False, 'evidence', True)
    assert [item.computed for item in plan.staff_updates] == [16000]
    assert plan.client_updates == ()
    assert plan.persons[1].after_amount is None
    assert 'historical_pricing_original_calculation_basis_required' in plan.pending
    assert HistoricalRepricingPlanView.model_validate(plan).client_delta is None
    assert HistoricalRepricingPlanView.model_validate(plan).subsidy_delta is None
    confirmed = replace(facts, historical_service_hours=Decimal(80), historical_people=(
        facts.historical_people[0], replace(facts.historical_people[1], hours=Decimal(40), actual_service_days=5)))
    resolved_current_volume = _partial_historical_repricing_plan(facts, facts.terms,
        confirmed, (), (row,), (), False, 'new-evidence', True)
    assert 'historical_pricing_original_calculation_basis_required' in resolved_current_volume.pending
    assert resolved_current_volume.client_delta is None
    assert resolved_current_volume.subsidy_delta is None


@pytest.mark.parametrize('historical', [False, True])
def test_legacy_mixed_person_rates_preserve_unselected_pay_and_explicit_case_candidate(historical):
    from domains.payroll.calculation import AssignmentRateSnapshot, PayrollPolicyKind
    from shared_kernel.money import MoneyNTD
    from infrastructure.mysql.pricing_configuration_repository import _partial_historical_repricing_plan
    from subsystems.client_finance.pricing_configuration import HistoricalPricingPerson, current_pricing_impact

    people = tuple(HistoricalPricingPerson(f'assignment:{index}', index, f'Synthetic {index}',
        Decimal(hours), days, adjustment,
        AssignmentRateSnapshot(f'assignment:{index}', 'approved-rates-v1', kind, MoneyNTD(rate)))
        for index, hours, days, adjustment, kind, rate in (
            (1, 24, 3, 150, PayrollPolicyKind.CITIZEN, 300),
            (2, 16, 2, 200, PayrollPolicyKind.SUBSIDIZED_CITIZEN, 350)))
    facts = CasePricingFacts('legacy-mixed', 0, (1, 1, 1, 0, 1, 1), terms(), 'legacy', (), 0,
        payroll_adjustment=350, historical_service_hours=Decimal(40), historical_people=people,
        historical=historical)
    assert current_pricing_impact(facts).staff_total_amount == 13150
    after = replace(facts, historical_service_hours=Decimal(48),
        historical_people=(replace(people[0], hours=Decimal(32)), people[1]))
    rows = tuple({'obligation_identity': f'original:{index}', 'assignment_id': index, 'staff_id': index,
        'computed_ntd': amount, 'effective_ntd': amount, 'nominal': amount, 'amount_mode': 'automatic'}
        for index, amount in ((1, 7350), (2, 5800)))
    service = _partial_historical_repricing_plan(facts, facts.terms, after, (), rows, (), False, 'evidence',
        True, use_legacy_person_rates=True)
    assert [(item.before_amount, item.after_amount, item.delta) for item in service.persons] == [
        (7350, 9750, 2400), (5800, 5800, 0)]
    assert current_pricing_impact(after).staff_total_amount == 15550
    explicit = _partial_historical_repricing_plan(facts, facts.terms, after, (), rows, (), False,
        'evidence', True)
    assert [item.after_amount for item in explicit.persons] == [11350, 5800]
    assert pricing_impact(facts.terms, after).staff_total_amount == 17150
    for source in ('manual', 'policy'):
        assert current_pricing_impact(replace(after, source=source)).staff_total_amount == 17150


def test_legacy_person_rate_correction_preserves_floor_allocation_and_manual_effective_amount():
    from domains.payroll.calculation import AssignmentRateSnapshot, PayrollPolicyKind
    from shared_kernel.money import MoneyNTD
    from infrastructure.mysql.pricing_configuration_repository import _partial_historical_repricing_plan
    from subsystems.client_finance.pricing_configuration import HistoricalPricingPerson

    person = HistoricalPricingPerson('assignment:1', 1, 'Synthetic', Decimal(24), 3, 150,
        AssignmentRateSnapshot('assignment:1', 'approved-rates-v1', PayrollPolicyKind.CITIZEN, MoneyNTD(300)))
    facts = CasePricingFacts('legacy-manual', 0, (1, 1, 1, 0, 1, 1), terms(), 'legacy', (), 500,
        payroll_adjustment=150, historical_service_hours=Decimal(24), historical_people=(person,), historical=True)
    after = replace(facts, historical_service_hours=Decimal(32), historical_people=(replace(person, hours=Decimal(32)),))
    row = {'obligation_identity': 'original', 'assignment_id': 1, 'staff_id': 1,
        'computed_ntd': 7850, 'effective_ntd': 8000, 'nominal': 7850, 'amount_mode': 'manual'}
    plan = _partial_historical_repricing_plan(facts, facts.terms, after, (), (row,), (), False, 'evidence',
        True, use_legacy_person_rates=True)
    assert (plan.staff_updates[0].computed, plan.staff_updates[0].effective) == (10250, 8000)
    assert (plan.persons[0].before_amount, plan.persons[0].after_amount, plan.persons[0].delta) == (8000, 8000, 0)
    unresolved = replace(facts, historical_people=(replace(person, rate_snapshot=None),))
    with pytest.raises(PricingConflict, match='case_pricing_payroll_snapshot_required'):
        pricing_impact(facts.terms, unresolved, use_legacy_person_rates=True)

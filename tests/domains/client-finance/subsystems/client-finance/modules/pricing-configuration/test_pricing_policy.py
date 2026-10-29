from datetime import date
from decimal import Decimal

import pytest

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, PricingPolicy
from subsystems.client_finance.pricing_configuration import (
    CasePricingFacts, PricingServiceDay, pricing_impact, PricingConfigurationApplication, PricingConflict,
)


def terms(rule=IdentityRule.SOCIAL):
    return CasePricingTerms("社福", rule, Decimal(120), HourlyRates(350, 300), HourlyRates(360, 310))


def test_customer_and_payroll_tiers_are_independent_and_claim_uses_covered_rate():
    facts = CasePricingFacts("case-1", 0, (1, 2, 3), terms(), "policy",
        tuple(PricingServiceDay(date(2026, 10, day), Decimal(8)) for day in range(1, 21)), 1000)
    impact = pricing_impact(terms(), facts)
    assert (impact.covered_hours, impact.excess_hours) == (120, 40)
    assert impact.client_amount == 40 * 300 + 1000
    assert impact.staff_total_amount == 120 * 360 + 40 * 310 + 1000
    assert impact.subsidy_amount == 120 * 360
    assert impact.subsidy_return_amount == 0


def test_cutoff_inside_a_service_day_and_customer_advance_refund():
    pricing = CasePricingTerms("補助市民", IdentityRule.CITIZEN, Decimal(10), HourlyRates(300, 320), HourlyRates(350, 330))
    assert pricing.client_charge(Decimal(8), Decimal(8)) == 2 * 300 + 6 * 320
    assert pricing.subsidy_return(Decimal(16)) == 10 * 300
    from domains.government_subsidy.pricing import subsidy_claim_amount
    assert subsidy_claim_amount(Decimal(16), pricing.subsidy_hours, pricing.payroll.covered) == 10 * 350


def test_policy_birth_override_preserves_identity_subsidy_cap():
    policy = PricingPolicy(date(2026, 11, 1), (
        CasePricingTerms("補助市民", IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 300), HourlyRates(300, 300)),
        terms(), CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(320, 320), HourlyRates(320, 320))),
        HourlyRates(450, 400), HourlyRates(460, 410))
    case = policy.for_case("低收入戶", twins=True)
    assert case.subsidy_hours == 120
    assert case.client.excess == 400
    assert case.payroll.excess == 410


def test_non_citizen_cannot_acquire_subsidy_through_numeric_override():
    with pytest.raises(ValueError, match="non_citizen"):
        CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(40), HourlyRates(320, 320), HourlyRates(320, 320))


def test_case_preview_changes_when_owner_facts_change_and_is_read_only():
    class Repository:
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

    class Repository:
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
        CasePricingTerms('補助市民', IdentityRule.CITIZEN, Decimal(40), HourlyRates(300, 300), HourlyRates(300, 300)),
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

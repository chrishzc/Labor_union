"""Full case service charge is independent of who funds the covered service."""
from decimal import Decimal

import pytest

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, calculate_case_total_amount


@pytest.mark.parametrize("rule", [IdentityRule.CITIZEN, IdentityRule.SOCIAL])
def test_full_case_charge_prices_subsidized_hours_with_holiday_multiplier(rule):
    terms = CasePricingTerms("測試", rule, Decimal(40), HourlyRates(300, 350), HourlyRates(400, 450))
    assert calculate_case_total_amount(terms, ((Decimal(30), False), (Decimal(20), True)), 1000) == 23000
    # Historical unequal salary rates must never replace the service price.
    assert calculate_case_total_amount(terms, ((Decimal('8.5'), False),), 500) == 3050


def test_self_pay_case_and_fixed_fee_once():
    terms = CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 350), HourlyRates(0, 300))
    assert calculate_case_total_amount(terms, ((Decimal(30), False), (Decimal(20), True)), 1000) == 25500


def test_effective_holiday_hours_price_both_sides_without_doubling_hours():
    from datetime import date
    from subsystems.client_finance.pricing_configuration import CasePricingFacts, PricingServiceDay, pricing_impact
    terms = CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 350), HourlyRates(0, 320))
    facts = CasePricingFacts("holiday-fixture", 0, (), terms, "policy",
        (PricingServiceDay(date(2026, 1, 1), Decimal(8), False, Decimal(8)),), 0)
    result = pricing_impact(terms, facts)
    assert result.covered_hours + result.excess_hours == 8
    assert (result.case_total_amount, result.client_amount, result.staff_total_amount, result.union_income_amount) == (5600, 5600, 5120, 480)


def test_historical_same_date_ignores_current_holiday_configuration():
    from dataclasses import replace
    from datetime import date
    from subsystems.client_finance.pricing_configuration import CasePricingFacts, PricingServiceDay, pricing_impact
    terms = CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 350), HourlyRates(0, 320))
    facts = CasePricingFacts("historical-fixture", 0, (), terms, "policy",
        (PricingServiceDay(date(2026, 1, 1), Decimal(8), True, Decimal(8)),), 0)
    result = pricing_impact(terms, replace(facts, historical_service_hours=Decimal(8)))
    assert (result.case_total_amount, result.client_amount, result.staff_total_amount, result.union_income_amount) == (2800, 2800, 2560, 240)

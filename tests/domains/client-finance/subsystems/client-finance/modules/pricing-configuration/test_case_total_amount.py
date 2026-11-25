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


@pytest.mark.parametrize("holiday_hours", [Decimal(0), Decimal(8)])
def test_paid_social_case_preserves_gross_service_total_and_union_difference(holiday_hours):
    from datetime import date
    from subsystems.client_finance.pricing_configuration import CasePricingFacts, PricingServiceDay, pricing_impact
    terms = CasePricingTerms("補助市民", IdentityRule.SOCIAL, Decimal(120), HourlyRates(350, 350), HourlyRates(350, 350))
    facts = CasePricingFacts("paid-social", 0, (), terms, "policy",
        (PricingServiceDay(date(2026, 1, 1), Decimal(128), False, holiday_hours),), 0,
        frozen_amounts=(2800, 44800), frozen_case_total=44800)
    result = pricing_impact(terms, facts)
    assert (result.case_total_amount, result.client_amount, result.staff_total_amount, result.union_income_amount) == (44800, 2800, 44800, 0)


def test_paid_manual_receivable_does_not_replace_original_service_price():
    from datetime import date
    from subsystems.client_finance.pricing_configuration import CasePricingFacts, PricingServiceDay, pricing_impact
    terms = CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 350), HourlyRates(0, 320))
    facts = CasePricingFacts("paid-manual", 0, (), terms, "policy",
        (PricingServiceDay(date(2026, 1, 1), Decimal(8), False, Decimal(8)),), 0,
        frozen_amounts=(2500, 2560), frozen_case_total=2800)
    result = pricing_impact(terms, facts)
    assert (result.case_total_amount, result.client_amount, result.staff_total_amount, result.union_income_amount) == (2800, 2500, 2560, 240)
    assert result.staff_covered_amount is None
    assert result.staff_excess_amount is None


def test_current_union_income_uses_formal_staff_own_rate_result():
    from datetime import date
    from subsystems.client_finance.pricing_configuration import CasePricingFacts, PricingServiceDay, current_pricing_impact
    terms = CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 350), HourlyRates(0, 320))
    facts = CasePricingFacts("own-staff-rate", 0, (), terms, "policy",
        (PricingServiceDay(date(2026, 1, 1), Decimal(8), False, Decimal(8)),), 0, formal_staff_amount=4960, formal_client_amount=5500)
    result = current_pricing_impact(facts)
    assert (result.case_total_amount, result.client_amount, result.staff_total_amount, result.union_income_amount) == (5600, 5500, 4960, 640)

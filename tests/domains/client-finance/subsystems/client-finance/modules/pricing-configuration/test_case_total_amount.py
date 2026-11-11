"""Full case service charge is independent of who funds the covered service."""
from decimal import Decimal

import pytest

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, calculate_case_total_amount


@pytest.mark.parametrize("rule", [IdentityRule.CITIZEN, IdentityRule.SOCIAL])
def test_full_case_charge_prices_subsidized_hours_without_holiday_multiplier(rule):
    terms = CasePricingTerms("測試", rule, Decimal(40), HourlyRates(300, 350), HourlyRates(400, 450))
    assert calculate_case_total_amount(terms, ((Decimal(30), False), (Decimal(20), True)), 1000) == 16500
    # Historical unequal salary rates must never replace the service price.
    assert calculate_case_total_amount(terms, ((Decimal('8.5'), False),), 500) == 3050


def test_self_pay_case_and_fixed_fee_once():
    terms = CasePricingTerms("非市民", IdentityRule.NON_CITIZEN, Decimal(0), HourlyRates(0, 350), HourlyRates(0, 300))
    assert calculate_case_total_amount(terms, ((Decimal(30), False), (Decimal(20), True)), 1000) == 18500

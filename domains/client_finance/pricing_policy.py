"""Versioned client pricing and subsidy limits; transport and persistence free."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class IdentityRule(StrEnum):
    CITIZEN = "citizen"
    SOCIAL = "social"
    NON_CITIZEN = "non_citizen"


@dataclass(frozen=True, slots=True)
class HourlyRates:
    covered: int
    excess: int

    def __post_init__(self):
        if type(self.covered) is not int or self.covered < 0 or type(self.excess) is not int or self.excess <= 0:
            raise ValueError("pricing_hourly_rate_invalid")


@dataclass(frozen=True, slots=True)
class CasePricingTerms:
    identity_name: str
    rule: IdentityRule
    subsidy_hours: Decimal
    client: HourlyRates
    payroll: HourlyRates

    def __post_init__(self):
        if not self.identity_name.strip() or len(self.identity_name) > 100:
            raise ValueError("pricing_identity_name_required")
        if self.identity_name != self.identity_name.strip():
            raise ValueError("pricing_identity_name_must_be_trimmed")
        if not isinstance(self.rule, IdentityRule):
            raise ValueError("pricing_identity_rule_invalid")
        hours = Decimal(str(self.subsidy_hours))
        if not hours.is_finite() or hours < 0 or hours * 2 != (hours * 2).to_integral_value():
            raise ValueError("pricing_subsidy_hours_invalid")
        if self.rule is IdentityRule.NON_CITIZEN and hours != 0:
            raise ValueError("pricing_non_citizen_subsidy_hours_must_be_zero")
        if hours > 0 and (self.client.covered == 0 or self.payroll.covered == 0):
            raise ValueError("pricing_covered_rate_must_be_positive")
        if self.rule is IdentityRule.NON_CITIZEN:
            # Unused historical covered rates carry no entitlement or money.
            object.__setattr__(self, "client", HourlyRates(0, self.client.excess))
            object.__setattr__(self, "payroll", HourlyRates(0, self.payroll.excess))
        object.__setattr__(self, "subsidy_hours", hours)

    def validate_subsidy_rates(self) -> None:
        """Guard new settings; historical unequal settings remain readable."""
        if self.client.covered != self.payroll.covered:
            raise ValueError("pricing_covered_rates_must_match")

    def split_hours(self, total: Decimal) -> tuple[Decimal, Decimal]:
        total = Decimal(str(total))
        if not total.is_finite() or total < 0:
            raise ValueError("pricing_service_hours_invalid")
        covered = min(total, self.subsidy_hours)
        return covered, total - covered

    def client_charge(self, hours: Decimal, consumed: Decimal = Decimal(0), *, double_pay=False) -> int:
        remaining = max(Decimal(0), self.subsidy_hours - consumed)
        covered = min(Decimal(str(hours)), remaining)
        excess = Decimal(str(hours)) - covered
        amount = excess * self.client.excess
        if self.rule is not IdentityRule.SOCIAL:
            amount += covered * self.client.covered
        return whole_ntd(amount * (2 if double_pay else 1))

    def subsidy_return(self, total_hours: Decimal) -> int:
        covered, _ = self.split_hours(total_hours)
        return whole_ntd(covered * self.client.covered) if self.rule is IdentityRule.CITIZEN else 0

@dataclass(frozen=True, slots=True)
class PricingPolicy:
    effective_on: date
    identities: tuple[CasePricingTerms, ...]
    twins_client: HourlyRates
    twins_payroll: HourlyRates

    def __post_init__(self):
        if type(self.effective_on) is not date or not self.identities:
            raise ValueError("pricing_policy_date_and_identities_required")
        names = tuple(item.identity_name for item in self.identities)
        if len(set(names)) != len(names):
            raise ValueError("pricing_identity_names_must_be_unique")
        if {"一般市民", "低收入戶", "中低收入戶"}.intersection(names):
            raise ValueError("pricing_identity_alias_reserved")
        if not {"補助市民", "社福", "非市民"}.issubset(names):
            raise ValueError("pricing_existing_identities_required")
        expected = {"補助市民": IdentityRule.CITIZEN, "社福": IdentityRule.SOCIAL, "非市民": IdentityRule.NON_CITIZEN}
        if any(item.rule is not expected[item.identity_name] for item in self.identities if item.identity_name in expected):
            raise ValueError("pricing_existing_identity_rule_immutable")

    def for_case(self, identity: str, *, twins=False) -> CasePricingTerms:
        identity = {"一般市民": "補助市民", "低收入戶": "社福", "中低收入戶": "社福"}.get(identity, identity)
        result = next((item for item in self.identities if item.identity_name == identity), None)
        if result is None:
            raise ValueError("pricing_identity_not_in_bound_policy")
        if not twins:
            return result
        return CasePricingTerms(result.identity_name, result.rule, result.subsidy_hours, self.twins_client, self.twins_payroll)

    def validate_subsidy_rates(self) -> None:
        for item in self.identities:
            item.validate_subsidy_rates()
        if self.twins_client.covered != self.twins_payroll.covered:
            raise ValueError("pricing_covered_rates_must_match")
        if self.twins_client.covered == 0:
            raise ValueError("pricing_covered_rate_must_be_positive")


def whole_ntd(value: Decimal) -> int:
    if not value.is_finite() or value != value.to_integral_value():
        raise ValueError("pricing_amount_must_be_whole_ntd")
    return int(value)

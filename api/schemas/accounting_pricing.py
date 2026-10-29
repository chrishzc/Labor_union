"""Closed public contracts for policy versions and individual case pricing."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, PricingPolicy


class PricingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class HourlyRatesBody(PricingModel):
    covered: int = Field(strict=True, ge=0)
    excess: int = Field(strict=True, gt=0)


class CasePricingTermsBody(PricingModel):
    identity_name: str = Field(min_length=1, max_length=100)
    rule: Literal["citizen", "social", "non_citizen"]
    subsidy_hours: float = Field(ge=0, multiple_of=0.5, allow_inf_nan=False)
    client: HourlyRatesBody
    payroll: HourlyRatesBody

    def domain(self):
        return CasePricingTerms(self.identity_name.strip(), IdentityRule(self.rule), Decimal(str(self.subsidy_hours)),
            HourlyRates(**self.client.model_dump()), HourlyRates(**self.payroll.model_dump()))


class PricingPolicyBody(PricingModel):
    effective_on: date
    identities: list[CasePricingTermsBody] = Field(min_length=1, max_length=100)
    twins_client: HourlyRatesBody
    twins_payroll: HourlyRatesBody

    def domain(self):
        return PricingPolicy(self.effective_on, tuple(item.domain() for item in self.identities),
            HourlyRates(**self.twins_client.model_dump()), HourlyRates(**self.twins_payroll.model_dump()))


class PolicyVersionView(PricingModel):
    revision: int
    policy: PricingPolicyBody
    actor: str
    reason: str


class PricingCatalogView(PricingModel):
    revision: int
    versions: list[PolicyVersionView]


class SavePricingPolicyBody(PricingModel):
    policy: PricingPolicyBody
    expected_revision: int = Field(ge=0)
    reason: str = Field(default="", max_length=500)


class PricingImpactView(PricingModel):
    covered_hours: float
    excess_hours: float
    client_amount: int
    staff_covered_amount: int
    staff_excess_amount: int
    staff_total_amount: int
    subsidy_amount: int
    subsidy_return_amount: int


class CasePricingView(PricingModel):
    case_no: str
    revision: int
    source: str
    terms: CasePricingTermsBody
    impact: PricingImpactView


class CasePricingPreviewBody(PricingModel):
    terms: CasePricingTermsBody
    expected_revision: int = Field(ge=0)


class CasePricingApplyBody(CasePricingPreviewBody):
    preview_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=500)


class CasePricingPreviewView(PricingModel):
    current: CasePricingView
    candidate: CasePricingTermsBody
    before: PricingImpactView
    after: PricingImpactView
    preview_fingerprint: str


class PricingReceiptView(PricingModel):
    revision: int

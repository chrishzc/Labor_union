"""Closed public contracts for policy versions and individual case pricing."""

from datetime import date
from dataclasses import replace
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


class PolicyIdentityBody(CasePricingTermsBody):
    deposit_service_days: int | None = Field(default=None, strict=True, ge=0, le=2_147_483_647)

    def domain(self):
        return replace(super().domain(), deposit_service_days=self.deposit_service_days)


class PricingPolicyBody(PricingModel):
    effective_on: date
    identities: list[PolicyIdentityBody] = Field(min_length=1, max_length=100)
    twins_client: HourlyRatesBody
    twins_payroll: HourlyRatesBody
    indigenous_deposit_service_days: int | None = Field(default=None, strict=True, ge=0, le=2_147_483_647)

    def domain(self):
        return PricingPolicy(self.effective_on, tuple(item.domain() for item in self.identities),
            HourlyRates(**self.twins_client.model_dump()), HourlyRates(**self.twins_payroll.model_dump()),
            self.indigenous_deposit_service_days)


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
    covered_hours: float | None
    excess_hours: float | None
    client_amount: int | None
    staff_covered_amount: int | None
    staff_excess_amount: int | None
    staff_total_amount: int | None
    subsidy_amount: int | None
    subsidy_return_amount: int | None
    case_total_amount: int | None
    union_income_amount: int | None


class CasePricingView(PricingModel):
    case_no: str
    revision: int
    source: str
    terms: CasePricingTermsBody
    impact: PricingImpactView
    historical: bool = False
    accounting_pending: list[str] = Field(default_factory=list)


class CasePricingPreviewBody(PricingModel):
    terms: CasePricingTermsBody
    expected_revision: int = Field(ge=0)


class CasePricingApplyBody(CasePricingPreviewBody):
    preview_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=500)


class HistoricalAmountUpdateView(PricingModel):
    identity: str
    computed: int
    effective: int
    before_computed: int
    before_effective: int
    mode: Literal['automatic', 'manual']


class HistoricalPersonPricingView(PricingModel):
    assignment_identity: str
    staff_id: int
    staff_name: str
    hours: float | None
    before_amount: int | None
    after_amount: int | None
    delta: int | None


class HistoricalRepricingPlanView(PricingModel):
    client_updates: list[HistoricalAmountUpdateView]
    staff_updates: list[HistoricalAmountUpdateView]
    persons: list[HistoricalPersonPricingView]
    pending: list[str]
    client_exempt: bool
    client_delta: int | None
    subsidy_delta: int | None


class CasePricingPreviewView(PricingModel):
    current: CasePricingView
    candidate: CasePricingTermsBody
    before: PricingImpactView
    after: PricingImpactView
    preview_fingerprint: str
    historical_plan: HistoricalRepricingPlanView | None = None


class PricingReceiptView(PricingModel):
    revision: int
    accounting_pending: list[str] = Field(default_factory=list)

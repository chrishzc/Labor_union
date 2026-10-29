"""Versioned pricing configuration and explicit, atomic case repricing."""

from dataclasses import asdict, dataclass, is_dataclass, replace
import json
from datetime import date
from decimal import Decimal
from typing import Callable, ContextManager, Protocol

from domains.client_finance.pricing_policy import CasePricingTerms, PricingPolicy
from domains.payroll.tiered_rates import TieredPayrollRate, price_hours
from domains.government_subsidy.pricing import subsidy_claim_amount
from shared_kernel.fingerprints import fingerprint_payload


class PricingConflict(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def pricing_payload(value):
    """Canonical representation for this pricing contract's dataclasses only."""
    def encode(item):
        if is_dataclass(item):
            return asdict(item)
        if isinstance(item, date):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        raise TypeError("unsupported pricing value")
    return json.loads(json.dumps(value, default=encode, ensure_ascii=False))


def _fingerprint(payload):
    return fingerprint_payload(pricing_payload(payload)).value


@dataclass(frozen=True)
class PolicyVersion:
    revision: int
    policy: PricingPolicy
    actor: str
    reason: str


@dataclass(frozen=True)
class PricingCatalog:
    revision: int
    versions: tuple[PolicyVersion, ...]


@dataclass(frozen=True)
class PricingServiceDay:
    occurred_on: date
    hours: Decimal
    double_pay: bool = False


@dataclass(frozen=True)
class PricingImpact:
    covered_hours: Decimal
    excess_hours: Decimal
    client_amount: int
    staff_covered_amount: int
    staff_excess_amount: int
    staff_total_amount: int
    subsidy_amount: int
    subsidy_return_amount: int


@dataclass(frozen=True)
class CasePricingFacts:
    case_no: str
    revision: int
    versions: tuple[int, ...]
    terms: CasePricingTerms
    source: str
    days: tuple[PricingServiceDay, ...]
    floor_fee: int
    payroll_adjustment: int = 0
    legacy_client_amount: int | None = None


@dataclass(frozen=True)
class CasePricingPreview:
    facts: CasePricingFacts
    candidate: CasePricingTerms
    before: PricingImpact
    after: PricingImpact
    fingerprint: str


class PricingRepository(Protocol):
    def catalog(self, *, lock: bool = False) -> PricingCatalog: ...
    def case(self, case_no: str, *, lock: bool = False) -> CasePricingFacts: ...
    def receipt(self, key: str, actor: str, command_hash: str) -> int | None: ...
    def save_policy(self, policy: PricingPolicy, revision: int, actor: str, reason: str) -> None: ...
    def save_case(self, facts: CasePricingFacts, terms: CasePricingTerms, actor: str, reason: str, key: str) -> None: ...
    def save_receipt(self, key: str, actor: str, command_hash: str, revision: int) -> None: ...


def pricing_impact(terms: CasePricingTerms, facts: CasePricingFacts) -> PricingImpact:
    consumed = Decimal(0)
    client = 0
    for day in sorted(facts.days, key=lambda item: item.occurred_on):
        client += terms.client_charge(day.hours, consumed, double_pay=day.double_pay)
        consumed += day.hours
    covered, excess = terms.split_hours(consumed)
    staff_covered, staff_excess = price_hours(
        tuple((day.hours, day.double_pay) for day in sorted(facts.days, key=lambda item: item.occurred_on)),
        TieredPayrollRate(terms.payroll.covered, terms.payroll.excess, terms.subsidy_hours, terms.rule.value == "social"),
    )
    return PricingImpact(covered, excess, client + facts.floor_fee, staff_covered,
        staff_excess, staff_covered + staff_excess + facts.floor_fee + facts.payroll_adjustment,
        subsidy_claim_amount(consumed, terms.subsidy_hours, terms.payroll.covered), terms.subsidy_return(consumed))


def current_pricing_impact(facts):
    result = pricing_impact(facts.terms, facts)
    return replace(result, client_amount=facts.legacy_client_amount) if facts.legacy_client_amount is not None else result


class PricingConfigurationApplication:
    def __init__(self, repository: PricingRepository, unit_factory: Callable[[], ContextManager]):
        self.repository = repository
        self.unit_factory = unit_factory

    def catalog(self):
        return self.repository.catalog()

    def save_policy(self, policy: PricingPolicy, expected_revision: int, actor: str, reason: str, key: str) -> int:
        command = _fingerprint({"policy": policy, "expected_revision": expected_revision, "reason": reason})
        with self.unit_factory() as unit:
            catalog = self.repository.catalog(lock=True)
            replay = self.repository.receipt(key, actor, command)
            if replay is not None:
                return replay
            if catalog.revision != expected_revision:
                raise PricingConflict("pricing_policy_stale")
            revision = catalog.revision + 1
            self.repository.save_policy(policy, revision, actor, reason)
            self.repository.save_receipt(key, actor, command, revision)
            unit.commit()
            return revision

    def query_case(self, case_no: str):
        facts = self.repository.case(case_no)
        return facts, current_pricing_impact(facts)

    def preview_case(self, case_no: str, terms: CasePricingTerms, expected_revision: int) -> CasePricingPreview:
        return self._preview(self.repository.case(case_no), terms, expected_revision)

    def _validate_case_terms(self, facts, terms, expected_revision):
        if facts.revision != expected_revision:
            raise PricingConflict("case_pricing_stale")
        if terms.rule is not facts.terms.rule or terms.identity_name != facts.terms.identity_name:
            raise ValueError("case_pricing_identity_rule_immutable")

    def _preview(self, facts, terms, expected_revision):
        self._validate_case_terms(facts, terms, expected_revision)
        fingerprint = _fingerprint({"case_no": facts.case_no, "revision": facts.revision,
            "owner_versions": facts.versions, "candidate": terms, "days": facts.days,
            "floor_fee": facts.floor_fee, "payroll_adjustment":facts.payroll_adjustment,
            "legacy_client_amount":facts.legacy_client_amount, "before": facts.terms})
        return CasePricingPreview(facts, terms, current_pricing_impact(facts), pricing_impact(terms, facts), fingerprint)

    def apply_case(self, case_no, terms, expected_revision, preview_fingerprint, actor, reason, key):
        reason = reason.strip()
        command = _fingerprint({"case_no": case_no, "terms": terms,
            "revision": expected_revision, "preview": preview_fingerprint, "reason": reason})
        with self.unit_factory() as unit:
            facts = self.repository.case(case_no, lock=True)
            replay = self.repository.receipt(key, actor, command)
            if replay is not None:
                return replay
            self._validate_case_terms(facts, terms, expected_revision)
            if preview_fingerprint is not None and self._preview(facts, terms, expected_revision).fingerprint != preview_fingerprint:
                raise PricingConflict("case_pricing_preview_stale")
            self.repository.save_case(facts, terms, actor, reason, key)
            self.repository.save_receipt(key, actor, command, facts.revision + 1)
            unit.commit()
            return facts.revision + 1

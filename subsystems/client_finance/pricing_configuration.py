"""Versioned pricing configuration and explicit, atomic case repricing."""

from dataclasses import asdict, dataclass, is_dataclass, replace
import json
from datetime import date
from decimal import Decimal
from typing import Callable, ContextManager, Literal, Protocol

from domains.client_finance.pricing_policy import CasePricingTerms, PricingPolicy, calculate_case_total_amount, calculate_holiday_premium, whole_ntd
from domains.payroll.tiered_rates import TieredPayrollRate, price_hours
from domains.payroll.calculation import AssignmentRateSnapshot
from domains.payroll.historical_calculation import historical_service_salary
from domains.government_subsidy.pricing import subsidy_claim_amount
from domains.client_finance.subsidy_coverage import normalize_subsidy_policy_identity
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.fingerprints import PreviewFingerprint


HistoricalRateAuthority = Literal['legacy', 'policy', 'manual']


class PricingConflict(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def pricing_payload(value):
    """Canonical representation for this pricing contract's dataclasses only."""
    def encode(item):
        if is_dataclass(item) and not isinstance(item, type):
            payload = asdict(item, dict_factory=lambda fields: {
                key: value for key, value in fields
                if key != "deposit_service_days" or (isinstance(item, PricingPolicy) and value is not None)
            })
            if isinstance(item, PricingPolicy) and item.indigenous_deposit_service_days is None:
                # Keep the original hash for replays of policy commands without this setting.
                del payload["indigenous_deposit_service_days"]
            return payload
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
    holiday_hours: Decimal = Decimal(0)
    holiday_hour_segments: tuple[tuple[Decimal, Decimal], ...] = ()


@dataclass(frozen=True)
class PricingImpact:
    covered_hours: Decimal | None
    excess_hours: Decimal | None
    client_amount: int | None
    staff_covered_amount: int | None
    staff_excess_amount: int | None
    staff_total_amount: int | None
    subsidy_amount: int | None
    subsidy_return_amount: int | None
    case_total_amount: int | None = 0
    union_income_amount: int | None = None


@dataclass(frozen=True)
class HistoricalPricingPerson:
    assignment_identity: str
    staff_id: int
    staff_name: str
    hours: Decimal | None
    actual_service_days: int | None
    adjustment: int = 0
    rate_snapshot: AssignmentRateSnapshot | None = None


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
    historical_service_hours: Decimal | None = None
    frozen_amounts: tuple[int, int] | None = None
    frozen_case_total: int | None = None
    formal_staff_amount: int | None = None
    formal_client_amount: int | None = None
    historical_people: tuple[HistoricalPricingPerson, ...] = ()
    historical: bool = False
    accounting_pending: tuple[str, ...] = ()
    financial_sources_digest: str = ""
    historical_plan: "HistoricalRepricingPlan | None" = None
    accounting_carry: tuple["HistoricalAccountingCarry", ...] = ()


@dataclass(frozen=True)
class CasePricingKnownTerms:
    """Read-only projection when the case has pricing but no payment terms."""

    case_no: str
    revision: int
    terms: CasePricingTerms
    source: str
    case_total_amount: int | None
    historical: bool
    accounting_pending: tuple[str, ...]


@dataclass(frozen=True)
class CasePricingPreview:
    facts: CasePricingFacts
    candidate: CasePricingTerms
    before: PricingImpact
    after: PricingImpact
    fingerprint: str
    historical_plan: "HistoricalRepricingPlan | None" = None


@dataclass(frozen=True)
class HistoricalAmountFacts:
    identity: str
    computed: int
    effective: int
    mode: str


@dataclass(frozen=True)
class HistoricalAmountUpdate:
    identity: str
    computed: int
    effective: int
    before_computed: int
    before_effective: int
    mode: str


@dataclass(frozen=True)
class HistoricalPersonPricing:
    assignment_identity: str
    staff_id: int
    staff_name: str
    hours: Decimal | None
    before_amount: int | None
    after_amount: int | None
    delta: int | None


@dataclass(frozen=True)
class HistoricalAccountingCarry:
    component: Literal['client', 'subsidy', 'payroll']
    identity: str
    basis_amount: int | None
    pending: tuple[str, ...]
    financial_sources_digest: str
    subsidy_claim_basis: int | None = None


@dataclass(frozen=True)
class HistoricalRepricingPlan:
    case_no: str
    client_version: int
    payroll_version: int | None
    client_updates: tuple[HistoricalAmountUpdate, ...]
    staff_updates: tuple[HistoricalAmountUpdate, ...]
    source_versions: tuple[int, ...] = ()
    new_deposit: tuple[str, str | None] | None = None
    persons: tuple[HistoricalPersonPricing, ...] = ()
    pending: tuple[str, ...] = ()
    client_exempt: bool = False
    client_delta: int | None = 0
    subsidy_delta: int | None = 0
    financial_sources_digest: str = ""
    carry: tuple[HistoricalAccountingCarry, ...] = ()
    rate_authority: HistoricalRateAuthority | None = None

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)

    @property
    def client_changed(self):
        return any(i.computed != i.before_computed or i.effective != i.before_effective for i in self.client_updates)

    @property
    def payroll_changed(self):
        return any(i.computed != i.before_computed or i.effective != i.before_effective for i in self.staff_updates)


@dataclass(frozen=True)
class HistoricalBirthCorrectionPreview:
    fingerprint: PreviewFingerprint
    impact: HistoricalRepricingPlan
    facts: CasePricingFacts
    terms: CasePricingTerms
    before_birth_count: str | None
    after_birth_count: str


def build_historical_deposit_floor_fee_plan(case_no, client_version, service_basis, source, new_deposit, delta):
    if source is None and delta < 0:
        raise PricingConflict('historical_pricing_amount_conflict')
    if source is None and delta > 0:
        source = HistoricalAmountFacts(new_deposit[0], 0, 0, 'automatic')
    else:
        new_deposit = None
    updates = ()
    if source is not None and delta:
        computed = source.computed + delta
        effective = source.effective + delta
        if min(computed, effective) < 0:
            raise PricingConflict('historical_pricing_amount_conflict')
        updates = (HistoricalAmountUpdate(source.identity, computed, effective,
            source.computed, source.effective, source.mode),)
    return HistoricalRepricingPlan(case_no, client_version, None, updates, (), service_basis, new_deposit)


def build_historical_repricing_plan(facts, terms, client_sources, staff_source, *, subsidy_source=None):
    before = pricing_impact(facts.terms, facts)
    after = pricing_impact(terms, facts)
    def update(source, delta):
        revised = source.computed + delta
        effective = source.effective if source.mode == 'manual' else revised
        if min(revised, effective) < 0:
            raise PricingConflict('historical_pricing_amount_conflict')
        return HistoricalAmountUpdate(source.identity, revised, effective,
            source.computed, source.effective, source.mode)
    if (after.client_amount is None or before.client_amount is None
            or after.staff_total_amount is None or before.staff_total_amount is None):
        raise PricingConflict('historical_pricing_original_calculation_basis_required')
    delta = after.client_amount - before.client_amount
    updates = []
    for source in reversed(client_sources):
        applied = max(-source.computed, delta) if delta < 0 else delta
        updates.append(update(source, applied))
        delta -= applied
    if delta:
        raise PricingConflict('historical_pricing_amount_conflict')
    if subsidy_source is not None:
        if after.subsidy_return_amount is None or before.subsidy_return_amount is None:
            raise PricingConflict('historical_pricing_original_calculation_basis_required')
        updates.append(update(subsidy_source, after.subsidy_return_amount - before.subsidy_return_amount))
    return HistoricalRepricingPlan(facts.case_no, facts.versions[1], facts.versions[2], tuple(updates),
        (update(staff_source, after.staff_total_amount - before.staff_total_amount),), facts.versions)


class PricingRepository(Protocol):
    accounting_pending: tuple[str, ...]
    def catalog(self, *, lock: bool = False) -> PricingCatalog: ...
    def case_for_query(self, case_no: str) -> CasePricingFacts | CasePricingKnownTerms: ...
    def case(self, case_no: str, *, lock: bool = False) -> CasePricingFacts: ...
    def historical_plan(self, facts: CasePricingFacts, terms: CasePricingTerms, *, lock: bool) -> HistoricalRepricingPlan: ...
    def receipt(self, key: str, actor: str, command_hash: str) -> int | None: ...
    def save_policy(self, policy: PricingPolicy, revision: int, actor: str, reason: str) -> None: ...
    def save_case(self, facts: CasePricingFacts, terms: CasePricingTerms, actor: str, reason: str, key: str) -> None: ...
    def save_receipt(self, key: str, actor: str, command_hash: str, revision: int) -> None: ...


def legacy_historical_service_salary(person: HistoricalPricingPerson, hours: Decimal) -> int:
    snapshot = person.rate_snapshot
    if (snapshot is None or snapshot.assignment_identity != person.assignment_identity
            or snapshot.hourly_rate.amount <= 0):
        raise PricingConflict('case_pricing_payroll_snapshot_required')
    return historical_service_salary(hours, snapshot.hourly_rate).amount


def _base_pricing_impact(terms: CasePricingTerms, facts: CasePricingFacts, *,
        use_legacy_person_rates: bool = False) -> PricingImpact:
    if facts.historical_service_hours is not None:
        hours = facts.historical_service_hours
        covered, excess = terms.split_hours(hours)
        staff_covered, staff_excess = price_hours(((hours, False),),
            TieredPayrollRate(terms.payroll.covered, terms.payroll.excess, terms.subsidy_hours, terms.rule.value == "social"))
        if facts.historical_people and all(person.hours is not None for person in facts.historical_people):
            consumed = Decimal(0)
            staff_covered = staff_excess = 0
            for person in facts.historical_people:
                if person.hours is None:
                    continue
                if use_legacy_person_rates and facts.source == 'legacy':
                    covered_hours = min(person.hours, max(Decimal(0), terms.subsidy_hours - consumed))
                    covered_amount = legacy_historical_service_salary(person, covered_hours)
                    excess_amount = legacy_historical_service_salary(person, person.hours - covered_hours)
                else:
                    covered_amount, excess_amount = price_hours(((person.hours, False),),
                        TieredPayrollRate(terms.payroll.covered, terms.payroll.excess, terms.subsidy_hours, terms.rule.value == "social"), consumed)
                staff_covered += covered_amount
                staff_excess += excess_amount
                consumed += person.hours
        full_subsidy = facts.historical and terms.is_full_subsidy(hours) is True
        staff_total = staff_covered + staff_excess + facts.floor_fee + facts.payroll_adjustment
        if facts.historical and (not facts.historical_people or any(person.hours is None for person in facts.historical_people)):
            staff_covered = staff_excess = staff_total = None
        return PricingImpact(covered, excess, 0 if full_subsidy else terms.client_charge(hours) + facts.floor_fee,
            staff_covered, staff_excess, staff_total,
            calculate_case_total_amount(terms, ((hours, False),), facts.floor_fee) if full_subsidy else
            subsidy_claim_amount(hours, terms.subsidy_hours, terms.payroll.covered), terms.subsidy_return(hours))
    service_hours = tuple((day.hours, day.double_pay) for day in sorted(facts.days, key=lambda item: item.occurred_on))
    total_hours = sum((hours for hours, _ in service_hours), Decimal(0))
    covered, excess = terms.split_hours(total_hours)
    staff_covered, staff_excess = price_hours(
        service_hours,
        TieredPayrollRate(terms.payroll.covered, terms.payroll.excess, terms.subsidy_hours, terms.rule.value == "social"),
    )
    staff_total = staff_covered + staff_excess + facts.floor_fee + facts.payroll_adjustment
    if terms.is_full_subsidy(total_hours):
        subsidy = calculate_case_total_amount(terms, service_hours, facts.floor_fee)
        return PricingImpact(covered, excess, 0, staff_covered, staff_excess, staff_total, subsidy, 0)

    consumed = Decimal(0)
    client = facts.floor_fee
    for hours, double_pay in service_hours:
        client += terms.client_charge(hours, consumed) * (2 if double_pay else 1)
        consumed += hours
    return PricingImpact(covered, excess, client, staff_covered,
        staff_excess, staff_total, subsidy_claim_amount(total_hours, terms.subsidy_hours, terms.payroll.covered),
        terms.subsidy_return(total_hours))


def _holiday_premium(terms: CasePricingTerms, facts: CasePricingFacts, *, payroll: bool = False) -> int:
    if facts.historical_service_hours is not None:
        return 0
    return calculate_holiday_premium(terms, tuple(
        (day.hours, day.holiday_hour_segments or ((Decimal(0), day.holiday_hours),))
        for day in sorted(facts.days, key=lambda item: item.occurred_on)
    ), payroll=payroll)


def case_total_amount(facts: CasePricingFacts) -> int | None:
    if facts.historical and facts.historical_service_hours is None:
        return None
    if facts.frozen_case_total is not None:
        return facts.frozen_case_total
    if facts.historical_service_hours is not None:
        return calculate_case_total_amount(facts.terms, ((facts.historical_service_hours, False),), facts.floor_fee)
    return calculate_case_total_amount(facts.terms,
        tuple((day.hours, day.double_pay) for day in sorted(facts.days, key=lambda item: item.occurred_on)), facts.floor_fee
    ) + _holiday_premium(facts.terms, facts)


def pricing_impact(terms: CasePricingTerms, facts: CasePricingFacts, *,
        use_legacy_person_rates: bool = False) -> PricingImpact:
    if facts.historical and facts.historical_service_hours is None:
        return PricingImpact(None, None, None, None, None, None, None, None, None)
    if terms != facts.terms:
        facts = replace(facts, frozen_amounts=None, frozen_case_total=None)
    base = _base_pricing_impact(terms, facts, use_legacy_person_rates=use_legacy_person_rates)
    client_premium = _holiday_premium(terms, facts)
    staff_premium = _holiday_premium(terms, facts, payroll=True)
    total = case_total_amount(replace(facts, terms=terms))
    hours = facts.historical_service_hours if facts.historical_service_hours is not None else sum((day.hours for day in facts.days), Decimal(0))
    full_subsidy = terms.is_full_subsidy(hours)
    subsidy = base.subsidy_amount
    if full_subsidy and facts.historical_service_hours is None:
        subsidy = calculate_case_total_amount(terms, tuple((day.hours, False) for day in facts.days), facts.floor_fee)
    staff_total = base.staff_total_amount + staff_premium if base.staff_total_amount is not None else None
    income = None if total is None or staff_total is None or (full_subsidy and client_premium) else total - staff_total + facts.payroll_adjustment
    if facts.frozen_amounts is not None:
        client_amount, staff_total = facts.frozen_amounts
        return replace(base, client_amount=client_amount, staff_total_amount=staff_total,
            staff_covered_amount=None, staff_excess_amount=None,
            case_total_amount=total, subsidy_amount=subsidy,
            union_income_amount=total - staff_total + facts.payroll_adjustment if total is not None else None)
    covered_premium_amount = Decimal(0)
    consumed = Decimal(0)
    for day in sorted(facts.days, key=lambda item: item.occurred_on):
        for offset, premium_hours in day.holiday_hour_segments or ((Decimal(0), day.holiday_hours),):
            covered = min(premium_hours, max(Decimal(0), terms.subsidy_hours - consumed - offset))
            covered_premium_amount += covered * terms.payroll.covered
        consumed += day.hours
    staff_covered_premium = whole_ntd(covered_premium_amount)
    return replace(base, client_amount=base.client_amount + (0 if full_subsidy else client_premium) if base.client_amount is not None else None,
        staff_covered_amount=base.staff_covered_amount + staff_covered_premium if base.staff_covered_amount is not None else None,
        staff_excess_amount=base.staff_excess_amount + staff_premium - staff_covered_premium if base.staff_excess_amount is not None else None,
        staff_total_amount=staff_total, subsidy_amount=subsidy, case_total_amount=total,
        union_income_amount=income)


def current_pricing_impact(facts: CasePricingFacts) -> PricingImpact:
    result = pricing_impact(facts.terms, facts,
        use_legacy_person_rates=facts.historical_service_hours is not None and facts.source == 'legacy')
    if (facts.source == "legacy"
            and normalize_subsidy_policy_identity(facts.terms.identity_name) in {"補助市民", "原住民"}
            and any(day.double_pay or day.holiday_hours for day in facts.days)):
        result = replace(result, union_income_amount=None)
    if facts.formal_staff_amount is not None:
        result = replace(result, staff_total_amount=facts.formal_staff_amount,
            staff_covered_amount=None, staff_excess_amount=None,
            union_income_amount=(result.case_total_amount - facts.formal_staff_amount + facts.payroll_adjustment)
                if result.union_income_amount is not None and result.case_total_amount is not None else None)
    client_amount = facts.formal_client_amount if facts.formal_client_amount is not None else facts.legacy_client_amount
    return replace(result, client_amount=client_amount) if client_amount is not None else result


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
            policy.validate_current_identity_names()
            policy.validate_subsidy_rates()
            revision = catalog.revision + 1
            self.repository.save_policy(policy, revision, actor, reason)
            self.repository.save_receipt(key, actor, command, revision)
            unit.commit()
            return revision

    def query_case(self, case_no: str) -> tuple[CasePricingFacts | CasePricingKnownTerms, PricingImpact]:
        facts = self.repository.case_for_query(case_no)
        if isinstance(facts, CasePricingKnownTerms):
            return facts, PricingImpact(
                covered_hours=None, excess_hours=None, client_amount=None,
                staff_covered_amount=None, staff_excess_amount=None, staff_total_amount=None,
                subsidy_amount=None, subsidy_return_amount=None, case_total_amount=facts.case_total_amount,
            )
        return facts, current_pricing_impact(facts)

    def preview_case(self, case_no: str, terms: CasePricingTerms, expected_revision: int) -> CasePricingPreview:
        facts = self.repository.case(case_no)
        plan = self.repository.historical_plan(facts, terms, lock=False) if facts.historical else None
        return self._preview(facts, terms, expected_revision, plan)

    def _validate_case_terms(self, facts, terms, expected_revision):
        if facts.revision != expected_revision:
            raise PricingConflict("case_pricing_stale")
        if terms.rule is not facts.terms.rule or terms.identity_name != facts.terms.identity_name:
            raise ValueError("case_pricing_identity_rule_immutable")
        terms.validate_subsidy_rates()

    def _preview(self, facts, terms, expected_revision, plan=None):
        self._validate_case_terms(facts, terms, expected_revision)
        fingerprint = _fingerprint({"case_no": facts.case_no, "revision": facts.revision,
            "owner_versions": facts.versions, "candidate": terms, "days": facts.days,
            "floor_fee": facts.floor_fee, "payroll_adjustment":facts.payroll_adjustment,
            "legacy_client_amount":facts.legacy_client_amount, "before": facts.terms,
            "historical_service_hours": facts.historical_service_hours,
            "historical_people": facts.historical_people, "financial_sources_digest": facts.financial_sources_digest,
            "historical_plan": plan})
        return CasePricingPreview(facts, terms, current_pricing_impact(facts), pricing_impact(terms, facts), fingerprint, plan)

    def apply_case(self, case_no, terms, expected_revision, preview_fingerprint, actor, reason, key):
        reason = reason.strip()
        command = _fingerprint({"case_no": case_no, "terms": terms,
            "revision": expected_revision, "preview": preview_fingerprint, "reason": reason})
        with self.unit_factory() as unit:
            replay = self.repository.receipt(key, actor, command)
            if replay is not None:
                return replay
            facts = self.repository.case(case_no, lock=True)
            self._validate_case_terms(facts, terms, expected_revision)
            plan = self.repository.historical_plan(facts, terms, lock=True) if facts.historical else None
            if facts.historical and preview_fingerprint is None:
                raise PricingConflict("case_pricing_preview_required")
            if preview_fingerprint is not None and self._preview(facts, terms, expected_revision, plan).fingerprint != preview_fingerprint:
                raise PricingConflict("case_pricing_preview_stale")
            facts = replace(facts, historical_plan=plan)
            self.repository.save_case(facts, terms, actor, reason, key)
            self.repository.save_receipt(key, actor, command, facts.revision + 1)
            unit.commit()
            return facts.revision + 1

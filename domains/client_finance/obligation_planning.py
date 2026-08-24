"""
File: obligation_planning.py
Description: 規劃客戶帳務義務，並表達未排班條款補正的零寫入影響。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum

from domains.client_finance.reconciliation import PaymentStage
from domains.orders.terms import OrderTerms
from domains.orders.floor_fee import prorate_floor_fee
from domains.scheduling.generation import SchedulingGenerationCandidate
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_FIRST_PAYMENT_MAXIMUM_DAYS = 15


class ClientObligationActionKind(StrEnum):
    CREATE_STAGE = "create_stage"
    REPLACE_OPEN = "replace_open"
    CANCEL_OPEN = "cancel_open"
    CREATE_ADJUSTMENT = "create_adjustment"
    CREATE_REFUND = "create_refund"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class ClientChargeDay:
    service_date: date
    is_double_pay: bool

    def __post_init__(self) -> None:
        if not isinstance(self.service_date, date):
            raise TypeError("client charge service date must be a date")
        if not isinstance(self.is_double_pay, bool):
            raise TypeError("client charge double-pay marker must be bool")


@dataclass(frozen=True, slots=True)
class ClientPaymentTerms:
    deposit_service_days: int
    client_hourly_rate: MoneyNTD
    deposit_due_date: date
    first_payment_due_date: date
    second_payment_due_date: date | None

    def __post_init__(self) -> None:
        require_nonnegative_integer(
            self.deposit_service_days,
            "deposit service days",
        )
        _require_positive_money(self.client_hourly_rate, "client hourly rate")
        _require_date(self.deposit_due_date, "deposit due date")
        _require_date(self.first_payment_due_date, "first payment due date")
        if self.second_payment_due_date is not None:
            _require_date(self.second_payment_due_date, "second payment due date")


@dataclass(frozen=True, slots=True)
class ExistingClientStageObligation:
    obligation_identity: str
    payment_stage: PaymentStage
    contracted_amount: MoneyNTD
    net_settled_amount: MoneyNTD
    due_date: date | None
    formal_history_exists: bool

    def __post_init__(self) -> None:
        _validate_identity(self.obligation_identity, "obligation identity")
        _require_nonnegative_money(self.contracted_amount, "contracted amount")
        _require_nonnegative_money(self.net_settled_amount, "settled amount")
        if self.net_settled_amount.amount > self.contracted_amount.amount:
            raise ValueError("settled amount exceeds contracted amount")
        if self.formal_history_exists:
            _validate_exact_history(self)


@dataclass(frozen=True, slots=True)
class ClientFinanceTermsFacts:
    case_no: str
    account_version: int
    service_hours_per_day: int
    floor_fee: MoneyNTD
    charge_days: tuple[ClientChargeDay, ...]
    payment_terms: ClientPaymentTerms
    existing_obligations: tuple[ExistingClientStageObligation, ...]
    open_nonstage_obligation_count: int = 0

    def __post_init__(self) -> None:
        _validate_identity(self.case_no, "case number")
        require_nonnegative_integer(self.account_version, "account version")
        require_positive_integer(
            self.service_hours_per_day,
            "service hours per day",
        )
        _require_nonnegative_money(self.floor_fee, "floor fee")
        _validate_charge_days(self.charge_days)
        _validate_existing_stages(self.existing_obligations)
        require_nonnegative_integer(
            self.open_nonstage_obligation_count,
            "open nonstage obligation count",
        )


@dataclass(frozen=True, slots=True)
class ClientFinanceTermsSourceFacts:
    case_no: str
    account_version: int
    payment_terms: ClientPaymentTerms
    double_pay_dates: tuple[date, ...]
    existing_obligations: tuple[ExistingClientStageObligation, ...]
    open_nonstage_obligation_count: int = 0

    def __post_init__(self) -> None:
        _validate_identity(self.case_no, "case number")
        require_nonnegative_integer(self.account_version, "account version")
        _validate_dates(self.double_pay_dates, "client double-pay dates")
        _validate_existing_stages(self.existing_obligations)
        require_nonnegative_integer(
            self.open_nonstage_obligation_count,
            "open nonstage obligation count",
        )


@dataclass(frozen=True, slots=True)
class ClientStagePlan:
    payment_stage: PaymentStage
    service_dates: tuple[date, ...]
    amount: MoneyNTD
    due_date: date | None


@dataclass(frozen=True, slots=True)
class ClientObligationAction:
    action: ClientObligationActionKind
    payment_stage: PaymentStage
    obligation_identity: str
    before_amount: MoneyNTD
    after_amount: MoneyNTD
    obligation_amount: MoneyNTD
    before_due_date: date | None
    after_due_date: date | None
    source_obligation_identity: str | None


@dataclass(frozen=True, slots=True)
class ClientFinanceTermsCandidate:
    case_no: str
    expected_account_version: int
    resulting_account_version: int
    stage_plans: tuple[ClientStagePlan, ...]
    actions: tuple[ClientObligationAction, ...]
    settlement: ClientSettlementProjection
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class PrecontractDepositCandidate:
    """The sole receivable that may exist before the client signs."""

    case_no: str
    expected_account_version: int
    resulting_account_version: int
    deposit_stage: ClientStagePlan
    deposit_action: ClientObligationAction
    mutates: bool
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClientSettlementProjection:
    deposit_settled: bool
    all_formal_obligations_settled: bool
    fingerprint: PreviewFingerprint


def build_client_finance_terms_candidate(
    facts: ClientFinanceTermsFacts,
    change_identity: str,
) -> ClientFinanceTermsCandidate:
    _validate_identity(change_identity, "change identity")
    stage_plans = _build_stage_plans(facts)
    existing_by_stage = {
        item.payment_stage: item for item in facts.existing_obligations
    }
    actions = tuple(
        _build_stage_action(
            facts.case_no,
            change_identity,
            stage_plan,
            existing_by_stage.get(stage_plan.payment_stage),
        )
        for stage_plan in stage_plans
    )
    return _candidate(facts, stage_plans, actions)


def build_precontract_deposit_candidate(
    facts: ClientFinanceTermsFacts,
    commitment_identity: str,
) -> PrecontractDepositCandidate:
    """Create only the deposit obligation from signed precontract service days."""

    full_candidate = build_client_finance_terms_candidate(
        facts, commitment_identity,
    )
    deposit_stage = _required_deposit_stage(full_candidate.stage_plans)
    deposit_action = _required_deposit_action(full_candidate.actions)
    _validate_precontract_deposit_action(deposit_action)
    mutates = deposit_action.action is ClientObligationActionKind.CREATE_STAGE
    resulting_version = facts.account_version + 1 if mutates else facts.account_version
    return PrecontractDepositCandidate(
        facts.case_no,
        facts.account_version,
        resulting_version,
        deposit_stage,
        deposit_action,
        mutates,
        fingerprint_payload(
            {
                "case_no": facts.case_no,
                "commitment_identity": commitment_identity,
                "account_version": facts.account_version,
                "deposit_action": _action_payload(deposit_action),
                "mutates": mutates,
            }
        ),
    )


def precontract_deposit_terms_impact(
    candidate: PrecontractDepositCandidate,
) -> ClientFinanceTermsCandidate:
    """Adapt the single permitted precontract action for the canonical writer."""

    return ClientFinanceTermsCandidate(
        candidate.case_no,
        candidate.expected_account_version,
        candidate.resulting_account_version,
        (candidate.deposit_stage,),
        (candidate.deposit_action,),
        ClientSettlementProjection(
            False,
            False,
            fingerprint_payload(
                {
                    "deposit_settled": False,
                    "all_formal_obligations_settled": False,
                }
            ),
        ),
        (),
        candidate.fingerprint,
    )


def build_client_finance_terms_impact(
    source_facts: ClientFinanceTermsSourceFacts,
    order_terms: OrderTerms,
    scheduling: SchedulingGenerationCandidate,
    change_identity: str,
) -> ClientFinanceTermsCandidate:
    facts = _materialize_terms_facts(source_facts, order_terms, scheduling)
    return build_client_finance_terms_candidate(facts, change_identity)


def build_preassignment_client_finance_noop(
    source_facts: ClientFinanceTermsSourceFacts,
    order_terms: OrderTerms,
    scheduling: SchedulingGenerationCandidate,
    change_identity: str,
) -> ClientFinanceTermsCandidate:
    _validate_identity(change_identity, "change identity")
    if source_facts.case_no != scheduling.case_no or scheduling.assignments:
        raise ValueError("preassignment_client_finance_facts_conflict")
    if source_facts.existing_obligations or source_facts.open_nonstage_obligation_count:
        raise ValueError("preassignment_client_finance_obligation_conflict")
    settlement = ClientSettlementProjection(
        False,
        False,
        fingerprint_payload({"mode": "preassignment", "settlement": "none"}),
    )
    return ClientFinanceTermsCandidate(
        source_facts.case_no,
        source_facts.account_version,
        source_facts.account_version,
        (),
        (),
        settlement,
        (),
        fingerprint_payload(
            {
                "mode": "preassignment_noop",
                "case_no": source_facts.case_no,
                "account_version": source_facts.account_version,
                "terms": order_terms.canonical_payload(),
                "scheduling_generation": scheduling.generation_number,
                "settlement": settlement.fingerprint.value,
            }
        ),
    )


def build_client_finance_cancellation_impact(
    source_facts: ClientFinanceTermsSourceFacts,
    order_terms: OrderTerms,
    scheduling: SchedulingGenerationCandidate,
    change_identity: str,
) -> ClientFinanceTermsCandidate:
    service_dates = _scheduling_service_dates(scheduling)
    earned_floor_fee = prorate_floor_fee(
        order_terms.floor_fee,
        order_terms.service_days,
        len(service_dates),
    )
    cancellation_terms = replace(order_terms, floor_fee=earned_floor_fee)
    cancellation_source = _cancellation_source_facts(
        source_facts, service_dates
    )
    return build_client_finance_terms_impact(
        cancellation_source,
        cancellation_terms,
        scheduling,
        change_identity,
    )


def _scheduling_service_dates(scheduling):
    assignment_dates = tuple(
        service_date
        for assignment in scheduling.assignments
        for service_date in assignment.service_dates
    )
    if len(assignment_dates) != len(set(assignment_dates)):
        raise ValueError("official client service days must be unique")
    return tuple(sorted(assignment_dates))


def _cancellation_source_facts(source_facts, service_dates):
    payment_terms = replace(
        source_facts.payment_terms,
        deposit_service_days=min(
            source_facts.payment_terms.deposit_service_days,
            len(service_dates),
        ),
    )
    return replace(
        source_facts,
        payment_terms=payment_terms,
        double_pay_dates=tuple(
            value
            for value in source_facts.double_pay_dates
            if value in service_dates
        ),
    )


def _materialize_terms_facts(source_facts, order_terms, scheduling):
    if source_facts.case_no != scheduling.case_no:
        raise ValueError("Client Finance and Scheduling case numbers must match")
    service_dates = _scheduling_service_dates(scheduling)
    charge_days = _charge_days(service_dates, source_facts.double_pay_dates)
    return ClientFinanceTermsFacts(
        source_facts.case_no,
        source_facts.account_version,
        order_terms.service_hours_per_day,
        order_terms.floor_fee,
        charge_days,
        source_facts.payment_terms,
        source_facts.existing_obligations,
        source_facts.open_nonstage_obligation_count,
    )


def _charge_days(service_dates, double_pay_dates):
    if service_dates != tuple(sorted(set(service_dates))):
        raise ValueError("official client service days must be sorted and unique")
    if not set(double_pay_dates).issubset(service_dates):
        raise ValueError("client double-pay date is not an official service day")
    return tuple(
        ClientChargeDay(value, value in double_pay_dates)
        for value in service_dates
    )


def _build_stage_plans(
    facts: ClientFinanceTermsFacts,
) -> tuple[ClientStagePlan, ...]:
    deposit_days, first_days, second_days = _split_charge_days(facts)
    return (
        _stage_plan(facts, PaymentStage.DEPOSIT, deposit_days, facts.floor_fee),
        _stage_plan(facts, PaymentStage.FIRST, first_days, MoneyNTD(0)),
        _stage_plan(facts, PaymentStage.SECOND, second_days, MoneyNTD(0)),
    )


def _required_deposit_stage(
    stage_plans: tuple[ClientStagePlan, ...],
) -> ClientStagePlan:
    return next(
        item for item in stage_plans if item.payment_stage is PaymentStage.DEPOSIT
    )


def _required_deposit_action(
    actions: tuple[ClientObligationAction, ...],
) -> ClientObligationAction:
    return next(
        item for item in actions if item.payment_stage is PaymentStage.DEPOSIT
    )


def _validate_precontract_deposit_action(action: ClientObligationAction) -> None:
    allowed = {
        ClientObligationActionKind.CREATE_STAGE,
        ClientObligationActionKind.UNCHANGED,
    }
    if action.action not in allowed:
        raise ValueError("precontract_deposit_obligation_conflict")


def _split_charge_days(facts):
    deposit_count = facts.payment_terms.deposit_service_days
    if deposit_count > len(facts.charge_days):
        raise ValueError("deposit service days exceed official service days")
    first_end = min(
        len(facts.charge_days),
        deposit_count + _FIRST_PAYMENT_MAXIMUM_DAYS,
    )
    return (
        facts.charge_days[:deposit_count],
        facts.charge_days[deposit_count:first_end],
        facts.charge_days[first_end:],
    )


def _stage_plan(facts, payment_stage, charge_days, floor_fee):
    daily_amounts = tuple(_daily_charge(facts, item) for item in charge_days)
    amount = MoneyNTD(sum(item.amount for item in daily_amounts)) + floor_fee
    return ClientStagePlan(
        payment_stage,
        tuple(item.service_date for item in charge_days),
        amount,
        _stage_due_date(facts.payment_terms, payment_stage),
    )


def _daily_charge(facts, charge_day):
    multiplier = 2 if charge_day.is_double_pay else 1
    return (
        facts.payment_terms.client_hourly_rate
        * facts.service_hours_per_day
        * multiplier
    )


def _stage_due_date(payment_terms, payment_stage):
    if payment_stage is PaymentStage.DEPOSIT:
        return payment_terms.deposit_due_date
    if payment_stage is PaymentStage.FIRST:
        return payment_terms.first_payment_due_date
    return payment_terms.second_payment_due_date


def _build_stage_action(case_no, change_identity, stage_plan, existing):
    if existing is None:
        return _new_stage_action(case_no, stage_plan)
    if not existing.formal_history_exists:
        return _open_stage_action(stage_plan, existing)
    return _settled_stage_action(change_identity, stage_plan, existing)


def _new_stage_action(case_no, stage_plan):
    action = (
        ClientObligationActionKind.UNCHANGED
        if stage_plan.amount.is_zero
        else ClientObligationActionKind.CREATE_STAGE
    )
    return ClientObligationAction(
        action,
        stage_plan.payment_stage,
        _base_obligation_identity(case_no, stage_plan.payment_stage),
        MoneyNTD(0),
        stage_plan.amount,
        stage_plan.amount,
        None,
        stage_plan.due_date,
        None,
    )


def _open_stage_action(stage_plan, existing):
    action = _open_action_kind(stage_plan, existing)
    return ClientObligationAction(
        action,
        stage_plan.payment_stage,
        existing.obligation_identity,
        existing.contracted_amount,
        stage_plan.amount,
        abs_money(stage_plan.amount - existing.contracted_amount),
        existing.due_date,
        stage_plan.due_date,
        None,
    )


def _open_action_kind(stage_plan, existing):
    if _stage_is_unchanged(stage_plan, existing):
        return ClientObligationActionKind.UNCHANGED
    if stage_plan.amount.is_zero:
        return ClientObligationActionKind.CANCEL_OPEN
    return ClientObligationActionKind.REPLACE_OPEN


def _settled_stage_action(change_identity, stage_plan, existing):
    difference = stage_plan.amount - existing.net_settled_amount
    action = _settled_action_kind(difference)
    return ClientObligationAction(
        action,
        stage_plan.payment_stage,
        _difference_identity(change_identity, stage_plan.payment_stage, action),
        existing.contracted_amount,
        stage_plan.amount,
        abs_money(difference),
        None,
        stage_plan.due_date,
        existing.obligation_identity,
    )


def _settled_action_kind(difference):
    if difference.is_zero:
        return ClientObligationActionKind.UNCHANGED
    if difference.amount > 0:
        return ClientObligationActionKind.CREATE_ADJUSTMENT
    return ClientObligationActionKind.CREATE_REFUND


def _candidate(facts, stage_plans, actions):
    settlement = _settlement_projection(facts, stage_plans, actions)
    payload = {
        "case_no": facts.case_no,
        "account_version": facts.account_version,
        "stage_plans": tuple(_stage_payload(item) for item in stage_plans),
        "actions": tuple(_action_payload(item) for item in actions),
        "settlement_fingerprint": settlement.fingerprint.value,
    }
    return ClientFinanceTermsCandidate(
        facts.case_no,
        facts.account_version,
        facts.account_version + 1,
        stage_plans,
        actions,
        settlement,
        (),
        fingerprint_payload(payload),
    )


def _settlement_projection(facts, stage_plans, actions):
    existing = {
        item.payment_stage: item for item in facts.existing_obligations
    }
    settled_by_stage = {
        item.payment_stage: _stage_settled(item, existing.get(item.payment_stage))
        for item in stage_plans
    }
    all_settled = (
        all(settled_by_stage.values())
        and facts.open_nonstage_obligation_count == 0
        and not _creates_open_difference(actions)
    )
    payload = {
        "deposit_settled": settled_by_stage[PaymentStage.DEPOSIT],
        "all_formal_obligations_settled": all_settled,
    }
    return ClientSettlementProjection(
        payload["deposit_settled"],
        all_settled,
        fingerprint_payload(payload),
    )


def _stage_settled(stage_plan, existing):
    if stage_plan.amount.is_zero:
        return True
    if existing is None or not existing.formal_history_exists:
        return False
    return existing.net_settled_amount.amount >= stage_plan.amount.amount


def _creates_open_difference(actions):
    open_actions = {
        ClientObligationActionKind.CREATE_STAGE,
        ClientObligationActionKind.REPLACE_OPEN,
        ClientObligationActionKind.CREATE_ADJUSTMENT,
        ClientObligationActionKind.CREATE_REFUND,
    }
    return any(
        item.action in open_actions and not item.obligation_amount.is_zero
        for item in actions
    )


def _stage_payload(stage_plan):
    return {
        "stage": stage_plan.payment_stage.value,
        "service_dates": tuple(
            value.isoformat() for value in stage_plan.service_dates
        ),
        "amount_ntd": stage_plan.amount.amount,
        "due_date": _date_text(stage_plan.due_date),
    }


def _action_payload(action):
    return {
        "action": action.action.value,
        "stage": action.payment_stage.value,
        "obligation_identity": action.obligation_identity,
        "before_amount_ntd": action.before_amount.amount,
        "after_amount_ntd": action.after_amount.amount,
        "obligation_amount_ntd": action.obligation_amount.amount,
        "before_due_date": _date_text(action.before_due_date),
        "after_due_date": _date_text(action.after_due_date),
        "source_obligation_identity": action.source_obligation_identity,
    }


def _validate_charge_days(charge_days):
    if not isinstance(charge_days, tuple):
        raise TypeError("client charge days must be a tuple")
    ordered_dates = tuple(item.service_date for item in charge_days)
    if ordered_dates != tuple(sorted(set(ordered_dates))):
        raise ValueError("client charge days must be sorted and unique")


def _validate_dates(values, field_name):
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if any(not isinstance(value, date) for value in values):
        raise TypeError(f"{field_name} contains an invalid date")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _validate_existing_stages(existing_obligations):
    stages = tuple(item.payment_stage for item in existing_obligations)
    allowed = {PaymentStage.DEPOSIT, PaymentStage.FIRST, PaymentStage.SECOND}
    if any(stage not in allowed for stage in stages):
        raise ValueError("invalid client stage obligation")
    if len(stages) != len(set(stages)):
        raise ValueError("duplicate client stage obligation")


def _validate_exact_history(existing):
    if existing.net_settled_amount != existing.contracted_amount:
        raise ValueError("formal client obligation history must be exactly settled")


def _stage_is_unchanged(stage_plan, existing):
    return (
        stage_plan.amount == existing.contracted_amount
        and stage_plan.due_date == existing.due_date
    )


def _base_obligation_identity(case_no, payment_stage):
    return f"client-obligation:{case_no}:{payment_stage.value}"


def _difference_identity(change_identity, payment_stage, action):
    return f"client-{action.value}:{change_identity}:{payment_stage.value}"


def abs_money(value: MoneyNTD) -> MoneyNTD:
    return MoneyNTD(abs(value.amount))


def _date_text(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _require_date(value, field_name):
    if not isinstance(value, date):
        raise TypeError(f"{field_name} must be a date")


def _require_positive_money(value, field_name):
    if not isinstance(value, MoneyNTD) or value.amount <= 0:
        raise ValueError(f"{field_name} must be positive MoneyNTD")


def _require_nonnegative_money(value, field_name):
    if not isinstance(value, MoneyNTD) or value.amount < 0:
        raise ValueError(f"{field_name} must be nonnegative MoneyNTD")


def _validate_identity(value, field_name):
    require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)

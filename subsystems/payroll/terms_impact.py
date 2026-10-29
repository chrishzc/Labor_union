"""
File: terms_impact.py
Description: 建立條款異動的薪資影響，並表達未排班案件的零寫入候選。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum

from domains.orders.terms import OrderTerms
from domains.payroll.calculation import (
    AssignmentRateSnapshot,
    CasePayrollCandidate,
    OfficialAssignmentServiceFacts,
    PayrollAdjustment,
    PayrollPolicyKind,
    PayrollTerms,
    build_case_payroll_candidate,
    rate_snapshot,
)
from domains.payroll.tiered_rates import TieredPayrollRate
from domains.scheduling.generation import SchedulingGenerationCandidate
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class StaffObligationKind(StrEnum):
    SERVICE_PAY = "service_pay"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"


class StaffObligationDirection(StrEnum):
    PAYABLE_TO_STAFF = "payable_to_staff"
    RECEIVABLE_FROM_STAFF = "receivable_from_staff"


class PayrollTermsActionKind(StrEnum):
    ESTABLISH = "establish"
    CLOSE_UNPAID = "close_unpaid"
    APPEND_FROZEN_DIFFERENCE = "append_frozen_difference"
    KEEP_FROZEN = "keep_frozen"


@dataclass(frozen=True, slots=True)
class SourceAssignmentPayrollTerms:
    source_assignment_id: int
    staff_id: int
    policy_version: str
    policy_kind: PayrollPolicyKind
    double_pay_dates: tuple[date, ...] = ()
    adjustment_total: MoneyNTD = MoneyNTD(0)
    ancestor_assignment_ids: tuple[int, ...] = ()
    hourly_rate: MoneyNTD | None = None
    tiered: TieredPayrollRate | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.source_assignment_id, "source assignment id")
        require_positive_integer(self.staff_id, "staff id")
        require_canonical_text(self.policy_version, "payroll policy version", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.adjustment_total, MoneyNTD):
            raise TypeError("payroll adjustment total must be MoneyNTD")
        _validate_dates(self.double_pay_dates, "double-pay dates")


@dataclass(frozen=True, slots=True)
class CasePayrollPolicyTerms:
    policy_version: str
    policy_kind: PayrollPolicyKind
    hourly_rate: MoneyNTD | None = None
    tiered: TieredPayrollRate | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.policy_version, "payroll policy version", _IDENTITY_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class ExistingStaffObligationTermsFact:
    obligation_identity: str
    source_assignment_id: int
    staff_id: int
    obligation_kind: StaffObligationKind
    direction: StaffObligationDirection
    contractual_amount: MoneyNTD
    outstanding_amount: MoneyNTD
    paid_net_amount: MoneyNTD
    payout_history_exists: bool
    due_date: date | None
    source_obligation_identity: str | None = None
    historically_settled: bool = False

    def __post_init__(self) -> None:
        require_canonical_text(self.obligation_identity, "staff obligation identity", _IDENTITY_MAXIMUM_LENGTH)
        require_positive_integer(self.source_assignment_id, "source assignment id")
        require_positive_integer(self.staff_id, "staff id")
        _require_nonnegative_money(self.contractual_amount, "contractual amount")
        _require_nonnegative_money(self.outstanding_amount, "outstanding amount")
        _require_nonnegative_money(self.paid_net_amount, "paid net amount")
        _validate_existing_obligation_state(self)


@dataclass(frozen=True, slots=True)
class PayrollTermsSourceFacts:
    case_no: str
    payroll_version: int
    source_terms: tuple[SourceAssignmentPayrollTerms, ...]
    existing_obligations: tuple[ExistingStaffObligationTermsFact, ...]
    staff_payment_due_date: date | None
    case_policy: CasePayrollPolicyTerms | None = None
    recovery_balances: tuple["PayrollRecoveryBalance", ...] = ()

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _IDENTITY_MAXIMUM_LENGTH)
        require_nonnegative_integer(self.payroll_version, "payroll version")
        if self.case_policy is not None and not isinstance(self.case_policy, CasePayrollPolicyTerms):
            raise TypeError("case payroll policy is invalid")


@dataclass(frozen=True, slots=True)
class PayrollRecoveryBalance:
    staff_id: int
    remaining_amount: MoneyNTD


@dataclass(frozen=True, slots=True)
class PayrollTermsImpactFacts:
    case_no: str
    payroll_version: int
    scheduling: SchedulingGenerationCandidate
    payroll_terms: PayrollTerms
    source_terms: tuple[SourceAssignmentPayrollTerms, ...]
    existing_obligations: tuple[ExistingStaffObligationTermsFact, ...]
    staff_payment_due_date: date | None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", _IDENTITY_MAXIMUM_LENGTH)
        require_nonnegative_integer(self.payroll_version, "payroll version")
        if self.case_no != self.scheduling.case_no:
            raise ValueError("Payroll and Scheduling case numbers must match")


@dataclass(frozen=True, slots=True)
class PayrollTermsAction:
    action: PayrollTermsActionKind
    obligation_identity: str
    source_obligation_identity: str | None
    source_assignment_id: int | None
    candidate_assignment_key: str | None
    staff_id: int
    obligation_kind: StaffObligationKind
    direction: StaffObligationDirection
    amount: MoneyNTD
    due_date: date | None


@dataclass(frozen=True, slots=True)
class PayrollSpecialPayEventCandidate:
    assignment_identity: str
    assignment_sequence: int
    service_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        require_canonical_text(
            self.assignment_identity,
            "special-pay assignment identity",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        require_positive_integer(
            self.assignment_sequence,
            "special-pay assignment sequence",
        )
        _validate_dates(self.service_dates, "special-pay service dates")


@dataclass(frozen=True, slots=True)
class PayrollFrozenSettlement:
    obligation_identity: str
    correction_identity: str | None
    staff_id: int
    previous_entitlement: MoneyNTD
    revised_entitlement: MoneyNTD
    paid_net_amount: MoneyNTD
    recovery_increase: MoneyNTD


@dataclass(frozen=True, slots=True)
class PayrollTermsImpactCandidate:
    case_no: str
    expected_payroll_version: int
    resulting_payroll_version: int
    payroll: CasePayrollCandidate
    carried_rate_snapshots: tuple[AssignmentRateSnapshot, ...]
    actions: tuple[PayrollTermsAction, ...]
    blockers: tuple[str, ...]
    fingerprint: PreviewFingerprint
    special_pay_events: tuple[PayrollSpecialPayEventCandidate, ...] = ()
    frozen_settlements: tuple[PayrollFrozenSettlement, ...] = ()
    rate_source_assignments: tuple[tuple[str, int | None], ...] = ()


def build_payroll_terms_impact_candidate(facts: PayrollTermsImpactFacts, change_identity: str) -> PayrollTermsImpactCandidate:
    require_canonical_text(change_identity, "change identity", _IDENTITY_MAXIMUM_LENGTH)
    payroll, rates = _calculate_payroll(facts)
    if _has_handover_corrections(facts):
        return _handover_candidate(facts, payroll, rates, change_identity)
    return _candidate(facts, payroll, rates, _build_actions(facts, payroll, change_identity))


def build_payroll_terms_impact(source_facts: PayrollTermsSourceFacts, scheduling: SchedulingGenerationCandidate, order_terms: OrderTerms, change_identity: str) -> PayrollTermsImpactCandidate:
    facts = _impact_facts(source_facts, scheduling, order_terms)
    return build_payroll_terms_impact_candidate(facts, change_identity)


def build_payroll_rate_correction_impact(source_facts: PayrollTermsSourceFacts, scheduling: SchedulingGenerationCandidate, order_terms: OrderTerms, change_identity: str) -> PayrollTermsImpactCandidate:
    """Rebuild unpaid obligations without replacing their Scheduling identities."""
    require_canonical_text(change_identity, "change identity", _IDENTITY_MAXIMUM_LENGTH)
    facts = _impact_facts(source_facts, scheduling, order_terms)
    payroll, rates = _calculate_payroll(facts)
    # An unchanged assignment/generation can be corrected more than once.
    # Each replacement obligation belongs to its immutable correction event.
    actions = tuple(
        replace(action, obligation_identity=_obligation_identity(
            change_identity, facts.case_no, action.candidate_assignment_key
        )) if action.action is PayrollTermsActionKind.ESTABLISH else action
        for action in _build_actions(facts, payroll, change_identity)
    )
    return _candidate(facts, payroll, rates, actions)


def build_preassignment_payroll_noop(
    source_facts: PayrollTermsSourceFacts,
    scheduling: SchedulingGenerationCandidate,
    order_terms: OrderTerms,
    change_identity: str,
) -> PayrollTermsImpactCandidate:
    require_canonical_text(change_identity, "change identity", _IDENTITY_MAXIMUM_LENGTH)
    if source_facts.case_no != scheduling.case_no or scheduling.assignments:
        raise ValueError("preassignment_payroll_facts_conflict")
    if source_facts.source_terms:
        raise ValueError("preassignment_source_assignment_conflict")
    if source_facts.existing_obligations:
        raise ValueError("preassignment_payroll_obligation_conflict")
    terms = _payroll_terms(order_terms)
    payroll = build_case_payroll_candidate((), (), terms)
    return PayrollTermsImpactCandidate(
        source_facts.case_no,
        source_facts.payroll_version,
        source_facts.payroll_version,
        payroll,
        (),
        (),
        (),
        fingerprint_payload(
            {
                "mode": "preassignment_noop",
                "case_no": source_facts.case_no,
                "payroll_version": source_facts.payroll_version,
                "terms": order_terms.canonical_payload(),
                "scheduling_generation": scheduling.generation_number,
                "payroll": payroll.fingerprint.value,
            }
        ),
    )


def build_payroll_cancellation_impact(source_facts: PayrollTermsSourceFacts, scheduling: SchedulingGenerationCandidate, order_terms: OrderTerms, change_identity: str) -> PayrollTermsImpactCandidate:
    if _has_handover_corrections(source_facts):
        return build_payroll_handover_impact(source_facts, scheduling, order_terms, change_identity)
    facts = _impact_facts(source_facts, scheduling, order_terms)
    payroll, rates = _calculate_cancellation_payroll(facts, source_facts.case_policy)
    return _candidate(facts, payroll, rates, _build_cancellation_actions(facts, payroll, change_identity))


def calculate_assignment_payroll(source_facts, scheduling, order_terms):
    """Read-only owner calculation for a before/after service arrangement."""
    facts = _impact_facts(source_facts, scheduling, order_terms)
    payroll, _ = _calculate_cancellation_payroll(facts, source_facts.case_policy)
    return payroll


def build_payroll_handover_impact(source_facts, scheduling, order_terms, change_identity):
    """Preserve paid roots and append only the change in legal entitlement.

    Corrections belong to the original obligation, across Scheduling generations.
    Staff Payables projects that root with these corrections; they are never a
    second independently payable bill.
    """
    facts = _impact_facts(source_facts, scheduling, order_terms)
    payroll, rates = _calculate_cancellation_payroll(facts, source_facts.case_policy, candidate_special_pay=True)
    return _handover_candidate(facts, payroll, rates, change_identity)


def _has_handover_corrections(facts):
    return any(item.obligation_identity.startswith("staff-handover:") for item in facts.existing_obligations)


def _handover_candidate(facts, payroll, rates, change_identity):
    if any(item.paid_net_amount.amount > 0 and not item.payout_history_exists for item in facts.existing_obligations):
        raise ValueError("handover_paid_history_review_required")
    if any(item.total_payable.amount < 0 for item in payroll.assignments):
        raise ValueError("handover_adjustment_review_required")
    if any(item.historically_settled for item in facts.existing_obligations):
        raise ValueError("handover_historical_payment_review_required")
    roots = _service_obligations_by_source(facts)
    by_source = {item.source_assignment_id: item for item in facts.source_terms}
    children = {}
    for obligation in facts.existing_obligations:
        if obligation.obligation_kind is not StaffObligationKind.SERVICE_PAY:
            children.setdefault(obligation.source_obligation_identity, []).append(obligation)
    if children.get(None):
        raise ValueError("handover_obligation_lineage_ambiguous")
    actions, settlements, retained = [], [], set()
    for assignment in payroll.assignments:
        segment = _scheduling_assignment(facts, assignment)
        source = by_source.get(segment.source_assignment_id)
        ancestry = (segment.source_assignment_id,) + (source.ancestor_assignment_ids if source else ())
        matches = [root for root in roots.values()
                   if source is not None and source.staff_id == assignment.staff_id
                   and root.source_assignment_id in ancestry and root.staff_id == assignment.staff_id]
        if len(matches) > 1:
            raise ValueError("handover_obligation_lineage_ambiguous")
        if not matches:
            actions.append(_establish_action(facts, assignment, segment.source_assignment_id))
            continue
        root = matches[0]
        if root.obligation_identity in retained:
            raise ValueError("handover_obligation_lineage_ambiguous")
        retained.add(root.obligation_identity)
        _handover_root_actions(facts, root, assignment.total_payable, assignment.assignment_identity,
                               children.get(root.obligation_identity, ()), change_identity, actions, settlements)
    for root in roots.values():
        if root.obligation_identity not in retained:
            _handover_root_actions(facts, root, MoneyNTD(0), None,
                                   children.get(root.obligation_identity, ()), change_identity, actions, settlements)
    candidate = _candidate(facts, payroll, rates, tuple(actions))
    return replace(candidate, frozen_settlements=tuple(settlements), fingerprint=fingerprint_payload({
        "payroll": candidate.fingerprint.value,
        "settlements": tuple((item.obligation_identity, item.previous_entitlement.amount,
                              item.revised_entitlement.amount, item.paid_net_amount.amount,
                              item.recovery_increase.amount) for item in settlements),
    }))


def _handover_root_actions(facts, root, total, key, children, change_identity, actions, settlements):
    # Unpaid adjustment projections can be rebuilt; immutable allocations stay
    # with their original caregiver. A paid independent correction needs review.
    corrections = [item for item in children if item.obligation_identity.startswith("staff-handover:")]
    independent = [item for item in children if item not in corrections]
    if any(not item.obligation_identity.startswith("staff-obligation:adjustment:") for item in independent):
        raise ValueError("handover_obligation_lineage_ambiguous")
    if any(item.payout_history_exists for item in independent):
        raise ValueError("handover_paid_adjustment_review_required")
    actions.extend(_close_unpaid_action(item) for item in independent)
    if not root.payout_history_exists:
        if corrections:
            raise ValueError("handover_obligation_lineage_ambiguous")
        actions.append(_close_unpaid_action(root))
        if key is not None:
            actions.append(PayrollTermsAction(
                PayrollTermsActionKind.ESTABLISH, _obligation_identity("service", facts.case_no, key),
                None, root.source_assignment_id, key, root.staff_id, StaffObligationKind.SERVICE_PAY,
                StaffObligationDirection.PAYABLE_TO_STAFF, total, root.due_date,
            ))
        return
    previous = root.contractual_amount.amount + sum(
        item.contractual_amount.amount * (1 if item.direction is StaffObligationDirection.PAYABLE_TO_STAFF else -1)
        for item in corrections
    )
    if previous < 0 or any(item.payout_history_exists for item in corrections):
        raise ValueError("handover_obligation_lineage_ambiguous")
    recovery_delta = max(0, root.paid_net_amount.amount - total.amount) - max(0, root.paid_net_amount.amount - previous)
    if recovery_delta < 0:
        raise ValueError("handover_recovery_adjustment_required")
    delta = total.amount - previous
    identity = None
    if delta:
        identity = "staff-handover:" + fingerprint_payload({
            "case": facts.case_no, "change": change_identity, "root": root.obligation_identity,
        }).value
        actions.append(PayrollTermsAction(
            PayrollTermsActionKind.APPEND_FROZEN_DIFFERENCE, identity, root.obligation_identity,
            root.source_assignment_id, key, root.staff_id,
            StaffObligationKind.ADJUSTMENT if delta > 0 else StaffObligationKind.REVERSAL,
            StaffObligationDirection.PAYABLE_TO_STAFF if delta > 0 else StaffObligationDirection.RECEIVABLE_FROM_STAFF,
            MoneyNTD(abs(delta)), root.due_date,
        ))
    settlements.append(PayrollFrozenSettlement(root.obligation_identity, identity, root.staff_id,
        MoneyNTD(previous), total, root.paid_net_amount, MoneyNTD(recovery_delta)))


def _impact_facts(source, scheduling, order_terms):
    return PayrollTermsImpactFacts(source.case_no, source.payroll_version, scheduling, _payroll_terms(order_terms), source.source_terms, source.existing_obligations, source.staff_payment_due_date)


def _payroll_terms(order_terms: OrderTerms) -> PayrollTerms:
    service_hours = order_terms.service_hours_per_day
    if isinstance(service_hours, float):
        service_hours = Decimal(str(service_hours))
    return PayrollTerms(
        order_terms.service_days,
        service_hours,
        order_terms.floor_fee,
    )


def _calculate_payroll(facts):
    terms = _source_terms_by_assignment(facts)
    service_facts = _service_facts(facts, terms)
    rates = _carried_rate_snapshots(facts, terms)
    return build_case_payroll_candidate(service_facts, rates, facts.payroll_terms, _carried_adjustments(facts, terms)), rates


def _calculate_cancellation_payroll(facts, case_policy, *, candidate_special_pay=False):
    policies = _cancellation_policies(facts, case_policy)
    service_facts = _cancellation_service_facts(facts, policies, candidate_special_pay=candidate_special_pay)
    rates = _cancellation_rate_snapshots(facts, policies)
    return build_case_payroll_candidate(service_facts, rates, facts.payroll_terms, _cancellation_adjustments(facts, policies)), rates


def _source_terms_by_assignment(facts):
    result = {item.source_assignment_id: item for item in facts.source_terms}
    if len(result) != len(facts.source_terms):
        raise ValueError("invalid_payroll_facts")
    expected = {item.source_assignment_id for item in facts.scheduling.assignments}
    if set(result) != expected:
        raise ValueError("payroll_rate_policy_not_found")
    return result


def _service_facts(facts, source_terms):
    return tuple(OfficialAssignmentServiceFacts(item.candidate_key, item.staff_id, item.service_dates, _candidate_double_pay_dates(item, source_terms)) for item in facts.scheduling.assignments)


def _candidate_double_pay_dates(assignment, source_terms):
    return tuple(value for value in source_terms[assignment.source_assignment_id].double_pay_dates if value in assignment.service_dates)


def _carried_rate_snapshots(facts, source_terms):
    return tuple(_exact_rate(item.candidate_key, source_terms[item.source_assignment_id]) for item in facts.scheduling.assignments)


def _exact_rate(identity, policy):
    return (AssignmentRateSnapshot(identity, policy.policy_version, policy.policy_kind, policy.hourly_rate, policy.tiered)
            if policy.hourly_rate is not None else rate_snapshot(identity, policy.policy_version, policy.policy_kind))


def _carried_adjustments(facts, source_terms):
    return tuple(PayrollAdjustment(item.candidate_key, source_terms[item.source_assignment_id].adjustment_total) for item in facts.scheduling.assignments if not source_terms[item.source_assignment_id].adjustment_total.is_zero)


def _unanimous_case_policy(source_terms):
    policies = {(item.policy_version, item.policy_kind) for item in source_terms}
    if len(policies) != 1:
        return None
    return CasePayrollPolicyTerms(*policies.pop())


def _cancellation_policies(facts, case_policy):
    source_by_id = {item.source_assignment_id: item for item in facts.source_terms}
    fallback = case_policy or _unanimous_case_policy(facts.source_terms)
    policies = {}
    for assignment in facts.scheduling.assignments:
        policy = source_by_id.get(assignment.source_assignment_id) or fallback
        if policy is None:
            raise ValueError("payroll_rate_policy_not_found")
        policies[assignment.candidate_key] = policy
    return policies


def _cancellation_service_facts(facts, policies, *, candidate_special_pay=False):
    return tuple(OfficialAssignmentServiceFacts(item.candidate_key, item.staff_id, item.service_dates,
        item.double_pay_dates if candidate_special_pay else _cancellation_double_pay_dates(item, policies))
        for item in facts.scheduling.assignments)


def _cancellation_double_pay_dates(assignment, policies):
    policy = policies[assignment.candidate_key]
    return tuple(value for value in getattr(policy, "double_pay_dates", ()) if value in assignment.service_dates)


def _cancellation_rate_snapshots(facts, policies):
    return tuple(_exact_rate(item.candidate_key, policies[item.candidate_key]) for item in facts.scheduling.assignments)


def _cancellation_adjustments(facts, policies):
    adjustments = []
    for source in facts.source_terms:
        if source.adjustment_total.is_zero:
            continue
        owners = tuple(item for item in facts.scheduling.assignments
                       if item.source_assignment_id == source.source_assignment_id and item.staff_id == source.staff_id)
        if len(owners) != 1:
            raise ValueError("payroll_adjustment_owner_ambiguous")
        adjustments.append(PayrollAdjustment(owners[0].candidate_key, source.adjustment_total))
    return tuple(adjustments)


def _build_actions(facts, payroll, change_identity):
    return _actions_for_payroll(facts, payroll, change_identity)


def _build_cancellation_actions(facts, payroll, change_identity):
    return _actions_for_payroll(facts, payroll, change_identity)


def _actions_for_payroll(facts, payroll, change_identity):
    if _has_handover_corrections(facts):
        raise ValueError("payroll_handover_settlement_required")
    existing = _service_obligations_by_source(facts)
    actions = []
    retained = set()
    for assignment in payroll.assignments:
        scheduling = _scheduling_assignment(facts, assignment)
        source_id = scheduling.source_assignment_id
        previous = _matching_existing_obligation(existing, source_id, assignment.staff_id)
        if previous is not None:
            retained.add(source_id)
        actions.extend(_assignment_actions(facts, assignment, source_id, previous, change_identity))
    for source_id in sorted(set(existing) - retained):
        actions.extend(_removed_assignment_actions(facts, existing[source_id], change_identity))
    return tuple(actions)


def _service_obligations_by_source(facts):
    values = tuple(item for item in facts.existing_obligations if item.obligation_kind is StaffObligationKind.SERVICE_PAY)
    result = {item.source_assignment_id: item for item in values}
    if len(result) != len(values):
        raise ValueError("invalid_payroll_facts")
    return result


def _scheduling_assignment(facts, payroll_assignment):
    return next(item for item in facts.scheduling.assignments if item.candidate_key == payroll_assignment.assignment_identity)


def _matching_existing_obligation(existing, source_id, staff_id):
    previous = existing.get(source_id) if source_id is not None else None
    return previous if previous is not None and previous.staff_id == staff_id else None


def _assignment_actions(facts, assignment, source_id, existing, change_identity):
    if existing is None:
        return (_establish_action(facts, assignment, source_id),)
    if existing.payout_history_exists:
        return (_frozen_action(facts, assignment, source_id, existing, change_identity),)
    return (_close_unpaid_action(existing), _establish_action(facts, assignment, source_id))


def _removed_assignment_actions(facts, existing, change_identity):
    if not existing.payout_history_exists:
        return (_close_unpaid_action(existing),)
    return (_removed_frozen_reversal(facts, existing, change_identity),)


def _establish_action(facts, assignment, source_assignment_id):
    return PayrollTermsAction(PayrollTermsActionKind.ESTABLISH, _obligation_identity("service", facts.case_no, assignment.assignment_identity), None, source_assignment_id, assignment.assignment_identity, assignment.staff_id, StaffObligationKind.SERVICE_PAY, StaffObligationDirection.PAYABLE_TO_STAFF, assignment.total_payable, facts.staff_payment_due_date)


def _close_unpaid_action(existing):
    return PayrollTermsAction(PayrollTermsActionKind.CLOSE_UNPAID, existing.obligation_identity, None, existing.source_assignment_id, None, existing.staff_id, existing.obligation_kind, existing.direction, existing.outstanding_amount, existing.due_date)


def _frozen_action(facts, assignment, source_assignment_id, existing, change_identity):
    difference = assignment.total_payable - existing.paid_net_amount
    if difference.is_zero:
        return _keep_frozen_action(existing, assignment.assignment_identity)
    return _frozen_difference_action(facts, assignment, source_assignment_id, existing, change_identity, difference)


def _keep_frozen_action(existing, candidate_key):
    return PayrollTermsAction(PayrollTermsActionKind.KEEP_FROZEN, existing.obligation_identity, existing.obligation_identity, existing.source_assignment_id, candidate_key, existing.staff_id, existing.obligation_kind, existing.direction, existing.contractual_amount, existing.due_date)


def _frozen_difference_action(facts, assignment, source_assignment_id, existing, change_identity, difference):
    kind = StaffObligationKind.ADJUSTMENT if difference.amount > 0 else StaffObligationKind.REVERSAL
    direction = StaffObligationDirection.PAYABLE_TO_STAFF if difference.amount > 0 else StaffObligationDirection.RECEIVABLE_FROM_STAFF
    return PayrollTermsAction(PayrollTermsActionKind.APPEND_FROZEN_DIFFERENCE, _obligation_identity(change_identity, facts.case_no, assignment.assignment_identity), existing.obligation_identity, source_assignment_id, assignment.assignment_identity, assignment.staff_id, kind, direction, MoneyNTD(abs(difference.amount)), existing.due_date)


def _removed_frozen_reversal(facts, existing, change_identity):
    return PayrollTermsAction(PayrollTermsActionKind.APPEND_FROZEN_DIFFERENCE, _obligation_identity(change_identity, facts.case_no, f"removed:{existing.source_assignment_id}"), existing.obligation_identity, existing.source_assignment_id, None, existing.staff_id, StaffObligationKind.REVERSAL, StaffObligationDirection.RECEIVABLE_FROM_STAFF, existing.paid_net_amount, existing.due_date)


def _candidate(facts, payroll, rate_snapshots, actions):
    special_pay_events = tuple(
        PayrollSpecialPayEventCandidate(
            item.candidate_key,
            item.sequence,
            item.double_pay_dates,
        )
        for item in facts.scheduling.assignments
        if item.double_pay_dates
    )
    payload = {
        "case_no": facts.case_no,
        "payroll_version": facts.payroll_version,
        "payroll_fingerprint": payroll.fingerprint.value,
        "rates": tuple(_rate_payload(item) for item in rate_snapshots),
        "rate_sources": tuple((item.candidate_key, getattr(item, "source_assignment_id", None))
                              for item in facts.scheduling.assignments),
        "actions": tuple(_action_payload(item) for item in actions),
        "special_pay_events": tuple(
            {
                "assignment_identity": item.assignment_identity,
                "assignment_sequence": item.assignment_sequence,
                "service_dates": tuple(value.isoformat() for value in item.service_dates),
            }
            for item in special_pay_events
        ),
    }
    return PayrollTermsImpactCandidate(
        facts.case_no,
        facts.payroll_version,
        facts.payroll_version + 1,
        payroll,
        rate_snapshots,
        actions,
        (),
        fingerprint_payload(payload),
        special_pay_events,
        rate_source_assignments=tuple((item.candidate_key, getattr(item, "source_assignment_id", None))
                                      for item in facts.scheduling.assignments),
    )


def _rate_payload(item):
    return {"assignment_identity": item.assignment_identity, "policy_version": item.policy_version, "policy_kind": item.policy_kind.value, "hourly_rate_ntd": item.hourly_rate.amount}


def _action_payload(item):
    return {"action": item.action.value, "obligation_identity": item.obligation_identity, "source_obligation_identity": item.source_obligation_identity, "source_assignment_id": item.source_assignment_id, "candidate_assignment_key": item.candidate_assignment_key, "staff_id": item.staff_id, "obligation_kind": item.obligation_kind.value, "direction": item.direction.value, "amount_ntd": item.amount.amount, "due_date": item.due_date.isoformat() if item.due_date else None}


def _obligation_identity(change_identity, case_no, candidate_key):
    return "staff-obligation:" + fingerprint_payload({"change_identity": change_identity, "case_no": case_no, "candidate_key": candidate_key}).value


def _validate_dates(values, field_name):
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if any(not isinstance(value, date) for value in values):
        raise TypeError(f"{field_name} contains an invalid date")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{field_name} must be sorted and unique")


def _require_nonnegative_money(value, field_name):
    if not isinstance(value, MoneyNTD):
        raise TypeError(f"{field_name} must be MoneyNTD")
    require_nonnegative_integer(value.amount, field_name)


def _validate_existing_obligation_state(item):
    if not isinstance(item.payout_history_exists, bool):
        raise TypeError("payout history exists must be bool")

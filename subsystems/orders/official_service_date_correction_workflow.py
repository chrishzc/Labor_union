"""Auditable correction of effective, already performed service dates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Callable, Literal, Protocol

from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from domains.payroll.installments import PayrollInstallment, payroll_installments
from domains.payroll.tiered_rates import funding_due_date
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.terms_workflow import SchedulingReplacementCommand
from subsystems.payroll.terms_impact import PayrollTermsImpactCandidate, build_payroll_handover_impact


@dataclass(frozen=True, slots=True)
class OfficialAssignmentDates:
    assignment_id: int
    staff_id: int
    sequence: int
    status: str
    service_dates: tuple[date, ...]
    staff_name: str = ""
    double_pay_dates: tuple[date, ...] = ()


MonetaryBlocker = Literal[
    "payroll_adjustments", "subsidy_return",
    "source_rate_snapshot_missing_or_ambiguous", "floor_fee",
]


class OfficialDateMonetaryImpactBlocked(ValueError):
    def __init__(self, blockers: tuple[MonetaryBlocker, ...]) -> None:
        super().__init__("official_date_monetary_impact_unsupported")
        self.blockers = blockers


class OfficialDateOccupancyConflict(ValueError):
    def __init__(self, staff_name: str, day: date) -> None:
        super().__init__("official_date_occupancy_conflict")
        self.staff_name = staff_name
        self.day = day


@dataclass(frozen=True, slots=True)
class OfficialDateHistoryRecord:
    event_id: int
    event_type: Literal["original_completion", "service_date_corrected"]
    recorded_at: datetime
    actor: str
    before_dates: tuple[date, ...]
    after_dates: tuple[date, ...]
    reason: str | None = None
    completion_instant: datetime | None = None


@dataclass(frozen=True, slots=True)
class OfficialDateFacts:
    case_no: str
    order_version: int
    order_status: str
    actual_start_date: date | None
    actual_end_date: date | None
    service_data_locked: bool
    service_days: int
    hours_per_day: float
    scheduling_version: int
    generation_id: int
    generation_number: int
    assignments: tuple[OfficialAssignmentDates, ...]
    monetary_change_blocker: bool = False
    client_finance_version: int | None = None
    payroll_version: int | None = None
    monetary_blockers: tuple[MonetaryBlocker, ...] = ()
    history: tuple[OfficialDateHistoryRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class OfficialDateSelection:
    assignment_id: int
    service_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class OfficialDatePreview:
    facts: OfficialDateFacts
    selections: tuple[OfficialDateSelection, ...]
    fingerprint: PreviewFingerprint
    finance_impact: str = "no_op"
    payroll_impact: str = "no_op"


@dataclass(frozen=True, slots=True)
class OfficialDateReceipt:
    case_no: str
    order_version: int
    scheduling_version: int
    generation_id: int
    effective_dates: tuple[OfficialDateSelection, ...]
    preview_fingerprint: PreviewFingerprint
    funding_review_pending: bool = False


@dataclass(frozen=True, slots=True)
class ServiceAttributionChange:
    source_assignment_id: int
    staff_id: int
    service_dates: tuple[date, ...]
    evidence: str
    replacement_dates: tuple[date, ...] = ()
    scope: Literal["served", "upcoming"] = "served"


@dataclass(frozen=True, slots=True)
class ServiceAttributionPreview:
    facts: OfficialDateFacts
    scheduling: SchedulingGenerationCandidate
    payroll: PayrollTermsImpactCandidate
    fingerprint: PreviewFingerprint
    evidence: str
    manual_amounts: tuple[tuple[str, int, int, int], ...] = ()
    funding: tuple[tuple[int, str, int, int | None, int | None], ...] = ()
    funding_review_staff: tuple[int, ...] = ()
    funding_review_roots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AttributionFundingSource:
    identity: str
    staff_id: int
    assignment_id: int | None
    kind: str
    amount: int
    settled: int | None
    due_date: date | None
    previous_recovery: int = 0


@dataclass(frozen=True, slots=True)
class AttributionFundingFacts:
    sources: tuple[AttributionFundingSource, ...] = ()
    pending_staff: tuple[int, ...] = ()
    pending_event_id: int | None = None
    paid_amount_controls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AttributionFundingChange:
    assignment_id: int
    subsidy_ntd: int


@dataclass(frozen=True, slots=True)
class AttributionFundingPlan:
    identity: str
    staff_id: int
    installments: tuple[PayrollInstallment, ...]
    revised: tuple[tuple[str, int, int], ...]
    recovery: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class AttributionFundingReview:
    facts: OfficialDateFacts
    accounting: AttributionFundingFacts
    payroll: PayrollTermsImpactCandidate
    manual_amounts: tuple[tuple[str, int, int, int], ...]
    fingerprint: PreviewFingerprint
    plan: tuple[AttributionFundingPlan, ...] = ()
    evidence: str = ""


def _attribution_family(status: str) -> str:
    return "orders_completed_service_attribution" if status == "訂單完成" else "orders_service_attribution"


class OfficialDateRepository(Protocol):
    def load(self, case_no: str, *, lock: bool = False) -> OfficialDateFacts: ...
    def load_history(self, case_no: str) -> tuple[OfficialDateHistoryRecord, ...]: ...
    def validate_availability(self, candidate: SchedulingGenerationCandidate, *, lock: bool) -> None: ...
    def replay(self, key: str, command_fingerprint: str, *, lock: bool = False) -> OfficialDateReceipt | None: ...
    def replace_and_record(self, command: SchedulingReplacementCommand, preview: OfficialDatePreview) -> OfficialDateReceipt: ...
    def load_attribution(self, case_no: str, change: ServiceAttributionChange, *, lock: bool): ...
    def replay_attribution(self, key: str, command_fingerprint: str, *, lock: bool = False) -> OfficialDateReceipt | None: ...
    def persist_attribution(self, command: SchedulingReplacementCommand, preview: ServiceAttributionPreview) -> OfficialDateReceipt: ...
    def load_funding_review(self, case_no: str, *, lock: bool): ...
    def replay_funding_review(self, case_no: str, key: str, digest: str, *, lock: bool = False): ...
    def persist_funding_review(self, review: AttributionFundingReview, *, actor: ActorContext, key: IdempotencyKey,
                               correlation: CorrelationId, digest: str) -> None: ...


class UnitOfWork(Protocol):
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exception_type, exception, traceback) -> bool: ...
    def commit(self) -> None: ...


class OfficialServiceDateCorrectionWorkflow:
    def __init__(self, repository: OfficialDateRepository, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work

    def query(self, case_no: str) -> OfficialDateFacts:
        return replace(self._repository.load(case_no), history=self._repository.load_history(case_no))

    def preview_attribution(self, case_no: str, change: ServiceAttributionChange) -> ServiceAttributionPreview:
        return self._prepare_attribution(case_no, change, lock=False)

    def apply_attribution(self, case_no: str, change: ServiceAttributionChange, *,
                          expected_order_version: int, expected_scheduling_version: int,
                          preview_fingerprint: str, actor: str, reason: str,
                          idempotency_key: str, correlation_id: str,
                          adopt_calculated_amounts: bool = False) -> OfficialDateReceipt:
        if not reason.strip():
            raise ValueError("service_attribution_reason_required")
        command_fingerprint = fingerprint_payload({
            "case_no": case_no, "source_assignment_id": change.source_assignment_id,
            "staff_id": change.staff_id, "dates": tuple(day.isoformat() for day in change.service_dates),
            **({"replacement_dates": tuple(day.isoformat() for day in change.replacement_dates), "scope": change.scope}
               if change.replacement_dates or change.scope != "served" else {}),
            **({"adopt_calculated_amounts": True} if adopt_calculated_amounts else {}),
            "evidence": change.evidence.strip(), "reason": reason.strip(), "actor": actor,
            "order_version": expected_order_version, "scheduling_version": expected_scheduling_version,
            "preview": preview_fingerprint,
        })
        replay = self._repository.replay_attribution(idempotency_key, command_fingerprint.value)
        if replay is not None:
            return replay
        with self._unit_of_work() as unit_of_work:
            facts, terms, payable_versions, manual_amounts, funding = self._repository.load_attribution(case_no, change, lock=True)
            replay = self._repository.replay_attribution(idempotency_key, command_fingerprint.value, lock=True)
            if replay is not None:
                return replay
            if (facts.order_version, facts.scheduling_version) != (expected_order_version, expected_scheduling_version):
                raise ValueError("official_date_version_conflict")
            preview = _attribution_preview(facts, terms, payable_versions, change, manual_amounts, funding)
            if preview.fingerprint.value != preview_fingerprint:
                raise ValueError("official_date_preview_stale")
            if preview.manual_amounts and not preview.funding_review_staff and not adopt_calculated_amounts:
                raise ValueError("service_attribution_manual_amount_confirmation_required")
            self._repository.validate_availability(preview.scheduling, lock=True)
            command = SchedulingReplacementCommand(
                preview.scheduling, _attribution_family(facts.order_status), facts.order_version,
                command_fingerprint, preview.fingerprint, IdempotencyKey(idempotency_key),
                ActorContext(actor), reason.strip(), CorrelationId(correlation_id),
                preserve_leave_occupancy=True,
            )
            receipt = self._repository.persist_attribution(command, preview)
            unit_of_work.commit()
            return receipt

    def _prepare_attribution(self, case_no, change, *, lock):
        facts, terms, payable_versions, manual_amounts, funding = self._repository.load_attribution(case_no, change, lock=lock)
        preview = _attribution_preview(facts, terms, payable_versions, change, manual_amounts, funding)
        self._repository.validate_availability(preview.scheduling, lock=lock)
        return preview

    def query_funding_review(self, case_no: str):
        loaded = self._repository.load_funding_review(case_no, lock=False)
        return _funding_review(*loaded) if loaded is not None else None

    def preview_funding_review(self, case_no: str, selections: tuple[AttributionFundingChange, ...], evidence: str):
        loaded = self._repository.load_funding_review(case_no, lock=False)
        if loaded is None:
            raise ValueError("service_attribution_funding_review_conflict")
        return _funding_review(*loaded, selections=selections, evidence=evidence)

    def apply_funding_review(self, case_no: str, selections: tuple[AttributionFundingChange, ...],
                             evidence: str, preview_fingerprint: str, *, actor: str, key: str, correlation: str):
        digest = fingerprint_payload({"case": case_no, "selections": _funding_selections(selections),
            "evidence": evidence.strip(), "preview": preview_fingerprint, "actor": actor}).value
        if self._repository.replay_funding_review(case_no, key, digest):
            return
        with self._unit_of_work() as unit_of_work:
            loaded = self._repository.load_funding_review(case_no, lock=True)
            if self._repository.replay_funding_review(case_no, key, digest, lock=True):
                return
            if loaded is None:
                raise ValueError("service_attribution_funding_review_conflict")
            review = _funding_review(*loaded, selections=selections, evidence=evidence)
            if review.fingerprint.value != preview_fingerprint:
                raise ValueError("official_date_preview_stale")
            self._repository.persist_funding_review(review, actor=ActorContext(actor), key=IdempotencyKey(key),
                correlation=CorrelationId(correlation), digest=digest)
            unit_of_work.commit()

    def preview(self, case_no: str, selections: tuple[OfficialDateSelection, ...]) -> OfficialDatePreview:
        facts = self._repository.load(case_no)
        preview = _preview(facts, selections)
        self._repository.validate_availability(_candidate(preview), lock=False)
        return preview

    def apply(self, case_no: str, selections: tuple[OfficialDateSelection, ...], *,
              expected_order_version: int, expected_scheduling_version: int,
              preview_fingerprint: str, actor: str, reason: str,
              idempotency_key: str, correlation_id: str) -> OfficialDateReceipt:
        command_fingerprint = fingerprint_payload({
            "case_no": case_no,
            "selections": _selection_payload(selections),
            "expected_order_version": expected_order_version,
            "expected_scheduling_version": expected_scheduling_version,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor,
            "reason": reason.strip(),
        })
        replay = self._repository.replay(idempotency_key, command_fingerprint.value)
        if replay is not None:
            return replay
        with self._unit_of_work() as unit_of_work:
            facts = self._repository.load(case_no, lock=True)
            replay = self._repository.replay(idempotency_key, command_fingerprint.value, lock=True)
            if replay is not None:
                return replay
            if (facts.order_version, facts.scheduling_version) != (
                expected_order_version, expected_scheduling_version
            ):
                raise ValueError("official_date_version_conflict")
            preview = _preview(facts, selections)
            if preview.fingerprint.value != preview_fingerprint:
                raise ValueError("official_date_preview_stale")
            candidate = _candidate(preview)
            self._repository.validate_availability(candidate, lock=True)
            command = SchedulingReplacementCommand(
                candidate=candidate,
                command_family="orders_official_service_date_correction",
                expected_order_version=facts.order_version,
                command_fingerprint=command_fingerprint,
                preview_fingerprint=preview.fingerprint,
                idempotency_key=IdempotencyKey(idempotency_key),
                actor=ActorContext(actor),
                reason=reason.strip(),
                correlation_id=CorrelationId(correlation_id),
            )
            receipt = self._repository.replace_and_record(command, preview)
            unit_of_work.commit()
            return receipt


def _attribution_preview(facts, terms, payable_versions, change, manual_amounts=(), funding=AttributionFundingFacts()):
    if facts.order_status not in {"訂單成立", "服務中", "訂單完成"} or facts.actual_start_date is None:
        raise ValueError("service_attribution_status_blocked")
    if not change.evidence.strip():
        raise ValueError("service_attribution_evidence_required")
    if facts.service_data_locked and facts.order_status != "訂單完成":
        raise ValueError("service_attribution_status_blocked")
    official_days = tuple(day for item in facts.assignments for day in item.service_dates)
    if len(official_days) != facts.service_days or len(set(official_days)) != facts.service_days:
        raise ValueError("official_date_schedule_incomplete")
    if "source_rate_snapshot_missing_or_ambiguous" in facts.monetary_blockers:
        raise ValueError("service_attribution_source_rate_required")
    selected = change.service_dates
    if not selected or tuple(sorted(set(selected))) != selected:
        raise ValueError("official_date_dates_not_canonical")
    replacement = change.replacement_dates or selected
    if len(replacement) != len(selected):
        raise ValueError("official_date_service_days_changed")
    if len(set(replacement)) != len(replacement):
        raise ValueError("official_date_dates_not_canonical")
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    changed_dates = (*selected, *replacement)
    if change.scope == "upcoming":
        if facts.order_status == "訂單完成" or any(day < today for day in changed_dates):
            raise ValueError("service_attribution_upcoming_date_blocked")
    elif (facts.order_status == "訂單成立" or any(day > today for day in changed_dates)
          or (facts.order_status == "服務中" and any(day == today for day in changed_dates))):
        raise ValueError("service_attribution_unperformed_date_blocked")
    source = next((item for item in facts.assignments if item.assignment_id == change.source_assignment_id), None)
    if source is None or not set(selected).issubset(source.service_dates):
        raise ValueError("service_attribution_assignment_conflict")
    if source.staff_id == change.staff_id and selected == replacement:
        raise ValueError("official_date_no_change")
    resulting_dates = (set(official_days) - set(selected)) | set(replacement)
    if len(resulting_dates) != facts.service_days:
        raise ValueError("official_date_service_days_changed")
    if change.scope == "upcoming" and facts.order_status == "服務中" and min(resulting_dates) != facts.actual_start_date:
        raise ValueError("official_date_actual_start_change_unsupported")
    if terms.payroll is None:
        raise ValueError("service_attribution_payroll_required")
    target = source if source.staff_id == change.staff_id else next((item for item in facts.assignments if item.staff_id == change.staff_id), None)
    if target != source and sum(item.staff_id == change.staff_id for item in facts.assignments) > 1:
        raise ValueError("service_attribution_target_assignment_ambiguous")
    moves = set(selected)
    flagged = {day for item in facts.assignments for day in item.double_pay_dates}
    effective_flags = (flagged - moves) | {new for old, new in zip(selected, replacement) if old in flagged}
    segments = []
    for item in facts.assignments:
        days = set(item.service_dates)
        if item == source:
            days -= moves
        if item == target:
            days.update(replacement)
        if days:
            segments.append((item.assignment_id, item.staff_id, tuple(sorted(days))))
    if target is None:
        segments.append((None, change.staff_id, replacement))
    assignments = tuple(
        AssignmentCandidate(
            f"service-attribution:{facts.case_no}:{facts.scheduling_version + 1}:{index}",
            assignment_id, staff_id, index, days[0], days[-1], days,
            len(days) * facts.hours_per_day,
            double_pay_dates=tuple(day for day in days if day in effective_flags),
        )
        for index, (assignment_id, staff_id, days) in enumerate(
            sorted(segments, key=lambda item: (item[2][0], item[1])), start=1,
        )
    )
    scheduling = SchedulingGenerationCandidate(
        facts.case_no, facts.generation_number + 1, facts.scheduling_version,
        facts.scheduling_version + 1, tuple(item.assignment_id for item in facts.assignments),
        assignments, (),
    )
    affected = set(funding.pending_staff) | {source.staff_id, change.staff_id}
    manual_split = any(item.kind != "unsplit" for item in funding.sources) and not any(
        item.tiered for item in terms.payroll.source_terms if item.staff_id in affected)
    review_staff = tuple(sorted(affected)) if funding.pending_event_id is not None or manual_split else ()
    review_roots = tuple(sorted({item.identity for item in funding.sources})) if review_staff else ()
    payroll = build_payroll_handover_impact(
        terms.payroll, scheduling, terms.order.terms,
        f"service-attribution:{facts.case_no}:{facts.scheduling_version + 1}",
        funding_staff=frozenset(review_staff),
    )
    if payroll.blockers:
        raise ValueError(payroll.blockers[0])
    payroll = _scope_attribution_payroll(payroll, affected)
    replaced = {item.obligation_identity for item in payroll.actions if item.action.value == "close_unpaid"}
    manual_amounts = tuple(item for item in manual_amounts if item[0] in replaced)
    funding_rows = _funding_preview(funding.sources, payroll, affected, max(resulting_dates), bool(review_staff))
    fingerprint = fingerprint_payload({
        "case": facts.case_no, "status": facts.order_status, "order": facts.order_version,
        "scheduling": facts.scheduling_version, "generation": facts.generation_id,
        "client_finance": facts.client_finance_version, "staff_payables": payable_versions,
        "payroll": payroll.fingerprint.value, "source": source.assignment_id,
        "staff": change.staff_id, "dates": tuple(day.isoformat() for day in selected),
        **({"replacement_dates": tuple(day.isoformat() for day in replacement), "scope": change.scope}
           if change.replacement_dates or change.scope != "served" else {}),
        "evidence": change.evidence.strip(),
        **({"manual_amounts": manual_amounts} if manual_amounts else {}),
        **({"funding": funding_rows} if funding_rows else {}),
        **({"funding_review": (funding.pending_event_id, review_staff, review_roots)} if review_staff else {}),
    })
    return ServiceAttributionPreview(facts, scheduling, payroll, fingerprint, change.evidence.strip(),
                                     manual_amounts, funding_rows, review_staff, review_roots)


def _funding_preview(funding, payroll, affected_staff, last_day, pending):
    before = {}
    for source in funding:
        key = (source.staff_id, source.kind)
        previous_amount, previous_settled = before.get(key, (0, 0))
        before[key] = (previous_amount + source.amount, None if source.settled is None or previous_settled is None
                       else previous_settled + source.settled)
    after = {}
    for item in payroll.payroll.assignments:
        if item.staff_id not in affected_staff:
            continue
        if item.tiered_pricing:
            for part in payroll_installments(item, last_day):
                key = (item.staff_id, part.funding_kind)
                after[key] = after.get(key, 0) + part.amount
        else:
            kind = "client" if (item.staff_id, "client") in before else "unsplit"
            key = (item.staff_id, kind)
            after[key] = after.get(key, 0) + item.total_payable.amount
    return tuple((*key, *before.get(key, (0, 0)), None if pending else after.get(key, 0))
                 for key in sorted(before.keys() | after.keys()))


def _funding_selections(selections):
    return tuple(sorted((item.assignment_id, item.subsidy_ntd) for item in selections))


def _funding_review(facts, terms, versions, manual_amounts, accounting, *, selections=None, evidence=""):
    staff = frozenset(accounting.pending_staff)
    assignments = tuple(AssignmentCandidate(
        str(item.assignment_id), item.assignment_id, item.staff_id, item.sequence,
        item.service_dates[0], item.service_dates[-1], item.service_dates,
        len(item.service_dates) * facts.hours_per_day, double_pay_dates=item.double_pay_dates,
    ) for item in facts.assignments)
    scheduling = SchedulingGenerationCandidate(facts.case_no, facts.generation_number, facts.scheduling_version,
                                               facts.scheduling_version, (), assignments, ())
    change_id = f"service-attribution-funding:{facts.case_no}:{accounting.pending_event_id}"
    payroll = build_payroll_handover_impact(terms.payroll, scheduling, terms.order.terms, change_id, funding_staff=staff)
    fingerprint = fingerprint_payload({
        "pending_event": accounting.pending_event_id, "generation": facts.generation_id, "order": facts.order_version,
        "payroll": payroll.fingerprint.value, "staff_payables": versions, "manual_amounts": manual_amounts,
        "sources": tuple((s.identity, s.kind, s.amount, s.settled, s.due_date.isoformat() if s.due_date else None,
                          s.previous_recovery) for s in accounting.sources),
        "selection": _funding_selections(selections or ()), "evidence": evidence.strip(),
    })
    if selections is None:
        return AttributionFundingReview(facts, accounting, payroll, manual_amounts, fingerprint)
    if not evidence.strip():
        raise ValueError("service_attribution_funding_evidence_required")
    if any(s.settled is None or (s.kind == "unsplit" and s.settled) for s in accounting.sources):
        raise ValueError("service_attribution_funding_payment_evidence_required")
    if accounting.paid_amount_controls:
        raise ValueError("service_attribution_funding_amount_control_required")
    amounts = {str(item.assignment_id): item.subsidy_ntd for item in selections}
    totals = {item.assignment_identity: item.total_payable.amount for item in payroll.payroll.assignments
              if item.staff_id in staff}
    subsidy = sum(item.amount for item in accounting.sources if item.kind == "subsidy")
    if (len(amounts) != len(selections) or amounts.keys() != totals.keys() or sum(amounts.values()) != subsidy
            or any(not 0 <= amount <= totals[key] for key, amount in amounts.items())):
        raise ValueError("service_attribution_funding_amount_invalid")
    by_root = {}
    by_assignment = {}
    for item in accounting.sources:
        by_root.setdefault(item.identity, {})[item.kind] = item
        by_assignment.setdefault(item.assignment_id, {})[item.kind] = item
    last_day = max(day for item in facts.assignments for day in item.service_dates)
    plan = []
    gross = {}
    for item in payroll.frozen_settlements:
        if item.staff_id not in staff:
            continue
        key = item.candidate_assignment_key
        split = _funding_plan(item.obligation_identity, item.staff_id, totals.get(key, 0), amounts.get(key, 0),
                              by_root.get(item.obligation_identity, {}), last_day, None)
        plan.append(split)
        gross[item.obligation_identity] = sum(p.amount for p in split.installments)
    for action in payroll.actions:
        if action.staff_id in staff and action.action.value == "establish" and action.amount.amount > 0:
            original = by_assignment.get(action.source_assignment_id, {}) if action.source_assignment_id else {}
            plan.append(_funding_plan(action.obligation_identity, action.staff_id, action.amount.amount,
                amounts[action.candidate_assignment_key], original, last_day, action.due_date, carry_paid=False))
    payroll = build_payroll_handover_impact(terms.payroll, scheduling, terms.order.terms, change_id,
                                            funding_staff=staff, settlement_amounts=gross)
    payroll = _scope_attribution_payroll(payroll, staff)
    return AttributionFundingReview(facts, accounting, payroll, manual_amounts, fingerprint, tuple(plan), evidence.strip())


def _scope_attribution_payroll(payroll, staff):
    return replace(payroll, actions=tuple(a for a in payroll.actions if a.staff_id in staff),
                   frozen_settlements=tuple(s for s in payroll.frozen_settlements if s.staff_id in staff))


def _funding_plan(identity, staff_id, total, subsidy, original, last_day, due_date, *, carry_paid=True):
    installments = []
    revised = []
    recovery = []
    for kind, amount in (("client", total - subsidy), ("subsidy", subsidy)):
        source = original.get(kind)
        settled = source.settled if source and carry_paid else 0
        excess = max(0, settled - amount)
        previous = source.previous_recovery if source and carry_paid else 0
        if excess < previous:
            raise ValueError("service_attribution_funding_recovery_review_required")
        if excess > previous:
            recovery.append((kind, excess - previous))
        due = source.due_date if source else (
            due_date if kind == "client" and due_date else funding_due_date(last_day, directly_subsidized=kind == "subsidy")
        )
        # Keep the paid amount on its original source. The excess has its own recovery.
        installments.append(PayrollInstallment(kind, max(amount, settled), due))
        revised.append((kind, amount, settled))
    return AttributionFundingPlan(identity, staff_id, tuple(installments), tuple(revised), tuple(recovery))


def _preview(facts: OfficialDateFacts, selections: tuple[OfficialDateSelection, ...]) -> OfficialDatePreview:
    if facts.order_status != "訂單完成" or not facts.assignments:
        raise ValueError("official_date_completed_assignment_required")
    if facts.monetary_change_blocker:
        raise OfficialDateMonetaryImpactBlocked(facts.monetary_blockers)
    source = {item.assignment_id: item for item in facts.assignments}
    if len(source) != len(facts.assignments) or len(selections) != len(source):
        raise ValueError("official_date_assignment_allocation_invalid")
    selected = {item.assignment_id: item for item in selections}
    if set(selected) != set(source) or len(selected) != len(selections):
        raise ValueError("official_date_assignment_allocation_invalid")
    all_dates = []
    for assignment_id, selection in selected.items():
        dates = selection.service_dates
        if not dates or dates != tuple(sorted(set(dates))):
            raise ValueError("official_date_dates_not_canonical")
        if len(dates) != len(source[assignment_id].service_dates):
            raise ValueError("official_date_service_days_changed")
        all_dates.extend(dates)
    if len(set(all_dates)) != facts.service_days or len(all_dates) != facts.service_days:
        raise ValueError("official_date_service_days_changed")
    if facts.actual_start_date is None or min(all_dates) != facts.actual_start_date:
        raise ValueError("official_date_actual_start_change_unsupported")
    if max(all_dates) > datetime.now(ZoneInfo("Asia/Taipei")).date():
        raise ValueError("official_date_future_completed_service_blocked")
    ordered = tuple(selected[item.assignment_id] for item in facts.assignments)
    if all(item.service_dates == selected[item.assignment_id].service_dates for item in facts.assignments):
        raise ValueError("official_date_no_change")
    return OfficialDatePreview(facts, ordered, fingerprint_payload({
        "case_no": facts.case_no,
        "order_version": facts.order_version,
        "scheduling_version": facts.scheduling_version,
        "generation_id": facts.generation_id,
        "source": _selection_payload(tuple(OfficialDateSelection(a.assignment_id, a.service_dates) for a in facts.assignments)),
        "proposed": _selection_payload(ordered),
        "service_data_locked": facts.service_data_locked,
        "actual_end_date": facts.actual_end_date.isoformat() if facts.actual_end_date else None,
        "monetary_change_blocker": facts.monetary_change_blocker,
        "client_finance_version": facts.client_finance_version,
        "payroll_version": facts.payroll_version,
    }))


def _candidate(preview: OfficialDatePreview) -> SchedulingGenerationCandidate:
    facts = preview.facts
    selected = {item.assignment_id: item.service_dates for item in preview.selections}
    return SchedulingGenerationCandidate(
        case_no=facts.case_no,
        generation_number=facts.generation_number + 1,
        expected_aggregate_version=facts.scheduling_version,
        resulting_aggregate_version=facts.scheduling_version + 1,
        cancelled_assignment_ids=tuple(a.assignment_id for a in facts.assignments),
        assignments=tuple(AssignmentCandidate(
            candidate_key=f"official-date-correction:{facts.case_no}:{facts.scheduling_version + 1}:{a.assignment_id}",
            source_assignment_id=a.assignment_id,
            staff_id=a.staff_id,
            sequence=a.sequence,
            assigned_start_date=selected[a.assignment_id][0],
            assigned_end_date=selected[a.assignment_id][-1],
            service_dates=selected[a.assignment_id],
            actual_hours=len(selected[a.assignment_id]) * facts.hours_per_day,
        ) for a in facts.assignments),
        buffers=(),
    )


def _selection_payload(selections: tuple[OfficialDateSelection, ...]) -> list[dict[str, object]]:
    return [{"assignment_id": item.assignment_id, "service_dates": [day.isoformat() for day in item.service_dates]} for item in selections]

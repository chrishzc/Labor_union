"""Auditable correction of effective, already performed service dates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Callable, Literal, Protocol

from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
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


@dataclass(frozen=True, slots=True)
class ServiceAttributionChange:
    source_assignment_id: int
    staff_id: int
    service_dates: tuple[date, ...]
    evidence: str


@dataclass(frozen=True, slots=True)
class ServiceAttributionPreview:
    facts: OfficialDateFacts
    scheduling: SchedulingGenerationCandidate
    payroll: PayrollTermsImpactCandidate
    fingerprint: PreviewFingerprint
    evidence: str


def _attribution_family(status: str) -> str:
    return "orders_completed_service_attribution" if status == "訂單完成" else "orders_service_attribution"


class OfficialDateRepository(Protocol):
    def load(self, case_no: str, *, lock: bool = False) -> OfficialDateFacts: ...
    def load_history(self, case_no: str) -> tuple[OfficialDateHistoryRecord, ...]: ...
    def validate_availability(self, candidate: SchedulingGenerationCandidate, *, lock: bool) -> None: ...
    def replay(self, key: str, command_fingerprint: str, *, lock: bool = False) -> OfficialDateReceipt | None: ...
    def replace_and_record(self, command: SchedulingReplacementCommand, preview: OfficialDatePreview) -> OfficialDateReceipt: ...
    def load_attribution(self, case_no: str, staff_id: int, *, lock: bool): ...
    def replay_attribution(self, key: str, command_fingerprint: str, *, lock: bool = False) -> OfficialDateReceipt | None: ...
    def persist_attribution(self, command: SchedulingReplacementCommand, preview: ServiceAttributionPreview) -> OfficialDateReceipt: ...


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
                          idempotency_key: str, correlation_id: str) -> OfficialDateReceipt:
        if not reason.strip():
            raise ValueError("service_attribution_reason_required")
        command_fingerprint = fingerprint_payload({
            "case_no": case_no, "source_assignment_id": change.source_assignment_id,
            "staff_id": change.staff_id, "dates": tuple(day.isoformat() for day in change.service_dates),
            "evidence": change.evidence.strip(), "reason": reason.strip(), "actor": actor,
            "order_version": expected_order_version, "scheduling_version": expected_scheduling_version,
            "preview": preview_fingerprint,
        })
        replay = self._repository.replay_attribution(idempotency_key, command_fingerprint.value)
        if replay is not None:
            return replay
        with self._unit_of_work() as unit_of_work:
            facts, terms, payable_versions = self._repository.load_attribution(case_no, change.staff_id, lock=True)
            replay = self._repository.replay_attribution(idempotency_key, command_fingerprint.value, lock=True)
            if replay is not None:
                return replay
            if (facts.order_version, facts.scheduling_version) != (expected_order_version, expected_scheduling_version):
                raise ValueError("official_date_version_conflict")
            preview = _attribution_preview(facts, terms, payable_versions, change)
            if preview.fingerprint.value != preview_fingerprint:
                raise ValueError("official_date_preview_stale")
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
        facts, terms, payable_versions = self._repository.load_attribution(case_no, change.staff_id, lock=lock)
        preview = _attribution_preview(facts, terms, payable_versions, change)
        self._repository.validate_availability(preview.scheduling, lock=lock)
        return preview

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


def _attribution_preview(facts, terms, payable_versions, change):
    if facts.order_status not in {"服務中", "訂單完成"} or facts.actual_start_date is None:
        raise ValueError("service_attribution_status_blocked")
    if not change.evidence.strip():
        raise ValueError("service_attribution_evidence_required")
    if facts.service_data_locked and facts.order_status == "服務中":
        raise ValueError("service_attribution_status_blocked")
    official_days = tuple(day for item in facts.assignments for day in item.service_dates)
    if len(official_days) != facts.service_days or len(set(official_days)) != facts.service_days:
        raise ValueError("official_date_schedule_incomplete")
    if any(item.double_pay_dates for item in facts.assignments):
        raise ValueError("service_attribution_special_pay_review_required")
    if "source_rate_snapshot_missing_or_ambiguous" in facts.monetary_blockers:
        raise ValueError("service_attribution_source_rate_required")
    selected = change.service_dates
    if not selected or tuple(sorted(set(selected))) != selected:
        raise ValueError("official_date_dates_not_canonical")
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    if any(day >= today for day in selected) and facts.order_status == "服務中":
        raise ValueError("service_attribution_unperformed_date_blocked")
    if any(day > today for day in selected):
        raise ValueError("service_attribution_unperformed_date_blocked")
    source = next((item for item in facts.assignments if item.assignment_id == change.source_assignment_id), None)
    if source is None or not set(selected).issubset(source.service_dates) or source.staff_id == change.staff_id:
        raise ValueError("service_attribution_assignment_conflict")
    if terms.payroll is None:
        raise ValueError("service_attribution_payroll_required")
    target = next((item for item in facts.assignments if item.staff_id == change.staff_id), None)
    if sum(item.staff_id == change.staff_id for item in facts.assignments) > 1:
        raise ValueError("service_attribution_target_assignment_ambiguous")
    moves = set(selected)
    segments = []
    for item in facts.assignments:
        days = set(item.service_dates)
        if item == source:
            days -= moves
        if item == target:
            days |= moves
        if days:
            segments.append((item.assignment_id, item.staff_id, tuple(sorted(days))))
    if target is None:
        segments.append((None, change.staff_id, selected))
    assignments = tuple(
        AssignmentCandidate(
            f"service-attribution:{facts.case_no}:{facts.scheduling_version + 1}:{index}",
            assignment_id, staff_id, index, days[0], days[-1], days,
            len(days) * facts.hours_per_day,
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
    payroll = build_payroll_handover_impact(
        terms.payroll, scheduling, terms.order.terms,
        f"service-attribution:{facts.case_no}:{facts.scheduling_version + 1}",
    )
    if payroll.blockers:
        raise ValueError(payroll.blockers[0])
    fingerprint = fingerprint_payload({
        "case": facts.case_no, "status": facts.order_status, "order": facts.order_version,
        "scheduling": facts.scheduling_version, "generation": facts.generation_id,
        "client_finance": facts.client_finance_version, "staff_payables": payable_versions,
        "payroll": payroll.fingerprint.value, "source": source.assignment_id,
        "staff": change.staff_id, "dates": tuple(day.isoformat() for day in selected),
        "evidence": change.evidence.strip(),
    })
    return ServiceAttributionPreview(facts, scheduling, payroll, fingerprint, change.evidence.strip())


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

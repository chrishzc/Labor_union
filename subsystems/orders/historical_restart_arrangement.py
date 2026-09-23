"""Explicit formal arrangement after historical Precision Restart date confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Protocol

from domains.scheduling.generation import (
    AssignmentCandidate,
    BufferCandidate,
    SchedulingGenerationCandidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
)
from subsystems.orders.terms_workflow import SchedulingReplacementCommand


@dataclass(frozen=True, slots=True)
class ArrangementSegmentIntent:
    staff_id: int
    service_dates: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class HistoricalRestartArrangementPreview:
    candidate: SchedulingGenerationCandidate
    order_version: int
    confirmed_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class HistoricalRestartArrangementReceipt:
    case_no: str
    scheduling_version: int
    generation_number: int
    assignment_ids: tuple[int, ...]
    preview_fingerprint: PreviewFingerprint


class HistoricalRestartArrangementRepository(Protocol):
    def load(self, case_no: str, *, lock: bool = False) -> ServiceDateConfirmationFacts: ...
    def lock_arrangement_staff(self, staff_ids: tuple[int, ...]) -> None: ...
    def validate_arrangement_availability(
        self, candidate: SchedulingGenerationCandidate, *, lock: bool,
    ) -> None: ...
    def arrangement_rate_fingerprint(
        self, candidate: SchedulingGenerationCandidate, *, lock: bool,
    ) -> PreviewFingerprint: ...
    def replay_arrangement(
        self, key: str, command_fingerprint: str, *, lock: bool,
    ) -> HistoricalRestartArrangementReceipt | None: ...
    def persist_arrangement(
        self, command: SchedulingReplacementCommand,
    ) -> HistoricalRestartArrangementReceipt: ...


class HistoricalRestartArrangementWorkflow:
    def __init__(
        self,
        repository: HistoricalRestartArrangementRepository,
        unit_of_work_factory: Callable,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def preview(
        self, case_no: str, segments: tuple[ArrangementSegmentIntent, ...],
    ) -> HistoricalRestartArrangementPreview:
        return self._build_preview(self._repository.load(case_no), segments, lock=False)

    def apply(
        self,
        case_no: str,
        segments: tuple[ArrangementSegmentIntent, ...],
        *,
        expected_order_version: int,
        expected_scheduling_version: int,
        expected_confirmed_version: int,
        preview_fingerprint: str,
        idempotency_key: str,
        actor: str,
        reason: str,
        correlation_id: str,
    ) -> HistoricalRestartArrangementReceipt:
        if not reason.strip():
            raise ValueError("historical_arrangement_reason_required")
        command_fingerprint = fingerprint_payload({
            "case_no": case_no,
            "segments": _segment_payload(segments),
            "versions": (
                expected_order_version, expected_scheduling_version,
                expected_confirmed_version,
            ),
            "preview_fingerprint": preview_fingerprint,
            "actor": actor,
            "reason": reason,
        }).value
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._repository.load(case_no, lock=True)
            replay = self._repository.replay_arrangement(
                idempotency_key, command_fingerprint, lock=True,
            )
            if replay is not None:
                return replay
            if (
                facts.order_version != expected_order_version
                or facts.scheduling_version != expected_scheduling_version
                or facts.current_version != expected_confirmed_version
            ):
                raise ValueError("historical_arrangement_stale_version")
            self._repository.lock_arrangement_staff(
                tuple(sorted({item.staff_id for item in segments}))
            )
            preview = self._build_preview(facts, segments, lock=True)
            if preview.fingerprint.value != preview_fingerprint:
                raise ValueError("historical_arrangement_stale_preview")
            command = SchedulingReplacementCommand(
                candidate=preview.candidate,
                command_family="orders_historical_restart_arrangement",
                expected_order_version=expected_order_version,
                command_fingerprint=PreviewFingerprint(command_fingerprint),
                preview_fingerprint=preview.fingerprint,
                idempotency_key=IdempotencyKey(idempotency_key),
                actor=ActorContext(actor),
                reason=reason,
                correlation_id=CorrelationId(correlation_id),
            )
            receipt = self._repository.persist_arrangement(command)
            unit_of_work.commit()
            return receipt

    def _build_preview(self, facts, segments, *, lock):
        candidate = _arrangement_candidate(facts, segments)
        self._repository.validate_arrangement_availability(candidate, lock=lock)
        rate_fingerprint = self._repository.arrangement_rate_fingerprint(
            candidate, lock=lock,
        )
        fingerprint = fingerprint_payload({
            "candidate": _candidate_payload(candidate),
            "order_version": facts.order_version,
            "confirmed_version": facts.current_version,
            "confirmed_dates": tuple(item.isoformat() for item in facts.current_dates),
            "rate_fingerprint": rate_fingerprint.value,
        })
        return HistoricalRestartArrangementPreview(
            candidate, facts.order_version, facts.current_version, fingerprint,
        )


def _arrangement_candidate(
    facts: ServiceDateConfirmationFacts,
    segments: tuple[ArrangementSegmentIntent, ...],
) -> SchedulingGenerationCandidate:
    if facts.restart_generation_number is None or facts.current_version is None:
        raise ValueError("historical_arrangement_not_pending_blocked")
    if (
        facts.current_confirmed_order_version is not None
        and facts.current_confirmed_order_version != facts.order_version
    ):
        raise ValueError("historical_arrangement_confirmed_dates_stale")
    if (
        not facts.current_dates
        or len(facts.current_dates) != facts.contracted_service_days
        or facts.current_dates != tuple(sorted(set(facts.current_dates)))
        or not facts.selectable_dates
        or any(day not in facts.selectable_dates for day in facts.current_dates)
    ):
        raise ValueError("historical_arrangement_confirmed_dates_required_blocked")
    if not segments or len(segments) != len(facts.restart_assignments):
        raise ValueError("historical_arrangement_staff_allocation_required_blocked")
    bound = {item.staff_id: item for item in facts.restart_assignments}
    if len(bound) != len(facts.restart_assignments) or {
        item.staff_id for item in segments
    } != set(bound) or len({item.staff_id for item in segments}) != len(segments):
        raise ValueError("historical_arrangement_bound_staff_mismatch_blocked")
    if facts.service_hours_per_day <= 0:
        raise ValueError("historical_arrangement_service_hours_missing_blocked")
    if tuple(day for segment in segments for day in segment.service_dates) != facts.current_dates:
        raise ValueError("historical_arrangement_date_ownership_mismatch_blocked")
    interval_start = facts.selectable_dates[0]
    assignments = []
    buffers = []
    generation = facts.restart_generation_number + 1
    for sequence, segment in enumerate(segments, start=1):
        dates = segment.service_dates
        if not dates or dates != tuple(sorted(set(dates))) or dates[0] < interval_start:
            raise ValueError("historical_arrangement_segment_invalid_blocked")
        key = f"{facts.case_no}:g{generation}:a{sequence}"
        assignment = AssignmentCandidate(
            candidate_key=key,
            source_assignment_id=bound[segment.staff_id].source_assignment_id,
            staff_id=segment.staff_id,
            sequence=sequence,
            assigned_start_date=interval_start,
            assigned_end_date=dates[-1],
            service_dates=dates,
            actual_hours=len(dates) * facts.service_hours_per_day,
        )
        assignments.append(assignment)
        buffers.append(BufferCandidate(
            candidate_key=f"{key}:buffer",
            staff_id=segment.staff_id,
            dates=tuple(dates[-1] + timedelta(days=offset) for offset in range(1, 8)),
            active=True,
        ))
        interval_start = dates[-1] + timedelta(days=1)
    return SchedulingGenerationCandidate(
        case_no=facts.case_no,
        generation_number=generation,
        expected_aggregate_version=facts.scheduling_version,
        resulting_aggregate_version=facts.scheduling_version + 1,
        cancelled_assignment_ids=(),
        assignments=tuple(assignments),
        buffers=tuple(buffers),
    )


def _segment_payload(segments):
    return tuple({
        "staff_id": item.staff_id,
        "service_dates": tuple(day.isoformat() for day in item.service_dates),
    } for item in segments)


def _candidate_payload(candidate):
    return {
        "case_no": candidate.case_no,
        "generation": candidate.generation_number,
        "scheduling_version": candidate.expected_aggregate_version,
        "assignments": tuple({
            "source_assignment_id": item.source_assignment_id,
            "staff_id": item.staff_id,
            "sequence": item.sequence,
            "start": item.assigned_start_date.isoformat(),
            "end": item.assigned_end_date.isoformat(),
            "dates": tuple(day.isoformat() for day in item.service_dates),
            "hours": item.actual_hours,
        } for item in candidate.assignments),
    }

"""Orders-owned Preview and Apply for confirmed planned service dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Protocol

from domains.orders.service_date_confirmation import (
    ConfirmedServiceDateCandidate,
    group_service_dates_by_calendar_week,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from domains.scheduling.generation import (
    AssignmentCandidate,
    BufferCandidate,
    SchedulingGenerationCandidate,
)
from subsystems.orders.terms_workflow import SchedulingReplacementCommand


@dataclass(frozen=True, slots=True)
class RestartSchedulingAssignmentFacts:
    source_assignment_id: int
    staff_id: int
    sequence: int
    service_day_count: int


@dataclass(frozen=True, slots=True)
class ServiceDateConfirmationFacts:
    case_no: str
    order_version: int
    scheduling_version: int
    contracted_service_days: int
    suggested_dates: tuple[date, ...]
    selectable_dates: tuple[date, ...]
    current_version: int | None
    current_dates: tuple[date, ...]
    restart_generation_number: int | None = None
    restart_assignments: tuple[RestartSchedulingAssignmentFacts, ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceDateConfirmationPreview:
    candidate: ConfirmedServiceDateCandidate
    current_version: int | None
    weeks: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ServiceDateConfirmationReceipt:
    case_no: str
    confirmed_version: int
    order_version: int
    scheduling_version: int
    service_dates: tuple[date, ...]
    fingerprint: PreviewFingerprint


class ServiceDateConfirmationRepository(Protocol):
    def load(self, case_no: str, *, lock: bool = False) -> ServiceDateConfirmationFacts: ...
    def replay(self, idempotency_key: str, command_fingerprint: str) -> ServiceDateConfirmationReceipt | None: ...
    def save(self, candidate: ConfirmedServiceDateCandidate, *, actor: str, reason: str,
             idempotency_key: str, command_fingerprint: str) -> ServiceDateConfirmationReceipt: ...
    def persist_restarted_scheduling(self, command: SchedulingReplacementCommand) -> int: ...


class SchedulingSnapshotInvalidationPort(Protocol):
    """Scheduling-owned invalidation using the caller's active transaction."""

    def invalidate_current_snapshot(self, case_no: str) -> None: ...


class UnitOfWork(Protocol):
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exception_type, exception, traceback) -> bool: ...
    def commit(self) -> None: ...


class ServiceDateConfirmationWorkflow:
    def __init__(
        self,
        repository: ServiceDateConfirmationRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
        scheduling_snapshot_invalidation: SchedulingSnapshotInvalidationPort,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._scheduling_snapshot_invalidation = scheduling_snapshot_invalidation

    def query(self, case_no: str) -> ServiceDateConfirmationFacts:
        return self._repository.load(case_no)

    def preview(self, case_no: str, service_dates: tuple[date, ...]) -> ServiceDateConfirmationPreview:
        facts = self._repository.load(case_no)
        candidate = _candidate(facts, service_dates)
        return ServiceDateConfirmationPreview(
            candidate,
            facts.current_version,
            group_service_dates_by_calendar_week(candidate.service_dates),
        )

    def apply(self, case_no: str, service_dates: tuple[date, ...], *, expected_order_version: int,
              expected_scheduling_version: int, preview_fingerprint: str, actor: str,
              reason: str, idempotency_key: str) -> ServiceDateConfirmationReceipt:
        command_fingerprint = _command_fingerprint(case_no, service_dates, expected_order_version,
                                                   expected_scheduling_version, preview_fingerprint)
        replay = self._repository.replay(idempotency_key, command_fingerprint)
        if replay is not None:
            return replay
        with self._unit_of_work_factory() as unit_of_work:
            facts = self._repository.load(case_no, lock=True)
            if (facts.order_version, facts.scheduling_version) != (
                expected_order_version,
                expected_scheduling_version,
            ):
                raise ValueError("service_date_confirmation_stale_version")
            candidate = _candidate(facts, service_dates)
            if candidate.fingerprint.value != preview_fingerprint:
                raise ValueError("service_date_confirmation_preview_stale")
            receipt = self._repository.save(
                candidate,
                actor=actor,
                reason=reason,
                idempotency_key=idempotency_key,
                command_fingerprint=command_fingerprint,
            )
            if facts.restart_generation_number is not None:
                scheduling_version = self._repository.persist_restarted_scheduling(
                    _restart_scheduling_command(
                        facts,
                        candidate.service_dates,
                        actor=actor,
                        reason=reason,
                        idempotency_key=idempotency_key,
                        command_fingerprint=command_fingerprint,
                        preview_fingerprint=preview_fingerprint,
                    )
                )
                receipt = ServiceDateConfirmationReceipt(
                    receipt.case_no,
                    receipt.confirmed_version,
                    receipt.order_version,
                    scheduling_version,
                    receipt.service_dates,
                    receipt.fingerprint,
                )
            self._scheduling_snapshot_invalidation.invalidate_current_snapshot(
                candidate.case_no
            )
            unit_of_work.commit()
            return receipt


def _restart_scheduling_command(
    facts: ServiceDateConfirmationFacts,
    service_dates: tuple[date, ...],
    *,
    actor: str,
    reason: str,
    idempotency_key: str,
    command_fingerprint: str,
    preview_fingerprint: str,
) -> SchedulingReplacementCommand:
    assignments = _restart_assignment_candidates(facts, service_dates)
    generation_number = facts.restart_generation_number
    if generation_number is None:
        raise ValueError("historical_restart_scheduling_not_pending")
    candidate = SchedulingGenerationCandidate(
        case_no=facts.case_no,
        generation_number=generation_number + 1,
        expected_aggregate_version=facts.scheduling_version,
        resulting_aggregate_version=facts.scheduling_version + 1,
        cancelled_assignment_ids=(),
        assignments=assignments,
        buffers=tuple(_restart_buffer(item) for item in assignments),
    )
    return SchedulingReplacementCommand(
        candidate=candidate,
        command_family="historical_restart_service_dates",
        expected_order_version=facts.order_version,
        command_fingerprint=PreviewFingerprint(command_fingerprint),
        preview_fingerprint=PreviewFingerprint(preview_fingerprint),
        idempotency_key=IdempotencyKey(idempotency_key),
        actor=ActorContext(actor),
        reason=reason,
        correlation_id=CorrelationId(f"historical-restart-service-dates:{idempotency_key}"),
    )


def _restart_assignment_candidates(
    facts: ServiceDateConfirmationFacts,
    service_dates: tuple[date, ...],
) -> tuple[AssignmentCandidate, ...]:
    sources = tuple(sorted(facts.restart_assignments, key=lambda item: item.sequence))
    if not sources:
        raise ValueError("historical_restart_assignment_required")
    if len(sources) == 1:
        counts = (len(service_dates),)
    else:
        counts = tuple(item.service_day_count for item in sources)
        if any(value <= 0 for value in counts) or sum(counts) != len(service_dates):
            raise ValueError("historical_restart_assignment_allocation_required")
    offset = 0
    result = []
    for source, count in zip(sources, counts, strict=True):
        assigned_dates = service_dates[offset:offset + count]
        offset += count
        result.append(AssignmentCandidate(
            candidate_key=f"{facts.case_no}:g{facts.restart_generation_number + 1}:a{source.sequence}",
            source_assignment_id=source.source_assignment_id,
            staff_id=source.staff_id,
            sequence=source.sequence,
            assigned_start_date=assigned_dates[0],
            assigned_end_date=assigned_dates[-1],
            service_dates=assigned_dates,
            actual_hours=0,
        ))
    return tuple(result)


def _restart_buffer(assignment: AssignmentCandidate) -> BufferCandidate:
    return BufferCandidate(
        candidate_key=f"{assignment.candidate_key}:buffer",
        staff_id=assignment.staff_id,
        dates=tuple(assignment.assigned_end_date + timedelta(days=value) for value in range(1, 8)),
        active=True,
    )


def _candidate(facts, service_dates):
    selected_dates = tuple(sorted(service_dates))
    selectable_dates = set(facts.selectable_dates)
    if any(value not in selectable_dates for value in selected_dates):
        raise ValueError("service_date_confirmation_date_outside_selectable_range")
    return ConfirmedServiceDateCandidate(
        facts.case_no,
        facts.order_version,
        facts.scheduling_version,
        selected_dates,
        facts.contracted_service_days,
    )


def _command_fingerprint(case_no, dates, order_version, scheduling_version, preview_fingerprint):
    from shared_kernel.fingerprints import fingerprint_payload

    return fingerprint_payload(
        {
            "case_no": case_no,
            "service_dates": [value.isoformat() for value in dates],
            "order_version": order_version,
            "scheduling_version": scheduling_version,
            "preview_fingerprint": preview_fingerprint,
        }
    ).value

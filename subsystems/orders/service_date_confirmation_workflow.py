"""Orders-owned Preview and Apply for confirmed planned service dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

from domains.orders.service_date_confirmation import (
    ConfirmedServiceDateCandidate,
    group_service_dates_by_calendar_week,
)
from shared_kernel.fingerprints import PreviewFingerprint


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


class UnitOfWork(Protocol):
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exception_type, exception, traceback) -> bool: ...
    def commit(self) -> None: ...


class ServiceDateConfirmationWorkflow:
    def __init__(
        self,
        repository: ServiceDateConfirmationRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

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
            unit_of_work.commit()
            return receipt


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

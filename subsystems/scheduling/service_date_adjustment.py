"""Apply a versioned date adjustment in the Scheduling owner's unit of work."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Callable, Protocol

from domains.scheduling.service_date_adjustment import (
    AdjustmentTarget,
    ServiceDateAdjustment,
    ServiceDay,
    plan_service_date_adjustment,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.service_date_confirmation_workflow import UnitOfWork


@dataclass(frozen=True, slots=True)
class ServiceDateAdjustmentPair:
    receipt_id: int
    change: ServiceDateAdjustment


@dataclass(frozen=True, slots=True)
class ServiceDateAdjustmentFacts:
    case_no: str
    order_version: int
    scheduling_version: int
    confirmed_version: int | None
    generation_id: int | None
    daily_hours: Decimal
    days: tuple[ServiceDay, ...]
    staff: tuple[tuple[int, str], ...]
    pairs: tuple[ServiceDateAdjustmentPair, ...]
    contracted_days: int
    selectable_dates: tuple[date, ...]
    planned_owners: tuple[tuple[date, int], ...] = ()
    first_schedule_days: tuple[ServiceDay, ...] = ()

    @property
    def versions(self) -> tuple[int, int, int | None]:
        return self.order_version, self.scheduling_version, self.confirmed_version


@dataclass(frozen=True, slots=True)
class ServiceDateAdjustmentIntent:
    source_dates: tuple[date, ...]
    targets: tuple[AdjustmentTarget, ...]
    reverse_receipt_id: int | None = None
    initial_dates: tuple[date, ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceDateAdjustmentPreview:
    facts: ServiceDateAdjustmentFacts
    change: ServiceDateAdjustment
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ServiceDateAdjustmentReceipt:
    receipt_id: int
    scheduling_version: int
    confirmed_version: int | None


class ServiceDateAdjustmentRepository(Protocol):
    def load(self, case_no: str, *, lock: bool = False) -> ServiceDateAdjustmentFacts: ...
    def lock_case_and_staff(self, case_no: str, staff_ids: tuple[int, ...]) -> None: ...
    def replay(self, key: str, fingerprint: str, *, lock: bool = False) -> ServiceDateAdjustmentReceipt | None: ...
    def validate_availability(self, facts: ServiceDateAdjustmentFacts, change: ServiceDateAdjustment, *, lock: bool) -> None: ...
    def save(self, preview: ServiceDateAdjustmentPreview, request: ServiceDateAdjustmentIntent, *, key: str,
             fingerprint: str, actor: str) -> ServiceDateAdjustmentReceipt: ...


class ServiceDateAdjustmentWorkflow:
    def __init__(self, repository: ServiceDateAdjustmentRepository, unit_of_work: Callable[[], UnitOfWork]):
        self._repository = repository
        self._unit_of_work = unit_of_work

    def query(self, case_no: str) -> ServiceDateAdjustmentFacts:
        return self._repository.load(case_no)

    def preview(self, case_no: str, request: ServiceDateAdjustmentIntent) -> ServiceDateAdjustmentPreview:
        preview = _preview(self.query(case_no), request)
        self._repository.validate_availability(preview.facts, preview.change, lock=False)
        return preview

    def apply(self, case_no: str, request: ServiceDateAdjustmentIntent, *, versions: tuple[int, int, int | None],
              preview_fingerprint: str, key: str, actor: str) -> ServiceDateAdjustmentReceipt:
        fingerprint = fingerprint_payload({
            "case_no": case_no, "intent": _intent_payload(request), "versions": versions,
            "preview_fingerprint": preview_fingerprint, "actor": actor,
        }).value
        replay = self._repository.replay(key, fingerprint)
        if replay is not None:
            return replay
        current = self.query(case_no)
        target_staff = {staff_id for staff_id, _ in current.staff}
        target_staff.update(target.staff_id for target in request.targets)
        target_staff.update(day.staff_id for pair in current.pairs if pair.receipt_id == request.reverse_receipt_id
                            for day in pair.change.removed if day.staff_id is not None)
        with self._unit_of_work() as unit:
            self._repository.lock_case_and_staff(case_no, tuple(sorted(target_staff)))
            replay = self._repository.replay(key, fingerprint, lock=True)
            if replay is not None:
                return replay
            facts = self._repository.load(case_no, lock=True)
            if facts.versions != versions:
                raise ValueError("service_date_adjustment_stale_version")
            preview = _preview(facts, request)
            if preview.fingerprint != preview_fingerprint:
                raise ValueError("service_date_adjustment_stale_preview")
            self._repository.validate_availability(facts, preview.change, lock=True)
            receipt = self._repository.save(preview, request, key=key, fingerprint=fingerprint, actor=actor)
            unit.commit()
            return receipt


def service_day_payload(day: ServiceDay) -> dict[str, object]:
    return {"service_date": day.service_date.isoformat(), "staff_id": day.staff_id,
            "hours_override": day.hours_override}


def _intent_payload(request: ServiceDateAdjustmentIntent) -> dict[str, object]:
    return {
        "source_dates": [value.isoformat() for value in sorted(request.source_dates)],
        "targets": sorted((target.service_date.isoformat(), target.staff_id) for target in request.targets),
        "reverse_receipt_id": request.reverse_receipt_id,
        "initial_dates": [value.isoformat() for value in sorted(request.initial_dates)],
    }


def _preview(facts: ServiceDateAdjustmentFacts, request: ServiceDateAdjustmentIntent) -> ServiceDateAdjustmentPreview:
    if request.initial_dates:
        if facts.days or facts.confirmed_version is not None or facts.generation_id is not None:
            raise ValueError("service_date_adjustment_stale_initial_dates")
        if (len(set(request.initial_dates)) != facts.contracted_days
                or len(request.initial_dates) != facts.contracted_days
                or not set(request.initial_dates).issubset(facts.selectable_dates)):
            raise ValueError("service_date_adjustment_invalid_initial_dates")
        owners = dict(facts.planned_owners)
        facts = replace(facts, days=tuple(ServiceDay(day, owners.get(day), None) for day in sorted(request.initial_dates)))
    matched = next((pair.change for pair in facts.pairs if pair.receipt_id == request.reverse_receipt_id), None)
    if request.reverse_receipt_id is not None and matched is None:
        raise ValueError("service_date_adjustment_stale_pair")
    staff_ids = {staff_id for staff_id, _ in facts.staff}
    if any(target.staff_id not in staff_ids for target in request.targets):
        raise ValueError("service_date_adjustment_staff_ownership_conflict")
    change = plan_service_date_adjustment(facts.days, facts.daily_hours, request.source_dates, request.targets, reverse=matched)
    fingerprint = fingerprint_payload({
        "case_no": facts.case_no,
        "versions": facts.versions,
        "intent": _intent_payload(request),
        "removed": [service_day_payload(day) for day in change.removed],
        "inserted": [service_day_payload(day) for day in change.inserted],
        "hours": str(change.total_hours),
    }).value
    return ServiceDateAdjustmentPreview(facts, change, fingerprint)

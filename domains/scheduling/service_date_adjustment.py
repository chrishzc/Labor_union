"""Scheduling's service-day merge, split and restoration rules."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class ServiceDay:
    service_date: date
    staff_id: int | None
    hours_override: Literal[4, 8] | None

    def hours(self, contracted_daily_hours: Decimal) -> Decimal:
        return contracted_daily_hours if self.hours_override is None else Decimal(self.hours_override)


@dataclass(frozen=True, slots=True)
class AdjustmentTarget:
    service_date: date
    staff_id: int


@dataclass(frozen=True, slots=True)
class ServiceDateAdjustment:
    removed: tuple[ServiceDay, ...]
    inserted: tuple[ServiceDay, ...]
    days: tuple[ServiceDay, ...]
    total_hours: Decimal


def plan_service_date_adjustment(
    days: tuple[ServiceDay, ...],
    contracted_daily_hours: Decimal,
    source_dates: tuple[date, ...],
    targets: tuple[AdjustmentTarget, ...],
    *,
    reverse: ServiceDateAdjustment | None = None,
) -> ServiceDateAdjustment:
    current = {day.service_date: day for day in days}
    if len(current) != len(days):
        raise ValueError("service_date_adjustment_ownership_conflict")
    if len(set(source_dates)) != len(source_dates) or any(day not in current for day in source_dates):
        raise ValueError("service_date_adjustment_stale_source")
    if reverse is not None:
        if (targets or not source_dates
                or not set(source_dates).issubset(day.service_date for day in reverse.inserted)
                or any(current.get(day.service_date) != day for day in reverse.inserted)):
            raise ValueError("service_date_adjustment_stale_pair")
        removed, inserted = reverse.inserted, reverse.removed
    else:
        removed = tuple(current[day] for day in sorted(source_dates))
        source_hours = tuple(day.hours(contracted_daily_hours) for day in removed)
        if source_hours == (4, 4) and len(targets) == 1:
            replacement_hours = 8
        elif source_hours == (8,) and len(targets) == 2:
            replacement_hours = 4
        else:
            raise ValueError("service_date_adjustment_invalid_hours_or_day_count")
        inserted = tuple(
            ServiceDay(target.service_date, target.staff_id, replacement_hours)
            for target in sorted(targets, key=lambda target: target.service_date)
        )
    for day in removed:
        del current[day.service_date]
    for day in inserted:
        if day.service_date in current:
            raise ValueError("service_date_adjustment_ownership_conflict")
        current[day.service_date] = day
    total = sum((day.hours(contracted_daily_hours) for day in current.values()), Decimal(0))
    before = sum((day.hours(contracted_daily_hours) for day in days), Decimal(0))
    if total != before:
        raise ValueError("service_date_adjustment_hours_conflict")
    return ServiceDateAdjustment(removed, inserted, tuple(current[key] for key in sorted(current)), total)

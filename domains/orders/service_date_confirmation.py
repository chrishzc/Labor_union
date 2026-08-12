"""Canonical validation for confirmed planned service dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


@dataclass(frozen=True, slots=True)
class ConfirmedServiceDateCandidate:
    case_no: str
    order_version: int
    scheduling_version: int
    service_dates: tuple[date, ...]
    contracted_service_days: int

    def __post_init__(self) -> None:
        if not self.case_no.strip():
            raise ValueError("case number is required")
        if self.contracted_service_days <= 0:
            raise ValueError("contracted service days must be positive")
        if tuple(sorted(set(self.service_dates))) != self.service_dates:
            raise ValueError("service dates must be unique and sorted")
        if len(self.service_dates) != self.contracted_service_days:
            raise ValueError("service date count must equal contracted service days")

    @property
    def fingerprint(self) -> PreviewFingerprint:
        return fingerprint_payload(
            {
                "case_no": self.case_no,
                "order_version": self.order_version,
                "scheduling_version": self.scheduling_version,
                "service_dates": [value.isoformat() for value in self.service_dates],
                "week_grouping_policy": "calendar_week_sunday_to_saturday_v1",
            }
        )


def group_service_dates_by_calendar_week(
    service_dates: tuple[date, ...],
) -> tuple[dict[str, object], ...]:
    grouped: dict[date, list[date]] = {}
    for service_date in service_dates:
        week_start = service_date - timedelta(days=(service_date.weekday() + 1) % 7)
        grouped.setdefault(week_start, []).append(service_date)
    return tuple(
        {
            "week_number": index,
            "period_start": week_start.isoformat(),
            "period_end": (week_start + timedelta(days=6)).isoformat(),
            "service_dates": [value.isoformat() for value in dates],
            "service_day_count": len(dates),
        }
        for index, (week_start, dates) in enumerate(sorted(grouped.items()), start=1)
    )


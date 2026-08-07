"""Pure occupancy projection for waiting-deposit locks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

WAITING_DEPOSIT_BUFFER_DAYS = 7


class WaitingDepositOccupancyKind(StrEnum):
    SERVICE = "service"
    BUFFER = "buffer"


@dataclass(frozen=True, slots=True)
class WaitingDepositSegment:
    segment_id: int
    staff_id: int
    assigned_start_date: date
    assigned_end_date: date

    def __post_init__(self) -> None:
        if self.segment_id < 1 or self.staff_id < 1:
            raise ValueError("waiting-deposit segment identities must be positive")
        if self.assigned_start_date > self.assigned_end_date:
            raise ValueError("waiting-deposit segment dates are reversed")


@dataclass(frozen=True, slots=True)
class WaitingDepositOccupancy:
    segment_id: int
    staff_id: int
    occupancy_date: date
    kind: WaitingDepositOccupancyKind


def project_waiting_deposit_occupancy(
    segments: tuple[WaitingDepositSegment, ...],
) -> tuple[WaitingDepositOccupancy, ...]:
    if not segments:
        raise ValueError("waiting-deposit segments are required")
    occupancy = tuple(
        item
        for segment in segments
        for item in _project_segment_occupancy(segment)
    )
    _reject_duplicate_staff_dates(occupancy)
    return tuple(
        sorted(
            occupancy,
            key=lambda item: (
                item.occupancy_date,
                item.segment_id,
                item.staff_id,
                item.kind,
            ),
        )
    )


def _project_segment_occupancy(
    segment: WaitingDepositSegment,
) -> tuple[WaitingDepositOccupancy, ...]:
    service_dates = _inclusive_dates(
        segment.assigned_start_date,
        segment.assigned_end_date,
    )
    buffer_start = segment.assigned_end_date + timedelta(days=1)
    buffer_end = segment.assigned_end_date + timedelta(
        days=WAITING_DEPOSIT_BUFFER_DAYS
    )
    return (
        *_occupancy(segment, service_dates, WaitingDepositOccupancyKind.SERVICE),
        *_occupancy(
            segment,
            _inclusive_dates(buffer_start, buffer_end),
            WaitingDepositOccupancyKind.BUFFER,
        ),
    )


def _occupancy(segment, dates, kind):
    return tuple(
        WaitingDepositOccupancy(
            segment.segment_id,
            segment.staff_id,
            occupancy_date,
            kind,
        )
        for occupancy_date in dates
    )


def _inclusive_dates(start: date, end: date) -> tuple[date, ...]:
    return tuple(
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    )


def _reject_duplicate_staff_dates(
    occupancy: tuple[WaitingDepositOccupancy, ...],
) -> None:
    identities = tuple(
        (item.staff_id, item.occupancy_date) for item in occupancy
    )
    if len(identities) != len(set(identities)):
        raise ValueError("waiting-deposit occupancy overlaps within the plan")


__all__ = [
    "WAITING_DEPOSIT_BUFFER_DAYS",
    "WaitingDepositOccupancy",
    "WaitingDepositOccupancyKind",
    "WaitingDepositSegment",
    "project_waiting_deposit_occupancy",
]

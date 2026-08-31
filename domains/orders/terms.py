"""
File: terms.py
Description: 定義 Orders Terms 根事實、唯一料理需求補正與通用驗證。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from shared_kernel.money import MoneyNTD
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True, slots=True)
class ServiceTimeTerms:
    start_time: time | None
    end_time: time | None
    end_day_offset: int | None

    def __post_init__(self) -> None:
        values = (self.start_time, self.end_time, self.end_day_offset)
        if all(value is None for value in values):
            return
        if any(value is None for value in values):
            raise ValueError("service time terms must be all empty or all present")
        if self.end_day_offset not in {0, 1}:
            raise ValueError("service end day offset must be 0 or 1")
        if not isinstance(self.start_time, time) or not isinstance(self.end_time, time):
            raise TypeError("service start and end times must be time values")

    @property
    def complete(self) -> bool:
        return self.start_time is not None

    def completion_instant(self, service_date: date) -> datetime:
        if not isinstance(service_date, date):
            raise TypeError("service date must be a date")
        if not self.complete:
            return datetime.combine(service_date, time.max, tzinfo=_TAIPEI)
        completion_date = service_date + timedelta(days=self.end_day_offset)
        return datetime.combine(completion_date, self.end_time, tzinfo=_TAIPEI)

    def service_start_instant(self, service_date: date) -> datetime:
        if not isinstance(service_date, date):
            raise TypeError("service date must be a date")
        return datetime.combine(
            service_date,
            self.start_time or time.min,
            tzinfo=_TAIPEI,
        )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "end_day_offset": self.end_day_offset,
        }


@dataclass(frozen=True, slots=True)
class OrderTerms:
    planned_start_date: date
    service_days: int
    service_hours_per_day: int
    floor_fee: MoneyNTD
    service_time: ServiceTimeTerms
    requires_cooking: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.planned_start_date, date):
            raise TypeError("planned start date must be a date")
        require_positive_integer(self.service_days, "service days")
        require_positive_integer(
            self.service_hours_per_day,
            "service hours per day",
        )
        if not isinstance(self.floor_fee, MoneyNTD):
            raise TypeError("floor fee must be MoneyNTD")
        if not isinstance(self.service_time, ServiceTimeTerms):
            raise TypeError("service time must be ServiceTimeTerms")
        if self.requires_cooking is not None and not isinstance(
            self.requires_cooking, bool
        ):
            raise TypeError("requires cooking must be bool or None")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "floor_fee_ntd": self.floor_fee.amount,
            "planned_start_date": self.planned_start_date.isoformat(),
            "service_days": self.service_days,
            "service_hours_per_day": self.service_hours_per_day,
            "requires_cooking": self.requires_cooking,
            "service_time": self.service_time.canonical_payload(),
        }


@dataclass(frozen=True, slots=True)
class OrderAggregateFacts:
    case_no: str
    version: int
    terms: OrderTerms
    service_data_locked: bool
    client_identity_status: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.case_no,
            "case number",
            _CASE_NUMBER_MAXIMUM_LENGTH,
        )
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise TypeError("order version must be an integer")
        if self.version < 0:
            raise ValueError("order version must be nonnegative")
        require_canonical_text(
            self.client_identity_status,
            "client identity status",
            100,
        )
        if not isinstance(self.service_data_locked, bool):
            raise TypeError("service data locked must be bool")


def is_unique_cooking_requirement_correction(
    current_terms: OrderTerms,
    proposed_terms: OrderTerms,
) -> bool:
    """Allow only the Case Import-owned unknown-to-known cooking correction."""
    return (
        current_terms.requires_cooking is None
        and proposed_terms.requires_cooking is not None
        and replace(proposed_terms, requires_cooking=None) == current_terms
    )


def validate_terms_change(
    current: OrderAggregateFacts,
    proposed_terms: OrderTerms,
) -> None:
    if current.service_data_locked:
        raise ValueError("service_data_locked")
    if (
        not proposed_terms.service_time.complete
        and not is_unique_cooking_requirement_correction(
            current.terms, proposed_terms
        )
    ):
        raise ValueError("service_time_terms_incomplete")

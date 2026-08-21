"""
File: holiday_calendar_query.py
Description: 定義 Scheduling 國定假日 horizon 的唯讀、版本化且可鎖定 port。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HolidayFact:
    holiday_date: date
    holiday_name: str
    is_double_pay_default: bool = False


@dataclass(frozen=True, slots=True)
class HolidayCalendarFacts:
    source_identity: str
    holiday_version: str
    holidays: tuple[HolidayFact, ...]


class HolidayCalendarUnavailable(Exception):
    pass


class SchedulingHolidayQuery(Protocol):
    def query(
        self,
        service_start_date: date,
        service_end_date: date,
        *,
        lock: bool,
    ) -> HolidayCalendarFacts: ...

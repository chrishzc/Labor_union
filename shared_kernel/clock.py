"""Injectable Asia/Taipei business clock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

TAIPEI_TIME_ZONE = ZoneInfo("Asia/Taipei")


class BusinessClock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...


@dataclass(frozen=True, slots=True)
class SystemBusinessClock:
    def now(self) -> datetime:
        return datetime.now(TAIPEI_TIME_ZONE)

    def today(self) -> date:
        return self.now().date()


@dataclass(frozen=True, slots=True)
class FixedBusinessClock:
    current_time: datetime

    def __post_init__(self) -> None:
        if self.current_time.tzinfo is None:
            raise ValueError("fixed business time must be timezone-aware")

    def now(self) -> datetime:
        return self.current_time.astimezone(TAIPEI_TIME_ZONE)

    def today(self) -> date:
        return self.now().date()

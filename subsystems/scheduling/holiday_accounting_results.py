"""Typed readback of accounting outcomes saved by holiday maintenance."""
from dataclasses import dataclass
from datetime import date

from subsystems.scheduling.holiday_maintenance import HolidayCaseRepricingResult


@dataclass(frozen=True, slots=True)
class HolidayAccountingReceipt:
    holiday_date: date
    receipt_key: str
    case_results: tuple[HolidayCaseRepricingResult, ...]

"""Typed read projection for Staff roster case preferences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from shared_kernel.validation import require_positive_integer


OtherDetailStatus = Literal["ready", "not_recorded", "source_not_ready"]


class StaffCasePreferenceSummaryContractError(ValueError):
    """Raised when Staff case-preference facts violate the read contract."""


@dataclass(frozen=True, slots=True)
class PreferenceTopicFacts:
    values: tuple[str, ...] = ()
    other_details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceFacts:
    staff_id: int
    service_regions: PreferenceTopicFacts
    service_periods: PreferenceTopicFacts
    rest_schedule: PreferenceTopicFacts
    baby_counts: PreferenceTopicFacts
    holiday_availability: PreferenceTopicFacts
    transportation: PreferenceTopicFacts


@dataclass(frozen=True, slots=True)
class PreferenceTopicSummary:
    values: tuple[str, ...]
    other_detail: str | None
    other_detail_status: OtherDetailStatus


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceSummary:
    staff_id: int
    service_regions: PreferenceTopicSummary
    service_periods: PreferenceTopicSummary
    rest_schedule: PreferenceTopicSummary
    baby_counts: PreferenceTopicSummary
    holiday_availability: PreferenceTopicSummary
    transportation: PreferenceTopicSummary


class StaffCasePreferenceSummaryRepository(Protocol):
    def fetch(self, staff_id: int) -> StaffCasePreferenceFacts | None: ...


_SERVICE_REGION_ORDER = ("北區", "東區", "香山區", "新竹縣", "苗栗縣")
_SERVICE_PERIOD_ORDER = (
    "4小時(上午8:30-12:30)",
    "4小時(下午13:00-17:00)",
    "8小時",
    "24小時",
)
_REST_SCHEDULE_ORDER = ("連續服務", "週休1日", "週休2日")
_BABY_COUNT_ORDER = ("單胞胎", "雙胞胎")
_HOLIDAY_AVAILABILITY_ORDER = (
    "年節農曆過年初一",
    "年節農曆過年初二",
    "年節農曆過年初三",
    "端午節",
    "中秋節",
    "國定假日必休",
)
_TRANSPORTATION_ORDER = ("機車", "轎車")


class StaffCasePreferenceSummaryQueryApplication:
    """Read one bounded Staff case-preference projection for roster consumers."""

    def __init__(self, repository: StaffCasePreferenceSummaryRepository) -> None:
        self._repository = repository

    def get(self, staff_id: int) -> StaffCasePreferenceSummary | None:
        require_positive_integer(staff_id, "staff case preference staff_id")
        facts = self._repository.fetch(staff_id)
        if facts is None:
            return None
        if facts.staff_id != staff_id:
            raise StaffCasePreferenceSummaryContractError(
                "repository staff id does not match requested staff"
            )
        return StaffCasePreferenceSummary(
            staff_id=staff_id,
            service_regions=_topic(facts.service_regions, _SERVICE_REGION_ORDER),
            service_periods=_topic(facts.service_periods, _SERVICE_PERIOD_ORDER),
            rest_schedule=_topic(facts.rest_schedule, _REST_SCHEDULE_ORDER),
            baby_counts=_topic(facts.baby_counts, _BABY_COUNT_ORDER),
            holiday_availability=_topic(
                facts.holiday_availability,
                _HOLIDAY_AVAILABILITY_ORDER,
            ),
            transportation=_topic(
                facts.transportation,
                _TRANSPORTATION_ORDER,
                source_not_ready=True,
            ),
        )


def _topic(
    facts: PreferenceTopicFacts,
    owner_order: tuple[str, ...],
    *,
    source_not_ready: bool = False,
) -> PreferenceTopicSummary:
    values = _ordered_values(facts.values, owner_order)
    if source_not_ready:
        return PreferenceTopicSummary(
            values=values,
            other_detail=None,
            other_detail_status="source_not_ready",
        )

    details = tuple(
        sorted(
            {
                detail
                for raw_detail in facts.other_details
                if (detail := _clean_text(raw_detail)) is not None
            }
        )
    )
    if len(details) > 1:
        raise StaffCasePreferenceSummaryContractError(
            "staff case preference other detail is ambiguous"
        )
    if details:
        return PreferenceTopicSummary(
            values=values,
            other_detail=details[0],
            other_detail_status="ready",
        )
    return PreferenceTopicSummary(
        values=values,
        other_detail=None,
        other_detail_status="not_recorded",
    )


def _ordered_values(
    raw_values: tuple[str, ...],
    owner_order: tuple[str, ...],
) -> tuple[str, ...]:
    values = {
        value
        for raw_value in raw_values
        if (value := _clean_text(raw_value)) is not None and value != "其他"
    }
    known = tuple(value for value in owner_order if value in values)
    owner_values = set(owner_order)
    unknown = tuple(sorted(values - owner_values))
    return known + unknown


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


__all__ = [
    "OtherDetailStatus",
    "PreferenceTopicFacts",
    "PreferenceTopicSummary",
    "StaffCasePreferenceFacts",
    "StaffCasePreferenceSummary",
    "StaffCasePreferenceSummaryContractError",
    "StaffCasePreferenceSummaryQueryApplication",
    "StaffCasePreferenceSummaryRepository",
]

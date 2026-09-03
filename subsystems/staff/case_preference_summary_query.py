"""Typed read contract for the Staff roster case-preference projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from shared_kernel.validation import require_positive_integer


OtherDetailStatus = Literal["ready", "not_recorded", "source_not_ready"]

_TOPIC_ORDER = (
    "service_regions",
    "service_periods",
    "rest_schedule",
    "baby_counts",
    "holiday_availability",
    "transportation",
)

_CANONICAL_VALUE_ORDER: dict[str, tuple[str, ...]] = {
    "service_regions": ("北區", "東區", "香山區", "新竹縣", "苗栗縣"),
    "service_periods": (
        "4小時(上午8:30-12:30)",
        "4小時(下午13:00-17:00)",
        "8小時",
        "24小時",
    ),
    "rest_schedule": ("連續服務", "週休1日", "週休2日"),
    "baby_counts": ("單胞胎", "雙胞胎"),
    "holiday_availability": (
        "年節農曆過年初一",
        "年節農曆過年初二",
        "年節農曆過年初三",
        "端午節",
        "中秋節",
        "國定假日必休",
    ),
    "transportation": ("機車", "轎車"),
}

_OTHER_VALUE = "其他"


class StaffCasePreferenceSummaryContractError(ValueError):
    """Raised when the Staff case-preference source violates its read contract."""


class StaffCasePreferenceSummaryNotFoundError(LookupError):
    """Raised when the requested Staff identity does not exist."""


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceSummaryQueryRequest:
    staff_id: int

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff case preference staff_id")


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
    def fetch_topics(
        self,
        *,
        staff_id: int,
    ) -> Mapping[str, tuple[Mapping[str, object], ...] | None] | None: ...


class StaffCasePreferenceSummaryQueryApplication:
    """Project Staff-owned canonical relation facts into the roster read model."""

    def __init__(self, repository: StaffCasePreferenceSummaryRepository) -> None:
        self._repository = repository

    def query(
        self,
        request: StaffCasePreferenceSummaryQueryRequest,
    ) -> StaffCasePreferenceSummary:
        topic_rows = self._repository.fetch_topics(staff_id=request.staff_id)
        if topic_rows is None:
            raise StaffCasePreferenceSummaryNotFoundError("staff not found")
        if not isinstance(topic_rows, Mapping) or set(topic_rows) != set(_TOPIC_ORDER):
            raise StaffCasePreferenceSummaryContractError(
                "repository topic set is not canonical"
            )

        projected = {
            topic: _topic_summary(topic, topic_rows[topic])
            for topic in _TOPIC_ORDER
        }
        return StaffCasePreferenceSummary(
            staff_id=request.staff_id,
            service_regions=projected["service_regions"],
            service_periods=projected["service_periods"],
            rest_schedule=projected["rest_schedule"],
            baby_counts=projected["baby_counts"],
            holiday_availability=projected["holiday_availability"],
            transportation=projected["transportation"],
        )


def _topic_summary(
    topic: str,
    rows: object,
) -> PreferenceTopicSummary:
    if rows is None:
        return PreferenceTopicSummary(
            values=(),
            other_detail=None,
            other_detail_status="source_not_ready",
        )
    if not isinstance(rows, tuple):
        raise StaffCasePreferenceSummaryContractError(f"{topic} rows must be a tuple")

    values: set[str] = set()
    details: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"value", "other_detail"}:
            raise StaffCasePreferenceSummaryContractError(
                f"{topic} repository row fields are not canonical"
            )
        value = _required_text(row["value"], f"{topic} value")
        detail = _optional_text(row["other_detail"], f"{topic} other_detail")
        if value != _OTHER_VALUE:
            values.add(value)
        if detail is not None:
            details.add(detail)

    if topic == "transportation":
        if details:
            raise StaffCasePreferenceSummaryContractError(
                "transportation other_detail source must remain unavailable"
            )
        return PreferenceTopicSummary(
            values=_ordered_values(topic, values),
            other_detail=None,
            other_detail_status="source_not_ready",
        )

    if len(details) > 1:
        raise StaffCasePreferenceSummaryContractError(
            f"{topic} contains conflicting other_detail values"
        )
    other_detail = next(iter(details), None)
    return PreferenceTopicSummary(
        values=_ordered_values(topic, values),
        other_detail=other_detail,
        other_detail_status="ready" if other_detail is not None else "not_recorded",
    )


def _ordered_values(topic: str, values: set[str]) -> tuple[str, ...]:
    canonical = _CANONICAL_VALUE_ORDER[topic]
    known = [value for value in canonical if value in values]
    unknown = sorted(values.difference(canonical))
    return tuple([*known, *unknown])


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise StaffCasePreferenceSummaryContractError(f"{label} is invalid")
    normalized = value.strip()
    if not normalized:
        raise StaffCasePreferenceSummaryContractError(f"{label} is invalid")
    return normalized


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StaffCasePreferenceSummaryContractError(f"{label} is invalid")
    normalized = value.strip()
    return normalized or None


__all__ = [
    "OtherDetailStatus",
    "PreferenceTopicSummary",
    "StaffCasePreferenceSummary",
    "StaffCasePreferenceSummaryContractError",
    "StaffCasePreferenceSummaryNotFoundError",
    "StaffCasePreferenceSummaryQueryApplication",
    "StaffCasePreferenceSummaryQueryRequest",
    "StaffCasePreferenceSummaryRepository",
]

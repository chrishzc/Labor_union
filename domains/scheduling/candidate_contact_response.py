"""Business rules for candidate questions, conditional adjustments, and silence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class CandidateIssueCategory(StrEnum):
    SERVICE_REGION = "service_region"
    SERVICE_DATES = "service_dates"
    DAILY_SERVICE_WINDOW = "daily_service_window"
    DAILY_SERVICE_HOURS = "daily_service_hours"
    COOKING_REQUIREMENT = "cooking_requirement"
    TRANSPORT_PARKING_FLOOR = "transport_parking_floor"
    PERSONAL_REASON = "personal_reason"


class CandidateIssueMode(StrEnum):
    INFORMATION_QUESTION = "information_question"
    CONDITION_ADJUSTMENT = "condition_adjustment"


class CandidateResponseKind(StrEnum):
    COORDINATION_REQUESTED = "coordination_requested"
    NO_INTEREST = "no_interest"
    TIMED_OUT = "timed_out"


class CandidateContactState(StrEnum):
    NOT_DELIVERED = "not_delivered"
    WAITING_INITIAL = "waiting_initial"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_FINAL_RESPONSE = "waiting_final_response"
    DUE_TIMEOUT = "due_timeout"
    TERMINAL = "terminal"
    WILLING = "willing"


class CandidatePoolResolution(StrEnum):
    OPEN = "open"
    WILLING = "willing"
    CUSTOMER_ADJUSTMENT = "customer_adjustment"
    UNION_MANUAL_FOLLOWUP = "union_manual_followup"


CATEGORY_LABELS = {
    CandidateIssueCategory.SERVICE_REGION: "服務地區",
    CandidateIssueCategory.SERVICE_DATES: "服務日期／檔期",
    CandidateIssueCategory.DAILY_SERVICE_WINDOW: "每日服務時段",
    CandidateIssueCategory.DAILY_SERVICE_HOURS: "每日服務時數",
    CandidateIssueCategory.COOKING_REQUIREMENT: "下廚需求",
    CandidateIssueCategory.TRANSPORT_PARKING_FLOOR: "交通、停車或樓層",
    CandidateIssueCategory.PERSONAL_REASON: "個人因素",
}


CATEGORY_AFFECTED_CRITERIA = {
    CandidateIssueCategory.SERVICE_REGION: ("service_city", "service_address"),
    CandidateIssueCategory.SERVICE_DATES: (
        "confirmed_service_dates",
        "planned_start_date",
        "service_days",
    ),
    CandidateIssueCategory.DAILY_SERVICE_WINDOW: ("service_time",),
    CandidateIssueCategory.DAILY_SERVICE_HOURS: ("service_hours_per_day",),
    CandidateIssueCategory.COOKING_REQUIREMENT: ("requires_cooking",),
    CandidateIssueCategory.TRANSPORT_PARKING_FLOOR: (
        "service_address",
        "floor_elevator_notes",
        "parking_space_provided",
    ),
    CandidateIssueCategory.PERSONAL_REASON: ("personal_reason",),
}


@dataclass(frozen=True, slots=True)
class CandidateIssue:
    category: CandidateIssueCategory
    mode: CandidateIssueMode
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.category, CandidateIssueCategory):
            raise TypeError("candidate_issue_category_invalid")
        if not isinstance(self.mode, CandidateIssueMode):
            raise TypeError("candidate_issue_mode_invalid")
        normalized = self.detail.strip() if isinstance(self.detail, str) else ""
        if not normalized or len(normalized) > 500:
            raise ValueError("candidate_issue_detail_invalid")
        object.__setattr__(self, "detail", normalized)

    def as_payload(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "mode": self.mode.value,
            "detail": self.detail,
            "affected_criteria": list(CATEGORY_AFFECTED_CRITERIA[self.category]),
        }


@dataclass(frozen=True, slots=True)
class CandidateCoordinationResponse:
    no_interest: bool
    issues: tuple[CandidateIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.no_interest, bool):
            raise TypeError("candidate_no_interest_invalid")
        if not isinstance(self.issues, tuple) or any(
            not isinstance(item, CandidateIssue) for item in self.issues
        ):
            raise TypeError("candidate_issues_invalid")
        if self.no_interest and self.issues:
            raise ValueError("candidate_no_interest_must_be_exclusive")
        if not self.no_interest and not self.issues:
            raise ValueError("candidate_issue_required")
        categories = tuple(item.category for item in self.issues)
        if len(categories) != len(set(categories)):
            raise ValueError("candidate_issue_category_duplicate")

    @property
    def response_kind(self) -> CandidateResponseKind:
        return (
            CandidateResponseKind.NO_INTEREST
            if self.no_interest
            else CandidateResponseKind.COORDINATION_REQUESTED
        )

    @property
    def has_information_questions(self) -> bool:
        return any(
            item.mode is CandidateIssueMode.INFORMATION_QUESTION for item in self.issues
        )

    @property
    def has_condition_adjustments(self) -> bool:
        return any(
            item.mode is CandidateIssueMode.CONDITION_ADJUSTMENT for item in self.issues
        )

    @property
    def affected_criteria(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    criterion
                    for item in self.issues
                    if item.mode is CandidateIssueMode.CONDITION_ADJUSTMENT
                    for criterion in CATEGORY_AFFECTED_CRITERIA[item.category]
                }
            )
        )

    def as_payload(self) -> dict[str, object]:
        adjustment_codes = [
            item.category.value
            for item in self.issues
            if item.mode is CandidateIssueMode.CONDITION_ADJUSTMENT
        ]
        reason_code = (
            "no_interest"
            if self.no_interest
            else adjustment_codes[0]
            if adjustment_codes
            else None
        )
        return {
            "response_kind": self.response_kind.value,
            "willingness": "unwilling" if self.no_interest or self.has_condition_adjustments else "pending",
            "reason_code": reason_code,
            "reason": reason_code,
            "affected_criteria": list(self.affected_criteria),
            "issues": [item.as_payload() for item in self.issues],
        }


def parse_candidate_response(
    *, no_interest: bool, issues: Iterable[dict[str, object]]
) -> CandidateCoordinationResponse:
    parsed = tuple(
        CandidateIssue(
            CandidateIssueCategory(str(item.get("category") or "")),
            CandidateIssueMode(str(item.get("mode") or "")),
            str(item.get("detail") or ""),
        )
        for item in issues
    )
    return CandidateCoordinationResponse(no_interest=no_interest, issues=parsed)


def category_label(value: str) -> str:
    return CATEGORY_LABELS[CandidateIssueCategory(value)]


def resolve_candidate_pool(
    states: Iterable[CandidateContactState | str],
    *,
    has_condition_adjustments: bool,
) -> CandidatePoolResolution:
    """Resolve only a contacted pool; an empty search result is not a follow-up."""

    normalized = tuple(CandidateContactState(value) for value in states)
    if not normalized:
        return CandidatePoolResolution.OPEN
    if CandidateContactState.WILLING in normalized:
        return CandidatePoolResolution.WILLING
    if any(state is not CandidateContactState.TERMINAL for state in normalized):
        return CandidatePoolResolution.OPEN
    return (
        CandidatePoolResolution.CUSTOMER_ADJUSTMENT
        if has_condition_adjustments
        else CandidatePoolResolution.UNION_MANUAL_FOLLOWUP
    )


__all__ = [
    "CATEGORY_AFFECTED_CRITERIA",
    "CATEGORY_LABELS",
    "CandidateCoordinationResponse",
    "CandidateContactState",
    "CandidateIssue",
    "CandidateIssueCategory",
    "CandidateIssueMode",
    "CandidateResponseKind",
    "CandidatePoolResolution",
    "category_label",
    "parse_candidate_response",
    "resolve_candidate_pool",
]

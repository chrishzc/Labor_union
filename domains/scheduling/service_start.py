"""Explicit caregiver results, independent of group conversation or delivery status."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ServiceStartDecision(StrEnum):
    ACCEPTED = "accepted"
    DECLINED = "declined"


class ServiceStartConflict(ValueError):
    """A closed business rejection; never an infrastructure failure."""

    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ServiceStartSubmission:
    case_no: str
    staff_id: int
    segment_id: int | None
    decision: ServiceStartDecision
    start_date: date | None
    expected_order_version: int
    key: str
    assignment_id: int | None = None

    def __post_init__(self):
        if not self.case_no.strip() or len(self.case_no) > 50 or self.staff_id < 1:
            raise ValueError("invalid service start subject")
        if not self.key.strip() or len(self.key) > 150:
            raise ValueError("invalid service start command identity")
        if self.decision is ServiceStartDecision.ACCEPTED and type(self.start_date) is not date:
            raise ServiceStartConflict("start_date_required", "請填入與客戶約定的服務開始日。")
        if self.decision is ServiceStartDecision.DECLINED and self.start_date is not None:
            raise ServiceStartConflict("decline_date_not_allowed", "不接受時不需填寫服務日期。")

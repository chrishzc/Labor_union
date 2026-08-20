"""File: test_service_day_log_workflow.py
Description: 驗證月嫂服務日日誌的餐食條件、正式指派限制與冪等編排。"""

from datetime import date

import pytest

from domains.scheduling.service_day_log import ServiceDayLogIntent
from subsystems.scheduling.service_day_log_workflow import (
    ServiceDayLogResult,
    ServiceDayLogWorkflow,
    SubmitServiceDayLog,
)


class FakeRepository:
    def __init__(self, requires_cooking: bool | None) -> None:
        self.assignment = {"case_no": "CASE-1", "requires_cooking": requires_cooking}
        self.submitted = []

    def load_assignment(self, staff_id: int, assignment_id: int, service_date: date):
        assert (staff_id, assignment_id, service_date) == (9, 12, date(2026, 8, 16))
        return self.assignment

    def submit(self, command, assignment):
        self.submitted.append((command, assignment))
        return ServiceDayLogResult(1, "CASE-1", "2026-08-16", bool(assignment["requires_cooking"]), "created")


def _command(*, photos: tuple[str, ...] = ()) -> SubmitServiceDayLog:
    return SubmitServiceDayLog(
        staff_id=9,
        line_user_id="U-caregiver",
        assignment_id=12,
        intent=ServiceDayLogIntent(date(2026, 8, 16), "寶寶今日狀況正常", photos),
        idempotency_key="service-day-log-1",
    )


def test_non_cooking_service_day_log_can_be_submitted_without_meal_photo() -> None:
    repository = FakeRepository(False)

    result = ServiceDayLogWorkflow(repository).submit(_command())

    assert result.outcome == "created"
    assert len(repository.submitted) == 1


def test_cooking_service_day_log_requires_at_least_one_meal_photo() -> None:
    repository = FakeRepository(True)

    with pytest.raises(ValueError, match="meal photo is required"):
        ServiceDayLogWorkflow(repository).submit(_command())

    assert repository.submitted == []


def test_unknown_cooking_requirement_fails_closed() -> None:
    repository = FakeRepository(None)

    with pytest.raises(ValueError, match="cooking requirement is unresolved"):
        ServiceDayLogWorkflow(repository).submit(_command(photos=("media-1",)))

    assert repository.submitted == []


def test_cooking_service_day_log_accepts_owned_meal_photo_reference() -> None:
    repository = FakeRepository(True)

    ServiceDayLogWorkflow(repository).submit(_command(photos=("media-1",)))

    assert repository.submitted[0][0].intent.meal_photo_media_ids == ("media-1",)

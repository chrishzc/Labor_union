"""File: test_service_day_log_workflow.py
Description: 驗證月嫂服務日日誌的餐食條件、正式指派限制與冪等編排。"""

from datetime import date

import pytest

from domains.scheduling.service_day_log import ServiceDayLogIntent
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.scheduling.service_day_log_workflow import (
    ApplyServiceDayLog,
    ControlledServiceDayLogAttachment,
    PreviewServiceDayLog,
    ServiceDayLogResult,
    ServiceDayLogWorkflow,
)


class FakeRepository:
    def __init__(self, requires_cooking: bool | None) -> None:
        self.assignment = {"case_no": "CASE-1", "requires_cooking": requires_cooking}
        self.submitted = []

    def load_assignment(self, staff_id: int, assignment_id: int, service_date: date, *, for_update: bool):
        assert (staff_id, assignment_id, service_date) == (9, 12, date(2026, 8, 16))
        self.for_update = for_update
        return self.assignment

    def submit(self, command, assignment):
        self.submitted.append((command, assignment))
        return ServiceDayLogResult(1, "CASE-1", 12, "2026-08-16", "寶寶今日狀況正常", bool(assignment["requires_cooking"]), "created")

    def load_replay(self, command):
        return None

    def load_for_staff(self, log_id, staff_id, line_user_id):
        if (log_id, staff_id, line_user_id) != (1, 9, "U-caregiver"):
            return None
        return ServiceDayLogResult(1, "CASE-1", 12, "2026-08-16", "寶寶今日狀況正常", False, "existing")


def _preview_command() -> PreviewServiceDayLog:
    return PreviewServiceDayLog(
        staff_id=9,
        line_user_id="U-caregiver",
        assignment_id=12,
        intent=ServiceDayLogIntent(date(2026, 8, 16), "寶寶今日狀況正常", ()),
    )


def test_non_cooking_service_day_log_preview_is_zero_lock_and_can_apply() -> None:
    repository = FakeRepository(False)
    workflow = ServiceDayLogWorkflow(repository)

    preview = workflow.preview(_preview_command())

    assert preview.can_apply is True
    assert preview.blockers == ()
    assert repository.for_update is False


def test_non_cooking_service_day_log_apply_rechecks_with_lock() -> None:
    repository = FakeRepository(False)
    workflow = ServiceDayLogWorkflow(repository)

    preview = workflow.preview(_preview_command())
    command = ApplyServiceDayLog(9, "U-caregiver", 12, _preview_command().intent, "service-day-log-1", preview.preview_fingerprint)
    result = workflow.apply(command)

    assert result.outcome == "created"
    assert repository.for_update is True
    assert len(repository.submitted) == 1


def test_cooking_service_day_log_is_blocked_pending_media_scope() -> None:
    repository = FakeRepository(True)

    preview = ServiceDayLogWorkflow(repository).preview(_preview_command())

    assert preview.blockers == ("service_day_log_meal_photo_required",)
    assert repository.submitted == []


def test_cooking_service_day_log_accepts_typed_controlled_file_attachment() -> None:
    repository = FakeRepository(True)
    attachment = ControlledServiceDayLogAttachment(
        "cf_1234567890abcdef1234567890abcdef",
        "cfs_1234567890abcdef1234567890abcdef",
        "a" * 64,
    )
    preview_command = PreviewServiceDayLog(
        9,
        "U-caregiver",
        12,
        ServiceDayLogIntent(date(2026, 8, 16), "寶寶正常", ()),
        controlled_file_attachments=(attachment,),
    )
    preview = ServiceDayLogWorkflow(repository).preview(preview_command)
    command = ApplyServiceDayLog(
        9,
        "U-caregiver",
        12,
        preview_command.intent,
        "service-day-log-controlled",
        preview.preview_fingerprint,
        controlled_file_attachments=(attachment,),
    )

    result = ServiceDayLogWorkflow(repository).apply(command)

    assert preview.can_apply is True
    assert result.outcome == "created"


def test_unknown_cooking_requirement_fails_closed() -> None:
    repository = FakeRepository(None)

    preview = ServiceDayLogWorkflow(repository).preview(_preview_command())

    assert preview.blockers == ("service_day_log_cooking_requirement_unresolved",)
    assert repository.submitted == []


def test_query_fails_closed_for_another_staff() -> None:
    workflow = ServiceDayLogWorkflow(FakeRepository(False))

    with pytest.raises(ValueError, match="service_day_log_not_found"):
        workflow.query(1, 10, "U-other")


def test_apply_rejects_stale_preview_before_submit() -> None:
    repository = FakeRepository(False)
    command = ApplyServiceDayLog(9, "U-caregiver", 12, _preview_command().intent, "service-day-log-1", PreviewFingerprint("0" * 64))

    with pytest.raises(ValueError, match="service_day_log_preview_stale"):
        ServiceDayLogWorkflow(repository).apply(command)

    assert repository.submitted == []


def test_apply_rejects_cooking_case_without_media_capability() -> None:
    repository = FakeRepository(True)
    workflow = ServiceDayLogWorkflow(repository)
    preview = workflow.preview(_preview_command())
    command = ApplyServiceDayLog(9, "U-caregiver", 12, _preview_command().intent, "service-day-log-1", preview.preview_fingerprint)

    with pytest.raises(ValueError, match="service_day_log_meal_photo_required"):
        workflow.apply(command)

    assert repository.submitted == []


def test_terminal_replay_is_returned_before_fresh_fact_validation() -> None:
    repository = FakeRepository(None)
    terminal = ServiceDayLogResult(1, "CASE-1", 12, "2026-08-16", "寶寶今日狀況正常", False, "existing")
    repository.load_replay = lambda _command: terminal
    command = ApplyServiceDayLog(9, "U-caregiver", 12, _preview_command().intent, "service-day-log-1", PreviewFingerprint("0" * 64))

    result = ServiceDayLogWorkflow(repository).apply(command)

    assert result is terminal
    assert not hasattr(repository, "for_update")

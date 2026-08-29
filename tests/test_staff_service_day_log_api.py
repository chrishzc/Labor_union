"""File: test_staff_service_day_log_api.py
Description: 驗證月嫂寶寶日誌 API 只以已驗證綁定身分建立 Scheduling command。"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import staff_service_day_logs
from api.schemas.line_staff_self_service import StaffServiceDayLogApplyRequest, StaffServiceDayLogPreviewRequest
from domains.line.identities import LineUserId
from subsystems.scheduling.service_day_log_workflow import ServiceDayLogResult


def test_legacy_direct_service_day_log_submit_is_retired() -> None:
    with pytest.raises(HTTPException) as captured:
        staff_service_day_logs.retired_direct_service_day_log()

    assert captured.value.status_code == 410
    assert captured.value.detail["code"] == "service_day_log_direct_submit_retired"


def test_apply_service_day_log_builds_a_bound_staff_command(monkeypatch) -> None:
    recorded = {}

    @contextmanager
    def line_uow():
        yield SimpleNamespace(
            customer_service=SimpleNamespace(
                staff_subject=lambda user_id: {"staff_id": 8, "staff_name": "月嫂"}
            ),
        )

    class Application:
        def apply(self, command):
            recorded["command"] = command
            recorded["scheduling_committed"] = True
            return ServiceDayLogResult(44, "CASE-44", 71, "2026-08-16", "寶寶已完成日誌", False, "created")

    monkeypatch.setattr(staff_service_day_logs, "open_line_unit_of_work", line_uow)
    monkeypatch.setattr(staff_service_day_logs, "_verified_line_user_id", lambda _body: LineUserId("U-caregiver"))

    response = staff_service_day_logs.apply_service_day_log(
        StaffServiceDayLogApplyRequest(
            assignment_id=71,
            service_date="2026-08-16",
            baby_log_text="寶寶已完成日誌",
            preview_fingerprint="a" * 64,
        ),
        "service-day-log-44",
        Application(),
    )

    assert response.data["receipt"]["log_id"] == 44
    assert recorded["command"].staff_id == 8
    assert recorded["command"].line_user_id == "U-caregiver"
    assert recorded["command"].intent.meal_photo_media_ids == ()
    assert recorded["scheduling_committed"] is True


def test_preview_service_day_log_is_read_only_and_returns_typed_blocker(monkeypatch) -> None:
    recorded = {}

    @contextmanager
    def line_uow():
        yield SimpleNamespace(customer_service=SimpleNamespace(staff_subject=lambda _user_id: {"staff_id": 8}))

    class Application:
        def preview(self, command):
            recorded["command"] = command
            return SimpleNamespace(case_no="CASE-44", assignment_id=71, service_date="2026-08-16", baby_log_text="寶寶已完成日誌", requires_cooking=True, can_apply=False, blockers=("service_day_log_meal_photo_required",), preview_fingerprint=SimpleNamespace(value="b" * 64))

    monkeypatch.setattr(staff_service_day_logs, "open_line_unit_of_work", line_uow)
    monkeypatch.setattr(staff_service_day_logs, "_verified_line_user_id", lambda _body: LineUserId("U-caregiver"))

    response = staff_service_day_logs.preview_service_day_log(
        StaffServiceDayLogPreviewRequest(assignment_id=71, service_date="2026-08-16", baby_log_text="寶寶已完成日誌"),
        Application(),
    )

    assert response.data["can_apply"] is False
    assert response.data["blockers"] == ["service_day_log_meal_photo_required"]
    assert recorded["command"].intent.meal_photo_media_ids == ()

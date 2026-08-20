"""File: test_staff_service_day_log_api.py
Description: 驗證月嫂寶寶日誌 API 只以已驗證綁定身分建立 Scheduling command。"""

from contextlib import contextmanager
from types import SimpleNamespace

from api.routes import staff_service_day_logs
from api.schemas.line_staff_self_service import StaffServiceDayLogCreate
from domains.line.identities import LineUserId
from subsystems.scheduling.service_day_log_workflow import ServiceDayLogResult


def test_submit_service_day_log_builds_a_bound_staff_command(monkeypatch) -> None:
    recorded = {}

    @contextmanager
    def line_uow():
        yield SimpleNamespace(
            customer_service=SimpleNamespace(
                staff_subject=lambda user_id: {"staff_id": 8, "staff_name": "月嫂"}
            ),
            commit=lambda: recorded.setdefault("line_committed", True),
        )

    class SchedulingUow:
        def __init__(self, connection) -> None:
            assert connection is recorded["connection"]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            recorded["scheduling_committed"] = True

    class Workflow:
        def __init__(self, _repository) -> None:
            pass

        def submit(self, command):
            recorded["command"] = command
            return ServiceDayLogResult(44, "CASE-44", "2026-08-16", True, "created")

    connection = SimpleNamespace(close=lambda: recorded.setdefault("closed", True))
    recorded["connection"] = connection
    monkeypatch.setattr(staff_service_day_logs, "open_line_unit_of_work", line_uow)
    monkeypatch.setattr(staff_service_day_logs, "get_connection", lambda: connection)
    monkeypatch.setattr(staff_service_day_logs, "MySqlUnitOfWork", SchedulingUow)
    monkeypatch.setattr(staff_service_day_logs, "MySqlServiceDayLogRepository", lambda _connection: object())
    monkeypatch.setattr(staff_service_day_logs, "ServiceDayLogWorkflow", Workflow)
    monkeypatch.setattr(staff_service_day_logs, "_verified_line_user_id", lambda _body: LineUserId("U-caregiver"))

    response = staff_service_day_logs.submit_service_day_log(
        StaffServiceDayLogCreate(
            assignment_id=71,
            service_date="2026-08-16",
            baby_log_text="寶寶已完成日誌",
            meal_photo_media_ids=["media-1"],
        ),
        "service-day-log-44",
    )

    assert response.data["log_id"] == 44
    assert recorded["command"].staff_id == 8
    assert recorded["command"].line_user_id == "U-caregiver"
    assert recorded["command"].intent.meal_photo_media_ids == ("media-1",)
    assert recorded["scheduling_committed"] is True
    assert recorded["closed"] is True

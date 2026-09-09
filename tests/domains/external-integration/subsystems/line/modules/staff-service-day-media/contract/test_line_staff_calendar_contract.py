"""
File: test_line_staff_calendar_contract.py
Description: 驗證月嫂 LIFF 班表的 typed 狀態與正式 Scheduling 可見語意。
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routes import line_staff_self_service
from api.schemas.line_staff_self_service import StaffLiffRequest, StaffScheduleDayView
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def _day(**overrides) -> dict:
    return {
        "work_date": "2026-08-24",
        "status": "available",
        "staff_id": 7,
        "is_work_day": False,
        "is_double_pay": False,
        **overrides,
    }


def test_staff_schedule_day_status_is_closed_and_unavailability_is_typed() -> None:
    unavailable = StaffScheduleDayView.model_validate(
        _day(
            status="staff_unavailability",
            unavailability_block_id=31,
            unavailability_kind="long_leave",
            unavailability_reason="返鄉休息",
        )
    )

    assert unavailable.unavailability_block_id == 31
    assert unavailable.unavailability_kind == "long_leave"
    assert unavailable.unavailability_reason == "返鄉休息"
    with pytest.raises(ValidationError):
        StaffScheduleDayView.model_validate(_day(status="unknown_calendar_state"))


def test_staff_schedule_page_distinguishes_waiting_lock_rest_and_unavailability() -> None:
    source = (ROOT / "line" / "static" / "staff_schedule.html").read_text(
        encoding="utf-8"
    )

    assert "已鎖定／待成立" in source
    assert "正式不可服務" in source
    assert "休息日" in source
    assert "休息/請假" not in source
    assert 'item.status === "waiting_deposit_lock"' in source
    assert 'item.status === "staff_unavailability"' in source


def test_staff_schedule_mutations_use_typed_preview_apply_readback() -> None:
    schedule = (ROOT / "line" / "static" / "staff_schedule.html").read_text(
        encoding="utf-8"
    )
    baby_log = (ROOT / "line" / "static" / "staff_baby_log.html").read_text(
        encoding="utf-8"
    )

    assert "function requireStaffSchedule" in schedule
    assert ".innerHTML" not in schedule and ".innerHTML" not in baby_log
    assert "/leave-requests/preview" in schedule
    assert "/leave-requests/apply" in schedule
    assert "/leave-requests/${result.data.request_id}/query" in schedule
    assert schedule.index("/leave-requests/preview") < schedule.index("/leave-requests/apply")
    assert "confirmLeave" in schedule
    assert 'idempotencyKey: `staff-leave-${crypto.randomUUID()}`' in schedule
    assert '"Idempotency-Key": candidate.idempotencyKey' in schedule
    assert "/service-day-logs/preview" not in schedule
    assert "/service-day-logs/preview" in baby_log
    assert "/service-day-logs/apply" in baby_log
    assert "/service-day-logs/${committed.log_id}/query" in baby_log
    assert "送出結果尚未確認。請勿重複送出" in baby_log
    assert "日誌已送出，但目前無法重新讀取結果。請勿重複送出" in baby_log
    assert "/service-day-media" in baby_log
    assert "受控檔案 staging" in baby_log
    assert "requires_cooking" in baby_log
    assert "selectServiceDay" in baby_log
    assert "Preview 指紋" not in baby_log
    assert 'id="babyLog"' in baby_log and 'placeholder="選擇服務日後填寫" disabled' in baby_log
    assert 'id="mealPhoto"' in baby_log and 'accept="image/jpeg,image/png" disabled' in baby_log


def test_staff_self_service_queries_never_commit() -> None:
    source = (ROOT / "api" / "routes" / "line_staff_self_service.py").read_text(
        encoding="utf-8"
    )

    query_source = source.split("def order_search", 1)[1].split("def _required_staff", 1)[0]
    flow_query_source = source.split("def _verified_staff_self_service_flow", 1)[1].split(
        "def _development_fallback_enabled", 1
    )[0]
    assert "unit_of_work.commit()" not in query_source
    assert "unit_of_work.commit()" not in flow_query_source


def test_staff_liff_invalid_token_returns_staff_specific_typed_error(monkeypatch) -> None:
    verifier = SimpleNamespace(
        verify=lambda _: (_ for _ in ()).throw(InvalidLiffTokenError("provider detail"))
    )
    monkeypatch.setattr(line_staff_self_service, "get_liff_token_verifier", lambda: verifier)

    with pytest.raises(HTTPException) as captured:
        line_staff_self_service._verified_line_user_id(
            StaffLiffRequest(line_id_token="signed-token")
        )

    assert captured.value.status_code == 401
    assert captured.value.detail["error"]["code"] == "liff_token_invalid"
    assert "管理員" not in captured.value.detail["error"]["message"]
    assert "provider detail" not in captured.value.detail["error"]["message"]

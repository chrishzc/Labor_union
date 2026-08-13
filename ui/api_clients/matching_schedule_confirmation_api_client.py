"""Typed Streamlit client for matching schedule confirmation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse


class ScheduleConfirmationRecipientView(BaseModel):
    recipient_snapshot_id: int
    audience_type: str
    segment_id: int | None
    delivery_status: str
    confirmation_status: str
    confirmation_source: str | None
    confirmation_reason: str | None
    confirmation_occurred_at_utc: datetime | None


class ExpectedServiceScheduleWeekView(BaseModel):
    week_number: int
    period_start: str
    period_end: str
    service_dates: list[str]
    service_day_count: int


class ScheduleConfirmationRecipientScheduleView(BaseModel):
    audience_type: str
    segment_id: int | None
    total_service_days: int
    total_weeks: int
    weeks: list[ExpectedServiceScheduleWeekView]


class ExpectedServiceSchedulePreviewView(BaseModel):
    week_grouping_policy: str
    total_service_days: int
    total_weeks: int
    weeks: list[ExpectedServiceScheduleWeekView]
    recipient_schedules: list[ScheduleConfirmationRecipientScheduleView]


class MatchingScheduleConfirmationView(BaseModel):
    case_no: str
    plan_id: int
    confirmed_service_date_version: int
    snapshot_id: int | None
    snapshot_status: str
    schedule_preview: ExpectedServiceSchedulePreviewView
    outdated_schedule_preview: ExpectedServiceSchedulePreviewView | None = None
    recipients: list[ScheduleConfirmationRecipientView]
    gate_passed: bool


@dataclass(slots=True)
class MatchingScheduleConfirmationApiError(RuntimeError):
    status_code: int | None
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class MatchingScheduleConfirmationApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._session = session or requests.Session()

    def query(self, case_no: str, plan_id: int) -> MatchingScheduleConfirmationView:
        return self._request("GET", _plan_path(case_no, plan_id))

    def send(
        self, case_no: str, plan_id: int, *, idempotency_key: str
    ) -> MatchingScheduleConfirmationView:
        return self._request(
            "POST",
            _plan_path(case_no, plan_id) + "/send",
            idempotency_key=idempotency_key,
        )

    def confirm(
        self,
        recipient_id: int,
        value: str,
        reason: str,
        *,
        idempotency_key: str,
    ) -> MatchingScheduleConfirmationView:
        return self._request(
            "PUT",
            f"/api/v1/orders/schedule-confirmation/recipients/{recipient_id}",
            payload={"value": value, "reason": reason},
            idempotency_key=idempotency_key,
        )

    def _request(self, method, path, *, payload=None, idempotency_key=None):
        headers = dict(self._headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self._session.request(
                method,
                self._base_url + path,
                headers=headers,
                json=payload,
                timeout=15,
            )
        except requests.RequestException as error:
            raise MatchingScheduleConfirmationApiError(
                None,
                "matching_schedule_confirmation_transport_error",
                "無法連線至日期表確認 API。",
            ) from error
        if not response.ok:
            raise _http_error(response)
        try:
            envelope = BaseResponse[MatchingScheduleConfirmationView].model_validate(
                response.json()
            )
        except (TypeError, ValidationError, ValueError) as error:
            raise MatchingScheduleConfirmationApiError(
                response.status_code,
                "matching_schedule_confirmation_invalid_response",
                "日期表確認 API 回傳格式不正確。",
            ) from error
        if not envelope.success or envelope.data is None:
            raise MatchingScheduleConfirmationApiError(
                response.status_code,
                "matching_schedule_confirmation_invalid_response",
                "日期表確認 API 回傳格式不正確。",
            )
        return envelope.data


def _plan_path(case_no: str, plan_id: int) -> str:
    return f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/schedule-confirmation"


def _http_error(response) -> MatchingScheduleConfirmationApiError:
    try:
        detail = response.json().get("detail")
        code = detail.get("code") if isinstance(detail, dict) else None
    except (TypeError, ValueError):
        code = None
    return MatchingScheduleConfirmationApiError(
        response.status_code,
        str(code or "matching_schedule_confirmation_request_failed"),
        _error_message(code),
    )


def _error_message(code: object) -> str:
    if code == "confirmed_service_dates_required":
        return "尚未在訂單管理確認服務日期，不能發送日期表。"
    if isinstance(code, str) and code.startswith(
        "matching_schedule_recipient_line_binding_required:"
    ):
        return "客戶或月嫂尚未完成 LINE 綁定，不能發送日期表。"
    return "日期表確認請求失敗。"

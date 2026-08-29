"""
File: holidays.py
Description: 暴露國定假日 typed Query、零寫入 Preview 與 single-UoW Apply HTTP 邊界。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from api.dependencies.admin_auth import require_admin
from api.dependencies.holidays import get_holiday_maintenance_application
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.holidays import (
    HolidayApplyRequest,
    HolidayCalendarView,
    HolidayPreviewRequest,
    HolidayPreviewView,
    HolidayReceiptView,
    HolidayRowView,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling import holiday_maintenance
from subsystems.scheduling.holiday_calendar_query import (
    HolidayCalendarFacts,
    HolidayCalendarUnavailable,
    HolidayFact,
)
from subsystems.scheduling.holiday_query_cache import query_holidays

router = APIRouter(prefix="/api/v1/holidays", tags=["Holidays 國定假日設定"])
_LEGACY_FROM = date(1900, 1, 1)
_LEGACY_TO = date(9999, 12, 31)
_QUERY_ERRORS = {
    401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
    403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢國定假日"},
    422: {"model": GlobalTypedErrorResponseView, "description": "查詢horizon不符合契約"},
    500: {"model": GlobalTypedErrorResponseView, "description": "國定假日查詢失敗"},
    503: {"model": GlobalTypedErrorResponseView, "description": "國定假日根事實無法讀取"},
}
_COMMAND_ERRORS = {
    **_QUERY_ERRORS,
    404: {"model": GlobalTypedErrorResponseView, "description": "找不到指定國定假日"},
    409: {"model": GlobalTypedErrorResponseView, "description": "預覽過期或冪等鍵衝突"},
}


@router.get(
    "",
    response_model=BaseResponse[HolidayCalendarView | list[HolidayRowView]],
    responses=_QUERY_ERRORS,
)
def get_all_holidays(
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    principal: AdminPrincipal = Depends(require_admin),
):
    del principal
    requested_range = from_date is not None or to_date is not None
    if (from_date is None) != (to_date is None):
        raise typed_http_error(
            422,
            "validation",
            "holiday_horizon_pair_required",
            "from_date 與 to_date 必須同時提供。",
            "holiday-query",
        )
    start, end = (from_date, to_date) if requested_range else (_LEGACY_FROM, _LEGACY_TO)
    if start > end:
        raise typed_http_error(
            422,
            "validation",
            "holiday_horizon_invalid",
            "國定假日查詢區間不正確。",
            "holiday-query",
        )
    connection = get_connection()
    try:
        calendar = query_holidays(MySqlSchedulingHolidayQuery(connection), start, end)
        data = _calendar_payload(calendar, start, end) if requested_range else [
            _fact_payload(item) for item in calendar.holidays
        ]
        return BaseResponse(data=data, message="成功取得國定假日列表")
    except HolidayCalendarUnavailable as error:
        raise typed_http_error(
            503,
            "unavailable",
            "holiday_calendar_unavailable",
            "國定假日根事實目前無法讀取。",
            "holiday-query",
            retryable=True,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "holiday_query_internal_error",
            "國定假日查詢失敗。",
            "holiday-query",
        ) from error
    finally:
        connection.close()


@router.post(
    "/preview",
    response_model=BaseResponse[HolidayPreviewView],
    responses=_COMMAND_ERRORS,
)
def preview_holiday_change(
    req: HolidayPreviewRequest,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", max_length=191)],
    principal: AdminPrincipal = Depends(require_admin),
    application: holiday_maintenance.HolidayMaintenanceApplication = Depends(
        get_holiday_maintenance_application
    ),
):
    del principal
    try:
        result = application.preview(_command(req))
        return BaseResponse(data=_preview_payload(result), message="已產生國定假日變更預覽")
    except holiday_maintenance.HolidayWorkflowError as error:
        _raise_workflow_error(error, correlation_id)
    except HolidayCalendarUnavailable as error:
        raise typed_http_error(
            503,
            "unavailable",
            "holiday_calendar_unavailable",
            "國定假日根事實目前無法讀取。",
            correlation_id,
            retryable=True,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "holiday_preview_internal_error",
            "國定假日預覽失敗。",
            correlation_id,
        ) from error


@router.post(
    "/apply",
    response_model=BaseResponse[HolidayReceiptView],
    responses=_COMMAND_ERRORS,
)
def apply_holiday_change(
    req: HolidayApplyRequest,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ],
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ],
    principal: AdminPrincipal = Depends(require_admin),
    application: holiday_maintenance.HolidayMaintenanceApplication = Depends(
        get_holiday_maintenance_application
    ),
):
    try:
        result = application.apply(
            _command(req),
            req.expected_calendar_version,
            req.preview_fingerprint,
            idempotency_key,
            str(principal.username or "").strip(),
            req.reason,
        )
    except holiday_maintenance.HolidayWorkflowError as error:
        _raise_workflow_error(error, correlation_id)
    except HolidayCalendarUnavailable as error:
        raise typed_http_error(
            503,
            "unavailable",
            "holiday_calendar_unavailable",
            "國定假日根事實目前無法讀取。",
            correlation_id,
            retryable=True,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "holiday_apply_internal_error",
            "國定假日套用失敗。",
            correlation_id,
        ) from error
    return BaseResponse(data=_receipt_payload(result), message="已套用國定假日變更")


def _command(req: HolidayPreviewRequest) -> holiday_maintenance.HolidayCommand:
    return holiday_maintenance.HolidayCommand(
        req.action,
        req.holiday_date,
        req.holiday_name,
        req.is_double_pay_default,
        req.from_date,
        req.to_date,
    )


def _calendar_payload(calendar: HolidayCalendarFacts, start: date, end: date) -> dict:
    return {
        "planning_horizon": {"from_date": start, "to_date": end},
        "source_identity": calendar.source_identity,
        "calendar_version": calendar.holiday_version,
        "holidays": [_fact_payload(item) for item in calendar.holidays],
    }


def _fact_payload(fact: HolidayFact) -> dict:
    return {
        "holiday_date": fact.holiday_date,
        "holiday_name": fact.holiday_name,
        "is_double_pay_default": fact.is_double_pay_default,
    }


def _preview_payload(result: holiday_maintenance.HolidayPreview) -> dict:
    command = result.command
    return {
        "command": {
            "action": command.action,
            "holiday_date": command.holiday_date,
            "holiday_name": command.holiday_name,
            "is_double_pay_default": command.is_double_pay_default,
            "from_date": command.from_date,
            "to_date": command.to_date,
            "expected_calendar_version": result.calendar.holiday_version,
        },
        "before": _fact_payload(result.before) if result.before else None,
        "planning_horizon": {
            "from_date": command.from_date,
            "to_date": command.to_date,
        },
        "source_identity": result.calendar.source_identity,
        "calendar_version": result.calendar.holiday_version,
        "schedule_impact": "none",
        "payroll_impact": "none",
        "preview_fingerprint": result.preview_fingerprint,
    }


def _receipt_payload(result: holiday_maintenance.HolidayReceipt) -> dict:
    return {
        "receipt_key": result.receipt_key,
        "action": result.action,
        "holiday_date": result.holiday_date,
        "changed": result.changed,
        "planning_horizon": {
            "from_date": result.from_date,
            "to_date": result.to_date,
        },
        "source_identity": result.source_identity,
        "previous_calendar_version": result.previous_calendar_version,
        "resulting_calendar_version": result.resulting_calendar_version,
        "preview_fingerprint": result.preview_fingerprint,
    }


def _raise_workflow_error(error, correlation_id: str) -> None:
    status, category = {
        "holiday_not_found": (404, "not_found"),
        "stale_preview": (409, "conflict"),
        "idempotency_key_conflict": (409, "idempotency_mismatch"),
    }.get(error.code, (422, "validation"))
    raise typed_http_error(
        status,
        category,
        error.code,
        "國定假日變更請求未通過契約驗證。",
        correlation_id,
    ) from error

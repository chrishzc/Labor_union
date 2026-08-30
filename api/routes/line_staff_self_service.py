"""Verified LIFF APIs for caregiver order and schedule queries."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from api.error_contracts import typed_http_error
from api.dependencies.line_identity import get_liff_token_verifier
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import (
    StaffLiffRequest,
    StaffOrderPageView,
    StaffOrderSearchRequest,
    StaffScheduleView,
)
from domains.line.identities import LineUserId
from domains.line.identity_flow import (
    LineIdentityFlowId,
    LineIdentityFlowPurpose,
    validate_identity_flow,
)
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError,
    LiffVerificationUnavailableError,
)
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.scheduling import staff_monthly_calendar_query as _staff_monthly_calendar_query
from subsystems.scheduling.staff_monthly_calendar_query import get_staff_monthly_calendar_schedule


_staff_monthly_calendar_query.get_connection = get_connection


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["LINE Staff Self Service"])


@router.post("/orders", response_model=BaseResponse[StaffOrderPageView])
def order_search(payload: StaffOrderSearchRequest):
    line_user_id = _verified_line_user_id(payload)
    with open_line_unit_of_work() as unit_of_work:
        staff = _required_staff(unit_of_work.customer_service.staff_subject(line_user_id.value))
        items = unit_of_work.customer_service.staff_orders(int(staff["staff_id"]), payload.keyword.strip())
    return BaseResponse(data={"staff_id": int(staff["staff_id"]), "staff_name": staff["staff_name"], "items": items})


@router.post("/schedule", response_model=BaseResponse[StaffScheduleView])
def monthly_schedule(
    payload: StaffLiffRequest,
    year: int = Query(ge=1900, le=2100),
    month: int = Query(ge=1, le=12),
):
    line_user_id = _verified_line_user_id(payload)
    with open_line_unit_of_work() as unit_of_work:
        staff = _required_staff(unit_of_work.customer_service.staff_subject(line_user_id.value))
    schedule = get_staff_monthly_calendar_schedule(int(staff["staff_id"]), year, month)
    return BaseResponse(data={**schedule, "staff_name": staff["staff_name"]})


def _required_staff(staff):
    if not staff:
        raise typed_http_error(
            403,
            "forbidden",
            "line_staff_binding_not_found",
            "此 LINE 帳號尚未綁定月嫂身分，請聯絡工會人員確認。",
            "line-staff-self-service:binding",
        )
    return staff


def _verified_line_user_id(payload) -> LineUserId:
    token = payload.line_id_token.strip()
    if token:
        try:
            return get_liff_token_verifier().verify(token).line_user_id
        except InvalidLiffTokenError as error:
            raise typed_http_error(
                401,
                "forbidden",
                "liff_token_invalid",
                "LINE 登入狀態已失效或與此 LIFF 不一致，請重新登入 LINE。",
                "line-staff-self-service:liff-token-invalid",
            ) from error
        except LiffVerificationUnavailableError as error:
            raise typed_http_error(
                503,
                "unavailable",
                "liff_verification_unavailable",
                "LINE 身分驗證服務暫時無法連線，請稍後再試。",
                "line-staff-self-service:liff-verification-unavailable",
                retryable=True,
            ) from error
    flow_id = payload.flow_id.strip()
    if flow_id:
        return _verified_staff_self_service_flow(flow_id)
    fallback = payload.development_line_user_id.strip()
    if fallback and _development_fallback_enabled():
        return LineUserId(fallback)
    raise typed_http_error(
        401,
        "forbidden",
        "liff_token_required",
        "缺少有效的 LINE 登入狀態，請重新從 LINE 開啟此頁。",
        "line-staff-self-service:liff-token-required",
    )


def _verified_staff_self_service_flow(flow_id: str) -> LineUserId:
    with open_line_unit_of_work() as unit_of_work:
        snapshot = unit_of_work.identity_flows.get(LineIdentityFlowId(flow_id))
    if snapshot is None:
        raise HTTPException(status_code=401, detail={"code": "line_flow_not_found", "message": "LINE 操作連結無效，請重新從圖文選單開啟"})
    try:
        validate_identity_flow(
            snapshot,
            purpose=LineIdentityFlowPurpose.STAFF_SELF_SERVICE,
            line_user_id=snapshot.line_user_id,
            now=datetime.now(UTC),
        )
    except ValueError as error:
        raise HTTPException(status_code=401, detail={"code": "line_flow_invalid", "message": str(error)}) from error
    return snapshot.line_user_id


def _development_fallback_enabled():
    environment = os.getenv("APP_ENV", "development").strip().lower()
    required = os.getenv("LIFF_REQUIRE_ID_TOKEN", "true").strip().lower()
    return environment in {"development", "dev", "local", "test"} and required in {"0", "false", "no", "off"}


__all__ = ["router"]

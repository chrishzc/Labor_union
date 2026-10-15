"""Admin Query/Preview/Apply for completed official service date corrections."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import IntegrityError, OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.official_service_date_correction import (
    get_official_service_date_correction_workflow,
)
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.official_service_date_correction_workflow import (
    OfficialDateMonetaryImpactBlocked,
    OfficialDateSelection,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Official Service Date Correction"])


class AssignmentDatesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment_id: int = Field(gt=0)
    service_dates: tuple[date, ...] = Field(min_length=1)


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignments: tuple[AssignmentDatesBody, ...] = Field(min_length=1)


class ApplyBody(PreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


@router.get("/{case_no}/official-service-dates", response_model=BaseResponse[dict[str, Any]])
def query_official_service_dates(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_official_service_date_correction_workflow),
):
    del principal
    return _call(lambda: _facts_payload(workflow.query(case_no)))


@router.post("/{case_no}/official-service-dates/preview", response_model=BaseResponse[dict[str, Any]])
def preview_official_service_dates(
    body: PreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_official_service_date_correction_workflow),
):
    del principal
    return _call(lambda: _preview_payload(workflow.preview(case_no, _selections(body))))


@router.post("/{case_no}/official-service-dates/apply", response_model=BaseResponse[dict[str, Any]])
def apply_official_service_dates(
    body: ApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow=Depends(get_official_service_date_correction_workflow),
):
    return _call(lambda: _receipt_payload(workflow.apply(
        case_no, _selections(body),
        expected_order_version=body.expected_order_version,
        expected_scheduling_version=body.expected_scheduling_version,
        preview_fingerprint=body.preview_fingerprint,
        actor=str(principal.username or "").strip(),
        reason=body.reason.strip(),
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )))


def _selections(body: PreviewBody) -> tuple[OfficialDateSelection, ...]:
    return tuple(OfficialDateSelection(item.assignment_id, item.service_dates) for item in body.assignments)


def _facts_payload(facts) -> dict[str, Any]:
    return {
        "case_no": facts.case_no,
        "order_version": facts.order_version,
        "scheduling_version": facts.scheduling_version,
        "generation_id": facts.generation_id,
        "order_status": facts.order_status,
        "service_data_locked": facts.service_data_locked,
        "actual_end_date": facts.actual_end_date,
        "assignments": [{
            "assignment_id": item.assignment_id,
            "staff_id": item.staff_id,
            "staff_name": item.staff_name,
            "service_dates": item.service_dates,
        } for item in facts.assignments],
        "monetary_change_blocker": facts.monetary_change_blocker,
        "monetary_blockers": [{"code": code, **_MONETARY_BLOCKERS[code]} for code in facts.monetary_blockers],
        "history": [{
            "event_id": item.event_id,
            "event_type": item.event_type,
            "recorded_at": item.recorded_at,
            "actor": item.actor,
            "before_dates": item.before_dates,
            "after_dates": item.after_dates,
            "reason": item.reason,
            "completion_instant": item.completion_instant,
        } for item in facts.history],
    }


def _preview_payload(preview) -> dict[str, Any]:
    return {
        **_facts_payload(preview.facts),
        "proposed_assignments": [{
            "assignment_id": item.assignment_id,
            "service_dates": item.service_dates,
        } for item in preview.selections],
        "finance_impact": preview.finance_impact,
        "payroll_impact": preview.payroll_impact,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _receipt_payload(receipt) -> dict[str, Any]:
    return {
        "case_no": receipt.case_no,
        "order_version": receipt.order_version,
        "scheduling_version": receipt.scheduling_version,
        "generation_id": receipt.generation_id,
        "effective_assignments": [{
            "assignment_id": item.assignment_id,
            "service_dates": item.service_dates,
        } for item in receipt.effective_dates],
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


_MONETARY_BLOCKERS = {
    "special_pay": {"message": "已有特殊薪資紀錄，純日期更正尚不能處理其薪資影響。", "repair_target": "payroll"},
    "payroll_adjustments": {"message": "已有薪資調整分攤，純日期更正尚不能處理其金額影響。", "repair_target": "payroll"},
    "subsidy_return": {"message": "已有補助退還義務，純日期更正尚不能處理其補助影響。", "repair_target": "subsidy"},
    "source_rate_snapshot_missing_or_ambiguous": {"message": "原排班的薪資快照缺漏或不唯一，無法確認更正後沿用原薪資。", "repair_target": "case_profile"},
    "double_pay": {"message": "原正式服務日含雙倍薪，純日期更正尚不能處理其薪資影響。", "repair_target": "payroll"},
    "floor_fee": {"message": "原排班已分配樓層費，純日期更正尚不能處理其費用影響。", "repair_target": "case_profile"},
}


_VALIDATION_MESSAGES = {
    'official_date_no_change': '更正日期與目前正式服務日期相同，無需更正；請先修改需要補正的日期，再重新預覽。',
    'official_date_dates_not_canonical': '同一位月嫂的服務日期不能重複或留白，請修正日期後重新預覽。',
    'official_date_service_days_changed': '更正後的服務天數或各月嫂分配天數與原紀錄不一致，請保持原天數並排除重複日期。',
    'official_date_actual_start_change_unsupported': '純日期更正不能改變實際開始日，請保留原第一個服務日期後重新預覽。',
    'official_date_future_completed_service_blocked': '已完工的服務日期不能晚於今天，請核對實際服務日期後重新預覽。',
    'official_date_monetary_impact_unsupported': '本案含特殊薪資或其他金額影響，無法使用純日期更正；請保留原日期並交由管理員核對。',
    'official_date_completed_assignment_required': '本案必須已完工且有正式排班，才能更正完工服務日期；請返回案件處理核對狀態。',
    'official_date_assignment_allocation_invalid': '目前月嫂與排班區段和更正內容不一致，請重新讀取排班日期後再預覽。',
    'official_date_effective_generation_required': '本案缺少有效正式排班，請返回案件處理核對排班紀錄。',
    'official_date_effective_generation_conflict': '本案有效正式排班已變更，請重新讀取排班日期後再預覽。',
    'official_date_schedule_ownership_invalid': '服務日期的月嫂或排班歸屬不一致，請重新讀取排班日期；若仍有問題，請由管理員核對排班紀錄。',
    'official_date_schedule_incomplete': '正式排班缺少完整服務日期，請返回案件處理核對各月嫂的服務紀錄。',
    'official_date_occupancy_conflict': '更正日期與月嫂其他案件的正式排班衝突，請改選沒有衝突的日期後重新預覽。',
    'official_date_version_conflict': '案件或排班已被更新，請重新讀取排班日期並重新預覽。',
    'official_date_preview_stale': '預覽後的案件或排班已變更，請重新讀取排班日期並重新預覽。',
    'official_date_idempotency_mismatch': '這次操作識別已用於不同的更正內容，請重新讀取排班日期並重新預覽。',
}


def _call(operation):
    try:
        return BaseResponse(data=operation(), message="正式服務日期已取得或更正")
    except ValueError as error:
        code = str(error)
        if "idempotency" in code:
            status = 409
            category = "idempotency_mismatch"
        elif "conflict" in code or "stale" in code or "occupancy" in code:
            status = 409
            category = "conflict"
        elif "required" in code or "unsupported" in code or "blocked" in code:
            status = 409
            category = "domain_blocked"
        else:
            status = 422
            category = "validation"
        message = _VALIDATION_MESSAGES.get(code, '正式排班日期更正未通過驗證，請重新讀取排班日期；若仍有問題，請由管理員核對排班紀錄。')
        if isinstance(error, OfficialDateMonetaryImpactBlocked) and error.blockers:
            message = "；".join(_MONETARY_BLOCKERS[item]["message"] for item in error.blockers) + "請重新讀取排班日期，依原因前往對應入口核對。"
        raise typed_http_error(status, category, code, message, "official-service-date-correction") from error
    except IntegrityError as error:
        if error.args and error.args[0] == 1062:
            raise typed_http_error(409, "conflict", "official_date_occupancy_conflict", "目標日期已有正式排班。", "official-service-date-correction") from error
        raise typed_http_error(500, "internal", "official_date_database_error", "正式排班日期讀寫失敗。", "official-service-date-correction") from error
    except OperationalError as error:
        if error.args and error.args[0] in (1205, 1213):
            raise typed_http_error(503, "unavailable", "official_date_transaction_temporarily_unavailable", "更正交易暫時無法完成，請稍後重試。", "official-service-date-correction", retryable=True) from error
        raise typed_http_error(500, "internal", "official_date_database_error", "正式排班日期讀寫失敗。", "official-service-date-correction") from error
    except RuntimeError as error:
        code = str(error)
        if "conflict" in code:
            raise typed_http_error(409, "conflict", code, "資料已變動，請重新查詢及預覽。", "official-service-date-correction") from error
        raise typed_http_error(500, "internal", "official_date_internal_error", "正式排班日期更正未完成。", "official-service-date-correction") from error

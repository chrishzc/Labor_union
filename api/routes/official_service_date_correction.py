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
from subsystems.orders.official_service_date_correction_workflow import OfficialDateSelection


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
        raise typed_http_error(status, category, code, "正式排班日期更正未通過驗證，請重新查詢。", "official-service-date-correction") from error
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

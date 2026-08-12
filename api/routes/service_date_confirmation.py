"""Orders-owned confirmed service-date Query, Preview and Apply endpoints."""

from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from api.dependencies.admin_auth import require_system_admin
from api.dependencies.service_date_confirmation import get_service_date_confirmation_workflow
from api.schemas.base import BaseResponse
from api.schemas.service_date_confirmation import ServiceDateConfirmationPreviewView, ServiceDateConfirmationQueryView, ServiceDateConfirmationReceiptView
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/orders", tags=["Confirmed Service Dates"])


class ServiceDatePreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_dates: list[date] = Field(min_length=1)


class ServiceDateApplyBody(ServiceDatePreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=500)


@router.get("/{case_no}/service-dates", response_model=BaseResponse[ServiceDateConfirmationQueryView])
def query_service_dates(case_no: str = Path(..., min_length=1, max_length=50), principal: AdminPrincipal = Depends(require_system_admin), workflow=Depends(get_service_date_confirmation_workflow)):
    del principal
    facts = workflow.query(case_no)
    return BaseResponse(data={"case_no": facts.case_no, "order_version": facts.order_version, "scheduling_version": facts.scheduling_version, "contracted_service_days": facts.contracted_service_days, "suggested_dates": facts.suggested_dates, "selectable_dates": facts.selectable_dates, "current_version": facts.current_version, "current_dates": facts.current_dates}, message="成功取得服務日期確認狀態")


@router.post("/{case_no}/service-dates/preview", response_model=BaseResponse[ServiceDateConfirmationPreviewView])
def preview_service_dates(body: ServiceDatePreviewBody, case_no: str = Path(..., min_length=1, max_length=50), principal: AdminPrincipal = Depends(require_system_admin), workflow=Depends(get_service_date_confirmation_workflow)):
    del principal
    try:
        preview = workflow.preview(case_no, tuple(body.service_dates))
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": str(error)}) from error
    candidate = preview.candidate
    return BaseResponse(data={"case_no": candidate.case_no, "order_version": candidate.order_version, "scheduling_version": candidate.scheduling_version, "current_version": preview.current_version, "service_dates": candidate.service_dates, "weeks": preview.weeks, "preview_fingerprint": candidate.fingerprint.value}, message="成功產生服務日期確認 Preview")


@router.post("/{case_no}/service-dates/apply", response_model=BaseResponse[ServiceDateConfirmationReceiptView])
def apply_service_dates(body: ServiceDateApplyBody, case_no: str = Path(..., min_length=1, max_length=50), idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ..., principal: AdminPrincipal = Depends(require_system_admin), workflow=Depends(get_service_date_confirmation_workflow)):
    try:
        receipt = workflow.apply(case_no, tuple(body.service_dates), expected_order_version=body.expected_order_version, expected_scheduling_version=body.expected_scheduling_version, preview_fingerprint=body.preview_fingerprint, actor=str(principal.username or "").strip(), reason=body.reason.strip(), idempotency_key=idempotency_key)
    except ValueError as error:
        code = str(error)
        raise HTTPException(status_code=409 if "stale" in code or "conflict" in code else 422, detail={"code": code}) from error
    return BaseResponse(data={"case_no": receipt.case_no, "confirmed_version": receipt.confirmed_version, "order_version": receipt.order_version, "scheduling_version": receipt.scheduling_version, "service_dates": receipt.service_dates, "preview_fingerprint": receipt.fingerprint.value}, message="服務日期已確認")

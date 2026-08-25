"""
File: matching_schedule_confirmation.py
Description: 提供日期表 Query、LINE 發送、人工快照 Preview／Apply 與確認 API。
"""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from api.dependencies.admin_auth import require_system_admin
from api.dependencies.matching_schedule_confirmation import get_matching_schedule_confirmation_workflow
from api.schemas.base import BaseResponse

router = APIRouter(prefix="/api/v1/orders", tags=["Matching Schedule Confirmation"])

class ConfirmationBody(BaseModel):
    value: Literal["confirmed", "rejected", "manually_confirmed", "manually_revoked"]
    reason: str = Field(default="", max_length=500)


class ManualPreparationBody(BaseModel):
    confirmed_service_date_version: int = Field(gt=0)
    preview_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)

@router.get("/{case_no}/matching-plans/{plan_id}/schedule-confirmation")
def query(case_no: str, plan_id: int, principal=Depends(require_system_admin), workflow=Depends(get_matching_schedule_confirmation_workflow)):
    del principal
    try: return BaseResponse(data=workflow.query(case_no, plan_id), message="成功取得日期表確認狀態")
    except ValueError as error: raise HTTPException(409, detail={"code": str(error)}) from error

@router.post("/{case_no}/matching-plans/{plan_id}/schedule-confirmation/send")
def send(case_no: str, plan_id: int, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], principal=Depends(require_system_admin), workflow=Depends(get_matching_schedule_confirmation_workflow)):
    try: return BaseResponse(data=workflow.send(case_no, plan_id, str(principal.username or ""), idempotency_key), message="日期表已排入發送佇列")
    except ValueError as error: raise HTTPException(409, detail={"code": str(error)}) from error


@router.post("/{case_no}/matching-plans/{plan_id}/schedule-confirmation/manual-preview")
def preview_manual(case_no: str, plan_id: int, principal=Depends(require_system_admin), workflow=Depends(get_matching_schedule_confirmation_workflow)):
    del principal
    try: return BaseResponse(data=workflow.preview_manual(case_no, plan_id), message="成功產生人工日期表確認 Preview")
    except ValueError as error: raise HTTPException(409, detail={"code": str(error)}) from error


@router.post("/{case_no}/matching-plans/{plan_id}/schedule-confirmation/manual-apply")
def prepare_manual(case_no: str, plan_id: int, body: ManualPreparationBody, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], principal=Depends(require_system_admin), workflow=Depends(get_matching_schedule_confirmation_workflow)):
    try:
        return BaseResponse(
            data=workflow.prepare_manual(case_no, plan_id, str(principal.username or ""), body.reason, body.confirmed_service_date_version, body.preview_fingerprint, idempotency_key),
            message="人工日期表確認快照已建立",
        )
    except ValueError as error: raise HTTPException(409, detail={"code": str(error)}) from error

@router.put("/schedule-confirmation/recipients/{recipient_id}")
def confirm(recipient_id: int, body: ConfirmationBody, idempotency_key: Annotated[str, Header(alias="Idempotency-Key")], principal=Depends(require_system_admin), workflow=Depends(get_matching_schedule_confirmation_workflow)):
    try: return BaseResponse(data=workflow.confirm(recipient_id, body.value, str(principal.username or ""), body.reason, idempotency_key), message="日期表確認狀態已更新")
    except ValueError as error: raise HTTPException(409, detail={"code": str(error)}) from error

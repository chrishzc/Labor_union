"""File: staff_leave_management.py
Description: 提供工會人員處理 Scheduling 請假待辦的管理 API。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_leave_intake import get_staff_leave_intake_application
from api.schemas.base import BaseResponse
from api.schemas.staff_leave_management import (
    StaffLeaveInboxItemView,
    StaffLeaveReviewReceiptView,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.staff_leave_intake_workflow import ReviewStaffLeaveRequest, StaffLeaveIntakeApplication, StaffLeaveIntakeWorkflowError


router = APIRouter(prefix="/api/v1/scheduling/staff-leave-requests", tags=["Scheduling Staff Leave Intake"])


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    action: Literal["accept", "reject", "cancel"]
    reason: str = Field(default="", max_length=1000)


@router.get("", response_model=BaseResponse[list[StaffLeaveInboxItemView]])
def list_staff_leave_requests(
    status: Literal["pending", "accepted_for_processing", "rejected", "cancelled", "resolved"] = "pending",
    limit: int = Query(default=50, ge=1, le=100),
    principal: AdminPrincipal = Depends(require_admin),
):
    del principal
    connection = get_connection()
    try:
        return BaseResponse(data=MySqlStaffLeaveIntakeRepository(connection).list_requests(status, limit))
    finally:
        connection.close()


@router.post("/{request_id}/review", response_model=BaseResponse[StaffLeaveReviewReceiptView])
def review_staff_leave_request(
    request_id: int,
    body: ReviewBody,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
    principal: AdminPrincipal = Depends(require_admin),
    application: StaffLeaveIntakeApplication = Depends(get_staff_leave_intake_application),
):
    try:
        result = application.review(
            ReviewStaffLeaveRequest(request_id, body.expected_version, body.action, body.reason, False, str(principal.username), idempotency_key)
        )
    except StaffLeaveIntakeWorkflowError as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from error
    return BaseResponse(data={"request_id": result.request_id, "status": result.status.value, "version": result.version, "actor": str(principal.username)})

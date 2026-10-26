"""File: staff_leave_management.py
Description: 保留舊請假歷史查閱；舊受理／退回操作已退役。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_admin
from api.schemas.base import BaseResponse
from api.schemas.staff_leave_management import (
    StaffLeaveCoordinationContextView,
    StaffLeaveInboxItemView,
    StaffLeaveInboxPageView,
    StaffLeaveReviewReceiptView,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from subsystems.access.authentication_session import AdminPrincipal


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


def query_pending_staff_leave_page(*, page: int, page_size: int) -> BaseResponse[StaffLeaveInboxPageView]:
    connection = get_connection()
    try:
        items, total = MySqlStaffLeaveIntakeRepository(connection).pending_page(page=page, page_size=page_size)
        return BaseResponse(data=StaffLeaveInboxPageView(items=items, total=total, page=page, page_size=page_size))
    finally:
        connection.close()


@router.get("/{request_id}/coordination-context", response_model=BaseResponse[StaffLeaveCoordinationContextView])
def get_staff_leave_coordination_context(
    request_id: int,
    expected_version: int = Query(ge=1),
    principal: AdminPrincipal = Depends(require_admin),
):
    del principal
    connection = get_connection()
    try:
        repository = MySqlStaffLeaveIntakeRepository(connection)
        try:
            result = repository.coordination_context(request_id, expected_version)
        except ValueError as error:
            code = str(error)
            if code == "leave_request_not_found":
                raise HTTPException(status_code=404, detail={"code": code}) from error
            raise HTTPException(status_code=409, detail={"code": code}) from error
        return BaseResponse(data=result)
    finally:
        connection.close()


@router.post("/{request_id}/review", response_model=BaseResponse[StaffLeaveReviewReceiptView])
def review_staff_leave_request(
    request_id: int,
    body: ReviewBody,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
    principal: AdminPrincipal = Depends(require_admin),
):
    raise HTTPException(status_code=410,detail={'code':'legacy_leave_review_retired',
        'message':'舊請假申請僅供歷史查閱；現行協調結果與代班請使用原案件流程。'})

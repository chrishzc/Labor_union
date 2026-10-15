"""File: staff_leave_management.py
Description: 提供工會人員處理 Scheduling 請假待辦的管理 API。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_leave_intake import get_staff_leave_customer_coordination_application
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalErrorCategory, GlobalTypedErrorView
from api.schemas.staff_leave_management import (
    StaffLeaveCoordinationContextView,
    StaffLeaveInboxItemView,
    StaffLeaveReviewReceiptView,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.staff_leave_customer_coordination import (
    StaffLeaveCustomerCoordinationApplication,
)
from subsystems.scheduling.staff_leave_intake_workflow import (
    ReviewStaffLeaveRequest,
    StaffLeaveIntakeWorkflowError,
)


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
    application: StaffLeaveCustomerCoordinationApplication = Depends(get_staff_leave_customer_coordination_application),
):
    try:
        result = application.review(
            ReviewStaffLeaveRequest(request_id, body.expected_version, body.action, body.reason, False, str(principal.username), idempotency_key)
        )
    except StaffLeaveIntakeWorkflowError as error:
        messages = {
            "leave_request_stale": "這筆請假待辦已由其他人更新；請按「重新整理」，再使用「狀態」篩選核對最新處理結果。",
            "leave_request_not_found": "找不到這筆請假待辦；請按「重新整理」讀取目前清單。",
            "leave_request_transition_invalid": "請假待辦目前的狀態無法執行此操作；請按「重新整理」核對最新狀態。",
        }
        raise _review_error(str(error), messages.get(str(error), "請假待辦目前無法執行此操作；請重新整理並核對狀態與處理原因。")) from error
    except ValueError as error:
        if str(error) != "leave_request_idempotency_conflict":
            raise
        raise _review_error(str(error), "此審核操作識別已用於不同內容；請重新整理待辦，核對狀態後重新操作。") from error

    return BaseResponse(data={"request_id": result.request_id, "status": result.status.value, "version": result.version, "actor": str(principal.username)})


def _review_error(code: str, message: str) -> HTTPException:
    error = GlobalTypedErrorView(
        category=GlobalErrorCategory.IDEMPOTENCY_MISMATCH if code == "leave_request_idempotency_conflict" else GlobalErrorCategory.CONFLICT,
        code=code, message=message,
        field_errors=[], domain_blockers=[], retryable=False,
        correlation_id="staff-leave-review", current_version=None,
    )
    return HTTPException(status_code=409, detail={"error": error.model_dump(mode="json")})

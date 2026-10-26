"""File: staff_leave_intake.py
Description: 提供已驗證月嫂提交請假協調結果，保留歷史請假查閱。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies.staff_leave_intake import get_staff_leave_intake_application
from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.error_contracts import typed_http_error
from api.schemas.line_staff_self_service import (
    StaffLeaveRequestApply,
    StaffLeaveRequestCancel,
    StaffLeaveRequestCreate,
    StaffLeaveRequestCreateResponse,
    StaffLeaveRequestPreviewResponse,
    StaffLeaveRequestReadbackResponse,
    StaffLiffRequest,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from subsystems.scheduling.staff_leave_intake_workflow import ReviewStaffLeaveRequest, StaffLeaveIntakeApplication, StaffLeaveIntakeWorkflowError


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Staff Leave Intake"])

from dataclasses import asdict
from api.dependencies.service_start import get_service_start_application
from api.routes.service_start import call as _result_call
from api.schemas.service_start import StaffLeaveResultSubmission, ServiceStartView
from domains.scheduling.leave_result import LeaveResultSubmission, LeaveDateChange


@router.post('/leave-results/cases')
def leave_result_cases(body: StaffLiffRequest, app=Depends(get_service_start_application)):
    _, staff = _verified_staff_context(body)
    return BaseResponse(data={'items': [asdict(item) for item in app.leave_cases(int(staff['staff_id']))]})


@router.post('/leave-results/submit', response_model=BaseResponse[ServiceStartView])
def submit_leave_result(body: StaffLeaveResultSubmission, app=Depends(get_service_start_application)):
    _, staff = _verified_staff_context(body)
    return BaseResponse(data=asdict(_result_call(lambda: app.submit_leave(LeaveResultSubmission(
        body.case_no,int(staff['staff_id']),body.assignment_id,body.decision,
        tuple(LeaveDateChange(d.original_date,d.new_date) for d in body.dates),
        body.expected_order_version,body.expected_scheduling_version,body.idempotency_key)))))


@router.post("/leave-requests/preview", response_model=BaseResponse[StaffLeaveRequestPreviewResponse])
def preview_staff_leave_request(body: StaffLeaveRequestCreate):
    _retired_intake(body)


@router.post("/leave-requests/apply", response_model=BaseResponse[StaffLeaveRequestReadbackResponse])
def apply_staff_leave_request(
    body: StaffLeaveRequestApply,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
    application: StaffLeaveIntakeApplication = Depends(get_staff_leave_intake_application),
):
    _retired_intake(body)


@router.post("/leave-requests/{request_id}/query", response_model=BaseResponse[StaffLeaveRequestReadbackResponse])
def query_staff_leave_request(request_id: int, body: StaffLiffRequest):
    """Read back a leave request only inside the verified staff ownership boundary."""
    line_user_id, staff = _verified_staff_context(body)
    del line_user_id
    connection = get_connection()
    try:
        result = MySqlStaffLeaveIntakeRepository(connection).load_for_staff(
            request_id, int(staff["staff_id"])
        )
    finally:
        connection.close()
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "leave_request_not_found"})
    return BaseResponse(data=_readback_payload(result, staff["staff_name"]), message="已取得請假待辦")


def _verified_staff_context(body: StaffLiffRequest):
    line_user_id = _verified_line_user_id(body)
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work

    with open_line_unit_of_work() as line_uow:
        staff = _required_staff(line_uow.customer_service.staff_subject(line_user_id.value))
    return line_user_id, staff


def _readback_payload(result, staff_name: str) -> dict:
    if result.leave_start_date is None or result.leave_end_date is None:
        raise HTTPException(status_code=500, detail={"code": "leave_request_readback_incomplete"})
    return {
        "request_id": result.request_id,
        "status": result.status.value,
        "staff_id": result.staff_id,
        "staff_name": staff_name,
        "leave_start_date": result.leave_start_date,
        "leave_end_date": result.leave_end_date,
        "leave_reason": result.leave_reason,
        "version": result.version,
    }


@router.post("/leave-requests", response_model=BaseResponse[StaffLeaveRequestCreateResponse])
def submit_staff_leave_request(
    body: StaffLeaveRequestCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
    application: StaffLeaveIntakeApplication = Depends(get_staff_leave_intake_application),
):
    _retired_intake(body)


@router.post("/leave-requests/{request_id}/cancel", response_model=BaseResponse[StaffLeaveRequestCreateResponse])
def cancel_staff_leave_request(
    request_id: int,
    body: StaffLeaveRequestCancel,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
    application: StaffLeaveIntakeApplication = Depends(get_staff_leave_intake_application),
):
    line_user_id = _verified_line_user_id(body)
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work

    with open_line_unit_of_work() as line_uow:
        staff = _required_staff(line_uow.customer_service.staff_subject(line_user_id.value))
    try:
        result = application.review(
            ReviewStaffLeaveRequest(
                request_id, body.expected_version, "cancel", body.reason, True,
                f"line:{line_user_id.value}", idempotency_key, int(staff["staff_id"]),
            )
        )
    except StaffLeaveIntakeWorkflowError as error:
        code = str(error)
        messages = {
            "leave_request_stale": "請假待辦已由其他人更新；請重新查詢目前狀態後再決定是否取消。",
            "leave_request_state_conflict": "此請假已受理或結束，月嫂只能自行取消尚未受理的申請；請重新查詢狀態，需撤回已受理申請時請聯繫工會。",
            "leave_request_not_found": "找不到本人這筆請假待辦；請重新查詢本人的申請。",
            "leave_request_reason_required": "取消請假必須填寫原因；請補上取消原因後重新送出。",
        }
        status = 404 if code == "leave_request_not_found" else 422 if code == "leave_request_reason_required" else 409
        category = "not_found" if status == 404 else "validation" if status == 422 else "conflict"
        raise typed_http_error(status, category, code, messages.get(code, "目前無法取消這筆請假；請重新查詢最新狀態或聯繫工會。"), "staff-leave-cancel") from error
    except ValueError as error:
        if str(error) != "leave_request_idempotency_conflict":
            raise
        raise typed_http_error(409, "idempotency_mismatch", str(error), "此取消操作識別已用於不同內容；請重新查詢請假狀態後再操作。", "staff-leave-cancel") from error
    return BaseResponse(data={"request_id": result.request_id, "status": result.status.value, "staff_id": result.staff_id, "staff_name": staff["staff_name"], "version": result.version}, message="請假申請已取消")


def _retired_intake(body):
    _verified_staff_context(body)
    raise HTTPException(status_code=410, detail={'code':'leave_intake_replaced',
        'message':'請重新開啟「排班資訊與請假」，直接送出雙方協調結果。'})

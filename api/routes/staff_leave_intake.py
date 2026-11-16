"""File: staff_leave_intake.py
Description: 提供月嫂查詢班表、預檢合意延期檔期及建立群組提案。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import ConfigDict, Field

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
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.line.group_helper_application import save_group_helper_proposal
from subsystems.scheduling.staff_leave_intake_workflow import ReviewStaffLeaveRequest, StaffLeaveIntakeApplication, StaffLeaveIntakeWorkflowError


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Staff Leave Intake"])

from dataclasses import asdict
from api.dependencies.service_start import get_service_start_application
from api.routes.service_start import call as _result_call
from api.schemas.service_start import LeaveDateChangeBody
from domains.scheduling.leave_result import LeaveDateChange


class StaffLeaveDeferPreviewRequest(StaffLiffRequest):
    model_config = ConfigDict(extra='forbid')
    case_no: str = Field(min_length=1, max_length=50)
    assignment_id: int = Field(gt=0)
    dates: list[LeaveDateChangeBody] = Field(min_length=1, max_length=366)


class StaffLeaveDeferProposeRequest(StaffLeaveDeferPreviewRequest):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=140)


@router.post('/leave-results/cases')
def leave_result_cases(body: StaffLiffRequest, app=Depends(get_service_start_application)):
    _, staff = _verified_staff_context(body)
    return BaseResponse(data={'items': [asdict(item) for item in app.leave_cases(int(staff['staff_id']))]})


@router.post('/leave-results/preview')
def preview_leave_defer(body: StaffLeaveDeferPreviewRequest, app=Depends(get_service_start_application)):
    """零寫入預檢月嫂合意順延補班日的排班衝突與總服務天數守恆。"""
    _, staff = _verified_staff_context(body)
    changes = tuple(LeaveDateChange(d.original_date, d.new_date) for d in body.dates)
    result = _result_call(
        lambda: app.arrangement.preview_leave_defer(
            body.case_no, int(staff['staff_id']), body.assignment_id, changes
        )
    )
    return BaseResponse(data=result, message=str(result.get('message') or '已完成檔期與補助天數檢核'))


@router.post('/leave-results/propose')
def propose_leave_defer(body: StaffLeaveDeferProposeRequest, app=Depends(get_service_start_application)):
    """驗證無檔期衝突後建立群組延期提案（不消耗任何 Push 推播額度）。"""
    _, staff = _verified_staff_context(body)
    staff_id = int(staff['staff_id'])
    changes = tuple(LeaveDateChange(d.original_date, d.new_date) for d in body.dates)
    result = _result_call(
        lambda: app.arrangement.preview_leave_defer(
            body.case_no, staff_id, body.assignment_id, changes
        )
    )
    if result.get('conflict'):
        raise typed_http_error(
            409,
            'conflict',
            str(result.get('code') or 'staff_occupancy_conflict'),
            str(result.get('message') or '此補班日已有其他案件排班或不可服務紀錄（檔期衝突），請重新與客戶協調其他日期！'),
            'staff-leave-propose',
        )
    leave_start_label = '、'.join(str(item.original_date) for item in changes)
    leave_end_label = '、'.join(str(item.new_date) for item in changes if item.new_date)
    proposal_payload = {
        'case_no': body.case_no,
        'staff_id': staff_id,
        'assignment_id': body.assignment_id,
        'dates': [{'original_date': str(c.original_date), 'new_date': str(c.new_date)} for c in changes],
        'leave_start_date': leave_start_label,
        'leave_end_date': leave_end_label,
    }
    event_ref = (
        body.idempotency_key
        or f"liff:{fingerprint_payload(proposal_payload).value[:24]}"
    )
    with open_line_unit_of_work() as line_uow:
        save_group_helper_proposal(
            line_uow,
            'group_helper_postpone_proposal',
            body.case_no,
            event_ref,
            proposal_payload,
        )
        line_uow.commit()
    group_message = (
        f"雙方合意延期：{changes[0].original_date}→{changes[0].new_date}"
        if len(changes) == 1 and changes[0].new_date is not None
        else None
    )
    return BaseResponse(
        data={
            **result,
            'case_no': body.case_no,
            'assignment_id': body.assignment_id,
            'leave_start_date': leave_start_label,
            'leave_end_date': leave_end_label,
            'group_message': group_message,
            'group_record_queued': False,
        },
        message=(
            '檔期無衝突，已建立群組延期提案（零推播額度）。'
            + ('請返回案件群組點選「雙方合意延期」送出確認卡。' if group_message is None else '')
        ),
    )


@router.post("/leave-results/submit", include_in_schema=False)
def submit_leave_result():
    raise typed_http_error(
        410,
        "conflict",
        "staff_leave_direct_submit_retired",
        "直接送出請假結果已停用。請從案件群組的小幫手發起「雙方合意延期」，由客戶確認。",
        "staff-leave-direct-submit",
    )


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
        'message':'請從案件群組的小幫手發起「雙方合意延期」，由客戶確認。'})

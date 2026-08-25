"""File: staff_leave_intake.py
Description: 提供已驗證月嫂提交 Scheduling 請假待辦的 LIFF API。"""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import (
    StaffLeaveRequestApply,
    StaffLeaveRequestCancel,
    StaffLeaveRequestCreate,
    StaffLeaveRequestCreateResponse,
    StaffLeaveRequestPreviewResponse,
    StaffLeaveRequestReadbackResponse,
    StaffLiffRequest,
)
from domains.scheduling.staff_leave_intake import StaffLeaveRequestIntent
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.scheduling.staff_leave_intake_workflow import ReviewStaffLeaveRequest, StaffLeaveIntakeWorkflow, StaffLeaveIntakeWorkflowError, SubmitStaffLeaveRequest


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Staff Leave Intake"])


@router.post("/leave-requests/preview", response_model=BaseResponse[StaffLeaveRequestPreviewResponse])
def preview_staff_leave_request(body: StaffLeaveRequestCreate):
    """Validate a staff-owned leave intent without writing Scheduling facts."""
    line_user_id, staff = _verified_staff_context(body)
    try:
        preview = StaffLeaveIntakeWorkflow.preview(
            SubmitStaffLeaveRequest(
                int(staff["staff_id"]),
                line_user_id.value,
                StaffLeaveRequestIntent(
                    body.leave_start_date,
                    body.leave_end_date,
                    body.leave_reason,
                ),
                "preview",
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": str(error)}) from error
    return BaseResponse(
        data={
            "staff_id": preview.staff_id,
            "staff_name": staff["staff_name"],
            "leave_start_date": preview.intent.leave_start_date,
            "leave_end_date": preview.intent.leave_end_date,
            "leave_reason": preview.intent.reason.strip(),
            "can_apply": preview.can_apply,
            "blockers": list(preview.blockers),
            "preview_fingerprint": preview.preview_fingerprint.value,
        },
        message="請假待辦預覽完成",
    )


@router.post("/leave-requests/apply", response_model=BaseResponse[StaffLeaveRequestReadbackResponse])
def apply_staff_leave_request(
    body: StaffLeaveRequestApply,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
):
    """Apply only the exact intent that was returned by Preview."""
    line_user_id, staff = _verified_staff_context(body)
    try:
        intent = StaffLeaveRequestIntent(
            body.leave_start_date,
            body.leave_end_date,
            body.leave_reason,
        )
        command = SubmitStaffLeaveRequest(
            int(staff["staff_id"]), line_user_id.value, intent, idempotency_key,
        )
        connection = get_connection()
        try:
            with MySqlUnitOfWork(connection) as unit_of_work:
                result = StaffLeaveIntakeWorkflow(
                    MySqlStaffLeaveIntakeRepository(connection)
                ).apply(command, PreviewFingerprint(body.preview_fingerprint))
                unit_of_work.commit()
        finally:
            connection.close()
    except StaffLeaveIntakeWorkflowError as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from error
    except ValueError as error:
        status_code = 409 if str(error) == "leave_request_idempotency_conflict" else 422
        raise HTTPException(status_code=status_code, detail={"code": str(error)}) from error
    return BaseResponse(
        data=_readback_payload(result, staff["staff_name"]),
        message="請假待辦已送出，等待工會人員處理",
    )


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
        line_uow.commit()
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
):
    line_user_id = _verified_line_user_id(body)
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work

    with open_line_unit_of_work() as line_uow:
        staff = _required_staff(line_uow.customer_service.staff_subject(line_user_id.value))
        line_uow.commit()
    connection = get_connection()
    try:
        with MySqlUnitOfWork(connection) as unit_of_work:
            workflow = StaffLeaveIntakeWorkflow(MySqlStaffLeaveIntakeRepository(connection))
            result = workflow.submit(
                SubmitStaffLeaveRequest(
                    int(staff["staff_id"]), line_user_id.value,
                    StaffLeaveRequestIntent(body.leave_start_date, body.leave_end_date, body.leave_reason),
                    idempotency_key,
                )
            )
            unit_of_work.commit()
    except StaffLeaveIntakeWorkflowError as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from error
    except ValueError as error:
        status_code = 409 if str(error) == "leave_request_idempotency_conflict" else 422
        raise HTTPException(status_code=status_code, detail={"code": str(error)}) from error
    finally:
        connection.close()
    return BaseResponse(data={"request_id": result.request_id, "status": result.status.value, "staff_id": result.staff_id, "staff_name": staff["staff_name"], "version": result.version}, message="請假申請已送出，等待工會人員處理")


@router.post("/leave-requests/{request_id}/cancel", response_model=BaseResponse[StaffLeaveRequestCreateResponse])
def cancel_staff_leave_request(
    request_id: int,
    body: StaffLeaveRequestCancel,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
):
    line_user_id = _verified_line_user_id(body)
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work

    with open_line_unit_of_work() as line_uow:
        staff = _required_staff(line_uow.customer_service.staff_subject(line_user_id.value))
        line_uow.commit()
    connection = get_connection()
    try:
        with MySqlUnitOfWork(connection) as unit_of_work:
            result = StaffLeaveIntakeWorkflow(MySqlStaffLeaveIntakeRepository(connection)).review(
                ReviewStaffLeaveRequest(
                    request_id, body.expected_version, "cancel", body.reason, True,
                    f"line:{line_user_id.value}", idempotency_key, int(staff["staff_id"]),
                )
            )
            unit_of_work.commit()
    except StaffLeaveIntakeWorkflowError as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from error
    finally:
        connection.close()
    return BaseResponse(data={"request_id": result.request_id, "status": result.status.value, "staff_id": result.staff_id, "staff_name": staff["staff_name"], "version": result.version}, message="請假申請已取消")

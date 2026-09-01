"""File: staff_service_day_logs.py
Description: 提供已驗證月嫂寶寶日誌的 Query、零寫入 Preview 與受控 Apply。"""

from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException
from api.dependencies.service_day_logs import get_service_day_log_application
from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import (
    StaffLiffRequest,
    StaffServiceDayLogApplyRequest,
    StaffServiceDayLogApplyResponse,
    StaffServiceDayLogMediaAttachment,
    StaffServiceDayLogPreviewRequest,
    StaffServiceDayLogPreviewResponse,
    StaffServiceDayLogReadbackResponse,
)
from domains.scheduling.service_day_log import ServiceDayLogIntent
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.scheduling.service_day_log_workflow import (
    ApplyServiceDayLog,
    ControlledServiceDayLogAttachment,
    PreviewServiceDayLog,
    ServiceDayLogApplication,
    ServiceDayLogResult,
)

router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])

@router.post("/service-day-logs", status_code=410)
def retired_direct_service_day_log():
    raise HTTPException(status_code=410, detail={"code": "service_day_log_direct_submit_retired", "replacement": "/api/v1/line/staff-self-service/service-day-logs/preview"})

@router.post("/service-day-logs/preview", response_model=BaseResponse[StaffServiceDayLogPreviewResponse])
def preview_service_day_log(
    body: StaffServiceDayLogPreviewRequest,
    application: ServiceDayLogApplication = Depends(get_service_day_log_application),
):
    staff_id, line_user_id = _verified_staff_identity(body)
    try:
        preview = application.preview(_preview_command(body, staff_id, line_user_id))
    except ValueError as error:
        raise _workflow_error(error) from error
    return BaseResponse(data={"case_no": preview.case_no, "assignment_id": preview.assignment_id, "service_date": preview.service_date, "baby_log_text": preview.baby_log_text, "requires_cooking": preview.requires_cooking, "can_apply": preview.can_apply, "blockers": list(preview.blockers), "preview_fingerprint": preview.preview_fingerprint.value})

@router.post("/service-day-logs/apply", response_model=BaseResponse[StaffServiceDayLogApplyResponse])
def apply_service_day_log(
    body: StaffServiceDayLogApplyRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
    application: ServiceDayLogApplication = Depends(get_service_day_log_application),
):
    staff_id, line_user_id = _verified_staff_identity(body)
    try:
        result = application.apply(
            ApplyServiceDayLog(
                staff_id,
                line_user_id,
                body.assignment_id,
                ServiceDayLogIntent(body.service_date, body.baby_log_text, ()),
                idempotency_key,
                PreviewFingerprint(body.preview_fingerprint),
                controlled_file_attachments=tuple(
                    _controlled_attachment(item)
                    for item in body.controlled_file_attachments
                ),
            )
        )
    except ValueError as error:
        raise _workflow_error(error) from error
    return BaseResponse(data={"receipt": {"log_id": result.log_id, "outcome": result.outcome, "receipt_reference": f"scheduling-service-day-log:{result.log_id}"}, "readback": _readback_data(result)})

@router.post("/service-day-logs/{log_id}/query", response_model=BaseResponse[StaffServiceDayLogReadbackResponse])
def query_service_day_log(
    log_id: int,
    body: StaffLiffRequest,
    application: ServiceDayLogApplication = Depends(get_service_day_log_application),
):
    staff_id, line_user_id = _verified_staff_identity(body)
    try:
        result = application.query(log_id, staff_id, line_user_id)
    except ValueError as error:
        raise _workflow_error(error) from error
    return BaseResponse(data=_readback_data(result))

def _verified_staff_identity(body: StaffLiffRequest) -> tuple[int, str]:
    line_user_id = _verified_line_user_id(body)
    with open_line_unit_of_work() as line_uow:
        staff = _required_staff(line_uow.customer_service.staff_subject(line_user_id.value))
    return int(staff["staff_id"]), line_user_id.value

def _preview_command(body, staff_id: int, line_user_id: str) -> PreviewServiceDayLog:
    return PreviewServiceDayLog(
        staff_id,
        line_user_id,
        body.assignment_id,
        ServiceDayLogIntent(body.service_date, body.baby_log_text, ()),
        controlled_file_attachments=tuple(_controlled_attachment(item) for item in body.controlled_file_attachments),
    )

def _readback_data(result: ServiceDayLogResult) -> dict:
    return {
        "log_id": result.log_id,
        "case_no": result.case_no,
        "assignment_id": result.assignment_id,
        "service_date": result.service_date,
        "baby_log_text": result.baby_log_text,
        "requires_cooking": result.requires_cooking,
        "outcome": result.outcome,
        "controlled_file_attachments": [
            {
                "controlled_file_object_id": item.controlled_file_object_id,
                "staging_id": item.staging_id,
                "sha256_digest": item.sha256_digest,
                "attachment_kind": item.attachment_kind,
                "sequence": item.sequence,
            }
            for item in result.controlled_file_attachments
        ],
    }


def _controlled_attachment(item: StaffServiceDayLogMediaAttachment) -> ControlledServiceDayLogAttachment:
    return ControlledServiceDayLogAttachment(
        item.controlled_file_object_id,
        item.staging_id,
        item.sha256_digest,
        item.attachment_kind,
        item.sequence,
    )

def _workflow_error(error: ValueError) -> HTTPException:
    code = str(error)
    return HTTPException(status_code=404 if code == "service_day_log_not_found" else 422, detail={"code": code})

__all__ = ["router"]

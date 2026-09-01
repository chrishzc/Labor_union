"""
File: staff_service_day_media.py
Description: 提供已驗證月嫂上傳寶寶／餐食照片的 LIFF API，回傳可交給服務日日誌 command 的受控 reference。
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from api.dependencies.service_day_media import get_controlled_file_workflow
from api.dependencies.service_day_logs import get_service_day_log_application
from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import (
    StaffLiffRequest,
    StaffServiceDayMediaResponse,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from domains.scheduling.service_day_log import ServiceDayLogIntent
from subsystems.controlled_files.contracts import ControlledFileStorageError
from subsystems.controlled_files.workflow import (
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileWorkflow,
    ControlledFileWorkflowError,
    StageControlledFile,
)
from subsystems.line.liff_media_upload import (
    LiffMealPhotoUpload,
    prepare_liff_meal_photo_upload,
)
from subsystems.scheduling.service_day_log_workflow import PreviewServiceDayLog
from domains.controlled_files.reference_finalize import canonical_scheduling_object_key


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])
_MAXIMUM_MEAL_PHOTO_BYTES = 10 * 1024 * 1024


@router.post("/service-day-media", response_model=BaseResponse[StaffServiceDayMediaResponse])
async def upload_service_day_meal_photo(
    photo: UploadFile = File(...),
    flow_id: Annotated[str, Form(max_length=191)] = "",
    line_id_token: Annotated[str, Form(max_length=4096)] = "",
    development_line_user_id: Annotated[str, Form(max_length=191)] = "",
    assignment_id: Annotated[int, Form(gt=0)] = ...,
    service_date: Annotated[date, Form()] = ...,
    attachment_kind: Annotated[
        Literal["meal_photo", "baby_log_photo"], Form()
    ] = "meal_photo",
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)] = ...,
    controlled_file_workflow: ControlledFileWorkflow = Depends(get_controlled_file_workflow),
    service_day_log_application=Depends(get_service_day_log_application),
):
    payload = StaffLiffRequest(
        flow_id=flow_id,
        line_id_token=line_id_token,
        development_line_user_id=development_line_user_id,
    )
    line_user_id = _verified_line_user_id(payload)
    content = await photo.read(_MAXIMUM_MEAL_PHOTO_BYTES + 1)
    if len(content) > _MAXIMUM_MEAL_PHOTO_BYTES:
        raise HTTPException(status_code=422, detail={"code": "service_day_meal_photo_too_large"})
    try:
        command = LiffMealPhotoUpload(
            line_user_id,
            content,
            (photo.content_type or "").split(";", 1)[0].lower(),
            IdempotencyKey(idempotency_key),
        )
        metadata = prepare_liff_meal_photo_upload(command)
        if metadata.content_type not in {"image/jpeg", "image/png"}:
            raise ValueError("service_day_meal_photo_content_type_invalid")
        staff_id, verified_line_user_id = _verified_staff_identity(payload)
        assignment_preview = service_day_log_application.preview(
            PreviewServiceDayLog(
                staff_id,
                verified_line_user_id,
                assignment_id,
                ServiceDayLogIntent(service_date, "餐食照片 staging 驗證"),
            )
        )
        if assignment_preview.requires_cooking is False and attachment_kind == "meal_photo":
            raise ValueError("service_day_log_meal_photo_forbidden")
        digest = hashlib.sha256(content).hexdigest()
        object_key = canonical_scheduling_object_key(
            assignment_id=assignment_id,
            service_date=service_date,
            attachment_kind=attachment_kind,
            sequence=1,
            sha256_digest=digest,
        )
        result = controlled_file_workflow.stage(
            StageControlledFile(
                owner=ControlledFileOwner.SCHEDULING,
                purpose=(
                    ControlledFilePurpose.MEAL_PHOTO
                    if attachment_kind == "meal_photo"
                    else ControlledFilePurpose.BABY_LOG_PHOTO
                ),
                subject_reference=assignment_preview.case_no,
                object_key=object_key,
                logical_folder=f"scheduling/service-day/{assignment_id}/{service_date.isoformat()}",
                filename=Path(getattr(photo, "filename", None) or "meal-photo").name,
                mime_type=metadata.content_type,
                content=content,
                idempotency_key=IdempotencyKey(idempotency_key),
                actor=ActorContext(f"staff:{staff_id}"),
                correlation_id=CorrelationId(f"service-day-media-stage:{idempotency_key}"),
            )
        )
    except ControlledFileWorkflowError as error:
        raise HTTPException(status_code=409, detail={"code": error.code}) from error
    except ControlledFileStorageError as error:
        raise HTTPException(status_code=422, detail={"code": error.code}) from error
    except RuntimeError as error:
        if str(error) == "controlled_file_staging_idempotency_conflict":
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": str(error)}) from error
    return BaseResponse(data={"staging_id": result.staging_id, "content_type": result.mime_type, "size_bytes": result.size_bytes, "sha256_digest": result.sha256_digest, "expires_at": result.expires_at.isoformat(), "outcome": "existing" if result.replayed else "created"})


def _verified_staff_identity(payload: StaffLiffRequest) -> tuple[int, str]:
    line_user_id = _verified_line_user_id(payload)
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work

    with open_line_unit_of_work() as unit_of_work:
        staff = _required_staff(unit_of_work.customer_service.staff_subject(line_user_id.value))
    return int(staff["staff_id"]), line_user_id.value


__all__ = ["router"]

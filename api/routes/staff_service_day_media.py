"""
File: staff_service_day_media.py
Description: 提供已驗證月嫂上傳餐食照片的 LIFF API，回傳可交給服務日日誌 command 的受控 reference。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from api.dependencies.service_day_media import get_liff_meal_photo_upload_application
from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import StaffLiffRequest, StaffServiceDayMediaResponse
from shared_kernel.identities import IdempotencyKey
from subsystems.line.liff_media_upload import (
    LiffMealPhotoUpload,
    LiffMealPhotoUploadApplication,
    LiffMealPhotoUploadStaffBindingNotFound,
)


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])
_MAXIMUM_MEAL_PHOTO_BYTES = 10 * 1024 * 1024


@router.post("/service-day-media", response_model=BaseResponse[StaffServiceDayMediaResponse])
async def upload_service_day_meal_photo(
    photo: UploadFile = File(...),
    flow_id: Annotated[str, Form(max_length=191)] = "",
    line_id_token: Annotated[str, Form(max_length=4096)] = "",
    development_line_user_id: Annotated[str, Form(max_length=191)] = "",
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)] = ...,
    application: LiffMealPhotoUploadApplication = Depends(
        get_liff_meal_photo_upload_application
    ),
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
    command = LiffMealPhotoUpload(
        line_user_id,
        content,
        (photo.content_type or "").split(";", 1)[0].lower(),
        IdempotencyKey(idempotency_key),
    )
    try:
        result = application.upload(command)
    except LiffMealPhotoUploadStaffBindingNotFound:
        _required_staff(None)
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=409 if code == "service_day_meal_photo_idempotency_conflict" else 422,
            detail={"code": code},
        ) from error
    return BaseResponse(data={"media_id": result.media_id, "content_type": result.content_type, "size_bytes": result.size_bytes, "outcome": result.outcome})


__all__ = ["router"]

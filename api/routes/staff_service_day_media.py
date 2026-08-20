"""
File: staff_service_day_media.py
Description: 提供已驗證月嫂上傳餐食照片的 LIFF API，回傳可交給服務日日誌 command 的受控 reference。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from api.dependencies.line_worker_operation import _media_storage_root
from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import StaffLiffRequest, StaffServiceDayMediaResponse
from shared_kernel.identities import IdempotencyKey
from infrastructure.line.media_adapters import FileSystemLineMediaObjectStore
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.liff_media_upload import (
    LiffMealPhotoUpload,
    existing_liff_upload_matches,
    prepare_liff_meal_photo_upload,
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
        metadata = prepare_liff_meal_photo_upload(command)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": str(error)}) from error
    with open_line_unit_of_work() as unit_of_work:
        _required_staff(unit_of_work.customer_service.staff_subject(line_user_id.value))
        existing = unit_of_work.media_metadata.get(metadata.provider_media_id)
        if existing is not None:
            if not existing_liff_upload_matches(existing, command):
                raise HTTPException(status_code=409, detail={"code": "service_day_meal_photo_idempotency_conflict"})
            unit_of_work.commit()
            return BaseResponse(data={"media_id": metadata.provider_media_id, "content_type": metadata.content_type, "size_bytes": metadata.size_bytes, "outcome": "existing"})
        object_reference = FileSystemLineMediaObjectStore(_media_storage_root()).put(metadata, content)
        unit_of_work.media_metadata.register(metadata, object_reference, command.idempotency_key)
        unit_of_work.commit()
    return BaseResponse(data={"media_id": metadata.provider_media_id, "content_type": metadata.content_type, "size_bytes": metadata.size_bytes, "outcome": "created"})


__all__ = ["router"]

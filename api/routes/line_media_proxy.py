"""NAS public routes preserve wire contracts without opening local file workflows."""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from api.dependencies.line_media_proxy import get_line_media_client, require_line_media_token
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import (
    StaffLiffRequest, StaffServiceDayMediaResponse, StaffServiceDayLogPreviewRequest,
    StaffServiceDayLogApplyRequest, StaffServiceDayLogPreviewResponse,
    StaffServiceDayLogApplyResponse, StaffServiceDayLogReadbackResponse,
    StaffServiceDayLogOptionsRequest, StaffServiceDayLogOptionsResponse,
)
from infrastructure.http.line_media_client import LineMediaError
from infrastructure.runtime.file_transfer_settings import FileTransferSettings, size_label


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])


async def _forward(operation, schema):
    try:
        return BaseResponse[schema].model_validate(await operation)
    except LineMediaError as error:
        _raise_proxy_error(error)
    except ValidationError:
        raise typed_http_error(503, "unavailable", "line_media_response_invalid",
                               "照片私人服務回應無法確認，請稍後重試", "line-media") from None


async def _policy(client, identity):
    identity = {key: identity.get(key, "") for key in ("line_id_token", "flow_id", "development_line_user_id")}
    response = await _forward(client.settings(identity), FileTransferSettings)
    value = response.data
    if (value is None or value.photo_max_bytes < 1 or value.resume_max_bytes < 1 or value.timeout_seconds < 0):
        raise typed_http_error(503, "unavailable", "line_media_response_invalid", "檔案設定目前無法確認，請稍後重試。", "line-media")
    return response


def _raise_proxy_error(error):
    category = {401: "forbidden", 403: "forbidden", 404: "not_found", 409: "conflict",
                422: "validation"}.get(error.status_code, "unavailable")
    message = (error.safe_message if error.code == "service_day_meal_photo_too_large" else None)
    raise typed_http_error(error.status_code, category, error.code,
                           message or "日誌照片操作未完成，請核對登入及服務資料後重試",
                           "line-media", retryable=error.status_code == 503) from None


@router.post("/service-day-logs", status_code=410)
def retired_direct_service_day_log():
    raise HTTPException(410, detail={"code": "service_day_log_direct_submit_retired",
                                   "replacement": "/api/v1/line/staff-self-service/service-day-logs/preview"})


@router.post("/service-day-media", response_model=BaseResponse[StaffServiceDayMediaResponse])
async def upload(
    photo: UploadFile = File(), flow_id: Annotated[str, Form(max_length=191)] = "",
    line_id_token: Annotated[str, Form(max_length=4096)] = "",
    development_line_user_id: Annotated[str, Form(max_length=191)] = "",
    assignment_id: Annotated[int, Form(gt=0)] = ...,
    service_date: Annotated[date, Form()] = ...,
    attachment_kind: Annotated[Literal["meal_photo", "baby_log_photo"], Form()] = "meal_photo",
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)] = ...,
    client=Depends(get_line_media_client),
):
    require_line_media_token(line_id_token)
    policy = await _policy(client, dict(line_id_token=line_id_token, flow_id=flow_id,
                                       development_line_user_id=development_line_user_id))
    limit = policy.data.photo_max_bytes
    content = await photo.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(422, detail={"code": "service_day_meal_photo_too_large",
            "message": f"照片超過入口上限 {size_label(limit)}；本次照片未保存，請選擇較小檔案或請管理者調整上限。"})
    fields = dict(line_id_token=line_id_token, flow_id=flow_id,
                  development_line_user_id=development_line_user_id,
                  assignment_id=str(assignment_id), service_date=service_date.isoformat(),
                  attachment_kind=attachment_kind)
    return await _forward(client.upload(fields, content, photo.filename or "photo",
                                        photo.content_type or "", idempotency_key), StaffServiceDayMediaResponse)


@router.post("/service-day-media/settings", response_model=BaseResponse[FileTransferSettings])
async def settings(body: StaffLiffRequest, client=Depends(get_line_media_client)):
    require_line_media_token(body.line_id_token)
    return await _policy(client, body.model_dump(mode="json"))


@router.post("/service-day-logs/preview", response_model=BaseResponse[StaffServiceDayLogPreviewResponse])
async def preview(body: StaffServiceDayLogPreviewRequest, client=Depends(get_line_media_client)):
    require_line_media_token(body.line_id_token)
    await _policy(client, body.model_dump(mode="json"))
    return await _forward(client.preview(body.model_dump(mode="json")), StaffServiceDayLogPreviewResponse)


@router.post("/service-day-logs/apply", response_model=BaseResponse[StaffServiceDayLogApplyResponse])
async def apply(body: StaffServiceDayLogApplyRequest,
                idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)],
                client=Depends(get_line_media_client)):
    require_line_media_token(body.line_id_token)
    await _policy(client, body.model_dump(mode="json"))
    return await _forward(client.apply(body.model_dump(mode="json"), idempotency_key), StaffServiceDayLogApplyResponse)


@router.post("/service-day-logs/options", response_model=BaseResponse[StaffServiceDayLogOptionsResponse])
async def log_options(body: StaffServiceDayLogOptionsRequest, client=Depends(get_line_media_client)):
    require_line_media_token(body.line_id_token)
    return await _forward(client.options(body.model_dump(mode="json")), StaffServiceDayLogOptionsResponse)


@router.post("/service-day-logs/{log_id}/query", response_model=BaseResponse[StaffServiceDayLogReadbackResponse])
async def query(log_id: int, body: StaffLiffRequest, client=Depends(get_line_media_client)):
    require_line_media_token(body.line_id_token)
    await _policy(client, body.model_dump(mode="json"))
    return await _forward(client.query(log_id, body.model_dump(mode="json")), StaffServiceDayLogReadbackResponse)


@router.post("/service-day-logs/{log_id}/photos/{file_id}/download")
async def download(log_id: int, file_id: str, body: StaffLiffRequest, client=Depends(get_line_media_client)):
    require_line_media_token(body.line_id_token)
    await _policy(client, body.model_dump(mode="json"))
    try:
        photo = await client.download(log_id, file_id, body.model_dump(mode="json"))
    except LineMediaError as error:
        _raise_proxy_error(error)
    suffix = "png" if photo.content_type == "image/png" else "jpg"
    return Response(photo.content, media_type=photo.content_type, headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{file_id}.{suffix}"',
    })

"""Private photo endpoints reuse the original verified Scheduling transport/owner."""
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.routing import APIRoute

from api.dependencies.line_media_proxy import require_private_line_media
from api.error_contracts import typed_http_error
from api.routes import staff_service_day_media as media, staff_service_day_logs as logs
from api.schemas.base import BaseResponse
from infrastructure.runtime.file_transfer_settings import FileTransferSettings
from api.schemas.line_staff_self_service import (
    StaffServiceDayMediaResponse, StaffServiceDayLogPreviewResponse,
    StaffServiceDayLogApplyResponse, StaffServiceDayLogReadbackResponse,
)


class PrivateLineMediaRoute(APIRoute):
    """Translate the reused legacy HTTP errors at this private wire boundary."""
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            try:
                return await handler(request)
            except HTTPException as error:
                code = error.detail.get("code", "") if isinstance(error.detail, dict) else ""
                if not re.fullmatch(r"(?:service_day_|controlled_file_|internal_service_)[a-z_]{1,100}", code):
                    raise
                status = 409 if code.endswith("_stale") else error.status_code
                category = {401: "forbidden", 403: "forbidden", 404: "not_found", 409: "conflict",
                            422: "validation"}.get(status, "unavailable")
                message = (error.detail["message"] if code == "service_day_meal_photo_too_large"
                           and "message" in error.detail else "日誌照片操作未完成")
                raise typed_http_error(status, category, code, message,
                                       "line-media", retryable=status >= 500) from None
        return handle


router = APIRouter(prefix="/internal/v1/line-media", include_in_schema=False, route_class=PrivateLineMediaRoute,
                   dependencies=[Depends(require_private_line_media)])
for path, endpoint, schema in (
    ("/service-day-media/settings", media.service_day_media_settings, FileTransferSettings),
    ("/service-day-media", media.upload_service_day_meal_photo, StaffServiceDayMediaResponse),
    ("/service-day-logs/preview", logs.preview_service_day_log, StaffServiceDayLogPreviewResponse),
    ("/service-day-logs/apply", logs.apply_service_day_log, StaffServiceDayLogApplyResponse),
    ("/service-day-logs/{log_id}/query", logs.query_service_day_log, StaffServiceDayLogReadbackResponse),
):
    router.add_api_route(path, endpoint, methods=["POST"], response_model=BaseResponse[schema])

router.add_api_route("/service-day-logs/{log_id}/photos/{file_id}/download",
                     media.download_service_day_photo, methods=["POST"])

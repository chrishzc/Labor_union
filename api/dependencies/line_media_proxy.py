"""NAS-only client composition and machine-bound private photo gate."""
from fastapi import Depends, Request

from api.dependencies.internal_service_auth import require_internal_service, require_operation_service
from api.error_contracts import typed_http_error
from infrastructure.http.line_media_client import LineMediaClient, LineMediaError, SERVICE


def get_line_media_client():
    try:
        return LineMediaClient.from_environment()
    except (LineMediaError, ValueError):
        raise typed_http_error(503, "unavailable", "line_media_configuration_unavailable",
                               "照片私人服務尚未設定完成", "line-media", retryable=False) from None


def require_line_media_token(token):
    if not isinstance(token, str) or not token.strip():
        raise typed_http_error(401, "forbidden", "liff_token_required",
                               "請重新從 LINE 登入後操作日誌", "line-media")


async def require_private_line_media(request: Request, principal=Depends(require_internal_service)):
    if principal.authentication_method != "nas_service_token":
        raise typed_http_error(403, "forbidden", "line_media_machine_auth_required",
                               "照片服務需要獨立機器憑證", "line-media")
    require_operation_service(principal, SERVICE)
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        payload = await request.form()
    else:
        try:
            payload = await request.json()
        except ValueError:
            payload = {}
    require_line_media_token(payload.get("line_id_token") if hasattr(payload, "get") else None)

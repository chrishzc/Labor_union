"""
File: admin_setup.py
Description: 所有管理入口共用 MySQL root 狀態與同源首次建帳流程。
"""
from __future__ import annotations

import asyncio
import json
from datetime import timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
import pymysql

from api.dependencies.admin_auth import get_access_control_connection_factory
from api.schemas.errors import GlobalErrorCategory, GlobalTypedErrorView
from api.schemas.admin_auth import AdminPasswordChallengeResponse
from subsystems.access.authentication_session import (
    AdminMfaConfigurationError, AdminSessionSchemaError, RootSetupStatus,
    bootstrap_root_admin, get_root_setup_status,
)

router = APIRouter(include_in_schema=False)
HEADERS = {
    "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


class SetupRootRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=10, max_length=256)


def _error(status: int, code: str, message: str) -> HTTPException:
    category = (GlobalErrorCategory.FORBIDDEN if status in (403, 410, 426)
                else GlobalErrorCategory.CONFLICT if status == 409
                else GlobalErrorCategory.UNAVAILABLE if status == 503
                else GlobalErrorCategory.VALIDATION)
    error = GlobalTypedErrorView(category=category, code=code, message=message,
        field_errors=[], domain_blockers=[], retryable=status == 503,
        correlation_id=uuid4().hex, current_version=None)
    return HTTPException(status, {"error": error.model_dump(mode="json")}, headers=HEADERS)


def _require_secure_transport(request: Request) -> None:
    loopbacks = {"127.0.0.1", "localhost", "::1"}
    local = (request.url.hostname in loopbacks and request.client is not None
             and request.client.host in loopbacks)
    if request.url.scheme != "https" and not local:
        raise _error(426, "https_required", "請使用 HTTPS 網址開啟管理介面後設定帳號。")


def _status() -> RootSetupStatus:
    try:
        return get_root_setup_status(connection_factory=get_access_control_connection_factory())
    except pymysql.MySQLError:
        raise _error(503, "setup_unavailable", "設定服務暫時無法使用，請稍後再試。") from None


@router.get("/setup")
async def setup_page(request: Request):
    return RedirectResponse("/admin/", status_code=303, headers=HEADERS)


@router.get("/api/v1/admin/setup")
async def setup_status(request: Request):
    state = await asyncio.to_thread(_status)
    return JSONResponse({"required": state.required, "enrollment_required": state.enrollment_required}, headers=HEADERS)


@router.post("/api/v1/admin/setup")
async def create_first_root(request: Request):
    _require_secure_transport(request)
    # Compare the browser's origin with the current management endpoint.
    default_port = ":443" if request.url.scheme == "https" else ":80"
    origin = request.headers.get("origin", "").lower().removesuffix(default_port)
    expected_origin = f"{request.url.scheme}://{request.url.netloc}".lower().removesuffix(default_port)
    if origin != expected_origin:
        raise _error(403, "setup_origin_rejected", "請從設定的管理介面網址重新開啟。")
    if not (await asyncio.to_thread(_status)).required:
        raise _error(410, "setup_closed", "最高管理員已建立，請直接登入。")
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise _error(415, "json_required", "請使用設定頁面提交資料。")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 8192:
            raise _error(413, "setup_request_too_large", "設定資料過大。")
    try:
        payload = SetupRootRequest.model_validate(json.loads(body))
        if not payload.username.strip() or not payload.display_name.strip():
            raise ValueError("blank account")
    except (ValueError, ValidationError, UnicodeError):
        # Never echo validation input: it may contain the root password.
        raise _error(422, "setup_input_invalid", "請填寫帳號、顯示名稱及 10–256 字元的密碼。") from None
    try:
        result = await asyncio.to_thread(bootstrap_root_admin,
            connection_factory=get_access_control_connection_factory(),
            username=payload.username, password=payload.password.get_secret_value(),
            display_name=payload.display_name)
    except AdminMfaConfigurationError:
        raise _error(503, "mfa_configuration_unavailable",
                     "此主機的 TOTP 加密設定缺失或無效，請設定有效金鑰並重新啟動服務後再建立帳號。") from None
    except AdminSessionSchemaError:
        raise _error(503, "admin_session_schema_not_ready",
                     "帳號驗證資料庫結構尚未完成，請完成資料庫初始化或更新後重試。") from None
    except (ValueError, pymysql.err.IntegrityError):
        raise _error(409, "setup_conflict", "帳號設定已變更，請重新開啟頁面確認。") from None
    except pymysql.err.OperationalError as error:
        if error.args and error.args[0] in (1205, 1213):
            raise _error(409, "setup_conflict", "其他設定正在進行，請重新開啟頁面確認。") from None
        raise _error(503, "setup_unavailable", "設定服務暫時無法使用，請稍後再試。") from None
    except pymysql.MySQLError:
        raise _error(503, "setup_unavailable", "帳號驗證資料庫無法使用，請確認初始化與存取權限。") from None
    enrollment = result.enrollment
    challenge = AdminPasswordChallengeResponse(
        challenge_type="mfa_enrollment", challenge_id=enrollment.challenge_id,
        challenge_token=enrollment.challenge_token, provisioning_uri=enrollment.provisioning_uri,
        expires_at=enrollment.expires_at.replace(tzinfo=timezone.utc),
    )
    return JSONResponse({"created": True, "enrollment": challenge.model_dump(mode="json")},
                        status_code=201, headers=HEADERS)

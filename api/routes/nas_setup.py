"""One-time HTTPS root setup for the NAS image only."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
import pymysql

from api.dependencies.admin_auth import get_access_control_connection_factory
from api.schemas.errors import GlobalErrorCategory, GlobalTypedErrorView
from subsystems.access.authentication_session import bootstrap_root_admin, has_root_admin

router = APIRouter(include_in_schema=False)
ASSETS = Path("/opt/nas/setup")
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


def _require_https(request: Request) -> None:
    if request.url.scheme != "https":
        raise _error(426, "https_required", "請從 NAS 的 HTTPS 網址開啟設定頁面。")


def _required() -> bool:
    try:
        return not has_root_admin(connection_factory=get_access_control_connection_factory())
    except pymysql.MySQLError:
        raise _error(503, "setup_unavailable", "設定服務暫時無法使用，請稍後再試。") from None


@router.get("/setup")
async def setup_page(request: Request):
    _require_https(request)
    if not await asyncio.to_thread(_required):
        return RedirectResponse("/admin/", status_code=303, headers=HEADERS)
    return FileResponse(ASSETS / "index.html", headers=HEADERS)


@router.get("/setup/style.css")
async def setup_css():
    return FileResponse(ASSETS / "style.css", headers=HEADERS)


@router.get("/setup/setup.js")
async def setup_script():
    return FileResponse(ASSETS / "setup.js", headers=HEADERS)


@router.get("/api/v1/admin/setup")
async def setup_status(request: Request):
    _require_https(request)
    return JSONResponse({"required": await asyncio.to_thread(_required)}, headers=HEADERS)


@router.post("/api/v1/admin/setup")
async def create_first_root(request: Request):
    _require_https(request)
    # Use this request's HTTPS endpoint; no deployment URL or extra secret.
    origin = request.headers.get("origin", "").lower().removesuffix(":443")
    expected_origin = str(request.base_url).rstrip("/").lower().removesuffix(":443")
    if origin != expected_origin:
        raise _error(403, "setup_origin_rejected", "請從設定的管理介面網址重新開啟。")
    if not await asyncio.to_thread(_required):
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
        await asyncio.to_thread(bootstrap_root_admin,
            connection_factory=get_access_control_connection_factory(),
            username=payload.username, password=payload.password.get_secret_value(),
            display_name=payload.display_name)
    except (ValueError, pymysql.err.IntegrityError):
        raise _error(409, "setup_conflict", "帳號設定已變更，請重新開啟頁面確認。") from None
    except pymysql.err.OperationalError as error:
        if error.args and error.args[0] in (1205, 1213):
            raise _error(409, "setup_conflict", "其他設定正在進行，請重新開啟頁面確認。") from None
        raise _error(503, "setup_unavailable", "設定服務暫時無法使用，請稍後再試。") from None
    return JSONResponse({"created": True, "next": "/admin/"}, status_code=201, headers=HEADERS)


def create_app():
    """Attach setup only to the NAS entry, never to the normal API application."""
    from scripts.nas_test_runtime import management_preview_app
    app = management_preview_app()
    app.include_router(router)

    @app.middleware("http")
    async def first_visit(request: Request, call_next):
        if request.url.path in {"/admin", "/admin/"} and await asyncio.to_thread(_required):
            return RedirectResponse("/setup", status_code=303, headers=HEADERS)
        return await call_next(request)

    return app

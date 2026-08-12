"""Login/session endpoints used by the server-rendered administration UI."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from api.dependencies.admin_auth import (
    get_bearer_token,
    require_admin,
    require_internal_service,
)
from api.schemas.admin_auth import (
    AdminLoginRequest,
    AdminPublic,
    AdminRefreshResponse,
    AdminSessionResponse,
)
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import (
    AdminPrincipal,
    AdminSessionSchemaError,
    AdminSessionStorageError,
    authenticate_admin,
    record_admin_audit,
    renew_admin_session,
    revoke_admin_session,
)


router = APIRouter(prefix="/api/v1/admin/auth", tags=["Admin Auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=BaseResponse[AdminSessionResponse])
async def login(
    payload: AdminLoginRequest,
    request: Request,
    _: None = Depends(require_internal_service),
):
    result = await _authenticate(payload)
    if result is None:
        await _reject_invalid_login(payload, request)
    token, expires_at, principal = result
    await _record_login_success(principal, request)
    return _login_response(token, expires_at, principal)


async def _authenticate(payload: AdminLoginRequest):
    try:
        return await asyncio.to_thread(
            authenticate_admin,
            payload.username,
            payload.password,
            session_minutes=30,
        )
    except AdminSessionSchemaError as error:
        raise _login_unavailable("admin_session_schema_not_ready", str(error)) from error
    except AdminSessionStorageError as error:
        raise _login_unavailable("admin_session_storage_unavailable", str(error)) from error


async def _reject_invalid_login(payload, request) -> None:
    await asyncio.to_thread(
        record_admin_audit,
        principal=None,
        action="admin.login.failed",
        request_path=str(request.url.path),
        http_method=request.method,
        result_status=status.HTTP_401_UNAUTHORIZED,
        ip_address=_client_ip(request),
        details={"username": payload.username.strip().lower()},
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "admin_credentials_invalid",
            "message": "帳號或密碼錯誤",
            "retryable": False,
        },
    )


async def _record_login_success(principal, request) -> None:
    await asyncio.to_thread(
        record_admin_audit,
        principal=principal,
        action="admin.login.success",
        request_path=str(request.url.path),
        http_method=request.method,
        result_status=200,
        ip_address=_client_ip(request),
    )


def _login_response(token, expires_at, principal):
    return BaseResponse(
        data=AdminSessionResponse(
            access_token=token,
            expires_at=expires_at,
            admin=AdminPublic(**principal.as_dict()),
        ),
        message="登入成功",
    )


def _login_unavailable(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": message, "retryable": True},
    )


@router.get("/me", response_model=BaseResponse[AdminPublic])
def me(principal: AdminPrincipal = Depends(require_admin)):
    return BaseResponse(data=AdminPublic(**principal.as_dict()))


@router.post("/refresh", response_model=BaseResponse[AdminRefreshResponse])
async def refresh(
    authorization: str | None = Header(default=None),
    principal: AdminPrincipal = Depends(require_admin),
):
    token = get_bearer_token(authorization)
    try:
        expires_at = await asyncio.to_thread(
            renew_admin_session,
            token,
            session_minutes=30,
        )
    except AdminSessionStorageError as error:
        raise _login_unavailable("admin_session_storage_unavailable", str(error)) from error
    if expires_at is None:
        raise HTTPException(status_code=401, detail="管理員 Session 已失效")
    return BaseResponse(
        data=AdminRefreshResponse(expires_at=expires_at),
        message=f"{principal.display_name} 的 Session 已延長",
    )


@router.post("/logout", response_model=BaseResponse[dict])
async def logout(
    authorization: str | None = Header(default=None),
    principal: AdminPrincipal = Depends(require_admin),
):
    token = get_bearer_token(authorization)
    try:
        await asyncio.to_thread(revoke_admin_session, token)
    except AdminSessionStorageError as error:
        raise _login_unavailable("admin_session_storage_unavailable", str(error)) from error
    return BaseResponse(data={"logged_out": True}, message=f"{principal.display_name} 已登出")

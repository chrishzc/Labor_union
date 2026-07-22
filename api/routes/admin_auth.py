"""Login/session endpoints used by the server-rendered administration UI."""

from __future__ import annotations

import asyncio
import os

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
from services.admin_auth_service import (
    AdminPrincipal,
    authenticate_admin,
    record_admin_audit,
    renew_admin_session,
    revoke_admin_session,
)


router = APIRouter(prefix="/api/v1/admin/auth", tags=["Admin Auth"])


def _session_minutes() -> int:
    try:
        return int(os.getenv("ADMIN_SESSION_MINUTES", "30"))
    except ValueError:
        return 30


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=BaseResponse[AdminSessionResponse])
async def login(
    payload: AdminLoginRequest,
    request: Request,
    _: None = Depends(require_internal_service),
):
    result = await asyncio.to_thread(
        authenticate_admin,
        payload.username,
        payload.password,
        session_minutes=_session_minutes(),
    )
    if result is None:
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
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    token, expires_at, principal = result
    await asyncio.to_thread(
        record_admin_audit,
        principal=principal,
        action="admin.login.success",
        request_path=str(request.url.path),
        http_method=request.method,
        result_status=200,
        ip_address=_client_ip(request),
    )
    return BaseResponse(
        data=AdminSessionResponse(
            access_token=token,
            expires_at=expires_at,
            admin=AdminPublic(**principal.as_dict()),
        ),
        message="登入成功",
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
    expires_at = await asyncio.to_thread(
        renew_admin_session,
        token,
        session_minutes=_session_minutes(),
    )
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
    await asyncio.to_thread(revoke_admin_session, token)
    return BaseResponse(data={"logged_out": True}, message=f"{principal.display_name} 已登出")

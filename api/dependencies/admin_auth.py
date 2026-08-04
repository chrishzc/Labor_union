"""Internal service-key and administrator-session dependencies."""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from subsystems.access.authentication_session import (
    AdminPrincipal,
    get_admin_session,
    has_required_role,
)


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}


def admin_auth_is_enabled() -> bool:
    """Return False only for an explicit bypass in a development environment."""
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    configured = os.getenv("ENABLE_ADMIN_AUTH", "true").strip().lower()
    requested_bypass = configured in {"0", "false", "no", "off"}
    return not (app_env in DEVELOPMENT_ENVIRONMENTS and requested_bypass)


def require_internal_service(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
) -> None:
    expected = os.getenv("INTERNAL_API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_API_KEY 尚未設定",
        )
    if not x_internal_api_key or not hmac.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="內部服務金鑰錯誤",
        )


def get_bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少有效的管理員 Session",
        )
    return token.strip()


def require_admin(
    request: Request,
    authorization: str | None = Header(default=None),
    _: None = Depends(require_internal_service),
) -> AdminPrincipal:
    if not admin_auth_is_enabled():
        principal = AdminPrincipal(
            id=None,
            username="development-bypass",
            display_name="開發模式管理員",
            role="system_admin",
        )
        request.state.admin_principal = principal
        request.state.admin_auth_bypassed = True
        return principal

    token = get_bearer_token(authorization)
    principal = get_admin_session(token)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理員 Session 已失效或過期",
        )
    request.state.admin_principal = principal
    request.state.admin_session_token = token
    return principal


def require_role(minimum_role: str) -> Callable[..., AdminPrincipal]:
    def dependency(principal: AdminPrincipal = Depends(require_admin)) -> AdminPrincipal:
        if not has_required_role(principal, minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 {minimum_role} 或更高權限",
            )
        return principal

    return dependency


require_line_viewer = require_role("line_viewer")
require_line_agent = require_role("line_agent")
require_line_manager = require_role("line_manager")
require_system_admin = require_role("system_admin")

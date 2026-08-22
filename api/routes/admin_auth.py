"""
File: admin_auth.py
Description: 提供管理後台 Bearer Session 與 TOTP 登入的 API 端點。
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from api.dependencies.admin_auth import (
    get_bearer_token,
    require_admin,
)
from api.schemas.admin_auth import (
    AdminLoginRequest,
    AdminPasswordChallengeRequest,
    AdminPasswordChallengeResponse,
    AdminFactorVerificationRequest,
    AdminPublic,
    MfaEnrollmentVerificationRequest,
    MfaEnrollmentVerificationResponse,
    AdminRefreshResponse,
    AdminSessionResponse,
)
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import (
    AdminPrincipal,
    AdminSessionSchemaError,
    AdminSessionStorageError,
    AdminLoginRateLimitedError,
    AdminMfaConfigurationError,
    MfaEnrollmentChallenge,
    authenticate_admin,
    issue_password_login_challenge,
    complete_password_login_challenge,
    PasswordLoginChallenge,
    authenticate_local_developer_root,
    complete_mfa_enrollment,
    renew_admin_session,
    revoke_admin_session,
)


router = APIRouter(prefix="/api/v1/admin/auth", tags=["Admin Auth"])


def _as_utc_transport_datetime(value: datetime) -> datetime:
    """把 repository 的 UTC-naive 值收斂為具有明確 offset 的公開傳輸時間。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=BaseResponse[AdminSessionResponse])
async def login(
    payload: AdminLoginRequest,
    request: Request,
):
    result = await _authenticate(payload, _client_ip(request))
    if isinstance(result, MfaEnrollmentChallenge):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "mfa_enrollment_required",
                "message": "請完成 MFA 綁定後再登入",
                "retryable": False,
            },
        )
    if result is None:
        await _reject_invalid_login(payload, request)
    token, expires_at, principal = result
    return _login_response(token, expires_at, principal)


@router.post("/login/challenges", response_model=BaseResponse[AdminPasswordChallengeResponse])
async def issue_login_challenge(payload: AdminPasswordChallengeRequest, request: Request):
    try:
        result = await asyncio.to_thread(issue_password_login_challenge, payload.username, payload.password, source_identifier=_client_ip(request) or "unknown")
    except AdminLoginRateLimitedError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "login_rate_limited", "message": "登入嘗試過於頻繁，請稍後再試", "retryable": True}) from error
    except (AdminSessionSchemaError, AdminSessionStorageError, AdminMfaConfigurationError) as error:
        raise _login_unavailable("admin_auth_unavailable", str(error)) from error
    if isinstance(result, MfaEnrollmentChallenge):
        return BaseResponse(
            data=AdminPasswordChallengeResponse(
                challenge_type="mfa_enrollment",
                challenge_id=result.challenge_id,
                challenge_token=result.challenge_token,
                expires_at=_as_utc_transport_datetime(result.expires_at),
                provisioning_uri=result.provisioning_uri,
            ),
            message="請完成 MFA 綁定",
        )
    if not isinstance(result, PasswordLoginChallenge):
        await _reject_invalid_login(payload, request)
    return BaseResponse(
        data=AdminPasswordChallengeResponse(
            challenge_type="factor_verification",
            challenge_id=result.challenge_id,
            challenge_token=result.challenge_token,
            expires_at=_as_utc_transport_datetime(result.expires_at),
        ),
        message="請輸入驗證器代碼",
    )


@router.post("/login/challenges/{challenge_id}/verify", response_model=BaseResponse[AdminSessionResponse])
async def verify_login_challenge(challenge_id: str, payload: AdminFactorVerificationRequest, request: Request):
    try:
        result = await asyncio.to_thread(complete_password_login_challenge, challenge_id=challenge_id, challenge_token=payload.challenge_token, factor_code=payload.factor_code, source_identifier=_client_ip(request) or "unknown")
    except AdminLoginRateLimitedError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "login_rate_limited", "message": "登入嘗試過於頻繁，請稍後再試", "retryable": True}) from error
    except (AdminSessionSchemaError, AdminSessionStorageError, AdminMfaConfigurationError) as error:
        raise _login_unavailable("admin_auth_unavailable", str(error)) from error
    if result is None:
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials_or_factor", "message": "帳號、密碼或驗證碼錯誤", "retryable": False})
    token, expires_at, principal = result
    return _login_response(token, expires_at, principal)


@router.post("/development-session", response_model=BaseResponse[AdminSessionResponse])
async def development_session():
    """Issue a local root Session only from explicit local env credentials; production always rejects it."""
    if not _local_developer_session_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到登入端點")
    username = os.getenv("DEV_ROOT_USERNAME", "").strip()
    password = os.getenv("DEV_ROOT_PASSWORD", "")
    if not username or not password:
        raise _login_unavailable("development_root_not_configured", "本機 root 帳密尚未設定")
    result = await asyncio.to_thread(authenticate_local_developer_root, username, password)
    if result is None:
        raise _login_unavailable("development_root_verification_failed", "本機 root 帳密驗證失敗")
    token, expires_at, principal = result
    return _login_response(token, expires_at, principal)


async def _authenticate(payload: AdminLoginRequest, source_identifier: str | None):
    try:
        return await asyncio.to_thread(
            authenticate_admin,
            payload.username,
            payload.password,
            session_minutes=30,
            totp_code=payload.totp_code,
            source_identifier=source_identifier or "unknown",
        )
    except AdminSessionSchemaError as error:
        raise _login_unavailable("admin_session_schema_not_ready", str(error)) from error
    except AdminLoginRateLimitedError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "login_rate_limited", "message": "登入嘗試過於頻繁，請稍後再試", "retryable": True}) from error
    except AdminSessionStorageError as error:
        raise _login_unavailable("admin_session_storage_unavailable", str(error)) from error
    except AdminMfaConfigurationError as error:
        raise _login_unavailable("admin_mfa_unavailable", str(error)) from error


async def _reject_invalid_login(payload, request) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "invalid_credentials_or_factor",
            "message": "帳號、密碼或驗證碼錯誤",
            "retryable": False,
        },
    )


def _login_response(token, expires_at, principal):
    return BaseResponse(
        data=AdminSessionResponse(
            access_token=token,
            expires_at=_as_utc_transport_datetime(expires_at),
            admin=AdminPublic(**principal.as_dict()),
        ),
        message="登入成功",
    )


def _local_developer_session_enabled() -> bool:
    environment = os.getenv("APP_ENV", "").strip().lower()
    profile = os.getenv("ACCESS_CONTROL_PROFILE", "").strip().lower()
    enabled = os.getenv("ENABLE_ADMIN_AUTH", "true").strip().lower()
    return (
        environment in {"development", "dev", "local", "test"}
        and profile == "local_developer_session"
        and enabled in {"1", "true", "yes", "on"}
    )


def _login_unavailable(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code, "message": message, "retryable": True},
    )


@router.post(
    "/enrollment/challenges/{challenge_id}/verify",
    response_model=BaseResponse[MfaEnrollmentVerificationResponse],
)
async def verify_enrollment_challenge(
    challenge_id: str, payload: MfaEnrollmentVerificationRequest
):
    try:
        recovery_codes = await asyncio.to_thread(
            complete_mfa_enrollment,
            challenge_id=challenge_id,
            challenge_token=payload.challenge_token,
            totp_code=payload.totp_code,
        )
    except ValueError as error:
        code = str(error)
        status_code = status.HTTP_409_CONFLICT if code == "mfa_challenge_expired" else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(
            status_code=status_code,
            detail={"code": code, "message": "MFA 綁定已失效或驗證碼錯誤", "retryable": False},
        ) from error
    except AdminMfaConfigurationError as error:
        raise _login_unavailable("mfa_secret_unavailable", str(error)) from error
    return BaseResponse(
        data=MfaEnrollmentVerificationResponse(recovery_codes=list(recovery_codes)),
        message="MFA 已完成綁定；請保存 recovery codes 後重新登入",
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
        data=AdminRefreshResponse(expires_at=_as_utc_transport_datetime(expires_at)),
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

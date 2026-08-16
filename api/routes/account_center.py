"""
File: account_center.py
Description: 提供 root 專屬帳號建立、啟停與密碼重設的 Account Center API。
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.admin_auth import require_root
from api.schemas.account_center import (
    AccountCenterUser,
    AccountCreateRequest,
    AccountEnabledRequest,
    AccountPasswordResetRequest,
    AccountSecurityActionRequest,
)
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import (
    AdminPrincipal,
    AdminSessionStorageError,
    create_account_center_user,
    list_account_center_users,
    reset_account_center_password,
    reset_account_center_mfa,
    revoke_account_center_sessions,
    set_account_center_enabled,
)


router = APIRouter(prefix="/api/v1/admin/accounts", tags=["Account Center"])


@router.get("", response_model=BaseResponse[list[AccountCenterUser]])
async def list_accounts(principal: AdminPrincipal = Depends(require_root)):
    del principal
    try:
        accounts = await asyncio.to_thread(list_account_center_users)
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data=[AccountCenterUser(**account.as_dict()) for account in accounts])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[AccountCenterUser])
async def create_account(
    payload: AccountCreateRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        account = await asyncio.to_thread(
            create_account_center_user,
            actor=principal,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            linked_line_user_id=payload.linked_line_user_id,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data=AccountCenterUser(**account.as_dict()), message="帳號已建立，首次登入需註冊 MFA")


@router.patch("/{account_id}/enabled", response_model=BaseResponse[dict[str, bool]])
async def set_enabled(
    account_id: int, payload: AccountEnabledRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        await asyncio.to_thread(
            set_account_center_enabled, actor=principal, account_id=account_id, enabled=payload.enabled, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data={"enabled": payload.enabled})


@router.post("/{account_id}/password-reset", response_model=BaseResponse[dict[str, bool]])
async def reset_password(
    account_id: int, payload: AccountPasswordResetRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        await asyncio.to_thread(
            reset_account_center_password, actor=principal, account_id=account_id, password=payload.password, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data={"password_reset": True})


@router.post("/{account_id}/mfa-reset", response_model=BaseResponse[dict[str, bool]])
async def reset_mfa(
    account_id: int, payload: AccountSecurityActionRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        await asyncio.to_thread(reset_account_center_mfa, actor=principal, account_id=account_id, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data={"mfa_reset": True})


@router.post("/{account_id}/sessions/revoke", response_model=BaseResponse[dict[str, bool]])
async def revoke_sessions(
    account_id: int, payload: AccountSecurityActionRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        await asyncio.to_thread(revoke_account_center_sessions, actor=principal, account_id=account_id, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data={"sessions_revoked": True})


def _storage_unavailable(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": "account_center_storage_unavailable", "message": str(error), "retryable": True},
    )

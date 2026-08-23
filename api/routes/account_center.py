"""
File: account_center.py
Description: 提供 root 專屬帳號建立、啟停與密碼重設的 Account Center API。
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.admin_auth import require_root
from api.error_contracts import typed_http_error
from api.schemas.account_center import (
    AccountDirectoryItemView,
    AccountCreateRequest,
    AccountEnabledRequest,
    AccountMutationReceiptView,
    AccountPasswordResetRequest,
    AccountSecurityActionRequest,
)
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import (
    AccountCommandReceipt,
    AdminPrincipal,
    AdminSessionStorageError,
    create_account_center_user_with_receipt,
    list_account_center_users,
    reset_account_center_password,
    reset_account_center_mfa,
    revoke_account_center_sessions,
    set_account_center_enabled,
)


router = APIRouter(prefix="/api/v1/admin/accounts", tags=["Account Center"])


@router.get("", response_model=BaseResponse[list[AccountDirectoryItemView]])
async def list_accounts(principal: AdminPrincipal = Depends(require_root)):
    del principal
    try:
        accounts = await asyncio.to_thread(list_account_center_users)
    except AdminSessionStorageError as error:
        raise typed_http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "unavailable",
            "account_directory_unavailable",
            "帳號清冊查詢暫時無法使用。",
            "account-directory-query",
            retryable=True,
        ) from error
    return BaseResponse(
        data=[
            AccountDirectoryItemView(
                id=int(account.id),
                username=account.username,
                display_name=account.display_name,
                enabled=account.enabled,
                is_root=account.is_root,
                access_control_version=account.access_control_version,
            )
            for account in accounts
        ]
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BaseResponse[AccountMutationReceiptView])
async def create_account(
    payload: AccountCreateRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        result = await asyncio.to_thread(
            create_account_center_user_with_receipt,
            actor=principal,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            linked_line_user_id=payload.linked_line_user_id,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as error:
        raise _command_error(error) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(
        data=_receipt_view(result.receipt, account=result.account),
        message="帳號已建立，首次登入需註冊 MFA",
    )


@router.patch("/{account_id}/enabled", response_model=BaseResponse[AccountMutationReceiptView])
async def set_enabled(
    account_id: int, payload: AccountEnabledRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        receipt = await asyncio.to_thread(
            set_account_center_enabled, actor=principal, account_id=account_id, enabled=payload.enabled, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key
        )
    except ValueError as error:
        raise _command_error(error) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data=_receipt_view(receipt))


@router.post("/{account_id}/password-reset", response_model=BaseResponse[AccountMutationReceiptView])
async def reset_password(
    account_id: int, payload: AccountPasswordResetRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        receipt = await asyncio.to_thread(
            reset_account_center_password, actor=principal, account_id=account_id, password=payload.password, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key
        )
    except ValueError as error:
        raise _command_error(error) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data=_receipt_view(receipt))


@router.post("/{account_id}/mfa-reset", response_model=BaseResponse[AccountMutationReceiptView])
async def reset_mfa(
    account_id: int, payload: AccountSecurityActionRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        receipt = await asyncio.to_thread(reset_account_center_mfa, actor=principal, account_id=account_id, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key)
    except ValueError as error:
        raise _command_error(error) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data=_receipt_view(receipt))


@router.post("/{account_id}/sessions/revoke", response_model=BaseResponse[AccountMutationReceiptView])
async def revoke_sessions(
    account_id: int, payload: AccountSecurityActionRequest, principal: AdminPrincipal = Depends(require_root)
):
    try:
        receipt = await asyncio.to_thread(revoke_account_center_sessions, actor=principal, account_id=account_id, reason=payload.reason, expected_version=payload.expected_version, idempotency_key=payload.idempotency_key)
    except ValueError as error:
        raise _command_error(error) from error
    except AdminSessionStorageError as error:
        raise _storage_unavailable(error) from error
    return BaseResponse(data=_receipt_view(receipt))


def _receipt_view(
    receipt: AccountCommandReceipt,
    *,
    account: AdminPrincipal | None = None,
) -> AccountMutationReceiptView:
    account_view = None
    if account is not None:
        account_view = AccountDirectoryItemView(
            id=int(account.id or 0),
            username=account.username,
            display_name=account.display_name,
            enabled=account.enabled,
            is_root=account.is_root,
            access_control_version=account.access_control_version,
        )
    return AccountMutationReceiptView(
        operation=receipt.operation,
        target_account_id=receipt.target_account_id,
        resulting_access_control_version=receipt.resulting_access_control_version,
        receipt_identity=receipt.receipt_identity,
        replayed=receipt.replayed,
        account=account_view,
    )


def _command_error(error: ValueError) -> HTTPException:
    code = str(error)
    if code == "帳號不存在":
        return typed_http_error(404, "not_found", "admin_account_not_found", "找不到指定帳號。", "account-center-command")
    if code == "admin_version_conflict":
        return typed_http_error(409, "conflict", "admin_version_conflict", "帳號版本已變更，請重新查詢。", "account-center-command")
    if code == "idempotency_key_conflict":
        return typed_http_error(409, "idempotency_mismatch", "admin_idempotency_mismatch", "相同識別碼已用於不同帳號命令。", "account-center-command")
    if "root 帳號受保護" in code:
        return typed_http_error(409, "domain_blocked", "admin_root_protected", "root 帳號不能由線上命令修改。", "account-center-command")
    return typed_http_error(409, "conflict", "admin_account_conflict", "帳號命令無法套用。", "account-center-command")


def _storage_unavailable(error: Exception) -> HTTPException:
    del error
    return typed_http_error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "unavailable",
        "account_center_storage_unavailable",
        "帳號中心暫時無法使用。",
        "account-center-command",
        retryable=True,
    )

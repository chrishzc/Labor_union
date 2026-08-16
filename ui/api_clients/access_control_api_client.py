"""
File: access_control_api_client.py
Description: 提供 Streamlit 全域登入與帳號中心使用的 typed Access Control API client。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import requests
from pydantic import BaseModel, ValidationError

from ui.pages.shared import resolve_api_base_url


class AccessControlApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, code: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.context = context or {}


class AdminPrincipalView(BaseModel):
    id: int | None
    username: str
    display_name: str
    role: str
    linked_line_user_id: str | None = None
    capabilities: list[str]
    is_root: bool = False
    access_control_version: int = 1


class AdminSessionView(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime
    admin: AdminPrincipalView


class PasswordChallengeView(BaseModel):
    challenge_id: str
    challenge_token: str
    expires_at: datetime


class AccountCenterUserView(AdminPrincipalView):
    enabled: bool


class _Envelope(BaseModel):
    data: Any = None


class AccessControlApiClient:
    def issue_password_challenge(self, *, username: str, password: str) -> PasswordChallengeView:
        return self._validate(PasswordChallengeView, self._request("POST", "/api/v1/admin/auth/login/challenges", json={"username": username, "password": password}))

    def verify_password_challenge(self, *, challenge_id: str, challenge_token: str, factor_code: str) -> AdminSessionView:
        return self._validate(AdminSessionView, self._request("POST", f"/api/v1/admin/auth/login/challenges/{challenge_id}/verify", json={"challenge_token": challenge_token, "factor_code": factor_code}))

    def login(self, *, username: str, password: str, totp_code: str) -> AdminSessionView:
        data = self._request("POST", "/api/v1/admin/auth/login", json={
            "username": username, "password": password, "totp_code": totp_code or None,
        })
        return self._validate(AdminSessionView, data)

    def me(self, token: str) -> AdminPrincipalView:
        return self._validate(AdminPrincipalView, self._request("GET", "/api/v1/admin/auth/me", token=token))

    def verify_enrollment(self, *, challenge_id: str, challenge_token: str, totp_code: str) -> list[str]:
        data = self._request(
            "POST", f"/api/v1/admin/auth/enrollment/challenges/{challenge_id}/verify",
            json={"challenge_token": challenge_token, "totp_code": totp_code},
        )
        recovery_codes = data.get("recovery_codes") if isinstance(data, dict) else None
        if not isinstance(recovery_codes, list) or not all(isinstance(code, str) for code in recovery_codes):
            raise AccessControlApiError("登入服務回傳格式無效", status_code=502, code="access_control_schema_invalid")
        return recovery_codes

    def logout(self, token: str) -> None:
        self._request("POST", "/api/v1/admin/auth/logout", token=token)

    def development_session(self) -> AdminSessionView:
        data = self._request("POST", "/api/v1/admin/auth/development-session")
        return self._validate(AdminSessionView, data)

    def list_accounts(self, token: str) -> list[AccountCenterUserView]:
        data = self._request("GET", "/api/v1/admin/accounts", token=token)
        if not isinstance(data, list):
            raise AccessControlApiError("帳號中心回傳格式無效", status_code=502, code="access_control_schema_invalid")
        return [self._validate(AccountCenterUserView, item) for item in data]

    def create_account(self, token: str, *, username: str, password: str, display_name: str, reason: str, idempotency_key: str | None = None) -> AccountCenterUserView:
        data = self._request("POST", "/api/v1/admin/accounts", token=token, json={
            "username": username, "password": password, "display_name": display_name,
            "reason": reason, "idempotency_key": idempotency_key or str(uuid4()),
        })
        return self._validate(AccountCenterUserView, data)

    def set_account_enabled(self, token: str, *, account_id: int, enabled: bool, reason: str, expected_version: int) -> None:
        self._request("PATCH", f"/api/v1/admin/accounts/{account_id}/enabled", token=token, json={"enabled": enabled, "reason": reason, "expected_version": expected_version, "idempotency_key": str(uuid4())})

    def reset_account_password(self, token: str, *, account_id: int, password: str, reason: str, expected_version: int) -> None:
        self._request("POST", f"/api/v1/admin/accounts/{account_id}/password-reset", token=token, json={"password": password, "reason": reason, "expected_version": expected_version, "idempotency_key": str(uuid4())})

    def reset_account_mfa(self, token: str, *, account_id: int, reason: str, expected_version: int) -> None:
        self._request("POST", f"/api/v1/admin/accounts/{account_id}/mfa-reset", token=token, json={"reason": reason, "expected_version": expected_version, "idempotency_key": str(uuid4())})

    def revoke_account_sessions(self, token: str, *, account_id: int, reason: str, expected_version: int) -> None:
        self._request("POST", f"/api/v1/admin/accounts/{account_id}/sessions/revoke", token=token, json={"reason": reason, "expected_version": expected_version, "idempotency_key": str(uuid4())})

    def _request(self, method: str, path: str, *, token: str | None = None, json: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = requests.request(method, f"{resolve_api_base_url()}{path}", headers=headers, json=json, timeout=8)
        except requests.RequestException as error:
            raise AccessControlApiError("無法連線到登入服務", status_code=503, code="access_control_transport_unavailable") from error
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not response.ok:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            detail = detail if isinstance(detail, dict) else {}
            raise AccessControlApiError(
                str(detail.get("message") or "登入請求失敗"), status_code=response.status_code,
                code=str(detail.get("code") or "access_control_request_failed"), context=detail,
            )
        try:
            return _Envelope.model_validate(payload).data or {}
        except ValidationError as error:
            raise AccessControlApiError("登入服務回傳格式無效", status_code=502, code="access_control_schema_invalid") from error

    @staticmethod
    def _validate(model: type[BaseModel], value: dict[str, Any]) -> Any:
        try:
            return model.model_validate(value)
        except ValidationError as error:
            raise AccessControlApiError("登入服務回傳格式無效", status_code=502, code="access_control_schema_invalid") from error

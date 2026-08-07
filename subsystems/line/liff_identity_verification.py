"""
================================================================================
檔案名稱: services/line_liff_identity_service.py
功能說明: LIFF 使用者身分驗證服務，驗證 ID Token 並取得可信任的 LINE User ID
================================================================================
"""

from __future__ import annotations

import os

import requests


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}
VERIFY_ID_TOKEN_URL = "https://api.line.me/oauth2/v2.1/verify"


class LiffIdentityError(ValueError):
    pass


def liff_token_required() -> bool:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    configured = os.getenv("LIFF_REQUIRE_ID_TOKEN", "").strip().lower()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    return app_env not in DEVELOPMENT_ENVIRONMENTS


def resolve_line_user_id(
    *,
    id_token: str | None,
    development_user_id: str | None,
) -> str:
    """Verify an ID token in production; allow an explicit local fallback in development."""
    token = (id_token or "").strip()
    channel_id = os.getenv("LINE_LOGIN_CHANNEL_ID", "").strip()
    if token and channel_id:
        try:
            response = requests.post(
                VERIFY_ID_TOKEN_URL,
                data={"id_token": token, "client_id": channel_id},
                timeout=8,
            )
        except requests.RequestException as exc:
            raise LiffIdentityError("目前無法向 LINE 驗證登入身分") from exc
        if not response.ok:
            raise LiffIdentityError("LINE 登入憑證無效或已過期")
        subject = str(response.json().get("sub") or "").strip()
        if not subject:
            raise LiffIdentityError("LINE 驗證結果缺少使用者識別碼")
        return subject

    if liff_token_required():
        if not channel_id:
            raise LiffIdentityError("正式環境尚未設定 LINE_LOGIN_CHANNEL_ID")
        raise LiffIdentityError("缺少 LIFF ID Token，請重新從 LINE 開啟此頁")

    fallback = (development_user_id or "").strip()
    if not fallback:
        raise LiffIdentityError("開發模式缺少測試用 LINE User ID")
    return fallback


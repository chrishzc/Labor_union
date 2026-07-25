"""共用 UI API 工具函式。"""

from __future__ import annotations

import os
import streamlit as st


API_BASE_URL_ENV = "API_BASE_URL"
API_BASE_URL_DEFAULT = "http://localhost:8000"
ADMIN_AUTH_CONTEXT_ENV = "ADMIN_AUTH_CONTEXT"


def resolve_api_base_url() -> str:
    """在 runtime 解析 API_BASE_URL，支援執行過程中動態變更。"""
    value = (os.getenv(API_BASE_URL_ENV, API_BASE_URL_DEFAULT) or API_BASE_URL_DEFAULT).strip()
    return value.rstrip("/")


def resolve_admin_auth_context() -> str:
    """從登入狀態或環境變數取得 admin auth context。

    現階段若未有可信登入上下文，僅允許透過 ADMIN_AUTH_CONTEXT 環境變數。
    缺少設定時採用 fail-closed，直接拋出錯誤，避免預設 fallback 帶來未授權風險。
    """
    # 目前未建立 UI 層登入憑證注入；保留 session_state fallback 以便日後整合。
    for key in ("operator", "operator_id", "user_role", "admin_role"):
        try:
            value = st.session_state.get(key)
        except Exception:
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip()

    env_value = (os.getenv(ADMIN_AUTH_CONTEXT_ENV, "") or "").strip()
    if not env_value:
        raise RuntimeError(
            "缺少 ADMIN_AUTH_CONTEXT 環境變數，無法組裝管理員授權 Header。"
        )
    return env_value


def build_admin_headers() -> dict[str, str]:
    return {"X-Auth-Context": resolve_admin_auth_context()}

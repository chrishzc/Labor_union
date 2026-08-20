"""
File: shared.py
Description: 提供 Streamlit 共用 API 位址、Bearer transport 與明確 auth profile 判定。
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_BASE_URL_ENV = "API_BASE_URL"
API_BASE_URL_DEFAULT = "http://localhost:8000"
ADMIN_ACCESS_TOKEN_KEY = "line_admin_access_token"
DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}


def resolve_api_base_url() -> str:
    """在 runtime 解析 API_BASE_URL，支援執行過程中動態變更。"""
    value = (os.getenv(API_BASE_URL_ENV, API_BASE_URL_DEFAULT) or API_BASE_URL_DEFAULT).strip()
    return value.rstrip("/")


def admin_auth_is_bypassed() -> bool:
    """與 backend 相同：只有 local_bypass 可省略 Bearer Session。"""
    app_env = (os.getenv("APP_ENV", "development") or "development").strip().lower()
    enabled = (os.getenv("ENABLE_ADMIN_AUTH", "true") or "true").strip().lower()
    profile = (os.getenv("ACCESS_CONTROL_PROFILE", "") or "").strip().lower()
    return (
        profile == "local_bypass"
        and app_env in DEVELOPMENT_ENVIRONMENTS
        and enabled in {"0", "false", "no", "off"}
    )


def local_developer_session_is_enabled() -> bool:
    """Allow only the named local profile to obtain a root Session from local env credentials."""
    app_env = (os.getenv("APP_ENV", "development") or "development").strip().lower()
    enabled = (os.getenv("ENABLE_ADMIN_AUTH", "true") or "true").strip().lower()
    profile = (os.getenv("ACCESS_CONTROL_PROFILE", "") or "").strip().lower()
    return (
        profile == "local_developer_session"
        and app_env in {"development", "dev", "local", "test"}
        and enabled in {"1", "true", "yes", "on"}
    )


def resolve_admin_access_token() -> str:
    try:
        value = st.session_state.get(ADMIN_ACCESS_TOKEN_KEY)
    except Exception:
        value = None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("缺少有效的管理員 Session，請先登入管理後台。")
    return value.strip()


def build_admin_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if not admin_auth_is_bypassed():
        headers["Authorization"] = f"Bearer {resolve_admin_access_token()}"
    return headers

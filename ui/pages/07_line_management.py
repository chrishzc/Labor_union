"""
================================================================================
檔案名稱: ui/pages/07_line_management.py
功能說明: Streamlit LINE 管理中心主頁，整合訊息、自動通知、選單、表單、人工確認與發送紀錄
================================================================================
"""

from __future__ import annotations

import streamlit as st

from ui.components.line_message_manager import render_message_manager
from ui.components.line_liff_manager import render_liff_manager
from ui.components.line_review_manager import render_review_manager
from ui.components.line_rich_menu_manager import render_rich_menu_manager
from ui.components.line_schedule_manager import render_schedule_manager
from ui.components.line_task_manager import render_task_manager
from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


title = "💬 LINE 管理中心"
TOKEN_KEY = "line_admin_access_token"
ADMIN_KEY = "line_admin_profile"


def _clear_session() -> None:
    st.session_state.pop(TOKEN_KEY, None)
    st.session_state.pop(ADMIN_KEY, None)


def _login(client: LineAdminApiClient) -> None:
    st.subheader("工會人員登入")
    st.caption("此登入只用於內部管理頁；LINE 一般使用者不會看到。")
    with st.form("line_admin_login"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", type="primary")
    if submitted:
        try:
            session = client.login(username, password)
        except LineAdminApiError as exc:
            st.error(str(exc))
            return
        st.session_state[TOKEN_KEY] = session["access_token"]
        st.session_state[ADMIN_KEY] = session["admin"]
        st.rerun()


ROLE_LABELS = {
    "line_agent": "服務人員",
    "line_manager": "LINE 主管",
    "system_admin": "系統管理員",
}


def _overview(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    try:
        health = client.health(token)
        capabilities = client.capabilities(token)
    except LineAdminApiError as exc:
        if exc.status_code == 401:
            _clear_session()
            st.warning("登入已過期，請重新登入。")
            st.rerun()
        st.error(str(exc))
        return

    status_value = health.get("status", "unknown")
    worker_running = health.get("worker", {}).get("running", False)
    database_ok = health.get("database", {}).get("ok", False)
    col1, col2, col3 = st.columns(3)
    system_ok = status_value in {"ok", "healthy"} and database_ok
    col1.metric("整體狀態", "可正常使用" if system_ok else "需要檢查")
    col2.metric("自動發送", "正常運作" if worker_running else "目前暫停")
    col3.metric("資料連線", "正常" if database_ok else "異常")

    if system_ok and worker_running:
        st.success("LINE 管理功能與自動發送服務目前運作正常。")
    else:
        st.warning("部分服務未正常運作，請通知系統管理員協助處理。")

    if profile.get("role") == "system_admin":
        with st.expander("系統管理資訊"):
            available = capabilities.get("available", {})
            for name, enabled in available.items():
                st.write(("✅" if enabled else "⬜") + f" {name}")
            st.caption("下列設定僅供系統管理員檢查，不會顯示實際金鑰內容。")
            st.json(health.get("line_credentials", {}))


def _planned_panel(name: str, description: str) -> None:
    st.subheader(name)
    st.info(f"5.1 已完成安全入口與接口骨架。{description}將在後續 5.x 接上現有 API。")


def _render_automatic_notifications(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    workspace = st.radio(
        "自動通知工作區",
        ("新好友通知設定", "發送紀錄"),
        horizontal=True,
    )
    if workspace == "新好友通知設定":
        render_schedule_manager(client, token, profile)
        return
    render_task_manager(client, token, profile)


def _render_messages(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_message_manager(client, token, profile)


def _render_rich_menu(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_rich_menu_manager(client, token, profile)


def _render_liff(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_liff_manager(client, token, profile)


def _render_reviews(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_review_manager(client, token, profile)


def _render_customer_service(
    _client: LineAdminApiClient,
    _token: str | None,
    _profile: dict,
) -> None:
    _planned_panel("客服入口", "工會人員客服系統")


def _render_audit_log(
    _client: LineAdminApiClient,
    _token: str | None,
    _profile: dict,
) -> None:
    _planned_panel("操作紀錄", "管理員異動稽核")


LINE_WORKSPACE_RENDERERS = {
    "使用狀態": _overview,
    "訊息內容": _render_messages,
    "自動通知": _render_automatic_notifications,
    "LINE 下方選單": _render_rich_menu,
    "LINE 表單": _render_liff,
    "待確認申請": _render_reviews,
    "客服入口": _render_customer_service,
    "操作紀錄": _render_audit_log,
}


def _render_selected_workspace(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    workspace = st.radio(
        "LINE 管理工作區",
        tuple(LINE_WORKSPACE_RENDERERS),
        horizontal=True,
    )
    LINE_WORKSPACE_RENDERERS[workspace](client, token, profile)


def show() -> None:
    st.title(title)
    client = LineAdminApiClient()
    if not client.configured:
        st.error("尚未設定 INTERNAL_API_KEY，LINE 管理中心已拒絕啟用。")
        st.code("請在 .env 設定 INTERNAL_API_KEY，或使用 start.bat 共同啟動前後端。")
        return

    bypassed = client.admin_auth_bypassed
    token = st.session_state.get(TOKEN_KEY)
    if not bypassed and not token:
        _login(client)
        return

    try:
        profile = client.me(token)
    except LineAdminApiError as exc:
        _clear_session()
        st.warning(f"請重新登入：{exc}")
        return
    st.session_state[ADMIN_KEY] = profile

    if bypassed:
        st.warning(
            "開發模式：已略過管理員登入。內部 API 金鑰仍在驗證；正式環境會強制恢復登入。"
        )

    header_left, header_right = st.columns([4, 1])
    header_left.caption(
        f"登入者：{profile['display_name']}（{ROLE_LABELS.get(profile['role'], '服務人員')}）"
    )
    if not bypassed and header_right.button("登出", width="stretch"):
        try:
            client.logout(token)
        except LineAdminApiError:
            pass
        _clear_session()
        st.rerun()

    _render_selected_workspace(client, token, profile)

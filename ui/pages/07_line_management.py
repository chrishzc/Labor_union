"""Stage 5.1 entry shell for the authenticated LINE management center."""

from __future__ import annotations

import streamlit as st

from ui.components.line_message_manager import render_message_manager
from ui.services.line_api_client import LineAdminApiClient, LineAdminApiError


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


def _overview(client: LineAdminApiClient, token: str | None) -> None:
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
    col1.metric("LINE 系統", status_value)
    col2.metric("背景 Worker", "執行中" if worker_running else "未執行")
    col3.metric("資料庫", "正常" if database_ok else "異常")

    st.subheader("目前已提供的後端能力")
    available = capabilities.get("available", {})
    for name, enabled in available.items():
        st.write(("✅" if enabled else "⬜") + f" {name}")

    with st.expander("LINE 金鑰設定狀態"):
        st.json(health.get("line_credentials", {}))


def _planned_panel(name: str, description: str) -> None:
    st.subheader(name)
    st.info(f"5.1 已完成安全入口與接口骨架。{description}將在後續 5.x 接上現有 API。")


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
        f"登入者：{profile['display_name']}（{profile['role']}）｜Session 僅保存在目前 Streamlit 執行階段"
    )
    if not bypassed and header_right.button("登出", use_container_width=True):
        try:
            client.logout(token)
        except LineAdminApiError:
            pass
        _clear_session()
        st.rerun()

    tabs = st.tabs(
        [
            "系統總覽",
            "訊息管理",
            "排程任務",
            "Rich Menu",
            "LIFF 設定",
            "人工審查",
            "客服入口",
            "操作紀錄",
        ]
    )
    with tabs[0]:
        _overview(client, token)
    with tabs[1]:
        render_message_manager(client, token, profile)

    panels = [
        ("排程與任務", "D+1／D+2／D+3 與 Worker 任務狀態"),
        ("Rich Menu 管理", "三種角色選單、按鈕與發布流程"),
        ("LIFF 設定", "頁面文字、欄位與主題設定"),
        ("人工審查", "月嫂身分申請與客戶重新綁定"),
        ("客服入口", "工會人員客服系統"),
        ("操作紀錄", "管理員異動稽核"),
    ]
    for tab, (name, description) in zip(tabs[2:], panels):
        with tab:
            _planned_panel(name, description)

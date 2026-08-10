"""Read-only performance summary for system administrators."""

from __future__ import annotations

import streamlit as st

from api.schemas.system_status import PerformanceSnapshotResponse
from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.api_clients.system_status_api_client import (
    SystemStatusApiClient,
    SystemStatusApiError,
)


title = "🩺 系統狀態"
TOKEN_KEY = "line_admin_access_token"


def _login(client: LineAdminApiClient) -> None:
    st.caption("此頁僅供系統管理員查看，不保存逐筆效能資料。")
    with st.form("system_status_login"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", type="primary")
    if submitted:
        try:
            st.session_state[TOKEN_KEY] = client.login(username, password)["access_token"]
        except LineAdminApiError as error:
            st.error(str(error))
            return
        st.rerun()


def _format_milliseconds(value: object) -> str:
    if value is None:
        return "尚無樣本"
    return f"{float(value):,.1f} ms"


def _render_snapshot(snapshot: PerformanceSnapshotResponse) -> None:
    st.caption("僅顯示服務啟動後的固定彙總；不保存逐筆請求、案件、人員或 payload。")
    st.caption(f"彙總起點：{snapshot.started_at}")
    columns = st.columns(4)
    columns[0].metric("API 樣本數", snapshot.request_count)
    columns[1].metric("平均回應", _format_milliseconds(snapshot.average_response_time_ms))
    columns[2].metric("p50 上限", _format_milliseconds(snapshot.p50_response_time_upper_bound_ms))
    columns[3].metric("p95 上限", _format_milliseconds(snapshot.p95_response_time_upper_bound_ms))
    st.metric("最大回應時間", _format_milliseconds(snapshot.maximum_response_time_ms))
    st.info("本頁只供人工檢視與比較，不會發出警告、建立異常或阻擋 release。")


def show() -> None:
    st.title(title)
    client = LineAdminApiClient()
    status_client = SystemStatusApiClient(client)
    if not client.configured:
        st.error("尚未設定 INTERNAL_API_KEY，無法讀取系統狀態。")
        return
    token = st.session_state.get(TOKEN_KEY)
    if not client.admin_auth_bypassed and not token:
        _login(client)
        return
    try:
        _render_snapshot(status_client.performance_snapshot(token))
    except SystemStatusApiError as error:
        st.error(str(error))

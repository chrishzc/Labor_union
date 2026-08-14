"""
================================================================================
檔案名稱: ui/pages/07_line_management.py
功能說明: Streamlit LINE 薄管理介面，整合監控、訊息、群組、契約與知識管理 API
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
from ui.components.line_runtime_manager import render_runtime_manager
from ui.components.line_order_group_manager import render_order_group_manager
from ui.components.knowledge_management import render_knowledge_management
from ui.components.line_customer_service_manager import render_customer_service_manager
from ui.components.line_audit_manager import render_audit_manager
from ui.components.line_identity_binding_manager import render_identity_binding_manager
from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.api_clients.runtime_health_api_client import RuntimeHealthApiClient
from ui.api_clients.knowledge_retrieval_api_client import KnowledgeRetrievalApiClient
from ui.components.line_ui_support import has_capability


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
    "line_viewer": "只讀人員",
    "line_agent": "一般職員",
    "line_manager": "主管",
    "system_admin": "老闆／系統管理者",
}


def _overview(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_runtime_manager(RuntimeHealthApiClient(client), token, profile)


def _render_automatic_notifications(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    options = []
    if has_capability(profile, "line.config.read"):
        options.append("新好友通知設定")
    if has_capability(profile, "line.task.read"):
        options.append("發送紀錄")
    if not options:
        st.info("目前帳號沒有自動通知的查看權限。")
        return
    workspace = st.radio(
        "自動通知工作區",
        options,
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


def _render_identity_bindings(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_identity_binding_manager(client, token, profile)


def _render_customer_service(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_customer_service_manager(client, token, profile)


def _render_audit_log(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    render_audit_manager(RuntimeHealthApiClient(client), token, profile)


def _render_order_groups(client, token, profile) -> None:
    render_order_group_manager(client, token, profile)


def _render_knowledge(client, token, profile) -> None:
    render_knowledge_management(KnowledgeRetrievalApiClient(client), token, profile)


LINE_WORKSPACE_RENDERERS = {
    "使用狀態": _overview,
    "訊息內容": _render_messages,
    "自動通知": _render_automatic_notifications,
    "Rich Menu": _render_rich_menu,
    "LIFF 表單": _render_liff,
    "待確認申請": _render_reviews,
    "身分管理": _render_identity_bindings,
    "訂單群組": _render_order_groups,
    "知識內容": _render_knowledge,
    "客服入口": _render_customer_service,
    "操作紀錄": _render_audit_log,
}

WORKSPACE_CAPABILITIES = {
    "使用狀態": {"line.monitor.read"},
    "訊息內容": {"line.config.read"},
    "自動通知": {"line.config.read", "line.task.read"},
    "Rich Menu": {"line.config.read"},
    "LIFF 表單": {"line.config.read"},
    "待確認申請": {"line.review.read"},
    "身分管理": {"line.identity.binding.read"},
    "訂單群組": {"line.order_group.read"},
    "知識內容": {"knowledge.read"},
    "客服入口": {"line.customer_service.read"},
    "操作紀錄": {"line.audit.read"},
}


def _render_selected_workspace(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict,
) -> None:
    available = [
        name
        for name in LINE_WORKSPACE_RENDERERS
        if any(has_capability(profile, capability) for capability in WORKSPACE_CAPABILITIES[name])
    ]
    if not available:
        st.warning("目前帳號沒有 LINE 管理功能的查看權限。")
        return
    workspace = st.radio(
        "LINE 管理工作區",
        available,
        horizontal=True,
    )
    LINE_WORKSPACE_RENDERERS[workspace](client, token, profile)


def show() -> None:
    st.title(title)
    client = LineAdminApiClient()
    bypassed = client.admin_auth_bypassed
    token = st.session_state.get(TOKEN_KEY)
    if not bypassed and not token:
        _login(client)
        return

    try:
        profile = client.me(token)
        capability_state = client.capabilities(token)
    except LineAdminApiError as exc:
        _clear_session()
        st.warning(f"請重新登入：{exc}")
        return
    profile["effective_capabilities"] = capability_state.get(
        "effective_capabilities", []
    )
    profile["runtime_availability"] = capability_state.get(
        "runtime_availability", {}
    )
    st.session_state[ADMIN_KEY] = profile

    if bypassed:
        st.warning(
            "開發模式：已略過管理員登入；正式環境會強制恢復登入與權限驗證。"
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

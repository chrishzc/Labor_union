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
from ui.components.contract_evidence_manager import render_contract_evidence_manager
from ui.components.knowledge_management import render_knowledge_management
from ui.components.line_customer_service_manager import render_customer_service_manager
from ui.components.line_audit_manager import render_audit_manager
from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.api_clients.runtime_health_api_client import RuntimeHealthApiClient
from ui.api_clients.contract_integration_api_client import ContractIntegrationApiClient
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
    "line_agent": "服務人員",
    "line_manager": "LINE 主管",
    "system_admin": "系統管理員",
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


def _render_contracts(client, token, profile) -> None:
    render_contract_evidence_manager(
        ContractIntegrationApiClient(client), token, profile
    )


def _render_knowledge(client, token, profile) -> None:
    render_knowledge_management(KnowledgeRetrievalApiClient(client), token, profile)


LINE_WORKSPACE_RENDERERS = {
    "使用狀態": _overview,
    "訊息內容": _render_messages,
    "自動通知": _render_automatic_notifications,
    "LINE 下方選單": _render_rich_menu,
    "LINE 表單": _render_liff,
    "待確認申請": _render_reviews,
    "訂單群組": _render_order_groups,
    "電子契約": _render_contracts,
    "知識內容": _render_knowledge,
    "客服入口": _render_customer_service,
    "操作紀錄": _render_audit_log,
}

WORKSPACE_CAPABILITIES = {
    "使用狀態": {"line.monitor.read"},
    "訊息內容": {"line.config.read"},
    "自動通知": {"line.config.read", "line.task.read"},
    "LINE 下方選單": {"line.config.read"},
    "LINE 表單": {"line.config.read"},
    "待確認申請": {"line.review.read"},
    "訂單群組": {"line.order_group.read"},
    "電子契約": {"contract.evidence.read"},
    "知識內容": {"knowledge.read"},
    "客服入口": {"line.config.read"},
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

"""
File: 09_access_management.py
Description: 呈現唯一 root 專屬的帳號中心，不提供一般業務權限調整。
"""

import streamlit as st

from ui.api_clients.access_control_api_client import AccessControlApiClient, AccessControlApiError
from ui.pages.shared import ADMIN_ACCESS_TOKEN_KEY


title = "帳號中心"


def show() -> None:
    st.title(title)
    token = st.session_state.get(ADMIN_ACCESS_TOKEN_KEY)
    if not isinstance(token, str) or not token:
        st.warning("請先完成全域登入。")
        return
    client = AccessControlApiClient()
    try:
        principal = client.me(token)
    except AccessControlApiError as error:
        st.error(str(error))
        return
    if not principal.is_root:
        st.error("僅唯一 root 可管理帳號中心；所有 enabled 帳號仍有相同業務功能。")
        return
    _render_create_account(client, token)
    _render_accounts(client, token)


def _render_create_account(client: AccessControlApiClient, token: str) -> None:
    st.subheader("建立帳號")
    st.caption("新帳號與 root 的業務功能相同；首次登入由本人完成 MFA 綁定。")
    with st.form("account_center_create"):
        username = st.text_input("帳號")
        display_name = st.text_input("顯示名稱")
        password = st.text_input("初始密碼", type="password")
        submitted = st.form_submit_button("建立帳號")
    if submitted:
        try:
            client.create_account(
                token, username=username, display_name=display_name, password=password,
                reason="root 建立帳號",
            )
        except AccessControlApiError as error:
            st.error(str(error))
            return
        st.success("帳號已建立。請安全交付初始密碼；本人首次登入時完成 MFA 綁定。")
        st.rerun()


def _render_accounts(client: AccessControlApiClient, token: str) -> None:
    st.subheader("帳號清單")
    try:
        accounts = client.list_accounts(token)
    except AccessControlApiError as error:
        st.error(str(error))
        return
    st.dataframe(
        [{"ID": item.id, "帳號": item.username, "姓名": item.display_name,
          "狀態": "啟用" if item.enabled else "停用", "root": item.is_root} for item in accounts],
        hide_index=True, use_container_width=True,
    )
    non_root = [item for item in accounts if not item.is_root]
    if not non_root:
        return
    labels = {f"{item.display_name}（{item.username}）": item for item in non_root}
    selected = labels[st.selectbox("選擇非 root 帳號", tuple(labels))]
    reason = st.text_input("本次高風險操作原因", key=f"account_reason_{selected.id}")
    action, reset, mfa, sessions = st.columns(4)
    with action:
        label = "停用並撤銷 Session" if selected.enabled else "啟用帳號"
        if st.button(label, key=f"account_enable_{selected.id}"):
            try:
                client.set_account_enabled(token, account_id=selected.id or 0, enabled=not selected.enabled, reason=reason, expected_version=selected.access_control_version)
            except AccessControlApiError as error:
                st.error(str(error))
            else:
                st.rerun()
    with reset:
        new_password = st.text_input("新密碼", type="password", key=f"account_password_{selected.id}")
        if st.button("重設密碼並撤銷 Session", key=f"account_reset_{selected.id}"):
            try:
                client.reset_account_password(token, account_id=selected.id or 0, password=new_password, reason=reason, expected_version=selected.access_control_version)
            except AccessControlApiError as error:
                st.error(str(error))
            else:
                st.success("密碼已重設，既有 Session 已撤銷。")
    with mfa:
        if st.button("重設 MFA", key=f"account_mfa_{selected.id}"):
            try:
                client.reset_account_mfa(token, account_id=selected.id or 0, reason=reason, expected_version=selected.access_control_version)
            except AccessControlApiError as error:
                st.error(str(error))
            else:
                st.success("MFA 已重設，帳號下次登入須重新綁定。")
    with sessions:
        if st.button("撤銷所有 Session", key=f"account_sessions_{selected.id}"):
            try:
                client.revoke_account_sessions(token, account_id=selected.id or 0, reason=reason, expected_version=selected.access_control_version)
            except AccessControlApiError as error:
                st.error(str(error))
            else:
                st.success("既有 Session 已撤銷。")

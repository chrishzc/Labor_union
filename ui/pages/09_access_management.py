"""工會人員角色與權限管理。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


title = "工會人員權限"
TOKEN_KEY = "line_admin_access_token"


def show() -> None:
    st.title(title)
    client = LineAdminApiClient()
    token = st.session_state.get(TOKEN_KEY)
    if not client.admin_auth_bypassed and not token:
        st.warning("請先至 LINE 管理中心登入工會人員帳號。")
        return
    try:
        profile = client.me(token)
        policy = client.request("GET", "/api/v1/admin/capability-grants/policy/overview", token=token)
        accounts = client.request("GET", "/api/v1/admin/capability-grants/accounts/list", token=token)
    except LineAdminApiError as exc:
        st.error(str(exc))
        return

    st.caption(f"目前登入者：{profile['display_name']}（{_role_label(profile['role'], policy)}）")
    tabs = st.tabs(["角色權限矩陣", "員工帳號權限", "個別權限調整"])
    with tabs[0]:
        _render_policy(policy)
    with tabs[1]:
        _render_accounts(accounts, policy)
    with tabs[2]:
        _render_grant_form(client, token, accounts, policy)


def _render_policy(policy: dict[str, Any]) -> None:
    st.subheader("角色權限矩陣")
    rows = []
    capability_labels = _capability_labels(policy)
    for role in policy.get("roles", []):
        rows.append(
            {
                "角色": role["label"],
                "等級": role["level"],
                "說明": role["description"],
                "預設功能數": len(role.get("capabilities", [])),
                "預設功能": "、".join(
                    capability_labels.get(item, item)
                    for item in role.get("capabilities", [])
                ),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_accounts(accounts: list[dict[str, Any]], policy: dict[str, Any]) -> None:
    st.subheader("員工帳號權限")
    capability_labels = _capability_labels(policy)
    rows = []
    for account in accounts:
        rows.append(
            {
                "ID": account["id"],
                "帳號": account["username"],
                "姓名": account["display_name"],
                "角色": _role_label(account["role"], policy),
                "狀態": "啟用" if account["enabled"] else "停用",
                "授權版本": account.get("authorization_version", 0),
                "額外授權": "、".join(
                    capability_labels.get(item["capability"], item["capability"])
                    for item in account.get("extra_grants", [])
                ) or "-",
                "有效功能數": len(account.get("effective_capabilities", [])),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_grant_form(
    client: LineAdminApiClient,
    token: str | None,
    accounts: list[dict[str, Any]],
    policy: dict[str, Any],
) -> None:
    st.subheader("個別權限調整")
    st.caption("用於臨時加權或撤回額外權限；角色本身的預設權限不會在這裡被改掉。")
    if not accounts:
        st.info("目前沒有工會人員帳號。")
        return
    capability_labels = _capability_labels(policy)
    account_labels = {
        f"{item['display_name']}（{item['username']}，{_role_label(item['role'], policy)}）": item
        for item in accounts
        if item.get("enabled")
    }
    selected_label = st.selectbox("選擇員工", tuple(account_labels))
    selected = account_labels[selected_label]
    capabilities = [item["capability"] for item in policy.get("capabilities", [])]
    capability = st.selectbox(
        "權限項目",
        capabilities,
        format_func=lambda value: f"{capability_labels.get(value, value)}（{value}）",
    )
    action = st.radio("操作", ("grant", "revoke"), format_func=lambda value: "授權" if value == "grant" else "撤回", horizontal=True)
    reason = st.text_input("原因", value="依職務需求調整權限")
    days = st.number_input("授權天數", min_value=1, max_value=365, value=30, disabled=action == "revoke")
    if st.button("送出權限調整", type="primary"):
        payload = {
            "target_admin_user_id": int(selected["id"]),
            "capability": capability,
            "action": action,
            "expected_authorization_version": int(selected.get("authorization_version", 0)),
            "reason": reason,
            "idempotency_key": f"ui-access-grant:{uuid4().hex}",
            "correlation_id": f"ui-access-grant:{uuid4().hex}",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(days=int(days))
            ).isoformat() if action == "grant" else None,
        }
        try:
            client.request(
                "POST",
                "/api/v1/admin/capability-grants/apply",
                token=token,
                json=payload,
            )
        except LineAdminApiError as exc:
            st.error(str(exc))
            return
        st.success("權限調整已送出，該員工既有登入 Session 會被撤銷，需重新登入。")
        st.rerun()


def _role_label(role: str, policy: dict[str, Any]) -> str:
    for item in policy.get("roles", []):
        if item["role"] == role:
            return item["label"]
    return role


def _capability_labels(policy: dict[str, Any]) -> dict[str, str]:
    return {
        item["capability"]: item["label"]
        for item in policy.get("capabilities", [])
    }

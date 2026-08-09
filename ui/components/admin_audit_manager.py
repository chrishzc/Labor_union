"""Privacy-safe audit review for every authenticated administrator."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


def render_admin_audit_manager(client: LineAdminApiClient, token: str | None, profile: dict) -> None:
    st.subheader("管理員操作紀錄")
    st.caption("可查看兩年內的操作紀錄；IP 與敏感資料均已遮罩。")
    search = st.text_input("依管理員名稱或帳號搜尋")
    try:
        page = client.admin_audits(token, actor_query=search)
    except LineAdminApiError as exc:
        st.error(f"無法載入操作紀錄：{exc}")
        return
    _render_audit_list(page)
    if page["items"]:
        _render_audit_detail(client, token, profile, page["items"])


def _render_audit_list(page: dict) -> None:
    rows = [{"編號": item["id"], "操作者": item.get("actor_display_name") or "系統", "動作": item["action"], "資源": item.get("resource_type") or "-", "結果": item.get("result_status") or "-", "IP": item.get("ip_address_masked") or "-", "時間": item["created_at"]} for item in page["items"]]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption(f"第 {page['page']} 頁，共 {page['total']} 筆；保存超過兩年的紀錄已移至受限 archive。")


def _render_audit_detail(client: LineAdminApiClient, token: str | None, profile: dict, items: list[dict]) -> None:
    del profile
    audit_id = st.selectbox("查看明細", [item["id"] for item in items])
    if not st.button("開啟明細"):
        return
    try:
        detail = client.admin_audit_detail(token, audit_id)
    except LineAdminApiError as exc:
        st.error(f"無法載入明細：{exc}")
        return
    st.json(detail)

"""Thin privacy-safe Streamlit viewer for administrator operation audit records."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiError


def render_audit_manager(runtime_client, token, _profile: dict[str, Any]) -> None:
    st.subheader("管理操作紀錄")
    st.caption("只顯示安全摘要，不包含密碼、Token、內部金鑰、IP 或完整請求內容。")
    category = st.selectbox("紀錄類型", ["LINE", "電子契約", "知識內容", "全部管理操作"])
    action_prefix = {
        "LINE": "line.",
        "電子契約": "contract.",
        "知識內容": "knowledge.",
        "全部管理操作": None,
    }[category]
    try:
        records = runtime_client.audit_records(token, action_prefix=action_prefix)
    except LineAdminApiError as error:
        st.error(f"無法載入操作紀錄：{error}")
        return
    if not records:
        st.info("目前沒有符合條件的操作紀錄。")
        return
    st.dataframe(pd.DataFrame(records), width="stretch", hide_index=True)


__all__ = ["render_audit_manager"]

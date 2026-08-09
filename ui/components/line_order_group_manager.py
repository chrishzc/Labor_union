"""Thin Streamlit panel for canonical order-group bindings and immutable events."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


STATUS_LABELS = {
    "unbound": "尚未綁定",
    "bound": "已綁定",
    "active": "使用中",
    "closed": "已結束",
}
EVENT_LABELS = {
    "bound": "綁定群組",
    "activated": "開始使用",
    "participant_joined": "成員加入",
    "participant_left": "成員離開",
    "invitation_forwarded": "邀請已轉送",
    "closed": "群組結束",
}


def render_order_group_manager(
    client: LineAdminApiClient,
    token: str | None,
    _profile: dict[str, Any],
) -> None:
    st.subheader("訂單 LINE 群組")
    st.caption("查看案件與群組的綁定及生命週期；一次性邀請網址不會在此顯示。")
    status = st.selectbox("群組狀態", ["全部", *STATUS_LABELS.values()])
    selected_status = next((key for key, label in STATUS_LABELS.items() if label == status), None)
    try:
        result = client.order_groups(token, status=selected_status)
    except LineAdminApiError as error:
        st.error(f"無法載入訂單群組：{error}")
        return
    items = result.get("items", [])
    if not items:
        st.info("目前沒有符合條件的訂單群組。")
        return
    st.dataframe(pd.DataFrame(_group_rows(items)), width="stretch", hide_index=True)
    case_no = st.selectbox("查看群組事件", [item["case_no"] for item in items])
    _render_group_events(client, token, case_no)


def _group_rows(items):
    return [
        {
            "案件編號": item["case_no"],
            "狀態": STATUS_LABELS.get(item["status"], item["status"]),
            "是否已綁定": "是" if item.get("group_id") else "否",
            "資料版本": item["version"],
        }
        for item in items
    ]


def _render_group_events(client, token, case_no) -> None:
    try:
        events = client.order_group_events(token, case_no)
    except LineAdminApiError as error:
        st.error(f"無法載入群組事件：{error}")
        return
    if not events:
        st.caption("這個案件尚無群組事件。")
        return
    rows = [
        {
            "時間": item.get("occurred_at"),
            "事件": EVENT_LABELS.get(item.get("event_type"), item.get("event_type")),
            "邀請已處理": "是" if item.get("invitation_fingerprint") else "-",
        }
        for item in events
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


__all__ = ["render_order_group_manager"]

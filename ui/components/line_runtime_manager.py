"""LINE runtime status, transition history, and alert-target management panel."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiError
from ui.api_clients.runtime_health_api_client import RuntimeHealthApiClient
from ui.components.line_ui_support import has_capability


STATUS_LABELS = {
    "healthy": "正常",
    "warning": "需要注意",
    "critical": "異常",
    "unknown": "尚無資料",
    "maintenance": "維護中",
}


def render_runtime_manager(
    runtime_client: RuntimeHealthApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("LINE 系統使用狀態")
    st.caption("顯示監控程序最近一次保存的結果；開啟此頁不會直接探測或重啟服務。")
    try:
        records = runtime_client.health_status(token)
    except LineAdminApiError as error:
        st.error(f"無法取得系統狀態：{error}")
        return
    _render_summary(records)
    _render_status_records(records)
    _render_events(runtime_client, token)
    _render_alert_targets(runtime_client, token, profile)


def _render_summary(records: list[dict]) -> None:
    critical = sum(item.get("status") == "critical" for item in records)
    warning = sum(item.get("status") == "warning" for item in records)
    unknown = sum(item.get("status") == "unknown" for item in records)
    columns = st.columns(4)
    columns[0].metric("已監控項目", len(records))
    columns[1].metric("嚴重異常", critical)
    columns[2].metric("需要注意", warning)
    columns[3].metric("尚無檢測資料", unknown)
    if not records:
        st.info("監控資料尚未建立。Stage 10 套用 migration 並啟動 Monitor 後才會開始出現結果。")


def _render_status_records(records: list[dict]) -> None:
    if not records:
        return
    rows = [
        {
            "服務": item.get("component"),
            "檢查項目": item.get("check_name"),
            "狀態": STATUS_LABELS.get(item.get("status"), item.get("status")),
            "說明": item.get("message"),
            "回應時間(ms)": item.get("response_ms"),
            "連續失敗": item.get("consecutive_failures"),
            "最後檢測": item.get("checked_at"),
            "狀態變更": item.get("status_changed_at"),
            "詳細資訊": _details_summary(item.get("details")),
        }
        for item in records
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_events(client: RuntimeHealthApiClient, token: str | None) -> None:
    with st.expander("最近狀態變更"):
        try:
            events = client.health_events(token, 100)
        except LineAdminApiError as error:
            st.error(f"無法載入狀態紀錄：{error}")
            return
        if not events:
            st.caption("目前沒有狀態變更紀錄。")
            return
        st.dataframe(_event_rows(events), width="stretch", hide_index=True)


def _event_rows(events):
    return [
        {
            "時間": item.get("occurred_at"),
            "檢查項目": item.get("check_name"),
            "狀態變化": item.get("transition_type"),
            "結果": STATUS_LABELS.get(
                item.get("resulting_status"), item.get("resulting_status")
            ),
            "說明": item.get("message"),
        }
        for item in events
    ]


def _render_alert_targets(client, token, profile) -> None:
    with st.expander("異常通知對象"):
        try:
            targets = client.alert_targets(token)
        except LineAdminApiError as error:
            st.error(f"無法載入通知對象：{error}")
            return
        if targets:
            st.dataframe(_target_rows(targets), width="stretch", hide_index=True)
        else:
            st.caption("尚未設定異常通知對象。")
        if not has_capability(profile, "line.alert.manage"):
            return
        _render_target_toggle(client, token, targets)


def _target_rows(targets):
    return [
        {
            "編號": item["id"],
            "對象": item.get("display_name"),
            "類型": "工會群組" if item.get("target_type") == "group" else "工會人員",
            "最低通知等級": STATUS_LABELS.get(item.get("minimum_status"), item.get("minimum_status")),
            "啟用": bool(item.get("enabled")),
        }
        for item in targets
    ]


def _render_target_toggle(client, token, targets) -> None:
    _render_target_add(client, token)
    if not targets:
        return
    target_id = st.selectbox("選擇通知對象", [item["id"] for item in targets])
    selected = next(item for item in targets if item["id"] == target_id)
    enabled = st.checkbox("啟用通知", value=bool(selected.get("enabled")), key=f"alert_target_{target_id}")
    if st.button("更新通知設定"):
        try:
            client.set_target_enabled(token, target_id, enabled)
        except LineAdminApiError as error:
            st.error(f"更新失敗：{error}")
            return
        st.success("通知設定已更新。")
        st.rerun()


def _render_target_add(client, token) -> None:
    candidates = _linked_admin_candidates(client, token)
    if not candidates:
        return
    _render_add_target_form(client, token, candidates)


def _linked_admin_candidates(client, token) -> list[dict]:
    try:
        candidates = [item for item in client.admin_alert_candidates(token) if item.get("line_linked")]
    except LineAdminApiError as error:
        st.error(f"無法載入工會人員：{error}")
        return []
    if not candidates:
        st.caption("目前沒有已綁定 LINE 的工會人員可加入通知。")
    return candidates


def _render_add_target_form(client, token, candidates: list[dict]) -> None:
    selected_id = st.selectbox(
        "新增工會人員通知",
        [item["id"] for item in candidates],
        format_func=lambda value: next(item["display_name"] for item in candidates if item["id"] == value),
    )
    minimum_status = st.selectbox("最低通知等級", ["warning", "critical"])
    if not st.button("加入通知對象"):
        return
    payload = {"admin_user_id": selected_id, "minimum_status": minimum_status}
    try:
        client.add_admin_target(token, payload)
    except LineAdminApiError as error:
        st.error(f"新增失敗：{error}")
        return
    st.success("通知對象已新增。")
    st.rerun()


def _details_summary(details) -> str:
    if not isinstance(details, dict) or not details:
        return "-"
    visible = [f"{key}={value}" for key, value in list(details.items())[:4]]
    return "、".join(visible)


__all__ = ["render_runtime_manager"]

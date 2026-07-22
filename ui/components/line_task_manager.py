"""On-demand LINE task dashboard; intentionally contains no fixed polling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ui.services.line_api_client import LineAdminApiClient, LineAdminApiError


FLASH_KEY = "line_task_flash"
PAGE_KEY = "line_task_page"
FILTER_KEY = "line_task_filter_signature"
OPERATE_ROLES = {"line_agent", "line_manager", "system_admin"}
RUN_NOW_ROLES = {"line_manager", "system_admin"}
STATUSES = ["pending", "processing", "sent", "failed", "cancelled"]
TASK_TYPES = ["line_push", "rag_reply", "rich_menu_link", "rich_menu_unlink"]
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


def _format_utc_as_taipei(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(TAIPEI_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def _task_action(
    client: LineAdminApiClient,
    token: str | None,
    task_id: int,
    action: str,
    reason: str,
) -> None:
    try:
        client.line_task_action(token, task_id, action, reason=reason)
    except LineAdminApiError as exc:
        st.error(f"任務操作失敗：{exc}")
        return
    st.session_state[FLASH_KEY] = f"任務 #{task_id} 操作完成"
    st.rerun()


def render_task_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("Worker 任務監控")
    st.caption("資料只在頁面操作或按下重新整理時讀取，不會每 3 秒輪詢。")
    if st.session_state.pop(FLASH_KEY, None):
        st.success("任務狀態已更新")

    try:
        summary = client.line_task_summary(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入任務統計：{exc}")
        return

    metric_columns = st.columns(7)
    metric_columns[0].metric("Worker", "執行中" if summary["worker_running"] else "未執行")
    metric_columns[1].metric("待執行", summary["pending"])
    metric_columns[2].metric("已到期", summary["due"])
    metric_columns[3].metric("處理中", summary["processing"])
    metric_columns[4].metric("今日成功", summary["sent_today"])
    metric_columns[5].metric("失敗", summary["failed"])
    metric_columns[6].metric("取消", summary["cancelled"])
    next_run_at = summary.get("next_run_at")
    st.caption(
        "下一筆執行時間（台北）："
        + (_format_utc_as_taipei(next_run_at) if next_run_at else "目前沒有待執行任務")
    )

    filter1, filter2, filter3, filter4 = st.columns([1, 1, 2, 1])
    status_filter = filter1.selectbox("狀態", ["全部", *STATUSES])
    type_filter = filter2.selectbox("任務類型", ["全部", *TASK_TYPES])
    user_filter = filter3.text_input("LINE User ID 包含")
    onboarding_only = filter4.checkbox("僅 D+任務")

    if st.button("重新整理任務", use_container_width=False):
        st.rerun()

    filter_signature = (
        status_filter,
        type_filter,
        user_filter.strip(),
        onboarding_only,
    )
    if st.session_state.get(FILTER_KEY) != filter_signature:
        st.session_state[FILTER_KEY] = filter_signature
        st.session_state[PAGE_KEY] = 1
    page = st.session_state.get(PAGE_KEY, 1)
    try:
        result = client.line_tasks(
            token,
            filters={
                "status": None if status_filter == "全部" else status_filter,
                "task_type": None if type_filter == "全部" else type_filter,
                "user_id": user_filter,
                "onboarding_only": onboarding_only,
                "page": page,
                "page_size": 25,
            },
        )
    except LineAdminApiError as exc:
        st.error(f"無法載入任務：{exc}")
        return

    items = result["items"]
    if not items:
        if result["page"] > 1:
            st.session_state[PAGE_KEY] = 1
            st.rerun()
        st.info("目前篩選條件沒有任務。")
        return

    display_rows = [
        {
            "ID": item["id"],
            "狀態": item["status"],
            "類型": item["task_type"],
            "LINE User": item["to_user_id"],
            "預定時間（台北）": _format_utc_as_taipei(item["scheduled_at"]),
            "重試": f"{item['retry_count']}/{item['max_retries']}",
            "內容": item.get("message_preview") or "",
            "錯誤": item.get("error_code") or "",
        }
        for item in items
    ]
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    if nav1.button("上一頁", disabled=result["page"] <= 1, use_container_width=True):
        st.session_state[PAGE_KEY] = result["page"] - 1
        st.rerun()
    nav2.markdown(
        f"<div style='text-align:center'>第 {result['page']} / {result['total_pages']} 頁，共 {result['total']} 筆</div>",
        unsafe_allow_html=True,
    )
    if nav3.button(
        "下一頁", disabled=result["page"] >= result["total_pages"], use_container_width=True
    ):
        st.session_state[PAGE_KEY] = result["page"] + 1
        st.rerun()

    task_id = st.selectbox(
        "查看任務詳細資料",
        [item["id"] for item in items],
        format_func=lambda value: f"#{value} · {next(item['status'] for item in items if item['id'] == value)}",
    )
    try:
        detail = client.line_task_detail(token, task_id)
    except LineAdminApiError as exc:
        st.error(f"無法載入任務詳細資料：{exc}")
        return

    task = detail["task"]
    with st.expander("任務完整內容", expanded=True):
        st.json(task)
    st.markdown("#### 執行歷史")
    if detail["attempts"]:
        st.dataframe(detail["attempts"], use_container_width=True, hide_index=True)
    else:
        st.caption("此任務尚未開始執行。")

    can_operate = profile.get("role") in OPERATE_ROLES
    can_run_now = profile.get("role") in RUN_NOW_ROLES
    if not can_operate:
        return
    reason = st.text_input("人工操作原因（選填，會寫入稽核紀錄）", key=f"task_reason_{task_id}")
    confirmed = st.checkbox("我確認要執行以下人工操作", key=f"task_confirm_{task_id}")
    action_columns = st.columns(3)
    if task["status"] == "pending":
        if action_columns[0].button(
            "立即執行",
            disabled=not confirmed or not can_run_now,
            use_container_width=True,
        ):
            _task_action(client, token, task_id, "run-now", reason)
        if action_columns[1].button(
            "取消任務", disabled=not confirmed, use_container_width=True
        ):
            _task_action(client, token, task_id, "cancel", reason)
    elif task["status"] == "failed":
        if action_columns[0].button(
            "重新執行", disabled=not confirmed, use_container_width=True
        ):
            _task_action(client, token, task_id, "retry", reason)
    else:
        st.caption("目前狀態沒有可用的人工操作。")

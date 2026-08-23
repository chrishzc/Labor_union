"""
File: line_task_manager.py
Description: 呈現 LINE Delivery 安全查詢並維持控制操作的薄 UI 邊界。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError
from ui.components.line_ui_support import (
    complete_operation,
    has_capability,
    operation_headers,
)


FLASH_KEY = "line_task_flash"
PAGE_KEY = "line_task_page"
FILTER_KEY = "line_task_filter_signature"
STATUSES = ["pending", "processing", "sent", "failed", "cancelled"]
TASK_TYPES = ["general_push", "rich_menu_link", "rich_menu_unlink"]
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
STATUS_LABELS = {
    "pending": "等待發送",
    "processing": "發送中",
    "sent": "已送出",
    "failed": "發送失敗",
    "cancelled": "已取消",
}
TASK_TYPE_LABELS = {
    "general_push": "LINE 訊息",
    "rich_menu_link": "套用 LINE 選單",
    "rich_menu_unlink": "移除 LINE 選單",
}


def _delivery_query_filters(
    status_filter: str | None,
    type_filter: str | None,
    onboarding_only: bool,
    page: int,
) -> dict[str, Any]:
    source_type = "follow_schedule" if onboarding_only else type_filter
    return {
        "status": status_filter,
        "source_type": source_type,
        "page": page,
        "page_size": 25,
    }


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
    operation = f"line-task:{task_id}:{action}"
    request_identity = operation_headers(
        operation,
        {"task_id": task_id, "action": action, "reason": reason},
    )
    try:
        client.line_task_action(
            token,
            task_id,
            action,
            reason=reason,
            idempotency_key=request_identity["Idempotency-Key"],
            correlation_id=request_identity["X-Correlation-ID"],
        )
    except LineAdminApiError as exc:
        st.error(f"操作失敗：{exc}")
        return
    complete_operation(operation)
    st.session_state[FLASH_KEY] = "發送項目已更新"
    st.rerun()


def render_task_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("自動通知發送紀錄")
    st.caption("查看哪些通知正在等待、已經送出或需要重新處理。")
    if st.session_state.pop(FLASH_KEY, None):
        st.success("發送狀態已更新")

    try:
        summary = client.line_task_summary(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入發送統計：{exc}")
        return

    metric_columns = st.columns(5)
    metric_columns[0].metric("自動發送", "正常" if summary["worker_running"] else "暫停")
    metric_columns[1].metric("等待發送", summary["pending"])
    metric_columns[2].metric("正在發送", summary["processing"])
    metric_columns[3].metric("今日已送出", summary["sent_today"])
    metric_columns[4].metric("需要處理", summary["failed"])
    next_run_at = summary.get("next_run_at")
    st.caption(
        "下一筆預計發送時間："
        + (_format_utc_as_taipei(next_run_at) if next_run_at else "目前沒有等待發送的通知")
    )

    filter1, filter2, filter3 = st.columns([1, 1, 1])
    status_label = filter1.selectbox("發送狀態", ["全部", *STATUS_LABELS.values()])
    type_label = filter2.selectbox("通知種類", ["全部", *TASK_TYPE_LABELS.values()])
    onboarding_only = filter3.checkbox("只看新好友通知")
    status_filter = next(
        (key for key, label in STATUS_LABELS.items() if label == status_label), None
    )
    type_filter = next(
        (key for key, label in TASK_TYPE_LABELS.items() if label == type_label), None
    )

    if st.button("重新整理", key="line_task_refresh", width="content"):
        st.rerun()

    filter_signature = (
        status_filter,
        type_filter,
        onboarding_only,
    )
    if st.session_state.get(FILTER_KEY) != filter_signature:
        st.session_state[FILTER_KEY] = filter_signature
        st.session_state[PAGE_KEY] = 1
    page = st.session_state.get(PAGE_KEY, 1)
    try:
        result = client.line_tasks(
            token,
            filters=_delivery_query_filters(
                status_filter, type_filter, onboarding_only, page
            ),
        )
    except LineAdminApiError as exc:
        st.error(f"無法載入發送紀錄：{exc}")
        return

    items = result["items"]
    if not items:
        if result["page"] > 1:
            st.session_state[PAGE_KEY] = 1
            st.rerun()
        st.info("目前沒有符合條件的發送紀錄。")
        return

    display_rows = [
        {
            "狀態": STATUS_LABELS.get(item["status"], item["status"]),
            "通知種類": TASK_TYPE_LABELS.get(item["task_type"], "系統通知"),
            "預計發送時間": _format_utc_as_taipei(item["scheduled_at"]),
            "通知範圍": item.get("source_type") or "受控來源",
        }
        for item in items
    ]
    st.dataframe(pd.DataFrame(display_rows), width="stretch", hide_index=True)

    nav1, nav2, nav3 = st.columns([1, 2, 1])
    if nav1.button("上一頁", disabled=result["page"] <= 1, width="stretch"):
        st.session_state[PAGE_KEY] = result["page"] - 1
        st.rerun()
    nav2.markdown(
        f"<div style='text-align:center'>第 {result['page']} / {result['total_pages']} 頁，共 {result['total']} 筆</div>",
        unsafe_allow_html=True,
    )
    if nav3.button(
        "下一頁", disabled=result["page"] >= result["total_pages"], width="stretch"
    ):
        st.session_state[PAGE_KEY] = result["page"] + 1
        st.rerun()

    task_id = st.selectbox(
        "查看一筆發送內容",
        [item["id"] for item in items],
        format_func=lambda value: next(
            f"{STATUS_LABELS.get(item['status'], item['status'])} · "
            f"{TASK_TYPE_LABELS.get(item['task_type'], '系統通知')}"
            for item in items
            if item["id"] == value
        ),
    )
    try:
        detail = client.line_task_detail(token, task_id)
    except LineAdminApiError as exc:
        st.error(f"無法載入發送明細：{exc}")
        return

    task = detail["task"]
    detail_rows = {
        "目前狀態": STATUS_LABELS.get(task["status"], task["status"]),
        "通知種類": TASK_TYPE_LABELS.get(task["task_type"], "系統通知"),
        "預計發送時間": _format_utc_as_taipei(task.get("scheduled_at")),
        "查詢來源": task.get("source_type") or "受控來源",
    }
    st.dataframe(
        pd.DataFrame([{"項目": key, "內容": value} for key, value in detail_rows.items()]),
        width="stretch",
        hide_index=True,
    )
    st.markdown("#### 處理紀錄")
    if detail["attempts"]:
        attempts = [
            {
                "時間": _format_utc_as_taipei(item.get("started_at")),
                "結果": STATUS_LABELS.get(item.get("outcome"), item.get("outcome") or "處理中"),
                "說明": item.get("outcome") or "處理中",
            }
            for item in detail["attempts"]
        ]
        st.dataframe(attempts, width="stretch", hide_index=True)
    else:
        st.caption("這筆通知尚未開始發送。")

    can_operate = has_capability(profile, "line.task.control")
    can_run_now = can_operate
    if not can_operate:
        return
    reason = st.text_input("處理備註（選填）", key=f"task_reason_{task_id}")
    confirmed = st.checkbox("我已確認要執行以下操作", key=f"task_confirm_{task_id}")
    action_columns = st.columns(3)
    if task["status"] == "pending":
        if action_columns[0].button(
            "現在發送",
            disabled=not confirmed or not can_run_now,
            width="stretch",
        ):
            _task_action(client, token, task_id, "run-now", reason)
        if action_columns[1].button(
            "取消發送", disabled=not confirmed, width="stretch"
        ):
            _task_action(client, token, task_id, "cancel", reason)
    elif task["status"] == "failed":
        if action_columns[0].button(
            "重新發送", disabled=not confirmed, width="stretch"
        ):
            _task_action(client, token, task_id, "retry", reason)
    else:
        st.caption("目前狀態沒有可用的人工操作。")

"""
================================================================================
檔案名稱: ui/components/line_review_manager.py
功能說明: LINE 待確認申請元件，處理月嫂身分認證與客戶帳號重新綁定
================================================================================
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


FLASH_KEY = "line_review_flash"
CURSOR_KEY = "line_review_cursor"
CURSOR_HISTORY_KEY = "line_review_cursor_history"
FILTER_KEY = "line_review_filter_signature"
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
TYPE_LABELS = {
    "staff_verification": "月嫂身分認證",
    "client_rebind": "客戶重新綁定",
}
STATUS_LABELS = {
    "pending": "待審核",
    "approved": "已核准",
    "rejected": "已拒絕",
    "cancelled": "已取消",
    "expired": "已逾期",
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


def _submit_decision(
    client: LineAdminApiClient,
    token: str | None,
    request_id: int,
    action: str,
    reason: str,
    expected_version: int,
) -> None:
    operation = f"line-review-{request_id}-{action}"
    identity = operation_headers(
        operation,
        {
            "request_id": request_id,
            "action": action,
            "reason": reason,
            "expected_version": expected_version,
        },
    )
    try:
        result = client.line_review_action(
            token,
            request_id,
            action,
            reason=reason,
            expected_version=expected_version,
            idempotency_key=identity["Idempotency-Key"],
        )
    except LineAdminApiError as exc:
        st.error(f"審查處理失敗：{exc}")
        return
    complete_operation(operation)
    st.session_state[FLASH_KEY] = result.get("message") or f"申請 #{request_id} 已處理"
    st.rerun()


def render_review_manager(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("待確認申請")
    st.caption("確認月嫂身分，或處理客戶提出的 LINE 帳號重新綁定申請。")
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        st.success(flash)

    try:
        summary = client.line_review_summary(token)
    except LineAdminApiError as exc:
        st.error(f"無法載入審查統計：{exc}")
        return

    metrics = st.columns(4)
    metrics[0].metric("全部待審", summary["pending_total"])
    metrics[1].metric("月嫂認證", summary["staff_pending"])
    metrics[2].metric("重新綁定", summary["rebind_pending"])
    metrics[3].metric("今日已處理", summary["processed_today"])

    filter1, filter2 = st.columns(2)
    type_label = filter1.selectbox("申請類型", ["全部", *TYPE_LABELS.values()])
    status_label = filter2.selectbox("處理狀態", list(STATUS_LABELS.values()))

    if st.button("重新整理", key="line_review_refresh"):
        st.rerun()

    request_type = next(
        (key for key, label in TYPE_LABELS.items() if label == type_label),
        None,
    )
    status_value = next(
        key for key, label in STATUS_LABELS.items() if label == status_label
    )
    signature = (
        request_type,
        status_value,
    )
    if st.session_state.get(FILTER_KEY) != signature:
        st.session_state[FILTER_KEY] = signature
        st.session_state[CURSOR_KEY] = None
        st.session_state[CURSOR_HISTORY_KEY] = []
    cursor = st.session_state.get(CURSOR_KEY)

    try:
        result = client.line_reviews(
            token,
            filters={
                "review_type": request_type,
                "review_status": status_value,
                "cursor": cursor,
                "page_size": 25,
            },
        )
    except LineAdminApiError as exc:
        st.error(f"無法載入審查清單：{exc}")
        return

    items = result["items"]
    if not items:
        st.info("目前沒有符合條件的待確認申請。")
        return

    rows = [
        {
            "申請編號": item["request_id"],
            "類型": TYPE_LABELS.get(item["review_type"], item["review_type"]),
            "狀態": STATUS_LABELS.get(item["status"], item["status"]),
            "申請者": item.get("display_name") or "-",
            "申請帳號": item.get("line_user_id_masked") or "-",
            "申請時間（台北）": _format_utc_as_taipei(item.get("created_at")),
            "處理者": item.get("reviewed_by_actor_id") or "-",
        }
        for item in items
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    history = st.session_state.get(CURSOR_HISTORY_KEY, [])
    nav1, nav2 = st.columns(2)
    if nav1.button("上一頁", disabled=not history, width="stretch"):
        st.session_state[CURSOR_KEY] = history[-1]
        st.session_state[CURSOR_HISTORY_KEY] = history[:-1]
        st.rerun()
    if nav2.button(
        "下一頁",
        disabled=not result.get("next_cursor"),
        width="stretch",
    ):
        st.session_state[CURSOR_HISTORY_KEY] = [*history, cursor]
        st.session_state[CURSOR_KEY] = result["next_cursor"]
        st.rerun()

    request_id = st.selectbox(
        "查看申請詳細資料",
        [int(item["request_id"]) for item in items],
        format_func=lambda value: (
            f"#{value} · "
            f"{TYPE_LABELS.get(next(item['review_type'] for item in items if int(item['request_id']) == value), '')}"
        ),
    )
    try:
        detail = client.line_review_detail(token, request_id)
    except LineAdminApiError as exc:
        st.error(f"無法載入申請內容：{exc}")
        return

    st.markdown("#### 申請詳細資料")
    detail_rows = {
        "申請編號": detail["request_id"],
        "申請類型": TYPE_LABELS.get(detail["review_type"], detail["review_type"]),
        "狀態": STATUS_LABELS.get(detail["status"], detail["status"]),
        "申請時間（台北）": _format_utc_as_taipei(detail.get("created_at")),
        "申請帳號": detail.get("line_user_id_masked") or "-",
        "綁定對象": detail.get("display_name") or "-",
    }
    st.dataframe(
        pd.DataFrame([{"欄位": key, "內容": value} for key, value in detail_rows.items()]),
        width="stretch",
        hide_index=True,
    )

    if detail["status"] != "pending":
        st.caption(
            f"處理者：{detail.get('reviewed_by_actor_id') or '-'}｜"
            f"處理時間：{_format_utc_as_taipei(detail.get('reviewed_at'))}"
        )
        st.write("處理原因：", detail.get("decision_reason") or "未填寫")
        return

    if not has_capability(profile, "line.review.decide"):
        st.info("目前帳號可以查看申請；核准或拒絕需要主管權限。")
        return

    with st.form(f"line_review_decision_{request_id}"):
        decision_label = st.radio("處理決定", ["核准", "拒絕"], horizontal=True)
        reason = st.text_area(
            "處理原因",
            help="核准或拒絕都必須留下可稽核的處理原因。",
            max_chars=1000,
        )
        confirmed = st.checkbox("我已核對上述資料，確認執行此操作")
        submitted = st.form_submit_button("送出審查結果", type="primary")
    if submitted:
        if not confirmed:
            st.error("請先勾選確認。")
        elif not reason.strip():
            st.error("請填寫處理原因。")
        else:
            _submit_decision(
                client,
                token,
                request_id,
                "approve" if decision_label == "核准" else "reject",
                reason,
                int(detail["version"]),
            )

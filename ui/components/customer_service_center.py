"""Streamlit customer service center for LINE tickets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ui.api_clients.line_api_client import LineAdminApiClient, LineAdminApiError


FLASH_KEY = "customer_service_flash"
PAGE_KEY = "customer_service_page"
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
STATUSES = {
    "waiting": "等待客服",
    "handling": "處理中",
    "resolved": "已完成",
}
CATEGORIES = {
    "service_flow": "服務流程",
    "payment_subsidy": "收費與補助",
    "service_progress": "查詢服務進度",
    "profile_update": "修改登記資料",
    "contact_union": "聯絡工會人員",
    "other": "其他問題",
}


def _field_options(profile: dict[str, Any]) -> dict[str, str]:
    labels = profile.get("field_labels") or {}
    return {
        f"{label}｜目前：{profile.get('fields', {}).get(field) or '空白'}": field
        for field, label in labels.items()
    }


def _format_time(value: Any) -> str:
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
    return parsed.astimezone(TAIPEI_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def _call(action, *, success_message: str) -> bool:
    try:
        action()
    except LineAdminApiError as exc:
        st.error(f"操作失敗：{exc}")
        return False
    st.session_state[FLASH_KEY] = success_message
    st.rerun()
    return True


def _ticket_options(items: list[dict[str, Any]]) -> dict[str, int]:
    options: dict[str, int] = {}
    for item in items:
        client = item.get("client_name") or item.get("line_user_id_masked") or "-"
        category = item.get("category_label") or CATEGORIES.get(item.get("category"), "-")
        case_no = item.get("case_no") or "未綁定案件"
        options[f"#{item['id']}｜{category}｜{client}｜{case_no}"] = int(item["id"])
    return options


def render_customer_service_center(
    client: LineAdminApiClient,
    token: str | None,
    profile: dict[str, Any],
) -> None:
    st.subheader("客服管理中心")
    st.caption("集中處理一般用戶從 LINE「服務說明」提出的問題與聯絡需求。")

    if FLASH_KEY in st.session_state:
        st.success(st.session_state.pop(FLASH_KEY))

    try:
        summary = client.customer_service_summary(token)
    except LineAdminApiError as exc:
        st.error(f"讀取客服統計失敗：{exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("等待客服", summary.get("waiting", 0))
    c2.metric("處理中", summary.get("handling", 0))
    c3.metric("今日新增", summary.get("created_today", 0))
    c4.metric("今日完成", summary.get("resolved_today", 0))

    filter_cols = st.columns([1.1, 1.3, 2.4])
    status_label = filter_cols[0].selectbox(
        "處理狀態",
        ["全部", *STATUSES.values()],
        index=1,
        key="customer_service_status_filter",
    )
    category_label = filter_cols[1].selectbox(
        "問題類型",
        ["全部", *CATEGORIES.values()],
        key="customer_service_category_filter",
    )
    search = filter_cols[2].text_input(
        "搜尋客戶、案件、電話或內容",
        key="customer_service_search",
    )

    status = None if status_label == "全部" else next(k for k, v in STATUSES.items() if v == status_label)
    category = None if category_label == "全部" else next(k for k, v in CATEGORIES.items() if v == category_label)
    page = int(st.session_state.get(PAGE_KEY, 1))
    try:
        result = client.customer_service_tickets(
            token,
            filters={
                "status": status,
                "category": category,
                "search": search,
                "page": page,
                "page_size": 20,
            },
        )
    except LineAdminApiError as exc:
        st.error(f"讀取客服需求失敗：{exc}")
        return

    items = result.get("items", [])
    if items:
        rows = [
            {
                "編號": item["id"],
                "狀態": item.get("status_label"),
                "類型": item.get("category_label"),
                "客戶": item.get("client_name") or "-",
                "案件": item.get("case_no") or "-",
                "建立時間": _format_time(item.get("created_at")),
                "摘要": (item.get("message") or "").replace("\n", " ")[:60],
            }
            for item in items
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("目前沒有符合條件的客服需求。")

    nav1, nav2, nav3 = st.columns([1, 1, 5])
    if nav1.button("上一頁", disabled=result.get("page", 1) <= 1, key="customer_service_prev"):
        st.session_state[PAGE_KEY] = max(1, page - 1)
        st.rerun()
    if nav2.button(
        "下一頁",
        disabled=result.get("page", 1) >= result.get("total_pages", 1),
        key="customer_service_next",
    ):
        st.session_state[PAGE_KEY] = page + 1
        st.rerun()
    nav3.caption(f"第 {result.get('page', 1)} / {result.get('total_pages', 1)} 頁，共 {result.get('total', 0)} 筆")

    if not items:
        return

    options = _ticket_options(items)
    selected_label = st.selectbox(
        "選擇要處理的客服需求",
        list(options.keys()),
        key="customer_service_selected_ticket",
    )
    ticket_id = options[selected_label]
    try:
        detail = client.customer_service_ticket_detail(token, ticket_id)
    except LineAdminApiError as exc:
        st.error(f"讀取客服需求明細失敗：{exc}")
        return

    st.divider()
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(f"**客服需求 #{detail['id']}**")
        st.write(f"狀態：{detail.get('status_label', '-')}")
        st.write(f"類型：{detail.get('category_label', '-')}")
        st.write(f"LINE：{detail.get('line_user_id_masked', '-')}")
        st.write(f"客戶：{detail.get('client_name') or '-'}")
        st.write(f"電話：{detail.get('client_phone') or '-'}")
        st.write(f"案件：{detail.get('case_no') or '-'}")
        if detail.get("order_status") or detail.get("start_date") or detail.get("end_date"):
            st.write(f"案件狀態：{detail.get('order_status') or '-'}")
            st.write(f"服務期間：{detail.get('start_date') or '-'} 至 {detail.get('end_date') or '-'}")
        st.text_area("用戶訊息", value=detail.get("message") or "", height=180, disabled=True)

    with right:
        profile_data = detail.get("client_profile") or {}
        with st.expander("客戶資料異動", expanded=detail.get("category") == "profile_update"):
            if not profile_data:
                st.info("此客服需求尚未綁定客戶資料。請先請客戶完成服務登記或帳號綁定。")
            else:
                fields = profile_data.get("fields") or {}
                field_options = _field_options(profile_data)
                selected_field_label = st.selectbox(
                    "選擇要處理的資料",
                    list(field_options.keys()),
                    key=f"customer_profile_field_{ticket_id}",
                )
                selected_field = field_options[selected_field_label]
                action_label = st.radio(
                    "異動方式",
                    ["新增", "修改", "清空"],
                    horizontal=True,
                    key=f"customer_profile_action_{ticket_id}",
                )
                action = {"新增": "add", "修改": "update", "清空": "clear"}[action_label]
                current_value = fields.get(selected_field)
                st.caption(f"目前內容：{current_value or '空白'}")
                new_value = ""
                if action != "clear":
                    if selected_field == "gender":
                        new_value = st.selectbox(
                            "新內容",
                            ["男", "女"],
                            key=f"customer_profile_value_gender_{ticket_id}",
                        )
                    elif selected_field == "delivery_type":
                        new_value = st.selectbox(
                            "新內容",
                            ["自然產", "剖腹產"],
                            key=f"customer_profile_value_delivery_{ticket_id}",
                        )
                    elif selected_field == "service_type":
                        new_value = st.selectbox(
                            "新內容",
                            ["週休2日", "週休1日", "連續服務"],
                            key=f"customer_profile_value_service_type_{ticket_id}",
                        )
                    elif selected_field == "service_days":
                        new_value = st.number_input(
                            "新內容",
                            min_value=1,
                            step=1,
                            value=int(current_value or 1) if str(current_value or "").isdigit() else 1,
                            key=f"customer_profile_value_days_{ticket_id}",
                        )
                    else:
                        new_value = st.text_area(
                            "新內容",
                            value="",
                            height=90,
                            placeholder="依客戶訊息輸入要寫入的內容",
                            key=f"customer_profile_value_{ticket_id}",
                        )
                change_note = st.text_input(
                    "異動說明",
                    placeholder="例如：依客戶 LINE 訊息補正",
                    key=f"customer_profile_note_{ticket_id}",
                )
                if st.button(
                    "套用到客戶資料",
                    key=f"customer_profile_apply_{ticket_id}",
                    use_container_width=True,
                ):
                    _call(
                        lambda: client.update_customer_service_client_profile_field(
                            token,
                            ticket_id,
                            {
                                "field": selected_field,
                                "action": action,
                                "value": None if action == "clear" else new_value,
                                "note": change_note,
                            },
                        ),
                        success_message="客戶資料已更新，異動紀錄已寫入客服備註",
                    )

        status_value = st.selectbox(
            "更新狀態",
            list(STATUSES.values()),
            index=list(STATUSES.keys()).index(detail.get("status", "waiting")),
            key=f"customer_service_status_{ticket_id}",
        )
        note = st.text_area(
            "內部備註",
            value=detail.get("internal_note") or "",
            height=140,
            key=f"customer_service_note_{ticket_id}",
        )
        if st.button("儲存狀態與備註", key=f"customer_service_save_{ticket_id}", use_container_width=True):
            status_key = next(k for k, v in STATUSES.items() if v == status_value)
            _call(
                lambda: client.update_customer_service_ticket(
                    token,
                    ticket_id,
                    {"status": status_key, "internal_note": note},
                ),
                success_message="客服需求已更新",
            )

        reply = st.text_area(
            "回覆客戶",
            value="",
            height=140,
            placeholder="輸入要傳送到客戶 LINE 的內容",
            key=f"customer_service_reply_{ticket_id}",
        )
        resolve = st.checkbox(
            "送出後標示為已完成",
            value=False,
            key=f"customer_service_resolve_{ticket_id}",
        )
        if st.button("送出 LINE 回覆", key=f"customer_service_reply_btn_{ticket_id}", use_container_width=True):
            _call(
                lambda: client.reply_customer_service_ticket(
                    token,
                    ticket_id,
                    {"reply_text": reply, "internal_note": note, "resolve": resolve},
                ),
                success_message="已排入 LINE 回覆",
            )

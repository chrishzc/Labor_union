"""
File: tab1_overview.py
Description: 顯示訂單摘要並安全標示待補件案件的未定衍生欄位。
"""

import streamlit as st
from ui.api_clients.order_detail_api_client import OrderDetailApiClient
from ui.pages.order.shared import safe_int
from ui.pages.order.editor import render_editor
from ui.pages.shared import build_admin_headers, resolve_api_base_url


ORDER_SELECTION_WIDGET_KEY = "tab1_order_select_v2"


def _render_tab1_overview(orders_data):
    st.subheader("訂單資訊總覽")
    if not orders_data:
        st.info("目前尚無任何訂單資料。")
        return
    filtered_orders = _filtered_orders(orders_data)
    if not filtered_orders:
        st.info("沒有符合篩選/搜尋條件的訂單。")
        return
    st.write(f"共 {len(filtered_orders)} 筆訂單，請直接在下拉式選單中選擇要編輯的訂單。")
    selected_case_no = _select_case_number(filtered_orders)
    if selected_case_no is None:
        st.info("請先選擇案件，再載入完整資料。")
        return
    selected_order = _find_order(filtered_orders, selected_case_no)
    if selected_order is None:
        st.warning("目前無法定位到該筆訂單資料，請重新整理頁面。")
        return
    _render_selected_order(selected_case_no)


def _filtered_orders(orders_data):
    status_filter = st.multiselect(
        "篩選訂單狀態",
        options=["待補件", "洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"],
    )
    return [
        order
        for order in orders_data
        if _matches_status(order, status_filter)
    ]


def _matches_status(order, status_filter):
    return not status_filter or order.get("order_status") in status_filter


def _select_case_number(filtered_orders):
    order_options = {
        _order_label(order): str(order.get("case_no"))
        for order in filtered_orders
    }
    session_state = getattr(st, "session_state", {})
    preferred_case_no = session_state.pop("orders_preferred_case_no", None)
    preferred_label = next(
        (label for label, case_no in order_options.items() if case_no == preferred_case_no),
        None,
    )
    if preferred_label is not None:
        session_state[ORDER_SELECTION_WIDGET_KEY] = preferred_label
    selected_label = st.selectbox(
        "選擇要編輯的訂單",
        options=list(order_options.keys()),
        index=None,
        placeholder="請選擇案件",
        key=ORDER_SELECTION_WIDGET_KEY,
    )
    if selected_label is None:
        return None
    return order_options[selected_label]


def _order_label(order):
    return (
        f"案件 #{order.get('case_no')} ｜ {order.get('client_name', '')} ｜ "
        f"[{order.get('order_status')}] ｜ "
        f"月嫂: {order.get('staff_name') or '尚未指派'} ｜ "
        f"身分資格: {order.get('identity_status') or '未設定'} ｜ "
        f"預期開始: {order.get('start_date') or '未定'} ｜ "
        f"天數: {_planned_term_label(order.get('service_days'))} ｜ "
        f"雇主自費合計: {_planned_amount_label(order.get('total_employer_self_pay_payable'))}"
    )


def _planned_term_label(value):
    return "未定" if value is None else str(safe_int(value))


def _planned_amount_label(value):
    return "未定" if value is None else f"{safe_int(value):,} 元"


def _find_order(orders, case_no):
    return next(
        (order for order in orders if str(order.get("case_no")) == case_no),
        None,
    )


def _render_selected_order(selected_case_no):
    with st.container(border=True):
        try:
            selected_order = OrderDetailApiClient(
                base_url=resolve_api_base_url(),
                headers=build_admin_headers(),
            ).query(selected_case_no)
        except RuntimeError as error:
            st.error(str(error))
            return
        render_editor(
            target_case_no=selected_case_no,
            orders_data=[selected_order.model_dump(mode="json")],
            payments_raw=[],
            key_prefix=f"tab1_acc_{selected_case_no}",
        )

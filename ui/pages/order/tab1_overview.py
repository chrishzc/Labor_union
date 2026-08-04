import streamlit as st
from ui.pages.order.shared import safe_int
from ui.pages.order.editor import render_editor


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
    selected_order = _find_order(filtered_orders, selected_case_no)
    if selected_order is None:
        st.warning("目前無法定位到該筆訂單資料，請重新整理頁面。")
        return
    _render_selected_order(selected_case_no, orders_data)


def _filtered_orders(orders_data):
    status_filter = st.multiselect(
        "篩選訂單狀態",
        options=["洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"],
    )
    search_text = st.text_input(
        "搜尋案件編號、客戶或服務人員姓名",
        "",
    ).strip().casefold()
    return [
        order
        for order in orders_data
        if _matches_status(order, status_filter)
        and _matches_search(order, search_text)
    ]


def _matches_status(order, status_filter):
    return not status_filter or order.get("order_status") in status_filter


def _matches_search(order, search_text):
    if not search_text:
        return True
    searchable_values = (
        order.get("case_no"),
        order.get("client_name"),
        order.get("staff_name"),
    )
    return any(search_text in str(value or "").casefold() for value in searchable_values)


def _select_case_number(filtered_orders):
    order_options = {
        _order_label(order): str(order.get("case_no"))
        for order in filtered_orders
    }
    selected_label = st.selectbox(
        "選擇要編輯的訂單",
        options=list(order_options.keys()),
        key="tab1_order_select",
    )
    return order_options[selected_label]


def _order_label(order):
    return (
        f"案件 #{order.get('case_no')} ｜ {order.get('client_name', '')} ｜ "
        f"[{order.get('order_status')}] ｜ "
        f"月嫂: {order.get('staff_name') or '尚未指派'} ｜ "
        f"身分資格: {order.get('identity_status') or '未設定'} ｜ "
        f"預期開始: {order.get('start_date') or '未定'} ｜ "
        f"天數: {safe_int(order.get('service_days'))} ｜ "
        "雇主自費合計: "
        f"{safe_int(order.get('total_employer_self_pay_payable')):,} 元"
    )


def _find_order(orders, case_no):
    return next(
        (order for order in orders if str(order.get("case_no")) == case_no),
        None,
    )


def _render_selected_order(selected_case_no, orders_data):
    with st.container(border=True):
        render_editor(
            target_case_no=selected_case_no,
            orders_data=orders_data,
            payments_raw=[],
            key_prefix=f"tab1_acc_{selected_case_no}",
        )

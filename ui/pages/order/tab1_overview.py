"""
================================================================================
檔案名稱: ui/pages/order/tab1_overview.py
功能說明: Tab 1 訂單資訊總覽 (OrderUI_Tab1_Overview)
================================================================================
"""

import streamlit as st
import pandas as pd
from ui.pages.order.shared import safe_int
from ui.pages.order.editor import render_editor


def _render_tab1_overview(orders_data):
    """Tab 1: 訂單資訊總覽 (OrderUI_Tab1_Overview)"""
    st.subheader("訂單資訊總覽")
    if not orders_data:
        st.info("目前尚無任何訂單資料。")
        return

    df_orders = pd.DataFrame(orders_data)

    status_filter = st.multiselect(
        "篩選訂單狀態",
        options=["洽談中", "訂單成立", "服務中", "訂單完成", "訂單取消"],
    )

    df_filtered = df_orders[df_orders['order_status'].isin(status_filter)] if status_filter else df_orders

    search_name = st.text_input("搜尋案件編號、客戶或服務人員姓名", "")
    if search_name:
        df_filtered = df_filtered[
            df_filtered['case_no'].astype(str).str.contains(search_name, case=False, na=False) |
            df_filtered['client_name'].str.contains(search_name, case=False, na=False) |
            df_filtered['staff_name'].str.contains(search_name, case=False, na=False)
        ]

    df_filtered = df_filtered.copy()
    payments_raw = []

    total_orders = len(df_filtered)
    if not total_orders:
        st.info("沒有符合篩選/搜尋條件的訂單。")
        return

    st.write(f"共 {total_orders} 筆訂單，請直接在下拉式選單中選擇要編輯的訂單。")
    ordered_rows = df_filtered.to_dict("records")
    if not ordered_rows:
        st.info("沒有符合篩選/搜尋條件的訂單。")
        return

    order_options = {
        (
            f"案件 #{o.get('case_no')} ｜ {o.get('client_name', '')} ｜ "
            f"[{o.get('order_status')}] ｜ 月嫂: {o.get('staff_name') or '尚未指派'} ｜ "
            f"身分資格: {o.get('identity_status') or '未設定'} ｜ "
            f"預期開始: {o.get('start_date') or '未定'} ｜ "
            f"天數: {safe_int(o.get('service_days'))} ｜ "
            f"雇主自費合計: {safe_int(o.get('total_employer_self_pay_payable')):,} 元"
        ): str(o.get("case_no"))
        for o in ordered_rows
    }

    selected_label = st.selectbox(
        "選擇要編輯的訂單",
        options=list(order_options.keys()),
        key="tab1_order_select",
    )
    selected_case_no = order_options[selected_label]

    selected_order = next((o for o in ordered_rows if str(o.get("case_no")) == selected_case_no), None)
    if not selected_order:
        st.warning("目前無法定位到該筆訂單資料，請重新整理頁面。")
        return

    with st.container(border=True):
        render_editor(
            target_case_no=selected_case_no,
            orders_data=orders_data,
            payments_raw=payments_raw,
            key_prefix=f"tab1_acc_{selected_case_no}"
        )

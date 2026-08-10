"""
================================================================================
檔案名稱: ui/pages/05_form_management.py
功能說明: 表單與履歷問卷管理專頁頁面殼層 (FormManagementUI)
================================================================================
"""

import streamlit as st
from ui.api_clients.form_management_api_client import FormManagementApiClient
from ui.api_clients.order_summary_api_client import OrderSummaryApiClient
from ui.pages.shared import build_admin_headers, resolve_api_base_url

from ui.pages.form_management.shared import (
    DB_TABLE_FIELDS,
    safe_int,
    load_json_templates,
)
from ui.pages.form_management.tab2_template_library import _render_tab2_template_library
from ui.pages.form_management.tab3_contract_management import _render_tab3_contract_management

title = "📋 表單與履歷問卷管理"
_CLIENT_CONTEXT_FIELDS = (
    "service_time",
    "service_type",
    "delivery_type",
    "residence_type",
    "city",
    "identity_status",
)


def _load_form_management_facts(base_url, headers):
    cursor = st.session_state.get("form_management_summary_after_case_no")
    page = OrderSummaryApiClient(base_url=base_url, headers=headers).query(
        page_size=50,
        after_case_no=cursor,
    ).page
    if page is None:
        raise ValueError("訂單摘要 API 未回傳資料頁")
    orders = [item.model_dump(mode="json") for item in page.items]
    statistics = FormManagementApiClient(
        base_url=base_url,
        headers=headers,
    ).statistics().model_dump()
    return orders, page.next_cursor, statistics


def _merge_client_context(target_order, context):
    client_context = {
        field: getattr(context, field)
        for field in _CLIENT_CONTEXT_FIELDS
    }
    return {**target_order, **client_context}


def _render_order_summary_pagination(next_cursor):
    cursor = st.session_state.get("form_management_summary_after_case_no")
    history = st.session_state.setdefault("form_management_summary_cursor_history", [])
    if not history and not next_cursor:
        return
    previous_column, page_column, next_column = st.columns([1, 2, 1])
    if previous_column.button("上一頁案件", disabled=not history, key="form_management_previous_page"):
        st.session_state["form_management_summary_after_case_no"] = history.pop()
        st.rerun()
    page_column.caption(f"案件摘要第 {len(history) + 1} 頁，每頁最多 50 筆")
    if next_column.button("下一頁案件", disabled=not next_cursor, key="form_management_next_page"):
        history.append(cursor)
        st.session_state["form_management_summary_after_case_no"] = next_cursor
        st.rerun()

def _render_form_management_page_shell(form_db_table_fields, field_types, field_widths, global_stats, target_order, form_table_for_key):
    """Render FormManagementUI's 2 fixed tabs."""
    tab2, tab3 = st.tabs([
        "🗄️ 2. 自訂表單模板庫與 5:5 雙視窗線上編輯預覽",
        "📜 3. 制式定型化契約管理 (EPPP 變數代理引擎)"
    ])

    with tab2:
        _render_tab2_template_library(form_db_table_fields, field_types, field_widths, global_stats, target_order)

    with tab3:
        _render_tab3_contract_management(form_db_table_fields, form_table_for_key, global_stats, target_order)


def show():
    """FormManagementUI 進入點 (5:5 雙視窗 Side-by-Side + 拖拉排序 + 二次確認刪除)"""
    st.title("📋 表單與履歷問卷管理專區")

    form_db_table_fields = {table_name: dict(fields) for table_name, fields in DB_TABLE_FIELDS.items()}
    order_table_name = "orders (訂單主表 - 36 大業務與金額 calculations)"
    form_db_table_fields[order_table_name] = {
        key: label
        for key, label in form_db_table_fields[order_table_name].items()
        if not (key.startswith("subsidy") and key.endswith("eligibility"))
    }
    form_db_table_fields["clients (客戶主表 - 個人基本資料與市府申請表)"]["identity_status"] = "身分資格（唯讀） (identity_status)"

    def form_table_for_key(db_key: str) -> str:
        for table_name, fields in form_db_table_fields.items():
            if db_key in fields:
                return table_name
        return next(iter(form_db_table_fields))

    base_url = resolve_api_base_url()

    try:
        admin_headers = build_admin_headers()
        orders_data, next_cursor, global_stats = _load_form_management_facts(
            base_url,
            admin_headers,
        )
    except Exception as error:
        st.error(f"讀取表單資料 API 失敗: {error}")
        orders_data = []
        next_cursor = None
        global_stats = {}

    _render_order_summary_pagination(next_cursor)

    col_scope, col_order = st.columns([1.5, 2.5])
    with col_scope:
        scope_mode = st.radio("⚙️ 選擇表單連動作用域", ["🎯 特定單筆案件 (契約/個人單據)", "📊 全域/多案件統計模式 (週報/統計表)"], horizontal=True, key="sbs_scope_mode")
    
    target_order = None
    with col_order:
        if "特定單筆案件" in scope_mode and orders_data:
            order_opts = {
                f"案件 #{o['case_no']} - 客戶: {o['client_name']} [{o['order_status']}] (月嫂: {o.get('staff_name') or '尚未指派'})": o['case_no']
                for o in orders_data
            }
            sel_label = st.selectbox("🎯 選擇連動測試的訂單案件", list(order_opts.keys()), key="sbs_order_picker")
            target_case_no = order_opts[sel_label]
            target_order = next((o for o in orders_data if o['case_no'] == target_case_no), None)
            if target_order:
                context = FormManagementApiClient(
                    base_url=base_url,
                    headers=admin_headers,
                ).case_context(target_case_no)
                target_order = _merge_client_context(target_order, context)

        else:
            st.info("💡 目前切換為「全域/多案件統計模式」，無須鎖定單一訂單。")

    st.session_state['custom_form_templates'] = load_json_templates()

    st.markdown("---")

    field_widths = {
        "half": "半寬 (50% 雙欄並排)",
        "full": "全寬 (100% 單獨一列)"
    }
    field_types = {
        "text": "單行文字輸入",
        "textarea": "多行備註區域",
        "number": "數字/金額數值",
        "date": "日期選擇器",
        "db_link": "⚡ 連動 DB 欄位 (支援單筆與全域統計)"
    }

    _render_form_management_page_shell(
        form_db_table_fields, field_types, field_widths, global_stats, target_order, form_table_for_key
    )

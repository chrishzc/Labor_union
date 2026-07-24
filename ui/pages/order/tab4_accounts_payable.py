"""
================================================================================
檔案名稱: ui/pages/order/tab4_accounts_payable.py
功能說明: Tab 4 應付帳款查詢/輸出 (AccountsPayableExportUI)
================================================================================
"""

import requests
import streamlit as st
import pandas as pd
from datetime import datetime
from ui.pages.order.shared import safe_float, _finance_report_request


def _render_tab4_accounts_payable():
    """唯讀查詢指定月份的應付帳款，並提供銀行匯款 Excel。"""
    st.subheader("應付帳款查詢／輸出")
    st.caption("本頁僅供查詢與下載，不會將任何帳款標記為已付款、已退款或已提交。")

    today = datetime.today()
    year_col, month_col = st.columns(2)
    with year_col:
        selected_year = st.selectbox("年份", list(range(today.year - 2, today.year + 3)), index=2, key="accounts_payable_year")
    with month_col:
        selected_month = st.selectbox("月份", list(range(1, 13)), index=today.month - 1, format_func=lambda month: f"{month:02d} 月", key="accounts_payable_month")
    target_month = f"{selected_year:04d}-{selected_month:02d}"
    try:
        export_preview = _finance_report_request("/accounts-payable", {"target_month": target_month, "view": "export"})
        try:
            summary_preview = _finance_report_request("/accounts-payable-summary", {"target_month": target_month})
        except requests.HTTPError as err:
            if getattr(err.response, "status_code", None) == 404:
                summary_preview = _finance_report_request("/accounts-payable", {"target_month": target_month, "view": "summary"})
            else:
                raise
    except requests.RequestException as err:
        st.error(f"讀取 {target_month} 應付帳款失敗：{err}")
        return

    summary_headers = summary_preview.get("headers") or []
    summary_df = pd.DataFrame(summary_preview.get("summary_rows") or []).reindex(columns=summary_headers)
    st.markdown("### 已完成訂單帳務總覽（比對用）")
    st.dataframe(summary_df, width="stretch", hide_index=True)
    if summary_totals := summary_preview.get("totals") or {}:
        st.caption(
            f"合計｜應付薪資 {safe_float(summary_totals.get('payable_salary', 0)):,.0f} 元、"
            f"已付薪資 {safe_float(summary_totals.get('paid_salary', 0)):,.0f} 元、"
            f"薪資未付 {safe_float(summary_totals.get('salary_outstanding', 0)):,.0f} 元、"
            f"應付補助款 {safe_float(summary_totals.get('subsidy_receivable', 0)):,.0f} 元、"
            f"已退補助款 {safe_float(summary_totals.get('subsidy_refunded', 0)):,.0f} 元、"
            f"補助剩餘 {safe_float(summary_totals.get('subsidy_remaining', 0)):,.0f} 元"
        )

    st.markdown("### 匯款匯出預覽")
    fixed_columns = ["月份-銀行代碼-流水號", "銀行名稱", "客戶or服務人員姓名", "銀行帳號", "銀行代號(碼)", "金額", "身分證字號(匯款到永豐才要填)", "案件編號", "匯款日期"]
    preview_df = pd.DataFrame(export_preview.get("payable_rows") or []).reindex(columns=fixed_columns)
    bank_totals = export_preview.get("bank_totals") or {}
    total_col1, total_col2 = st.columns(2)
    total_col1.metric("永豐銀行月嫂款（31）", f"{safe_float(bank_totals.get('31', 0)):,.0f} 元")
    total_col2.metric("台新銀行退還補助款（633）", f"{safe_float(bank_totals.get('633', 0)):,.0f} 元")
    st.write(f"共 {len(preview_df)} 筆待匯款項")
    st.dataframe(preview_df, width="stretch", hide_index=True)
    try:
        xlsx_bytes = _finance_report_request("/accounts-payable/export", {"target_month": target_month}, download=True)
    except requests.RequestException as err:
        st.error(f"下載應付帳款 Excel 失敗：{err}")
        return
    st.download_button("下載應付帳款 Excel", data=xlsx_bytes, file_name=f"應付帳款_{target_month}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_accounts_payable_xlsx")

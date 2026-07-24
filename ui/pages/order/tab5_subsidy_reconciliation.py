"""
================================================================================
檔案名稱: ui/pages/order/tab5_subsidy_reconciliation.py
功能說明: Tab 5 核銷補助清冊 (SubsidyReconciliationRegisterUI)
================================================================================
"""

import requests
import streamlit as st
import pandas as pd
from datetime import datetime
from ui.pages.order.shared import _finance_report_request


def _render_tab5_subsidy_reconciliation():
    """Render read-only quarterly subsidy registers and annual summaries."""
    st.subheader("核銷補助清冊")

    today = datetime.today()
    selected_year = st.selectbox("申請年度", list(range(today.year - 2, today.year + 3)), index=2, key="subsidy_reconciliation_year")
    quarterly_tab, annual_tab = st.tabs(["分季核銷", "年度總表"])
    with quarterly_tab:
        selected_quarter = st.selectbox("申請季度", [1, 2, 3, 4], format_func=lambda quarter: f"第 {quarter} 季", key="subsidy_reconciliation_quarter")
        params = {"application_year": selected_year, "quarter": selected_quarter}
        try:
            report = _finance_report_request("/subsidy-reconciliation/quarterly", params)
        except requests.RequestException as err:
            st.error(f"讀取季度核銷清冊失敗：{err}")
        else:
            st.markdown("#### 一般市民")
            st.dataframe(pd.DataFrame(report.get("general_citizen_rows") or []), width="stretch", hide_index=True)
            subsidized_rows = report.get("subsidized_citizen_rows") or []
            if subsidized_rows:
                st.markdown("#### 補助市民")
                st.dataframe(pd.DataFrame(subsidized_rows), width="stretch", hide_index=True)
            try:
                xlsx_bytes = _finance_report_request("/subsidy-reconciliation/quarterly/export", params, download=True)
            except requests.RequestException as err:
                st.error(f"下載分季核銷 Excel 失敗：{err}")
            else:
                st.download_button("下載分季核銷 Excel", data=xlsx_bytes, file_name=f"核銷補助清冊_{selected_year}_Q{selected_quarter}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_quarterly_subsidy_reconciliation")
    with annual_tab:
        params = {"application_year": selected_year}
        try:
            report = _finance_report_request("/subsidy-reconciliation/annual", params)
        except requests.RequestException as err:
            st.error(f"讀取年度補助總表失敗：{err}")
        else:
            st.markdown("#### 一般市民")
            st.dataframe(pd.DataFrame(report.get("general_citizen_rows") or []), width="stretch", hide_index=True)
            subsidized_rows = report.get("subsidized_citizen_rows") or []
            if subsidized_rows:
                st.markdown("#### 補助市民")
                st.dataframe(pd.DataFrame(subsidized_rows), width="stretch", hide_index=True)
            try:
                xlsx_bytes = _finance_report_request("/subsidy-reconciliation/annual/export", params, download=True)
            except requests.RequestException as err:
                st.error(f"下載年度補助 Excel 失敗：{err}")
            else:
                st.download_button("下載年度補助 Excel", data=xlsx_bytes, file_name=f"年度補助總表_{selected_year}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_annual_subsidy_summary")

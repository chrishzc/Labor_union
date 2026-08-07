"""
contract_match_panel.py — 合約完成確認面板
GET /{case_no}/contract-completion 查詢狀態並提供 Preview + Apply 流程。
"""
import streamlit as st
import requests
from ui.pages.shared import resolve_api_base_url, build_admin_headers


def render_contract_match_panel(case_no, headers=None, *args, **kwargs):
    st.markdown("#### 📋 合約完成確認")
    if headers is None:
        headers = build_admin_headers()

    base_url = resolve_api_base_url()
    try:
        resp = requests.get(
            f"{base_url}/api/v1/orders/{case_no}/contract-completion",
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            st.info("合約完成資料暫時無法取得（可能尚未完成前置作業）。")
            return
        data = resp.json().get("data", {})
    except Exception as e:
        st.warning(f"合約狀態查詢失敗：{e}")
        return

    contract_completed = data.get("contract_completed", False)
    lifecycle_status   = data.get("lifecycle_status", "—")
    completion_avail   = data.get("completion_available", False)
    deposit_settled    = data.get("deposit_settled", False)
    svc_terms_complete = data.get("service_time_terms_complete", False)
    blockers           = data.get("domain_blockers", [])

    col1, col2 = st.columns(2)
    col1.metric("合約已完成", "✅ 是" if contract_completed else "❌ 否")
    col2.metric("訂單生命週期狀態", lifecycle_status)
    st.caption(
        f"訂金已核銷：{'✅' if deposit_settled else '❌'} ｜ "
        f"服務時段條款完整：{'✅' if svc_terms_complete else '❌'} ｜ "
        f"可執行合約完成：{'✅' if completion_avail else '❌'}"
    )

    if not contract_completed and completion_avail:
        st.divider()
        reason = st.text_input("合約完成備註 (必填)", key=f"contract_reason_{case_no}")
        if st.button("確認合約完成", key=f"contract_apply_{case_no}", type="primary"):
            if not reason.strip():
                st.error("請填寫合約完成備註")
            else:
                st.info("請透過 Preview → Apply 流程完成合約確認（完整實作中）。")

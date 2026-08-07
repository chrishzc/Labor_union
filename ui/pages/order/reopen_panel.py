import streamlit as st

def render_order_reopen_panel(case_no, client=None, *args, **kwargs):
    st.markdown("#### 🔄 重新開啟取消訂單 (Reopen)")
    with st.expander("重新開啟訂單申請", expanded=True):
        reason = st.text_input("重開原因", key=f"reopen_reason_{case_no}")
        if st.button("確認重新開啟訂單", key=f"reopen_btn_{case_no}", type="primary"):
            if not reason.strip():
                st.error("請填寫重開原因")
            else:
                st.success(f"案件 {case_no} 已重新開啟！原因：{reason}")

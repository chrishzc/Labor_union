import streamlit as st

def render_order_cancellation_panel(case_no, client=None, *args, **kwargs):
    st.markdown("#### ❌ 訂單取消申請")
    with st.expander("執行訂單取消流程", expanded=True):
        reason = st.text_input("取消原因", key=f"cancel_reason_{case_no}")
        if st.button("確認取消訂單", key=f"cancel_btn_{case_no}", type="primary"):
            if not reason.strip():
                st.error("請填寫取消原因")
            else:
                st.success(f"案件 {case_no} 取消申請已送出！原因：{reason}")

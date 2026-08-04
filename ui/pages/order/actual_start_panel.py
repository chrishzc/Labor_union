"""Thin Streamlit panel for authoritative Actual Start Preview/Apply."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from ui.api_clients.order_actual_start_api_client import (
    ActualStartApiClient,
    ActualStartApiError,
)


def render_actual_start_panel(case_no: str, client: ActualStartApiClient) -> None:
    st.markdown("#### 服務開始確認（實際開工）")
    try:
        facts = client.query(case_no)
    except ActualStartApiError as error:
        st.error(f"無法讀取實際開工狀態：{error}")
        return
    if facts.service_data_locked:
        st.info("此案件服務資料已鎖定，不能變更實際開工日。")
        return
    target_date = st.date_input("實際服務開始日", value=facts.current_actual_start_date or facts.planned_start_date, key=f"actual_start_date_{case_no}")
    preview = _preview(case_no, client, target_date)
    if preview is None:
        return
    st.caption(f"服務區間：{preview.after_actual_start_date} 至 {preview.actual_end_date}")
    reason = st.text_input("變更原因", key=f"actual_start_reason_{case_no}")
    if st.button("確認套用實際開工日", key=f"actual_start_apply_{case_no}", type="primary"):
        _apply(case_no, client, preview, reason)


def _preview(case_no, client, target_date):
    state_key = f"actual_start_preview_{case_no}_{target_date.isoformat()}"
    if state_key not in st.session_state:
        try:
            st.session_state[state_key] = client.preview(case_no, target_date, correlation_id=str(uuid4()))
        except ActualStartApiError as error:
            st.error(f"無法產生實際開工日預覽：{error}")
            return None
    return st.session_state[state_key]


def _apply(case_no, client, preview, reason):
    if not reason.strip():
        st.error("請填寫變更原因。")
        return
    try:
        client.apply(case_no, preview, reason=reason, idempotency_key=str(uuid4()), correlation_id=str(uuid4()))
    except ActualStartApiError as error:
        st.error(f"套用實際開工日失敗：{error}")
        return
    st.success("實際開工日已套用，相關排班、帳務與薪資影響已由後端重算。")
    st.rerun()

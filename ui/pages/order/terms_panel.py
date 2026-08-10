"""Thin Streamlit panel for authoritative Orders Terms Preview/Apply."""

from __future__ import annotations

from datetime import date, time
from uuid import uuid4

import streamlit as st

from ui.api_clients.order_terms_api_client import OrderTermsApiClient, OrderTermsApiError


def render_order_terms_panel(case_no: str, client: OrderTermsApiClient) -> None:
    st.markdown("#### 正式條款與合約紀錄")
    try:
        facts = client.query(case_no)
    except OrderTermsApiError as error:
        st.error(f"無法讀取正式條款：{error}")
        return
    if facts.service_data_locked:
        st.info("服務資料已鎖定，不能變更正式條款。")
        return
    proposed_terms = _form(case_no, facts.terms.model_dump(mode="json"))
    preview = _preview(case_no, client, proposed_terms)
    if preview is None:
        return
    st.caption(f"預覽服務日：{preview.after.planned_start_date} 起，共 {preview.after.service_days} 日")
    reason = st.text_input("變更原因", key=f"terms_reason_{case_no}")
    if st.button("確認套用正式條款", key=f"terms_apply_{case_no}", type="primary"):
        _apply(case_no, client, proposed_terms, preview, reason)


def _form(case_no, terms):
    service_time = terms["service_time"]
    start_time = _read_time(service_time.get("start_time"), time(9, 0))
    end_time = _read_time(service_time.get("end_time"), time(17, 0))
    return {
        "planned_start_date": st.date_input("預計開始日", value=date.fromisoformat(terms["planned_start_date"]), key=f"terms_start_{case_no}").isoformat(),
        "service_days": int(st.number_input("服務天數", min_value=1, value=terms["service_days"], key=f"terms_days_{case_no}")),
        "service_hours_per_day": int(st.number_input("每日服務時數", min_value=1, value=terms["service_hours_per_day"], key=f"terms_hours_{case_no}")),
        "floor_fee_ntd": int(st.number_input("樓層費（元）", min_value=0, value=terms["floor_fee_ntd"], key=f"terms_floor_{case_no}")),
        "service_time": {"start_time": st.time_input("服務開始時間", value=start_time, key=f"terms_time_start_{case_no}").isoformat(), "end_time": st.time_input("服務結束時間", value=end_time, key=f"terms_time_end_{case_no}").isoformat(), "end_day_offset": int(st.selectbox("跨日", [0, 1], index=service_time.get("end_day_offset") or 0, key=f"terms_cross_day_{case_no}"))},
    }


def _read_time(value, default):
    return time.fromisoformat(value) if value else default


def _preview(case_no, client, proposed_terms):
    state_key = f"terms_preview_{case_no}_{hash(str(proposed_terms))}"
    if state_key not in st.session_state:
        try:
            st.session_state[state_key] = client.preview(case_no, proposed_terms, correlation_id=str(uuid4()))
        except OrderTermsApiError as error:
            st.error(f"無法產生條款預覽：{error}")
            return None
    return st.session_state[state_key]


def _apply(case_no, client, proposed_terms, preview, reason):
    if not reason.strip():
        st.error("請填寫變更原因。")
        return
    try:
        client.apply(case_no, proposed_terms, preview, reason=reason, idempotency_key=str(uuid4()), correlation_id=str(uuid4()))
    except OrderTermsApiError as error:
        st.error(f"套用正式條款失敗：{error}")
        return
    st.success("正式條款已套用，相關排班、帳務與薪資影響已由後端重算。")
    st.rerun()

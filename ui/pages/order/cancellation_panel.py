"""Thin Streamlit panel for authoritative Order Cancellation Preview/Apply."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from ui.api_clients.order_cancellation_api_client import (
    OrderCancellationApiClient,
    OrderCancellationApiError,
)


def render_order_cancellation_panel(case_no: str, client: OrderCancellationApiClient) -> None:
    st.markdown("#### 訂單取消")
    try:
        facts = client.query(case_no)
    except OrderCancellationApiError as error:
        st.error(f"無法讀取訂單取消狀態：{error}")
        return
    if facts.service_data_locked:
        st.info("此案件服務資料已鎖定，不能取消訂單。")
        return
    confirmed_days = _confirmed_service_days(case_no, facts)
    preview = _preview(case_no, client, confirmed_days)
    if preview is None:
        return
    st.caption(f"取消後正式服務日：{preview.official_service_day_count} 日／{preview.official_service_hours} 小時")
    reason = st.text_input("取消原因", key=f"cancellation_reason_{case_no}")
    if st.button("確認套用訂單取消", key=f"cancellation_apply_{case_no}", type="primary"):
        _apply(case_no, client, confirmed_days, preview, reason)


def _confirmed_service_days(case_no, facts) -> list[dict[str, object]]:
    caregiver_names = {item.staff_id: item.display_name for item in facts.caregiver_options}
    selected_days = []
    if facts.confirmed_service_days:
        st.caption("請只勾選已實際完成的服務日；服務日與人員由後端於 Preview 驗證。")
    for item in facts.confirmed_service_days:
        key = f"cancellation_day_{case_no}_{item.service_date.isoformat()}_{item.staff_id}"
        if st.checkbox(f"{item.service_date} · {caregiver_names.get(item.staff_id, f'人員 #{item.staff_id}')}", value=True, key=key):
            selected_days.append({"service_date": item.service_date, "staff_id": item.staff_id, "reason": item.reason})
    return selected_days


def _preview(case_no, client, confirmed_days):
    selection_key = tuple((item["service_date"].isoformat(), item["staff_id"]) for item in confirmed_days)
    state_key = f"cancellation_preview_{case_no}_{hash(selection_key)}"
    if st.button("產生訂單取消 Preview", key=f"cancellation_preview_btn_{case_no}"):
        try:
            st.session_state[state_key] = client.preview(case_no, confirmed_days, correlation_id=str(uuid4()))
        except OrderCancellationApiError as error:
            st.error(f"無法產生訂單取消預覽：{error}")
            return None
    return st.session_state.get(state_key)


def _apply(case_no, client, confirmed_days, preview, reason):
    if not reason.strip():
        st.error("請填寫取消原因。")
        return
    try:
        client.apply(case_no, confirmed_days, preview, reason=reason, idempotency_key=str(uuid4()), correlation_id=str(uuid4()))
    except OrderCancellationApiError as error:
        st.error(f"套用訂單取消失敗：{error}")
        return
    st.success("訂單取消已套用，相關排班、帳務與薪資影響已由後端處理。")
    st.rerun()

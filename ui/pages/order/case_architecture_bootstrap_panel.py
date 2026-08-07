"""Thin Streamlit boundary for canonical case architecture bootstrap."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from ui.api_clients.case_architecture_bootstrap_api_client import (
    CaseArchitectureBootstrapApiClient,
    CaseArchitectureBootstrapApiError,
)


def ensure_case_architecture_ready(
    case_no: str,
    client: CaseArchitectureBootstrapApiClient,
    *,
    require_service_time_complete: bool = True,
) -> bool:
    try:
        status = client.status(case_no)
    except CaseArchitectureBootstrapApiError as error:
        st.error(f"無法讀取案件架構狀態：{error}")
        return False
    if status.ready and (status.service_time_complete or not require_service_time_complete):
        return True
    render_case_architecture_bootstrap_panel(case_no, client, status.recommendation, status.domain_blockers)
    return False


def render_case_architecture_bootstrap_panel(case_no, client, recommendation, blockers=()):
    st.info("此案件尚未完成正式根狀態；完成初始化後才能進行後續正式操作。")
    for blocker in blockers:
        st.caption(f"阻擋原因：{blocker}")
    if recommendation is None:
        return
    intent = recommendation.model_dump(mode="json")
    preview = _load_preview(case_no, client, intent)
    if preview is None:
        return
    st.caption(f"將建立版本：排班 {preview.scheduling_version}／世代 {preview.scheduling_generation}")
    reason = st.text_input("初始化原因", key=f"bootstrap_reason_{case_no}")
    if st.button("確認建立正式案件架構", key=f"bootstrap_apply_{case_no}", type="primary"):
        _apply_preview(case_no, client, preview, reason)


def _load_preview(case_no, client, intent):
    state_key = f"bootstrap_preview_{case_no}"
    if state_key not in st.session_state:
        try:
            st.session_state[state_key] = client.preview(case_no, intent, correlation_id=str(uuid4()))
        except CaseArchitectureBootstrapApiError as error:
            st.error(f"無法產生初始化預覽：{error}")
            return None
    return st.session_state[state_key]


def _apply_preview(case_no, client, preview, reason):
    if not reason.strip():
        st.error("請填寫初始化原因。")
        return
    try:
        client.apply(case_no, preview, reason=reason, idempotency_key=str(uuid4()), correlation_id=str(uuid4()))
    except CaseArchitectureBootstrapApiError as error:
        st.error(f"建立案件架構失敗：{error}")
        return
    st.session_state.pop(f"bootstrap_preview_{case_no}", None)
    st.success("案件正式架構已建立。")
    st.rerun()

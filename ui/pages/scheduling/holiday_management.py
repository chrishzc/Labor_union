from __future__ import annotations

from uuid import uuid4

import requests
import streamlit as st

from ui.pages.shared import build_admin_headers, resolve_api_base_url


def render_holiday_management():
    st.markdown("#### 國定假日管理")
    st.caption("國定假日不會自動改寫既有排班或薪資；個案休假仍須走既有休假 Preview/Apply。")
    headers = build_admin_headers()
    command = _form()
    if st.button("預覽假日變更", key="holiday_preview"):
        _preview(command, headers)
    preview = st.session_state.get("holiday_management_preview")
    if preview:
        st.info(f"預覽動作：{preview['action']} {preview['holiday_date']}；排班與薪資影響：無自動異動。")
        reason = st.text_input("假日異動原因", key="holiday_management_reason")
        if st.button("確認套用假日變更", type="primary", key="holiday_apply"):
            _apply(preview, headers, reason)


def _form():
    action = st.selectbox("操作", ["upsert", "delete"], format_func=lambda value: "新增或更新" if value == "upsert" else "刪除", key="holiday_action")
    command = {"action": action, "holiday_date": st.date_input("假日日期", key="holiday_date").isoformat()}
    if action == "upsert":
        command["holiday_name"] = st.text_input("假日名稱", key="holiday_name").strip()
        command["is_double_pay_default"] = st.checkbox("雙倍薪資參考標記", key="holiday_double_pay")
    return command


def _preview(command, headers):
    try:
        response = requests.post(f"{resolve_api_base_url()}/api/v1/holidays/preview", headers=headers, json=command, timeout=15)
        response.raise_for_status()
        st.session_state["holiday_management_preview"] = response.json()["data"]
    except requests.RequestException as error:
        st.error(f"假日預覽失敗：{error}")


def _apply(preview, headers, reason):
    if not reason.strip():
        st.error("請填寫假日異動原因。")
        return
    body = {**preview["command"], "preview_fingerprint": preview["preview_fingerprint"], "reason": reason.strip()}
    try:
        response = requests.post(f"{resolve_api_base_url()}/api/v1/holidays/apply", headers={**headers, "Idempotency-Key": str(uuid4())}, json=body, timeout=15)
        response.raise_for_status()
    except requests.RequestException as error:
        st.error(f"假日套用失敗：{error}")
        return
    st.session_state.pop("holiday_management_preview", None)
    st.success("假日變更已套用。")
    st.rerun()

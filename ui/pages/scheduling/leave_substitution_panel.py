"""Thin UI for formal leave/substitution Preview and Apply."""

from __future__ import annotations

import uuid

import requests
import streamlit as st

from ui.api_clients.leave_substitution_api_client import (
    LeaveSubstitutionApiClient,
    LeaveSubstitutionApiError,
)
from ui.pages.shared import build_admin_headers, resolve_api_base_url


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_staff_options(base_url: str, header_items: tuple) -> dict[str, int]:
    """Return {姓名(電話): id} mapping from /api/v1/staff."""
    try:
        resp = requests.get(
            f"{base_url}/api/v1/staff",
            headers=dict(header_items),
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json().get("data") or []
        return {
            f"{r.get('name', '')}（{r.get('phone', '')}）": int(r["id"])
            for r in rows
            if r.get("id") and r.get("name")
        }
    except Exception:
        return {}


def render_leave_substitution_panel(case_no: str, client: LeaveSubstitutionApiClient, *, original_assignment_id: int) -> None:
    try:
        schedule = client.assignment_schedule(original_assignment_id)
    except LeaveSubstitutionApiError as error:
        st.error(f"正式服務日載入失敗 [{error.error.code}]：{error}")
        return
    work_days = [row for row in schedule.get("schedule_days", []) if row.get("is_work_day")]
    if not work_days:
        st.info("此指派沒有可處理的正式服務日。")
        return
    
    labels = {f"{row['work_date']}｜排班 #{row['id']}": row for row in work_days}
    
    # Initialize batch list in session state
    batch_key = f"leave_batch_{original_assignment_id}"
    if batch_key not in st.session_state:
        st.session_state[batch_key] = []
        
    st.markdown("#### 📝 新增休假/代班項目")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        selected = st.selectbox("選擇請假服務日", list(labels), key=f"leave_schedule_{original_assignment_id}")
    with col2:
        resolution = st.radio("處理方式", ["順延後續人力", "指定代班月嫂"], horizontal=True, key=f"leave_resolution_{original_assignment_id}")
    
    substitute = None
    if resolution == "指定代班月嫂":
        staff_opts = _fetch_staff_options(
            resolve_api_base_url(),
            tuple(sorted(build_admin_headers().items())),
        )
        if not staff_opts:
            st.warning("無法載入月嫂名單，請確認後端服務正常。")
        else:
            sub_label = st.selectbox(
                "代班月嫂",
                ["請選擇代班月嫂", *staff_opts.keys()],
                key=f"leave_substitute_{original_assignment_id}",
            )
            substitute = staff_opts.get(sub_label)
            
    if st.button("➕ 加入清單", key=f"add_leave_btn_{original_assignment_id}"):
        if resolution == "指定代班月嫂" and not substitute:
            st.warning("請選擇代班月嫂！")
        else:
            item = _item(labels[selected], resolution, substitute)
            # Check if already added
            if any(i["original_schedule_id"] == item["original_schedule_id"] for i in st.session_state[batch_key]):
                st.warning("該日期已在清單中。")
            else:
                st.session_state[batch_key].append(item)
                st.rerun()

    if st.session_state[batch_key]:
        st.markdown("#### 📋 待處理休假清單")
        
        # Display the pending items with delete buttons
        for idx, item in enumerate(st.session_state[batch_key]):
            c1, c2, c3, c4 = st.columns([3, 3, 3, 1])
            c1.write(f"📅 {item['work_date']}")
            c2.write(f"🛠️ {'順延' if item['resolution_type'] == 'defer_following_assignments' else '代班'}")
            c3.write(f"👤 代班 ID: {item.get('substitute_staff_id') or '-'}")
            if c4.button("❌ 刪除", key=f"del_leave_{original_assignment_id}_{idx}"):
                st.session_state[batch_key].pop(idx)
                # Also clear preview to force re-preview
                st.session_state.pop(f"leave_preview_{original_assignment_id}", None)
                st.rerun()
                
        st.markdown("---")
        _preview_and_apply(case_no, client, original_assignment_id, st.session_state[batch_key])


def _item(schedule_day, resolution, substitute) -> dict:
    return {
        "original_schedule_id": int(schedule_day["id"]), 
        "work_date": str(schedule_day["work_date"])[:10], 
        "resolution_type": "substitute" if resolution == "指定代班月嫂" else "defer_following_assignments", 
        "substitute_staff_id": int(substitute) if substitute else None, 
        "is_double_pay": bool(schedule_day.get("is_double_pay"))
    }


def _preview_and_apply(case_no, client, assignment_id, items) -> None:
    state_key = f"leave_preview_{assignment_id}"
    
    if st.button("產生預覽 (Preview)", type="primary", key=f"leave_preview_button_{assignment_id}"):
        try:
            identity = _identity("leave-preview", case_no)
            st.session_state[state_key] = client.preview(
                case_no, 
                {"original_assignment_id": assignment_id, "items": items}, 
                identity
            )
            # Notify calendar to update using session state!
            st.session_state[f"attendance_preview_formal_{case_no}"] = st.session_state[state_key]
        except LeaveSubstitutionApiError as error:
            st.error(f"Preview 失敗 [{error.error.code}]：{error}")
            
    preview = st.session_state.get(state_key)
    if preview is None:
        return
        
    st.success("預覽已產生，請查看月曆上的視覺變化（綠色為排休/順延、紅色為新工作日）。")
    st.dataframe([outcome.model_dump(mode="json") for outcome in preview.outcomes], hide_index=True, width="stretch")
    
    reason = st.text_input("確認儲存：請輸入請假／代班原因", key=f"leave_reason_{assignment_id}")
    confirm = st.checkbox("確認依此 Preview 套用", key=f"leave_confirm_{assignment_id}")
    
    if st.button("💾 確認儲存 (Apply)", disabled=not confirm or not reason.strip(), key=f"leave_apply_{assignment_id}"):
        _apply(case_no, client, assignment_id, preview, reason.strip())


def _apply(case_no, client, assignment_id, preview, reason) -> None:
    items = st.session_state.get(f"leave_batch_{assignment_id}")
    if not isinstance(items, list) or not items:
        st.error("請重新產生 Preview。")
        return
        
    payload = {
        "original_assignment_id": assignment_id, 
        "items": items, 
        "expected_order_version": preview.order_version, 
        "expected_scheduling_version": preview.scheduling_version, 
        "expected_client_finance_version": preview.client_finance_version, 
        "expected_payroll_version": preview.payroll_version, 
        "preview_fingerprint": preview.preview_fingerprint, 
        "reason": reason
    }
    
    try:
        receipt = client.apply(
            case_no, 
            payload, 
            _identity("leave-apply", case_no), 
            _identity("leave-apply-correlation", case_no)
        )
    except LeaveSubstitutionApiError as error:
        st.error(f"Apply 失敗 [{error.error.code}]：{error}")
        return
        
    st.success(f"已完成請假／代班處理；事件：{', '.join(map(str, receipt.outcome_event_ids))}")
    # Clear the batch and preview states after successful apply
    st.session_state.pop(f"leave_batch_{assignment_id}", None)
    st.session_state.pop(f"leave_preview_{assignment_id}", None)
    st.session_state.pop(f"attendance_preview_formal_{case_no}", None)
    # Rerun to refresh the view
    st.rerun()


def _identity(prefix: str, case_no: str) -> str:
    return f"{prefix}-{case_no}-{uuid.uuid4().hex}"

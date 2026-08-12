"""Thin UI for formal leave/substitution Preview and Apply."""

from __future__ import annotations

import uuid

import streamlit as st

from ui.api_clients.leave_substitution_api_client import (
    LeaveSubstitutionApiClient,
    LeaveSubstitutionApiError,
)
from ui.api_clients.staff_summary_api_client import StaffSummaryApiClient
from ui.pages.shared import build_admin_headers, resolve_api_base_url


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_staff_option_page(
    base_url: str,
    header_items: tuple,
    after_id: int | None,
) -> tuple[dict[str, int], int | None]:
    """Return one bounded page of substitute-staff options."""
    try:
        page = StaffSummaryApiClient(
            base_url=base_url,
            headers=dict(header_items),
        ).query(page_size=200, after_id=after_id)
        options = {
            f"{item.name or ''}（{item.phone or ''}）": item.id
            for item in page.items
            if item.name
        }
        return options, page.next_cursor
    except Exception:
        return {}, None


def _render_staff_option_pagination(assignment_id: int) -> dict[str, int]:
    cursor_key = f"leave_substitute_after_id_{assignment_id}"
    history_key = f"leave_substitute_history_{assignment_id}"
    next_key = f"leave_substitute_next_cursor_{assignment_id}"
    current_cursor = st.session_state.get(cursor_key)
    options, next_cursor = _fetch_staff_option_page(
        resolve_api_base_url(),
        tuple(sorted(build_admin_headers().items())),
        current_cursor,
    )
    st.session_state[next_key] = next_cursor
    history = st.session_state.setdefault(history_key, [])
    if not history and not next_cursor:
        return options
    previous_column, page_column, next_column = st.columns([1, 2, 1])
    if previous_column.button(
        "上一頁月嫂",
        disabled=not history,
        key=f"leave_previous_staff_{assignment_id}",
    ):
        st.session_state[cursor_key] = history.pop()
        st.rerun()
    page_column.caption(f"代班月嫂第 {len(history) + 1} 頁，每頁最多 200 筆")
    if next_column.button(
        "下一頁月嫂",
        disabled=not next_cursor,
        key=f"leave_next_staff_{assignment_id}",
    ):
        history.append(current_cursor)
        st.session_state[cursor_key] = next_cursor
        st.rerun()
    return options


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

    _render_service_day_baseline(work_days)
    
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
        staff_opts = _render_staff_option_pagination(original_assignment_id)
        if not staff_opts:
            st.warning("無法載入月嫂名單，請確認後端服務正常。")
        else:
            sub_label = st.selectbox(
                "代班月嫂",
                ["請選擇代班月嫂", *staff_opts.keys()],
                key=(
                    f"leave_substitute_{original_assignment_id}_"
                    f"{st.session_state.get(f'leave_substitute_after_id_{original_assignment_id}') or 0}"
                ),
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
                
    else:
        st.info("尚未加入手動調整項目；可直接產生國定假日精算 Preview。")

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
        
    st.success("預覽已產生；目前尚未寫入資料庫。")
    candidate = preview.calendar_candidate
    summary_columns = st.columns(4)
    summary_columns[0].metric("合約服務天數", candidate.contracted_service_day_count)
    summary_columns[1].metric("服務天數", f"{candidate.before_service_day_count} → {candidate.after_service_day_count}")
    summary_columns[2].metric("本批調整", f"順延 {candidate.deferred_day_count}／代班 {candidate.substitute_day_count}")
    summary_columns[3].metric("服務天數守恆", candidate.conservation_status)
    st.caption(
        "分類："
        f"國定假日休假 {candidate.holiday_rest_day_count}／"
        f"固定排休 {candidate.fixed_rest_day_count}／"
        f"本批請假 {candidate.leave_day_count}"
    )
    st.caption(
        "服務期間："
        f"{candidate.before_service_start_date or '-'} ～ {candidate.before_service_end_date or '-'}"
        " → "
        f"{candidate.after_service_start_date or '-'} ～ {candidate.after_service_end_date or '-'}"
    )
    if candidate.holiday_rows:
        st.caption(
            "國定假日（預設休假，已納入服務日順延）："
            + "、".join(f"{holiday_date} {holiday_name}" for holiday_date, holiday_name in candidate.holiday_rows)
        )
    _render_calendar_changes(candidate.day_cells)

    is_ready = preview.apply_readiness.status == "ready"
    if not is_ready:
        st.warning("目前只能預覽，尚不可儲存：" + "、".join(preview.apply_readiness.blockers))
    
    reason = st.text_input("確認儲存：請輸入請假／代班原因", key=f"leave_reason_{assignment_id}")
    confirm = st.checkbox("確認依此 Preview 套用", key=f"leave_confirm_{assignment_id}")
    
    if st.button("💾 確認儲存 (Apply)", disabled=not is_ready or not confirm or not reason.strip(), key=f"leave_apply_{assignment_id}"):
        _apply(case_no, client, assignment_id, preview, reason.strip())


def _apply(case_no, client, assignment_id, preview, reason) -> None:
    items = st.session_state.get(f"leave_batch_{assignment_id}")
    if not isinstance(items, list):
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


def _render_service_day_baseline(work_days: list[dict]) -> None:
    service_dates = sorted(str(row["work_date"])[:10] for row in work_days)
    columns = st.columns(2)
    columns[0].metric("目前正式服務天數", len(service_dates))
    columns[1].metric(
        "目前正式服務期間",
        f"{service_dates[0]} ～ {service_dates[-1]}",
    )
    st.caption("加入休假或代班項目後，產生 Preview 才會顯示調整後的服務日差異。")


def _render_calendar_changes(day_cells) -> None:
    changes = [cell for cell in day_cells if cell.change_kind != "unchanged"]
    if not changes:
        return
    st.markdown("#### 行事曆差異")
    st.caption("圖例：休假日不計服務天數並順延；順延後與代班日都是服務工作日。")
    for cell in changes:
        owner = f"月嫂 {cell.before_staff_id or '-'} → 月嫂 {cell.after_staff_id or '-'}"
        label = {
            "deferred_from": "休假日（扣除服務日並順延）",
            "deferred_to": "順延後服務日",
            "substitute": "代班服務日",
        }.get(cell.change_kind, cell.change_kind)
        st.write(f"{cell.calendar_date}｜{label}｜{owner}")

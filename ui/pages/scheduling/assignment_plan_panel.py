"""Thin Preview/Apply panel for the canonical Assignment Plan API."""

from __future__ import annotations

from datetime import date, timedelta
import uuid

import streamlit as st

from ui.api_clients.assignment_plan_api_client import (
    AssignmentPlanApiClient,
    AssignmentPlanApiError,
)


def render_assignment_plan_panel(
    case_no: str,
    client: AssignmentPlanApiClient,
    *,
    staff_choices: dict[str, int],
    draft_segments: list[dict] | None = None,
) -> None:
    try:
        current = client.query(case_no)
    except AssignmentPlanApiError as error:
        st.error(f"正式人力配置載入失敗 [{error.error.code}]：{error}")
        return
    if not staff_choices:
        st.warning("目前沒有可指派的月嫂。")
        return
    st.caption(
        f"合約服務 {current.contracted_service_days} 日｜"
        f"每天 {current.service_hours_per_day} 小時｜"
        f"目前 generation {current.scheduling_generation}"
    )
    _render_existing_assignments(current)
    segments = _segment_form(case_no, staff_choices, draft_segments)
    _preview_controls(case_no, client, segments)


def _render_existing_assignments(current) -> None:
    if not current.assignments:
        st.info("尚未建立正式人力配置。")
        return
    st.dataframe(
        [
            {
                "月嫂": item.staff_id,
                "期間": f"{item.assigned_start_date} ～ {item.assigned_end_date}",
                "正式服務日": len(item.official_service_dates),
                "狀態": item.assignment_id or "預覽",
            }
            for item in current.assignments
        ],
        hide_index=True,
        width="stretch",
    )


def _segment_form(case_no, staff_choices, draft_segments) -> list[dict]:
    defaults = draft_segments or []
    count_options = list(range(1, min(4, len(staff_choices)) + 1))
    count = st.selectbox(
        "人力分段數", count_options,
        index=min(max(len(defaults), 1), count_options[-1]) - 1,
        key=f"assignment_plan_count_{case_no}",
    )
    selected: list[dict] = []
    used_staff: set[int] = set()
    for index in range(count):
        default = defaults[index] if index < len(defaults) else {}
        selected.append(_segment_inputs(case_no, index, staff_choices, used_staff, default))
        used_staff.add(selected[-1]["staff_id"])
    return selected


def _segment_inputs(case_no, index, staff_choices, used_staff, default) -> dict:
    available = {
        label: staff_id for label, staff_id in staff_choices.items()
        if staff_id not in used_staff
    }
    label = st.selectbox(
        f"第 {index + 1} 段月嫂", list(available),
        key=f"assignment_plan_staff_{case_no}_{index}",
    )
    start_default = _as_date(default.get("assigned_start_date"), date.today())
    end_default = _as_date(default.get("assigned_end_date"), start_default)
    columns = st.columns(2)
    start = columns[0].date_input(
        f"第 {index + 1} 段開始", value=start_default,
        key=f"assignment_plan_start_{case_no}_{index}",
    )
    end = columns[1].date_input(
        f"第 {index + 1} 段結束", value=max(end_default, start),
        key=f"assignment_plan_end_{case_no}_{index}",
    )
    return {
        "staff_id": available[label],
        "assigned_start_date": start.isoformat(),
        "assigned_end_date": end.isoformat(),
        "official_service_dates": _date_range(start, end),
    }


def _preview_controls(case_no, client, segments) -> None:
    state_key = f"assignment_plan_preview_{case_no}"
    if st.button("產生正式人力配置 Preview", key=f"assignment_plan_preview_button_{case_no}"):
        try:
            st.session_state[state_key] = client.preview(
                case_no, segments, _command_id("assignment-plan-preview", case_no)
            )
            st.session_state[f"assignment_plan_segments_{case_no}"] = segments
        except (AssignmentPlanApiError, ValueError) as error:
            st.error(f"Preview 失敗：{error}")
    preview = st.session_state.get(state_key)
    if preview is not None:
        _apply_controls(case_no, client, preview)


def _apply_controls(case_no, client, preview) -> None:
    st.success(f"Preview 已產生：將建立 {len(preview.assignments)} 段正式指派。")
    reason = st.text_input("套用原因", key=f"assignment_plan_reason_{case_no}")
    confirmed = st.checkbox("確認依此 Preview 套用正式人力配置", key=f"assignment_plan_confirm_{case_no}")
    if st.button("Apply 正式人力配置", disabled=not confirmed or not reason.strip(), key=f"assignment_plan_apply_{case_no}"):
        _submit_apply(case_no, client, preview, reason.strip())
    job_id = st.session_state.get(f"assignment_plan_job_{case_no}")
    if job_id and st.button("查詢 Apply 狀態", key=f"assignment_plan_job_status_{case_no}"):
        _show_job_status(client, job_id)


def _submit_apply(case_no, client, preview, reason) -> None:
    segments = st.session_state.get(f"assignment_plan_segments_{case_no}")
    if not isinstance(segments, list):
        st.error("請重新產生 Preview。")
        return
    identity = _command_id("assignment-plan-apply", case_no)
    try:
        accepted = client.apply(case_no, segments, preview, reason=reason, idempotency_key=identity, correlation_id=identity)
    except (AssignmentPlanApiError, ValueError) as error:
        st.error(f"Apply 失敗：{error}")
        return
    st.session_state[f"assignment_plan_job_{case_no}"] = accepted.job_id
    st.info(f"正式人力配置正在處理，工作編號：{accepted.job_id}")


def _show_job_status(client, job_id) -> None:
    try:
        status = client.get_job_status(job_id)
    except AssignmentPlanApiError as error:
        st.error(f"工作狀態查詢失敗：{error}")
        return
    st.write({"job_id": status.job_id, "status": status.status, "error": status.error_payload})


def _as_date(value, fallback: date) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return fallback


def _date_range(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]


def _command_id(prefix: str, case_no: str) -> str:
    return f"{prefix}-{case_no}-{uuid.uuid4().hex}"

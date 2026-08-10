"""Thin Preview/Apply panel for the canonical Assignment Plan API."""

from __future__ import annotations

from datetime import date, timedelta
import uuid

import streamlit as st

from ui.api_clients.assignment_plan_api_client import (
    AssignmentPlanApiClient,
    AssignmentPlanApiError,
)


_APPLY_STATE_SUFFIX = "assignment_plan_apply_state"
_JOB_STATUS_POLL_INTERVAL_SECONDS = 5


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
            with st.spinner("正在產生正式人力配置 Preview…"):
                st.session_state[state_key] = client.preview(
                    case_no, segments, _command_id("assignment-plan-preview", case_no)
                )
            st.session_state[f"assignment_plan_segments_{case_no}"] = segments
            st.session_state.pop(_apply_state_key(case_no), None)
        except (AssignmentPlanApiError, ValueError) as error:
            st.error(f"Preview 失敗：{error}")
    preview = st.session_state.get(state_key)
    if preview is not None:
        _apply_controls(case_no, client, preview)


def _apply_controls(case_no, client, preview) -> None:
    st.success(f"Preview 已產生：將建立 {len(preview.assignments)} 段正式指派。")
    reason = st.text_input("套用原因", key=f"assignment_plan_reason_{case_no}")
    confirmed = st.checkbox("確認依此 Preview 套用正式人力配置", key=f"assignment_plan_confirm_{case_no}")
    command = st.session_state.get(_apply_state_key(case_no))
    command_pending = isinstance(command, dict) and not command.get("terminal")
    if st.button("Apply 正式人力配置", disabled=command_pending or not confirmed or not reason.strip(), key=f"assignment_plan_apply_{case_no}"):
        _submit_apply(case_no, client, preview, reason.strip())
    _render_apply_status(case_no, client, preview)


def _submit_apply(case_no, client, preview, reason) -> None:
    segments = st.session_state.get(f"assignment_plan_segments_{case_no}")
    if not isinstance(segments, list):
        st.error("請重新產生 Preview。")
        return
    command = _apply_command(case_no, preview, segments, reason, st.session_state)
    try:
        with st.spinner("正在受理正式人力配置工作…"):
            accepted = client.apply(
                case_no,
                command["segments"],
                command["preview"],
                reason=command["reason"],
                idempotency_key=command["idempotency_key"],
                correlation_id=command["correlation_id"],
            )
    except (AssignmentPlanApiError, ValueError) as error:
        st.warning(f"Apply 結果尚未確認：{error}")
        return
    command["job_id"] = accepted.job_id
    st.info(f"正式人力配置正在處理，工作編號：{accepted.job_id}")


@st.fragment(run_every=_JOB_STATUS_POLL_INTERVAL_SECONDS)
def _render_apply_status(case_no, client, preview) -> None:
    command = st.session_state.get(_apply_state_key(case_no))
    if not isinstance(command, dict) or command.get("terminal"):
        return
    if not command.get("job_id"):
        st.warning("Apply 結果尚未確認；可安全重送同一命令。")
        if st.button("重送相同 Apply 請求", key=f"assignment_plan_apply_retry_{case_no}"):
            _submit_apply(case_no, client, preview, command["reason"])
        return
    st.info(f"正式人力配置處理中，工作編號：{command['job_id']}")
    if st.button("查詢 Apply 狀態", key=f"assignment_plan_job_status_{case_no}"):
        _show_job_status(client, command)


def _show_job_status(client, command) -> None:
    try:
        with st.spinner("正在查詢正式人力配置工作狀態…"):
            status = client.get_job_status(command["job_id"])
    except AssignmentPlanApiError as error:
        st.error(f"工作狀態查詢失敗：{error}")
        return
    if status.status in {"queued", "running"}:
        st.info(f"正式人力配置仍在處理：{status.status}")
        return
    command["terminal"] = True
    if status.status == "succeeded":
        st.success("正式人力配置已完成。")
        st.json(status.receipt_payload)
        return
    st.error(f"正式人力配置未完成：{status.status}")
    st.write({"job_id": status.job_id, "status": status.status, "error": status.error_payload})


def _apply_state_key(case_no: str) -> str:
    return f"{_APPLY_STATE_SUFFIX}_{case_no}"


def _apply_command(case_no, preview, segments, reason, state) -> dict:
    existing = state.get(_apply_state_key(case_no))
    if isinstance(existing, dict) and not existing.get("terminal"):
        return existing
    identity = _command_id("assignment-plan-apply", case_no)
    command = {
        "preview": preview,
        "segments": segments,
        "reason": reason,
        "idempotency_key": identity,
        "correlation_id": _command_id("assignment-plan-correlation", case_no),
        "job_id": None,
        "terminal": False,
    }
    state[_apply_state_key(case_no)] = command
    return command


def _as_date(value, fallback: date) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return fallback


def _date_range(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]


def _command_id(prefix: str, case_no: str) -> str:
    return f"{prefix}-{case_no}-{uuid.uuid4().hex}"

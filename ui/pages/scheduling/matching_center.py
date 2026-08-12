"""Negotiation-stage segmented caregiver matching."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import uuid

import requests
import streamlit as st

from ui.api_clients.assignment_plan_api_client import AssignmentPlanApiClient
from ui.api_clients.waiting_deposit_lock_api_client import (
    WaitingDepositLockApiClient,
    WaitingDepositLockApiError,
)
from ui.pages.scheduling.assignment_plan_panel import (
    render_assignment_plan_panel,
)
from ui.pages.scheduling.navigation_state import apply_one_time_default
from ui.pages.shared import (
    admin_auth_is_bypassed,
    build_admin_headers,
    resolve_api_base_url,
)


def _request(path: str, *, method: str = "GET", payload: Any = None,
             idempotency_key: str | None = None):
    headers = build_admin_headers()
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    response = requests.request(
        method,
        f"{resolve_api_base_url()}{path}",
        headers=headers,
        json=payload,
        timeout=15,
    )
    body = response.json()
    if not response.ok or not body.get("success"):
        raise ValueError(body.get("detail") or body.get("message") or "API request failed")
    return body.get("data")


def _as_date(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def _actor() -> str:
    if admin_auth_is_bypassed():
        return "development-bypass"
    profile = st.session_state.get("line_admin_profile") or {}
    return str(
        profile.get("username") if isinstance(profile, dict) else ""
    ).strip() or "development-bypass"


def _assignment_plan_drafts(segments):
    return [
        {
            "staff_id": int(segment["staff_id"]),
            "assigned_start_date": str(segment["assigned_start_date"]),
            "assigned_end_date": str(segment["assigned_end_date"]),
            "official_service_dates": [],
        }
        for segment in segments
    ]


def _waiting_lock_client() -> WaitingDepositLockApiClient:
    return WaitingDepositLockApiClient(
        base_url=resolve_api_base_url(),
        headers=build_admin_headers(),
    )


def _show_waiting_lock_error(action: str, error: Exception) -> None:
    if not isinstance(error, WaitingDepositLockApiError):
        st.error(f"{action}失敗：{error}")
        return
    st.error(f"{action}失敗 [{error.error.code}]：{error.error.message}")
    if error.error.retryable:
        st.caption("此錯誤可重試；請確認後端服務後再次操作。")


def _new_command_identity(action: str, case_no: str) -> dict[str, str]:
    identity = uuid.uuid4().hex
    return {
        "idempotency_key": f"{action}-{case_no}-{identity}",
        "correlation_id": f"{action}-{case_no}-{identity}",
    }


def _clear_waiting_lock_state(case_no: str, action: str) -> None:
    st.session_state.pop(f"waiting_lock_{action}_preview_{case_no}", None)
    st.session_state.pop(f"waiting_lock_{action}_command_{case_no}", None)


# This view stays cohesive so its widgets share one explicit Preview lifecycle.
def _render_acquisition_preview(
    case_no: str,
    plan_id: int,
    preview: dict[str, Any],
    lock_state_key: str,
) -> None:
    st.caption(
        f"預計鎖定 {preview['service_day_count']} 個服務日，"
        f"另預留 {preview['buffer_day_count']} 個七日緩衝檔期。"
    )
    if preview.get("conflicts"):
        st.error("Preview 發現檔期衝突，請先調整配對方案。")
        st.dataframe(preview["conflicts"], hide_index=True, width="stretch")
    with st.expander("查看本次鎖定日期", expanded=False):
        st.dataframe(preview["occupancy"], hide_index=True, width="stretch")
    _render_acquisition_apply_controls(
        case_no,
        plan_id,
        preview,
        lock_state_key,
    )


def _render_acquisition_apply_controls(
    case_no: str,
    plan_id: int,
    preview: dict[str, Any],
    lock_state_key: str,
) -> None:
    confirmed = st.checkbox(
        "確認依此 Preview 鎖定服務日與七日緩衝",
        key=f"waiting_lock_acquire_confirm_{case_no}",
    )
    if st.button(
        "Apply 鎖定檔期",
        key=f"waiting_lock_acquire_apply_{case_no}",
        disabled=not confirmed or not preview["apply_allowed"],
        type="primary",
    ):
        _apply_waiting_lock_acquisition(case_no, plan_id, preview, lock_state_key)


# Apply stays cohesive so receipt persistence and rerun cannot be separated.
def _apply_waiting_lock_acquisition(
    case_no: str,
    plan_id: int,
    preview: dict[str, Any],
    lock_state_key: str,
) -> None:
    command = st.session_state[f"waiting_lock_acquire_command_{case_no}"]
    try:
        receipt = _waiting_lock_client().apply_acquisition(
            case_no,
            plan_id,
            preview["preview_fingerprint"],
            **command,
        )
    except Exception as error:
        _show_waiting_lock_error("鎖定", error)
        return
    st.session_state[lock_state_key] = receipt.model_dump()
    _clear_waiting_lock_state(case_no, "acquire")
    st.success("服務日期與結束後七日緩衝已鎖定，訂單維持洽談中等待訂金。")
    st.rerun()


def _render_waiting_lock_acquisition(
    case_no: str,
    plan_id: int,
    lock_state_key: str,
    *,
    enabled: bool,
) -> None:
    preview_state_key = f"waiting_lock_acquire_preview_{case_no}"
    if st.button(
        "產生等待訂金鎖 Preview",
        key=f"waiting_lock_acquire_preview_button_{case_no}",
        disabled=not enabled,
    ):
        _load_acquisition_preview(case_no, plan_id, preview_state_key)
    preview = st.session_state.get(preview_state_key)
    if preview and preview.get("plan_id") == plan_id:
        _render_acquisition_preview(case_no, plan_id, preview, lock_state_key)


def _load_acquisition_preview(
    case_no: str,
    plan_id: int,
    preview_state_key: str,
) -> None:
    try:
        preview = _waiting_lock_client().preview_acquisition(case_no, plan_id)
    except Exception as error:
        _show_waiting_lock_error("產生鎖定 Preview", error)
        return
    st.session_state[preview_state_key] = preview.model_dump()
    st.session_state[f"waiting_lock_acquire_command_{case_no}"] = (
        _new_command_identity("waiting-lock-acquire", case_no)
    )


_RELEASE_BLOCKER_LABELS = {
    "case_not_in_negotiation": "案件已不在洽談階段",
    "deposit_not_zero": "訂金已有入帳、退款或沖銷紀錄，不能直接解除檔期",
    "lock_not_active": "等待訂金鎖已不在有效狀態",
    "plan_not_accepted": "配對方案已不在已接受狀態",
}


def _release_blocker_text(blocker: str) -> str:
    return _RELEASE_BLOCKER_LABELS.get(blocker, blocker)


# This view stays cohesive so its widgets share one explicit Preview lifecycle.
def _render_release_preview(
    case_no: str,
    plan_id: int,
    lock_id: int,
    preview: dict[str, Any],
    lock_state_key: str,
    active_state_key: str,
) -> None:
    st.caption(
        f"預計解除 {preview['service_day_count']} 個服務日檔期，"
        f"涉及 {preview['staff_count']} 位月嫂；聯繫與意願歷史仍保留。"
    )
    if preview.get("blockers"):
        st.error("目前不能解除：" + "、".join(
            _release_blocker_text(item) for item in preview["blockers"]
        ))
    _render_release_apply_controls(
        case_no,
        plan_id,
        lock_id,
        preview,
        lock_state_key,
        active_state_key,
    )


# These widgets stay together because confirmation, reason, and Apply are one gate.
def _render_release_apply_controls(
    case_no: str,
    plan_id: int,
    lock_id: int,
    preview: dict[str, Any],
    lock_state_key: str,
    active_state_key: str,
) -> None:
    reason = st.text_input(
        "回復未綁定原因",
        key=f"waiting_lock_release_reason_{case_no}",
    )
    confirmed = st.checkbox(
        "確認依此 Preview 回復未綁定狀態",
        key=f"waiting_lock_release_confirm_{case_no}",
    )
    if st.button(
        "Apply 回復未綁定",
        key=f"waiting_lock_release_apply_{case_no}",
        disabled=(
            not confirmed
            or not reason.strip()
            or not preview["apply_allowed"]
        ),
        type="primary",
    ):
        _apply_waiting_lock_release(
            case_no,
            plan_id,
            lock_id,
            preview,
            reason.strip(),
            lock_state_key,
            active_state_key,
        )


# Apply stays cohesive so receipt cleanup and rerun cannot be separated.
def _apply_waiting_lock_release(
    case_no: str,
    plan_id: int,
    lock_id: int,
    preview: dict[str, Any],
    reason: str,
    lock_state_key: str,
    active_state_key: str,
) -> None:
    command = st.session_state[f"waiting_lock_release_command_{case_no}"]
    try:
        _waiting_lock_client().apply_release(
            case_no,
            plan_id,
            lock_id,
            preview["preview_fingerprint"],
            reason=reason,
            **command,
        )
    except Exception as error:
        _show_waiting_lock_error("回復未綁定", error)
        return
    for state_key in (lock_state_key, active_state_key):
        st.session_state.pop(state_key, None)
    _clear_waiting_lock_state(case_no, "release")
    st.success("已解除服務日與七日緩衝檔期；履歷與意願歷史保留。")
    st.rerun()


# Preview loading and rendering stay together to avoid stale lock session state.
def _render_waiting_lock_release(
    case_no: str,
    plan_id: int,
    lock_id: int,
    lock_state_key: str,
    active_state_key: str,
) -> None:
    preview_state_key = f"waiting_lock_release_preview_{case_no}"
    if st.button(
        "產生回復未綁定 Preview",
        key=f"waiting_lock_release_preview_button_{case_no}",
    ):
        _load_release_preview(case_no, plan_id, lock_id, preview_state_key)
    preview = st.session_state.get(preview_state_key)
    if preview and preview.get("lock_id") == lock_id:
        _render_release_preview(
            case_no,
            plan_id,
            lock_id,
            preview,
            lock_state_key,
            active_state_key,
        )


def _load_release_preview(
    case_no: str,
    plan_id: int,
    lock_id: int,
    preview_state_key: str,
) -> None:
    try:
        preview = _waiting_lock_client().preview_release(
            case_no,
            plan_id,
            lock_id,
        )
    except Exception as error:
        _show_waiting_lock_error("產生解除 Preview", error)
        return
    st.session_state[preview_state_key] = preview.model_dump()
    st.session_state[f"waiting_lock_release_command_{case_no}"] = (
        _new_command_identity("waiting-lock-release", case_no)
    )


# The page workflow remains ordered because Streamlit renders and mutates state linearly.
def _render_multi_segment_matching(
    order: dict[str, Any],
    staff: list[dict[str, Any]],
    *,
    preview_only: bool = False,
    fixed_segment_count: int | None = None,
) -> None:
    """Render the multi-caregiver fallback for one negotiation-stage order."""
    case_no = order["case_no"]
    active_state_key = f"matching_active_state_{case_no}"
    active_state = {}
    if not preview_only:
        try:
            active_state = _request(
                f"/api/v1/orders/{case_no}/matching-plans/active"
            )
            st.session_state[active_state_key] = active_state
            if active_state:
                st.session_state[f"matching_plan_{case_no}"] = active_state.get("plan") or {}
                st.session_state[f"matching_contact_state_{case_no}"] = active_state
                if active_state.get("availability_lock"):
                    st.session_state[f"matching_lock_{case_no}"] = active_state[
                        "availability_lock"
                    ]
        except Exception:
            active_state = st.session_state.get(active_state_key) or {}
    planned_start = _as_date(order.get("actual_start_date") or order.get("start_date"))
    raw_end = order.get("actual_end_date") or order.get("end_date")
    planned_end = (
        _as_date(raw_end)
        if raw_end
        else planned_start + timedelta(days=max(int(order.get("service_days") or 1) - 1, 0))
    )
    if preview_only:
        st.markdown("#### 多月嫂配對測試預覽")
    else:
        st.caption("單一與多月嫂皆使用同一份版本化配對方案與聯繫歷史。")
    count = fixed_segment_count or st.selectbox(
        "服務分段數", [2, 3, 4], key=f"matching_segment_count_{case_no}"
    )
    span = max((planned_end - planned_start).days + 1, count)
    state_key = f"matching_availability_{case_no}_{count}"
    default_drafts = []
    for index in range(count):
        default_start = planned_start + timedelta(days=(span * index) // count)
        default_end = (
            planned_end
            if index == count - 1
            else planned_start + timedelta(days=(span * (index + 1)) // count - 1)
        )
        default_drafts.append(
            {
                "start_date": default_start.isoformat(),
                "end_date": default_end.isoformat(),
            }
        )
    if state_key not in st.session_state:
        try:
            st.session_state[state_key] = _request(
                f"/api/v1/orders/{case_no}/caregiver-segment-availability/search",
                method="POST",
                payload={
                    "segment_count": count,
                    "segment_drafts": default_drafts,
                    "as_of": date.today().isoformat(),
                },
            )
        except Exception as error:
            st.session_state[state_key] = None
            st.warning(f"初始檔期查詢失敗：{error}")

    availability = st.session_state.get(state_key) or {}
    candidate_options = availability.get("candidate_options") or []
    drafts = []
    for index in range(count):
        default_start = planned_start + timedelta(days=(span * index) // count)
        default_end = (
            planned_end
            if index == count - 1
            else planned_start + timedelta(days=(span * (index + 1)) // count - 1)
        )
        start_key = f"matching_start_{case_no}_{index}"
        end_key = f"matching_end_{case_no}_{index}"
        current_start = st.session_state.get(start_key, default_start)
        current_end = st.session_state.get(end_key, default_end)
        selected_staff_ids = {
            row["staff_id"] for row in drafts if row.get("staff_id") is not None
        }
        eligible_options = [
            option
            for option in candidate_options
            if option.get("segment_index") == index
            and option.get("staff_id") not in selected_staff_ids
            and option.get("full_selected_segment_coverage")
        ]
        candidate_labels = {
            _candidate_option_label(option): int(option["staff_id"])
            for option in eligible_options
        }
        if fixed_segment_count:
            st.caption(f"服務期間：{default_start.isoformat()} ～ {default_end.isoformat()}")
            label = st.selectbox(
                "選擇月嫂",
                ["尚未選擇", *candidate_labels],
                key=f"matching_staff_{case_no}_{index}",
            )
            start, end = default_start, default_end
        else:
            columns = st.columns(3)
            label = columns[0].selectbox(
                f"第 {index + 1} 段月嫂",
                ["尚未選擇", *candidate_labels],
                key=f"matching_staff_{case_no}_{index}",
            )
            start = columns[1].date_input(
                f"第 {index + 1} 段開始日",
                value=default_start,
                key=start_key,
            )
            end = columns[2].date_input(
                f"第 {index + 1} 段結束日",
                value=default_end,
                key=end_key,
            )
        draft = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        if label != "尚未選擇":
            draft["staff_id"] = candidate_labels[label]
        drafts.append(draft)

    if st.button("重新查詢最新檔期", key=f"matching_refresh_{case_no}"):
        try:
            st.session_state[state_key] = _request(
                f"/api/v1/orders/{case_no}/caregiver-segment-availability/search",
                method="POST",
                payload={
                    "segment_count": count,
                    "segment_drafts": drafts,
                    "as_of": date.today().isoformat(),
                },
            )
        except Exception as error:
            st.error(f"檔期查詢失敗：{error}")

    availability = st.session_state.get(state_key)
    if availability:
        if availability.get("feasibility") == "partial":
            uncovered = sorted(
                {
                    str(item.get("work_date"))
                    for item in availability.get("conflicts", [])
                    if item.get("reason_code") == "coverage_gap"
                }
            )
            st.warning("目前只有部分可行人力；未覆蓋日期：" + "、".join(uncovered))
        conflicts = availability.get("conflicts") or []
        if conflicts:
            st.error(
                "阻擋原因："
                + "、".join(
                    f"月嫂 {item.get('staff_id') or '-'}／{item.get('work_date')}／{item.get('reason_code')}"
                    for item in conflicts
                )
            )

    selected_segments = [row for row in drafts if row.get("staff_id")]
    if st.button(
        "聯繫與確認意願",
        key=f"matching_contact_{case_no}_{'preview' if preview_only else 'live'}",
        disabled=preview_only,
    ):
        if len(selected_segments) != count:
            st.error("每個區段都必須選擇月嫂。")
        else:
            try:
                plan = _request(
                    f"/api/v1/orders/{case_no}/matching-plans",
                    method="POST",
                    payload={
                        "segments": [
                            {
                                "segment_order": index + 1,
                                **segment,
                            }
                            for index, segment in enumerate(selected_segments)
                        ],
                        "created_by": _actor(),
                        "as_of": date.today().isoformat(),
                    },
                )
                st.session_state[f"matching_plan_{case_no}"] = plan
                st.success("方案已通過最新檔期驗證，可逐位發送訂單資訊。")
            except Exception as error:
                st.error(f"未發送：{error}")

    if preview_only:
        st.caption("測試預覽不會建立方案、鎖定檔期或發送任何聯繫資料。")
        return

    plan = st.session_state.get(f"matching_plan_{case_no}") or {}
    plan_id = plan.get("plan_id") or plan.get("id")
    contact_state_key = f"matching_contact_state_{case_no}"
    if plan_id:
        try:
            refreshed_contact_state = _request(
                f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/contact-state"
            )
            for lifecycle_field in ("availability_lock", "deposit"):
                if lifecycle_field in active_state:
                    refreshed_contact_state[lifecycle_field] = active_state[
                        lifecycle_field
                    ]
            st.session_state[contact_state_key] = refreshed_contact_state
        except Exception as error:
            st.warning(f"聯繫紀錄讀取失敗：{error}")
    contact_state = st.session_state.get(contact_state_key) or {}
    contact_segments = contact_state.get("segments") or []
    communication_version = int(
        (contact_state.get("plan") or {}).get("communication_version") or 0
    )
    lock_state_key = f"matching_lock_{case_no}"
    lock = (
        contact_state.get("availability_lock")
        or st.session_state.get(lock_state_key)
        or {}
    )
    lock_id = lock.get("lock_id") or lock.get("id")
    if plan_id:
        st.markdown("#### 發送紀錄與月嫂意願")
        willingness_labels = {"願意": "willing", "無意願": "unwilling"}
        status_labels = {"pending": "待 LINE 回覆", "willing": "願意", "unwilling": "無意願"}
        for segment in contact_segments:
            segment_id = segment["segment_id"]
            with st.container(border=True):
                st.write(
                    f"{segment.get('staff_name') or '月嫂 ' + str(segment.get('staff_id'))}"
                    f"｜{segment.get('assigned_start_date')}～{segment.get('assigned_end_date')}"
                )
                info_1_col, info_2_col = st.columns(2)
                if info_1_col.button(
                    "發送訂單資訊-1",
                    key=f"matching_info_1_{case_no}_{segment_id}",
                ):
                    try:
                        _request(
                            f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/information",
                            method="POST",
                            payload={
                                "info_type": 1,
                                "expected_version": communication_version,
                                "event_key": f"info1-{case_no}-{uuid.uuid4().hex}",
                                "actor": _actor(),
                            },
                        )
                        st.success("訂單資訊-1 已進入可靠發送佇列。")
                        st.rerun()
                    except Exception as error:
                        st.error(f"未發送：{error}")
                if info_2_col.button(
                    "發送訂單資訊-2",
                    key=f"matching_info_2_{case_no}_{segment_id}",
                ):
                    try:
                        _request(
                            f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/information",
                            method="POST",
                            payload={
                                "info_type": 2,
                                "expected_version": communication_version,
                                "event_key": f"info2-{case_no}-{uuid.uuid4().hex}",
                                "actor": _actor(),
                            },
                        )
                        st.success("訂單資訊-2 已進入可靠發送佇列。")
                        st.rerun()
                    except Exception as error:
                        st.error(f"未發送：{error}")
                st.write("月嫂意願：" + status_labels.get(segment.get("willingness"), "未知"))
                with st.expander("人工補登意願（LINE 無法回覆時使用）"):
                    selected = st.selectbox(
                        "補登結果",
                        list(willingness_labels),
                        key=f"matching_willingness_{case_no}_{segment_id}",
                    )
                    manual_reason = st.text_input(
                        "補登原因",
                        key=f"matching_willingness_reason_{case_no}_{segment_id}",
                    )
                    if st.button(
                        "確認補登",
                        key=f"matching_willingness_update_{case_no}_{segment_id}",
                    ):
                        try:
                            _request(
                                f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment_id}/willingness",
                                method="PUT",
                                payload={
                                    "willingness": willingness_labels[selected],
                                    "expected_version": communication_version,
                                    "reason": manual_reason.strip(),
                                    "event_key": f"will-{case_no}-{uuid.uuid4().hex}",
                                    "actor": _actor(),
                                },
                            )
                            st.success("月嫂意願已補登。")
                            st.rerun()
                        except Exception as error:
                            st.error(f"意願補登失敗：{error}")
                st.caption(
                    "資訊-1："
                    + _delivery_status_label(segment.get("info_1_status"))
                    + "｜資訊-2："
                    + _delivery_status_label(segment.get("info_2_status"))
                )

        cancel_reason = st.text_input(
            "取消目前組合原因",
            key=f"matching_cancel_reason_{case_no}",
        )
        cancel_confirmed = st.checkbox(
            "確認取消目前組合；既有發送與意願歷史仍會保留",
            key=f"matching_cancel_confirm_{case_no}",
        )
        if st.button(
            "取消目前組合",
            key=f"matching_cancel_plan_{case_no}",
            disabled=bool(lock_id),
        ):
            if not cancel_confirmed or not cancel_reason.strip():
                st.error("取消目前組合前必須填寫原因並確認。")
            else:
                try:
                    _request(
                        f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/cancel",
                        method="POST",
                        payload={
                            "event_key": f"cancel-plan-{case_no}-{uuid.uuid4().hex}",
                            "actor": _actor(),
                            "reason": cancel_reason.strip(),
                        },
                    )
                    st.session_state.pop(f"matching_plan_{case_no}", None)
                    st.session_state.pop(contact_state_key, None)
                    st.success("目前組合已取消，可調整後重新聯繫。")
                    st.rerun()
                except Exception as error:
                    st.error(f"取消組合失敗：{error}")
        if lock_id:
            st.caption("目前方案已鎖定；若要取消案件，請使用既有訂單取消流程。")

    customer_decision = contact_state.get("customer_decision") or "pending"
    st.write("客戶配對回覆：" + _customer_decision_label(customer_decision))
    if plan_id:
        with st.expander("人工補登客戶回覆（LINE 無法回覆時使用）"):
            decision_labels = {
                "接受此配對": "accepted",
                "希望先聯絡": "contact_requested",
                "不接受此配對": "declined",
            }
            manual_customer_decision = st.selectbox(
                "補登結果",
                list(decision_labels),
                key=f"matching_customer_decision_{case_no}",
            )
            manual_customer_reason = st.text_input(
                "補登原因",
                key=f"matching_customer_reason_{case_no}",
            )
            if st.button(
                "確認補登客戶回覆",
                key=f"matching_customer_update_{case_no}",
            ):
                try:
                    _request(
                        f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/customer-decision",
                        method="PUT",
                        payload={
                            "decision": decision_labels[manual_customer_decision],
                            "expected_version": communication_version,
                            "reason": manual_customer_reason.strip(),
                            "event_key": f"customer-decision-{case_no}-{uuid.uuid4().hex}",
                            "actor": _actor(),
                        },
                    )
                    st.success("客戶回覆已補登。")
                    st.rerun()
                except Exception as error:
                    st.error(f"客戶回覆補登失敗：{error}")
    if plan_id:
        _render_waiting_lock_acquisition(
            case_no,
            plan_id,
            lock_state_key,
            enabled=(
                customer_decision == "accepted"
                and not bool(lock_id)
            ),
        )

    if plan_id and lock_id:
        from ui.pages.scheduling.matching_schedule_confirmation_panel import render_matching_schedule_confirmation
        schedule_gate_passed = render_matching_schedule_confirmation(case_no, plan_id, _request)
        st.caption("解除 Preview 會由後端確認案件狀態、有效鎖與訂金淨額。")
        _render_waiting_lock_release(
            case_no,
            plan_id,
            lock_id,
            lock_state_key,
            active_state_key,
        )

        st.markdown("#### 建立正式 Assignment Plan")
        st.caption(
            "配對區段只作預填；正式服務日必須逐段勾選。"
            "後端 Preview 會驗證訂金並重算排班、薪資、帳務與訂單影響。"
        )
        if schedule_gate_passed:
            assignment_client = AssignmentPlanApiClient(
                base_url=resolve_api_base_url(),
                headers=build_admin_headers(),
            )
            render_assignment_plan_panel(
                case_no,
                assignment_client,
                staff_choices=staff_labels,
                draft_segments=_assignment_plan_drafts(contact_segments),
            )
        else:
            st.info("客戶與月嫂確認目前日期表後，才會開放正式指派。")

    if plan_id:
        st.markdown("#### 傳送履歷給客戶")
        resume_note = st.text_area(
            "備註",
            placeholder="多月嫂案件請明確說明由多位月嫂共同完成。",
            key=f"matching_resume_note_{case_no}",
        )
        if st.button("傳送履歷", key=f"matching_resume_{case_no}"):
            if not contact_state.get("all_willing"):
                pending = [
                    str(segment.get("staff_name") or segment.get("staff_id"))
                    for segment in contact_segments
                    if segment.get("willingness") != "willing"
                ]
                st.error("尚未同意的月嫂：" + "、".join(pending))
            elif not resume_note.strip():
                st.error("請先填寫要與履歷一併傳送的備註。")
            else:
                try:
                    result = _request(
                        f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes",
                        method="POST",
                        payload={
                            "event_key": f"resume-{case_no}-{uuid.uuid4().hex}",
                            "actor": _actor(),
                            "note": resume_note.strip(),
                            "expected_version": communication_version,
                        },
                    )
                    st.success(
                        "已建立月嫂小卡與客戶確認按鈕的可靠發送任務。"
                    )
                    st.rerun()
                except Exception as error:
                    st.error(f"履歷未發送：{error}")
    else:
        st.info("請先建立配對方案並完成月嫂聯繫後，才可傳送履歷。")



def _delivery_status_label(status: str | None) -> str:
    labels = {
        None: "未建立",
        "pending": "等待發送",
        "processing": "發送中",
        "sent": "已送達",
        "retryable_failed": "等待重試",
        "failed": "發送失敗",
        "cancelled": "已取消",
    }
    return labels.get(status, "狀態未知")


def _customer_decision_label(decision: str) -> str:
    return {
        "pending": "待 LINE 回覆",
        "accepted": "已接受配對",
        "declined": "不接受配對",
        "contact_requested": "希望先聯絡",
    }.get(decision, "狀態未知")


_MATCHING_SUB_NAV_OPTIONS = ("⚡ 單月嫂智慧配對", "🧩 多月嫂配對方案(備案)")
_PLAN_SUB_NAV = "🧩 多月嫂配對方案(備案)"


def _apply_one_time_plan_default(default_to_plan: bool) -> None:
    apply_one_time_default(
        st.session_state,
        enabled=default_to_plan,
        navigation_value=_PLAN_SUB_NAV,
    )


def render_matching_center(
    orders: list[dict[str, Any]],
    staff: list[dict[str, Any]],
    *,
    preferred_case_no: str | None = None,
    default_to_plan: bool = False,
) -> None:
    st.subheader("🤝 月嫂配對中心 (Clients, Orders & Matching)")
    pending_orders = _negotiation_orders(orders)
    if not pending_orders:
        st.info("目前沒有洽談中的待配對案件。")
        return
    selected_order = _select_negotiation_order(
        pending_orders,
        preferred_case_no,
    )

    _render_matching_order_summary(selected_order)
    _apply_one_time_plan_default(default_to_plan)
    sub_nav = st.radio(
        "配對子頁籤",
        _MATCHING_SUB_NAV_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
        key="matching_center_sub_nav",
    )
    st.divider()
    if sub_nav == "⚡ 單月嫂智慧配對":
        _render_single_caregiver_matching(selected_order, staff)
    else:
        _render_multi_segment_matching(selected_order, staff)

def _iso_date_text(value, *, required=True, field_name="日期"):
    parsed = _parse_iso_date(value)
    if parsed is None:
        if required:
            raise ValueError(f"{field_name} 需提供 YYYY-MM-DD 日期")
        return None
    return parsed.isoformat()

def _parse_iso_date(value):
    from datetime import datetime, date
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        clean_value = value.split(" ")[0].strip()
        if not clean_value:
            return None
        return datetime.strptime(clean_value, "%Y-%m-%d").date()
    return None

def _single_caregiver_covers_service_period(order):
    from datetime import datetime, timedelta, date
    start_date = _iso_date_text(
        order.get("actual_start_date") or order.get("start_date"),
        required=True,
        field_name="服務開始日",
    )
    raw_end = order.get("actual_end_date") or order.get("end_date")
    if raw_end:
        end_date = _iso_date_text(raw_end, required=True, field_name="服務結束日")
    else:
        service_days = int(order.get("service_days") or 0)
        if service_days <= 0:
            raise ValueError("服務天數必須為正整數")
        end_date = (
            datetime.strptime(start_date, "%Y-%m-%d").date()
            + timedelta(days=service_days - 1)
        ).isoformat()
    availability = _request(
        f"/api/v1/orders/{order['case_no']}/caregiver-single-eligibility/check",
        method="POST",
        payload={
            "start_date": start_date,
            "end_date": end_date,
            "as_of": date.today().isoformat(),
        },
    )
    return bool(availability.get("complete_combinations"))

def _render_single_caregiver_matching(target_order, staff_list):
    target_case_no = target_order["case_no"]
    st.markdown(f"#### ⚡ 智慧配對與指派 (案件 #{target_case_no})")
    st.caption("先尋找一位可完整承接服務期間的月嫂；多月嫂僅作備案。")
    start_date_value = target_order.get("actual_start_date") or target_order.get("start_date")
    end_date_value = target_order.get("actual_end_date") or target_order.get("end_date")
    if start_date_value is None or end_date_value is None:
        _render_multi_segment_matching(target_order, staff_list)
        return
    start_date = _as_date(start_date_value)
    end_date = _as_date(end_date_value)
    result = _request(
        f"/api/v1/orders/{target_case_no}/caregiver-segment-availability/search",
        method="POST",
        payload={"segment_count": 1, "segment_drafts": [{"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}], "as_of": date.today().isoformat()},
    )
    candidates = [item for item in result.get("candidate_options", [])
                  if item.get("segment_index") == 0 and item.get("full_case_coverage")]
    if not candidates:
        st.warning("目前沒有月嫂能完整承接本案服務日期。請改至「多月嫂配對方案（備案）」。")
        return
    labels = {_candidate_option_label(item): item for item in candidates}
    selected_label = st.selectbox("選擇可完整承接的月嫂", list(labels), key=f"single_matching_staff_{target_case_no}")
    selected = labels[selected_label]
    st.caption(f"服務日期：{selected['case_period_start']} ～ {selected['case_period_end']}，共 {selected['required_day_count']} 天")
    if st.button("聯繫與確認意願", key=f"single_matching_contact_{target_case_no}"):
        try:
            plan = _request(f"/api/v1/orders/{target_case_no}/matching-plans", method="POST", payload={"segments": [{"staff_id": selected["staff_id"], "start_date": selected["case_period_start"], "end_date": selected["case_period_end"]}], "created_by": _actor(), "as_of": date.today().isoformat()})
            st.session_state[f"matching_plan_{target_case_no}"] = plan
            st.success("單月嫂配對方案已建立，可進行聯繫。")
        except Exception as error:
            st.error(f"建立方案失敗：{error}")
    _render_single_caregiver_contact(target_case_no)


def _render_single_caregiver_contact(case_no):
    plan = _current_matching_plan(case_no)
    plan_id = plan.get("plan_id") or plan.get("id")
    if not plan_id:
        return
    try:
        state = _request(f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/contact-state")
    except Exception as error:
        st.warning(f"聯繫紀錄讀取失敗：{error}")
        return
    segments = state.get("segments") or []
    if len(segments) != 1:
        st.error("單月嫂方案必須恰有一個服務區段。")
        return
    segment = segments[0]
    version = int((state.get("plan") or {}).get("communication_version") or 0)
    st.markdown("#### 聯繫、意願與日期表")
    st.write(
        f"{segment.get('staff_name') or '月嫂'}｜"
        f"{segment.get('assigned_start_date')}～{segment.get('assigned_end_date')}"
    )
    _render_single_information_actions(case_no, plan_id, segment, version)
    _render_single_willingness_action(case_no, plan_id, segment, version)
    customer_decision = _render_single_customer_decision(case_no, plan_id, version, state)
    _render_single_resume_delivery(case_no, plan_id, version, state)
    _render_waiting_lock_acquisition(
        case_no,
        plan_id,
        f"single_matching_lock_{case_no}",
        enabled=customer_decision == "accepted",
    )
    from ui.pages.scheduling.matching_schedule_confirmation_panel import (
        render_matching_schedule_confirmation,
    )
    from ui.api_clients.matching_schedule_confirmation_api_client import (
        MatchingScheduleConfirmationApiClient,
    )
    render_matching_schedule_confirmation(
        case_no,
        plan_id,
        MatchingScheduleConfirmationApiClient(
            base_url=resolve_api_base_url(),
            headers=build_admin_headers(),
        ),
    )


def _current_matching_plan(case_no):
    session_plan = st.session_state.get(f"matching_plan_{case_no}")
    if isinstance(session_plan, dict):
        return session_plan
    try:
        active_state = _request(
            f"/api/v1/orders/{case_no}/matching-plans/active"
        )
    except ValueError:
        return {}
    plan = active_state.get("plan") if isinstance(active_state, dict) else None
    return plan if isinstance(plan, dict) else {}


def _render_single_information_actions(case_no, plan_id, segment, version):
    columns = st.columns(2)
    for column, info_type in zip(columns, (1, 2)):
        if column.button(f"發送訂單資訊-{info_type}", key=f"single_info_{info_type}_{case_no}"):
            try:
                _request(
                    f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment['segment_id']}/information",
                    method="POST",
                    payload={
                        "info_type": info_type,
                        "expected_version": version,
                        "event_key": f"single-info-{info_type}-{uuid.uuid4().hex}",
                        "actor": _actor(),
                    },
                )
                st.success(f"訂單資訊-{info_type} 已排入可靠發送佇列。")
            except Exception as error:
                st.error(f"發送失敗：{error}")
    st.caption(
        "資訊-1：" + _delivery_status_label(segment.get("info_1_status"))
        + "｜資訊-2：" + _delivery_status_label(segment.get("info_2_status"))
    )


def _render_single_willingness_action(case_no, plan_id, segment, version):
    willingness_label = {
        "pending": "待回覆",
        "willing": "願意",
        "unwilling": "無意願",
    }.get(segment.get("willingness"), "未知")
    st.write("月嫂意願：" + willingness_label)
    with st.expander("人工補登月嫂意願"):
        choice = st.selectbox("補登意願", ("willing", "unwilling"), key=f"single_willingness_{case_no}")
        reason = st.text_input("拒絕理由（無意願時必填）", key=f"single_willingness_reason_{case_no}")
        if st.button("更新月嫂意願", key=f"single_willingness_apply_{case_no}"):
            if choice == "unwilling" and not reason.strip():
                st.error("月嫂無意願時必須填寫拒絕理由。")
                return
            try:
                _request(
                    f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/segments/{segment['segment_id']}/willingness",
                    method="PUT",
                    payload={
                        "willingness": choice,
                        "expected_version": version,
                        "reason": reason.strip() or "人工補登願意",
                        "event_key": f"single-willingness-{uuid.uuid4().hex}",
                        "actor": _actor(),
                    },
                )
                st.success("月嫂意願已更新。")
            except Exception as error:
                st.error(f"意願更新失敗：{error}")


def _render_single_customer_decision(case_no, plan_id, version, state):
    decision = str(state.get("customer_decision") or "pending")
    st.write("客戶配對回覆：" + _customer_decision_label(decision))
    with st.expander("人工補登客戶配對回覆"):
        choice = st.selectbox(
            "客戶回覆",
            ("accepted", "contact_requested", "declined"),
            key=f"single_customer_decision_{case_no}",
        )
        reason = st.text_input("補登說明", key=f"single_customer_reason_{case_no}")
        if st.button("更新客戶配對回覆", key=f"single_customer_apply_{case_no}"):
            try:
                _request(
                    f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/customer-decision",
                    method="PUT",
                    payload={
                        "decision": choice,
                        "expected_version": version,
                        "reason": reason.strip() or "人工補登客戶配對回覆",
                        "event_key": f"single-customer-{uuid.uuid4().hex}",
                        "actor": _actor(),
                    },
                )
                st.success("客戶配對回覆已更新。")
            except Exception as error:
                st.error(f"客戶回覆更新失敗：{error}")
    return decision


def _render_single_resume_delivery(case_no, plan_id, version, state):
    st.markdown("#### 傳送履歷給客戶")
    note = st.text_area("履歷訊息備註", key=f"single_resume_note_{case_no}")
    if not st.button("傳送履歷", key=f"single_resume_{case_no}"):
        return
    if not state.get("all_willing"):
        st.error("月嫂尚未表示願意承接，不能傳送履歷。")
        return
    if not note.strip():
        st.error("請填寫履歷訊息備註。")
        return
    try:
        _request(
            f"/api/v1/orders/{case_no}/matching-plans/{plan_id}/resumes",
            method="POST",
            payload={
                "event_key": f"single-resume-{uuid.uuid4().hex}",
                "actor": _actor(),
                "note": note.strip(),
                "expected_version": version,
            },
        )
        st.success("履歷已排入可靠發送佇列。")
    except Exception as error:
        st.error(f"履歷發送失敗：{error}")

def _render_single_caregiver_assignment_plan(order, staff_id, start_date, end_date):
    case_no = order["case_no"]
    st.markdown("#### 4️⃣ 指派與等待訂金鎖定")
    st.info("這將會建立配對方案並鎖定這名月嫂的檔期，直到收到訂金。")
    
    plan_key = f"single_caregiver_plan_{case_no}"
    if st.button("產生單月嫂配對方案", key=f"single_caregiver_gen_{case_no}"):
        try:
            from ui.api_clients.assignment_plan_api_client import AssignmentPlanApiClient
            from ui.pages.shared import resolve_api_base_url, build_admin_headers
            client = AssignmentPlanApiClient(
                base_url=resolve_api_base_url(),
                headers=build_admin_headers(),
            )
            drafts = [{
                "staff_id": int(staff_id),
                "assigned_start_date": start_date,
                "assigned_end_date": end_date,
                "official_service_dates": [],
            }]
            plan = client.propose_plan(
                case_no,
                drafts,
                idempotency_key=f"single-plan-{case_no}-{staff_id}",
            )
            st.session_state[plan_key] = plan.model_dump()
            st.success("配對方案建立成功。")
        except Exception as error:
            st.error(f"建立失敗：{error}")
            return
            
    plan_state = st.session_state.get(plan_key)
    if not plan_state:
        return
        
    plan_id = plan_state["plan_id"]
    st.write(f"目前方案編號: `{plan_id}`")
    lock_state_key = f"single_caregiver_lock_{case_no}"
    _render_waiting_lock_acquisition(case_no, plan_id, lock_state_key, enabled=True)


def _negotiation_orders(orders):
    return [
        order
        for order in orders
        if order.get("order_status") == "洽談中"
    ]


def _select_negotiation_order(orders, preferred_case_no):
    labels = {_matching_order_label(order): order for order in orders}
    preferred_label = next(
        (
            label
            for label, order in labels.items()
            if str(order.get("case_no")) == str(preferred_case_no)
        ),
        None,
    )
    if preferred_label:
        st.session_state["matching_center_case"] = preferred_label
    selected = st.selectbox(
        "選擇待配對案件",
        options=list(labels),
        key="matching_center_case",
    )
    return labels[selected]


def _matching_order_label(order):
    return (
        f"案件 #{order.get('case_no')}｜{order.get('client_name', '')}｜"
        f"{order.get('service_days') or 0} 天"
    )


def _render_matching_order_summary(order):
    service_start = order.get("actual_start_date") or order.get("start_date")
    service_end = order.get("actual_end_date") or order.get("end_date")
    with st.container(border=True):
        st.caption(
            f"案件 #{order.get('case_no')}｜{order.get('client_name') or '未提供客戶'}｜"
            f"服務期間 {service_start} ～ {service_end}｜"
            f"{order.get('service_days') or 0} 天｜"
            f"{order.get('identity_status') or '身分未設定'}"
        )


def _candidate_option_label(option):
    ranges = "、".join(
        f"{item['start_date']}～{item['end_date']}"
        for item in option.get("supported_ranges") or []
    )
    name = option.get("staff_name") or f"月嫂 #{option['staff_id']}"
    return f"{name}｜本案可支援 {ranges}（{option.get('supported_day_count', 0)}／{option.get('required_day_count', 0)} 天）"

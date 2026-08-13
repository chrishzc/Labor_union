"""Thin UI for staff matching preferences and unavailability blocks."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import streamlit as st

from api.schemas.staff_availability import StaffAvailabilityIntentBody
from api.schemas.staff_matching_preferences import (
    StaffPreferenceDefinitionInput,
    StaffPreferenceProfileInput,
)
from ui.api_clients.staff_availability_api_client import StaffAvailabilityApiClient
from ui.api_clients.staff_matching_preferences_api_client import (
    StaffMatchingPreferencesApiClient,
)
from ui.api_clients.staff_summary_api_client import StaffSummaryApiClient
from ui.pages.shared import build_admin_headers, resolve_api_base_url


def render_staff_matching_profile_panel() -> None:
    st.subheader("月嫂配對資料管理")
    staff = _staff_options()
    if not staff:
        st.info("目前沒有可管理的月嫂資料。")
        return
    labels = {f"{item['name']}（#{item['id']}）": item for item in staff}
    selected = labels[st.selectbox("選擇月嫂", list(labels))]
    tabs = st.tabs(("配對偏好", "長假／暫停接案"))
    with tabs[0]:
        _render_preferences(int(selected["id"]))
    with tabs[1]:
        _render_availability(int(selected["id"]))


def _staff_options():
    page = StaffSummaryApiClient(
        base_url=resolve_api_base_url(), headers=build_admin_headers()
    ).query(page_size=200)
    return [item.model_dump(mode="json") for item in page.items]


def _render_preferences(staff_id):
    client = _preference_client()
    definitions = client.definitions()
    _render_definition_management(definitions)
    profile = client.profile(staff_id)
    current = {item.preference_key: item.value.model_dump() for item in profile.values}
    values = []
    for definition in definitions:
        key = definition.preference_key
        label = definition.display_name
        previous = current.get(key) or {}
        if definition.value_kind == "integer_range":
            columns = st.columns(2)
            minimum = int(columns[0].number_input(
                f"{label}－最少", min_value=1,
                value=int(previous.get("minimum", 1)), key=f"pref_min_{staff_id}_{key}"
            ))
            maximum = int(columns[1].number_input(
                f"{label}－最多", min_value=minimum,
                value=max(minimum, int(previous.get("maximum", minimum))),
                key=f"pref_max_{staff_id}_{key}",
            ))
            value = {"kind": "integer_range", "minimum": minimum, "maximum": maximum}
        else:
            defaults = previous.get("values") or [4, 8]
            choices = st.multiselect(
                label, [4, 8, 9, 10, 12, 24], default=defaults,
                key=f"pref_set_{staff_id}_{key}",
            )
            if not choices:
                st.warning(f"{label}至少選一個時數。")
                return
            value = {"kind": "integer_set", "values": sorted(set(choices))}
        values.append({"preference_key": key, "value": value})
    reason = st.text_input("偏好修改原因", key=f"pref_reason_{staff_id}")
    profile_input = StaffPreferenceProfileInput.model_validate({"values": values})
    if st.button("預覽偏好變更", key=f"pref_preview_{staff_id}"):
        preview = client.preview_profile(staff_id, profile_input)
        st.session_state[f"pref_preview_result_{staff_id}"] = preview
    preview = st.session_state.get(f"pref_preview_result_{staff_id}")
    if preview and st.button("套用偏好變更", type="primary", key=f"pref_apply_{staff_id}"):
        if not reason.strip():
            st.error("請填寫修改原因。")
            return
        client.apply_profile(
            staff_id, profile_input, preview.version,
            preview.preview_fingerprint, reason.strip(), uuid4().hex,
        )
        st.success("月嫂配對偏好已更新。")
        st.rerun()


def _render_definition_management(definitions):
    with st.expander("偏好欄位名稱與篩選設定"):
        client = _preference_client()
        options = {item.display_name: item for item in definitions}
        mode = st.radio("欄位操作", ("修改現有欄位", "新增自訂欄位"), horizontal=True)
        if mode == "修改現有欄位":
            definition = options[st.selectbox("選擇欄位", list(options))]
            key = definition.preference_key
        else:
            key = st.text_input("穩定欄位代碼（英文小寫與底線）").strip()
            definition = None
        display_name = st.text_input(
            "UI 顯示名稱", value="" if definition is None else definition.display_name,
            key=f"definition_name_{key}"
        ).strip()
        current_kind = "integer_range" if definition is None else definition.value_kind
        value_kind = st.selectbox(
            "值類型", ("integer_range", "integer_set"),
            index=0 if current_kind == "integer_range" else 1,
            disabled=mode == "修改現有欄位",
            key=f"definition_kind_{key}",
        )
        order_fact_key = "service_days" if value_kind == "integer_range" else "service_hours_per_day"
        body = StaffPreferenceDefinitionInput(
            display_name=display_name or "待輸入", value_kind=value_kind,
            is_filterable=True, order_fact_key=order_fact_key,
            comparison_operator="range_with_tolerance" if value_kind == "integer_range" else "contains_integer",
            active=True,
        )
        reason = st.text_input("欄位設定原因", key=f"definition_reason_{key}")
        if st.button("預覽欄位設定", key=f"definition_preview_{key}"):
            if not key or not display_name:
                st.error("欄位代碼與顯示名稱不得空白。")
                return
            preview = client.preview_definition(key, body)
            st.session_state[f"definition_preview_result_{key}"] = preview
        preview = st.session_state.get(f"definition_preview_result_{key}")
        if preview and st.button("套用欄位設定", key=f"definition_apply_{key}"):
            if not reason.strip():
                st.error("請填寫欄位設定原因。")
                return
            client.apply_definition(
                key, body, preview.version, preview.preview_fingerprint,
                reason.strip(), uuid4().hex,
            )
            st.success("偏好欄位設定已更新。")
            st.rerun()


def _render_availability(staff_id):
    today = date.today()
    client = _availability_client()
    blocks = client.query(staff_id, today, today + timedelta(days=365))
    if blocks:
        st.dataframe([item.model_dump(mode="json") for item in blocks], hide_index=True, width="stretch")
    action = st.selectbox(
        "操作", ("create_long_leave", "create_pause", "end_pause", "cancel"),
        format_func=lambda value: {"create_long_leave": "新增長假", "create_pause": "暫停接案",
                                   "end_pause": "恢復接案", "cancel": "取消不可服務期間"}[value],
        key=f"availability_action_{staff_id}",
    )
    payload = {"action": action, "reason": st.text_input("原因", key=f"availability_reason_{staff_id}")}
    if action in {"create_long_leave", "create_pause"}:
        payload["start_date"] = st.date_input("開始日", value=today, key=f"availability_start_{staff_id}").isoformat()
        if action == "create_long_leave":
            payload["end_date"] = st.date_input("結束日", value=today + timedelta(days=7), key=f"availability_end_{staff_id}").isoformat()
    else:
        active = [item for item in blocks if item.status.value == "effective"]
        if not active:
            st.info("目前沒有可恢復或取消的不可服務期間。")
            return
        options = {f"#{item.block_id} {item.start_date}～{item.end_date or '未定'}": item for item in active}
        selected = options[st.selectbox("選擇紀錄", list(options), key=f"availability_block_{staff_id}")]
        payload["block_id"] = selected.block_id
        if action == "end_pause":
            payload["resume_date"] = st.date_input("恢復接案日", value=today, key=f"availability_resume_{staff_id}").isoformat()
    current_intent = _availability_intent(payload, show_error=False)
    if st.button("產生不可服務期間 Preview", key=f"availability_preview_{staff_id}"):
        current_intent = _availability_intent(payload)
        if current_intent is None:
            return
        _preview_availability_change(client, staff_id, current_intent)
    preview = st.session_state.get(f"availability_preview_result_{staff_id}")
    preview_intent = st.session_state.get(f"availability_preview_intent_{staff_id}")
    preview_matches_current_form = preview_intent == current_intent
    if preview and not preview_matches_current_form:
        st.info("日期、操作或原因已變更；請先重新產生目前表單的 Preview。")
    if preview:
        if preview.blockers:
            st.error("；".join(preview.blockers))
        if st.button(
            "套用不可服務期間異動",
            disabled=(
                not preview.can_apply
                or not preview_matches_current_form
                or preview_intent is None
            ),
            type="primary",
            key=f"availability_apply_{staff_id}",
        ):
            if not preview_matches_current_form:
                st.info("日期、操作或原因已變更；請先重新產生目前表單的 Preview。")
                return
            _apply_availability_change(
                client,
                staff_id,
                preview_intent,
                preview,
            )


def _availability_intent(payload, *, show_error=True):
    try:
        return StaffAvailabilityIntentBody.model_validate(payload)
    except ValueError:
        if show_error:
            st.error("請填寫原因並確認日期。")
        return None


def _preview_availability_change(client, staff_id, intent) -> None:
    try:
        preview = client.preview(staff_id, intent)
    except Exception as error:
        st.error(f"產生不可服務期間 Preview 失敗：{error}")
        return
    st.session_state[f"availability_preview_result_{staff_id}"] = preview
    st.session_state[f"availability_preview_intent_{staff_id}"] = intent


def _apply_availability_change(client, staff_id, intent, preview) -> None:
    try:
        client.apply(
            staff_id,
            intent,
            preview.source_version,
            preview.preview_fingerprint,
            uuid4().hex,
        )
    except Exception as error:
        st.error(f"套用不可服務期間異動失敗：{error}")
        return
    st.session_state.pop(f"availability_preview_result_{staff_id}", None)
    st.session_state.pop(f"availability_preview_intent_{staff_id}", None)
    st.success("不可服務期間已更新，配對檔期會同步套用。")
    st.rerun()


def _preference_client() -> StaffMatchingPreferencesApiClient:
    return StaffMatchingPreferencesApiClient(
        base_url=resolve_api_base_url(), headers=build_admin_headers()
    )


def _availability_client() -> StaffAvailabilityApiClient:
    return StaffAvailabilityApiClient(
        base_url=resolve_api_base_url(), headers=build_admin_headers()
    )


__all__ = ["render_staff_matching_profile_panel"]
